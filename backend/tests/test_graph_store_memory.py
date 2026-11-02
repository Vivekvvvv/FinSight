import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

import backend.graph.store as graph_store
import backend.services.memory as memory_module
from backend.graph.store import (
    load_memory_context,
    persist_memory_snapshot,
    resolve_user_id,
)
from backend.services.memory import MemoryService


def test_resolve_user_id_from_thread_id():
    assert resolve_user_id("public:alice:thread-1") == "alice"
    assert resolve_user_id("tenant:bob:abc") == "bob"
    assert resolve_user_id("no-segments") == "default_user"
    assert resolve_user_id("") == "default_user"


def test_persist_and_load_memory_snapshot(tmp_path):
    service = MemoryService(storage_path=str(tmp_path))
    thread_id = "public:test_user:thread-001"

    state = {
        "query": "请分析 AAPL 的投资机会",
        "subject": {"tickers": ["AAPL"]},
        "artifacts": {
            "render_vars": {
                "investment_summary": "AAPL 当前盈利质量稳定，估值处于历史中位附近。"
            }
        },
    }
    report = {"summary": "AAPL 基本面稳健，短期受业绩预期驱动。", "sentiment": "bullish"}

    assert persist_memory_snapshot(
        thread_id=thread_id,
        state=state,
        report=report,
        memory_service=service,
    )

    context = load_memory_context(thread_id=thread_id, memory_service=service)
    assert context["user_id"] == "test_user"
    assert context["last_focus"]["ticker"] == "AAPL"
    assert context["last_focus"]["query"] == "请分析 AAPL 的投资机会"
    assert context["last_focus"]["summary"]
    assert context["last_focus"]["sentiment"] == "bullish"
    assert isinstance(context["recent_focuses"], list)
    assert len(context["recent_focuses"]) >= 1


def test_persist_memory_snapshot_serializes_read_modify_write():
    """并发 run 的 “读 profile → 合并 → 写回” 必须整体互斥，否则两个线程
    都读到同一份旧 profile，后写者覆盖先写者的 recent_focuses 条目。"""

    class _OverlapDetectingService:
        def __init__(self):
            self._active = 0
            self._guard = threading.Lock()
            self.overlapped = False
            self.profile = SimpleNamespace(preferences={})

        def _enter(self):
            with self._guard:
                self._active += 1
                if self._active > 1:
                    self.overlapped = True

        def _exit(self):
            with self._guard:
                self._active -= 1

        def get_user_profile(self, _user_id):
            self._enter()
            try:
                # 给并发线程留出同时读窗口；有锁时第二个线程只能在锁外等待。
                time.sleep(0.05)
                return SimpleNamespace(preferences=dict(self.profile.preferences))
            finally:
                self._exit()

        def update_user_profile(self, profile):
            self._enter()
            try:
                time.sleep(0.01)
                self.profile = profile
                return True
            finally:
                self._exit()

    service = _OverlapDetectingService()
    start = threading.Barrier(2)
    results: list[bool] = []

    def _worker(ticker: str) -> None:
        start.wait(timeout=5)
        results.append(
            persist_memory_snapshot(
                thread_id="public:alice:thread",
                state={"query": ticker, "subject": {"tickers": [ticker]}},
                memory_service=service,
            )
        )

    threads = [threading.Thread(target=_worker, args=(ticker,)) for ticker in ("AAPL", "NVDA")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert results == [True, True]
    assert service.overlapped is False
    tickers = {item["ticker"] for item in service.profile.preferences["recent_focuses"]}
    assert tickers == {"AAPL", "NVDA"}


@pytest.mark.parametrize("mutation", ["add", "remove", "metadata", "preference"])
def test_snapshot_and_profile_mutations_preserve_both_updates(tmp_path, monkeypatch, mutation):
    """真实跨实例写入不能互相覆盖；用事件控制交错，避免依赖 sleep。"""
    snapshot_service = MemoryService(storage_path=str(tmp_path))
    mutation_service = MemoryService(storage_path=str(tmp_path))
    user_id = "alice"
    assert mutation_service.add_to_watchlist(user_id, "AAPL", note="原备注")
    assert mutation_service.set_preference(user_id, "theme", "dark")
    assert mutation_service.set_preference(user_id, "recent_focuses", [{"ticker": "MSFT"}])

    snapshot_loaded = threading.Event()
    mutation_reached = threading.Event()
    mutation_thread = threading.local()
    profile_lock = memory_module._PROFILE_LOCK

    class _ObservedProfileLock:
        def __enter__(self):
            if getattr(mutation_thread, "active", False):
                if not profile_lock.acquire(blocking=False):
                    # 修复后更新会等待快照事务，通知快照继续，避免测试死锁。
                    mutation_reached.set()
                    profile_lock.acquire()
            else:
                profile_lock.acquire()
            return self

        def __exit__(self, *_args):
            profile_lock.release()

    monkeypatch.setattr(memory_module, "_PROFILE_LOCK", _ObservedProfileLock())
    original_read = snapshot_service.get_user_profile

    def read_snapshot(requested_user_id):
        profile = original_read(requested_user_id)
        snapshot_loaded.set()
        # 未修复时让另一实例先写完；修复后在确认它等待共享锁时继续。
        assert mutation_reached.wait(timeout=5), "并发更新未进入测试窗口"
        return profile

    monkeypatch.setattr(snapshot_service, "get_user_profile", read_snapshot)

    def mutate_profile():
        assert snapshot_loaded.wait(timeout=5), "快照未读取画像"
        mutation_thread.active = True
        try:
            if mutation == "add":
                return mutation_service.add_to_watchlist(user_id, "NVDA", note="新关注")
            if mutation == "remove":
                return mutation_service.remove_from_watchlist(user_id, "AAPL")
            if mutation == "metadata":
                return mutation_service.update_watchlist_meta(user_id, "AAPL", note="新备注")
            return mutation_service.set_preference(user_id, "theme", "light")
        finally:
            mutation_reached.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        snapshot = pool.submit(
            persist_memory_snapshot,
            thread_id="public:alice:research",
            state={"query": "分析 NVDA", "subject": {"tickers": ["NVDA"]}},
            memory_service=snapshot_service,
        )
        update = pool.submit(mutate_profile)
        assert snapshot.result(timeout=10) is True
        assert update.result(timeout=10) is True

    profile = mutation_service.get_user_profile(user_id)
    assert profile.preferences["last_focus"]["ticker"] == "NVDA"
    assert [item["ticker"] for item in profile.preferences["recent_focuses"]] == ["NVDA", "MSFT"]
    assert profile.preferences["theme"] == ("light" if mutation == "preference" else "dark")
    if mutation == "remove":
        assert profile.watchlist == []
        assert "AAPL" not in profile.watchlist_meta
    else:
        assert profile.watchlist == (["AAPL", "NVDA"] if mutation == "add" else ["AAPL"])
        assert profile.watchlist_meta["AAPL"]["note"] == ("新备注" if mutation == "metadata" else "原备注")
        if mutation == "add":
            assert profile.watchlist_meta["NVDA"]["note"] == "新关注"


def test_memory_service_init_failure_only_warn_once(monkeypatch, caplog):
    secret = "PRIVATE postgres://memory:secret@db/profile"

    def _raise_init(*args, **kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(graph_store, "MemoryService", _raise_init)
    monkeypatch.setattr(graph_store, "_memory_service", None)

    caplog.set_level("WARNING")
    assert graph_store._get_memory_service() is None  # noqa: SLF001
    assert graph_store._get_memory_service() is None  # noqa: SLF001

    warning_logs = [rec.message for rec in caplog.records if "init memory service failed" in rec.message]
    assert len(warning_logs) == 1
    assert secret not in caplog.text
    assert "[graph.store] init memory service failed" in caplog.text


def test_load_memory_context_error_log_is_redacted(caplog):
    secret = "PRIVATE postgres://memory:secret@db/load"

    class _FailingService:
        def get_user_profile(self, _user_id):
            raise RuntimeError(secret)

    assert load_memory_context(thread_id="public:alice:thread", memory_service=_FailingService()) == {}
    assert secret not in caplog.text
    assert "[graph.store] load profile failed" in caplog.text


def test_persist_memory_load_error_log_is_redacted(caplog):
    secret = "PRIVATE postgres://memory:secret@db/prewrite"

    class _FailingService:
        def get_user_profile(self, _user_id):
            raise RuntimeError(secret)

    result = persist_memory_snapshot(
        thread_id="public:alice:thread",
        state={"query": "AAPL"},
        memory_service=_FailingService(),
    )

    assert result is False
    assert secret not in caplog.text
    assert "[graph.store] load profile before persist failed" in caplog.text


def test_persist_memory_write_error_log_is_redacted(caplog):
    secret = "PRIVATE postgres://memory:secret@db/write"

    class _Profile:
        preferences = {}

    class _FailingService:
        def get_user_profile(self, _user_id):
            return _Profile()

        def update_user_profile(self, _profile):
            raise RuntimeError(secret)

    result = persist_memory_snapshot(
        thread_id="public:alice:thread",
        state={"query": "AAPL"},
        memory_service=_FailingService(),
    )

    assert result is False
    assert secret not in caplog.text
    assert "[graph.store] persist profile failed" in caplog.text
