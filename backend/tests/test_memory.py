import pytest
import os
import json
from backend.services.memory import MemoryService, UserProfile

@pytest.fixture
def memory_service(tmp_path):
    # Use a temporary directory for tests
    return MemoryService(storage_path=str(tmp_path))


def test_reset_profiles_writes_atomically_and_reads_back(tmp_path):
    """测试夹具的重置必须走原子写 + 模块级锁（项目规则 1）。

    直写目标文件会和持锁的写入方争抢句柄，Windows 上表现为 Errno 13，
    且读侧可能看到写了一半的文件。reset_profiles 用 tempfile + os.replace，
    落盘内容必须能被 MemoryService 正常解析。
    """
    from backend.services.memory import reset_profiles

    payload = {
        "user_id": "test_api_user",
        "risk_tolerance": "medium",
        "investment_style": "balanced",
        "watchlist": [],
        "preferences": {},
        "last_active": "2026-02-03T00:00:00Z",
    }
    target = tmp_path / "test_api_user.json"

    reset_profiles(str(tmp_path), {"test_api_user": payload})

    assert json.loads(target.read_text(encoding="utf-8")) == payload
    # 落盘后目录里不应留下临时文件
    assert [p.name for p in tmp_path.iterdir()] == ["test_api_user.json"]
    profile = MemoryService(storage_path=str(tmp_path)).get_user_profile("test_api_user")
    assert profile.user_id == "test_api_user"

def test_get_new_profile(memory_service):
    profile = memory_service.get_user_profile("test_user_1")
    assert profile.user_id == "test_user_1"
    assert profile.risk_tolerance == "medium"
    assert profile.investment_style == "balanced"
    assert profile.watchlist == []

def test_update_profile(memory_service):
    profile = memory_service.get_user_profile("test_user_2")
    profile.risk_tolerance = "high"
    profile.investment_style = "aggressive"

    success = memory_service.update_user_profile(profile)
    assert success is True

    # Reload to verify persistence
    loaded_profile = memory_service.get_user_profile("test_user_2")
    assert loaded_profile.risk_tolerance == "high"
    assert loaded_profile.investment_style == "aggressive"

def test_watchlist_operations(memory_service):
    user_id = "test_user_3"

    # Add
    memory_service.add_to_watchlist(user_id, "AAPL")
    profile = memory_service.get_user_profile(user_id)
    assert "AAPL" in profile.watchlist

    # Add Duplicate (should ignore)
    memory_service.add_to_watchlist(user_id, "AAPL")
    profile = memory_service.get_user_profile(user_id)
    assert len(profile.watchlist) == 1

    # Add another
    memory_service.add_to_watchlist(user_id, "MSFT")
    profile = memory_service.get_user_profile(user_id)
    assert "MSFT" in profile.watchlist
    assert len(profile.watchlist) == 2

    # Remove
    memory_service.remove_from_watchlist(user_id, "AAPL")
    profile = memory_service.get_user_profile(user_id)
    assert "AAPL" not in profile.watchlist
    assert "MSFT" in profile.watchlist

def test_preferences(memory_service):
    user_id = "test_user_4"
    memory_service.set_preference(user_id, "theme", "dark")

    profile = memory_service.get_user_profile(user_id)
    assert profile.preferences.get("theme") == "dark"


def test_reject_path_traversal_user_id(memory_service):
    with pytest.raises(ValueError):
        memory_service.get_user_profile("../../etc/passwd")

    with pytest.raises(ValueError):
        memory_service.set_preference("../evil", "theme", "dark")


def test_corrupt_profile_backed_up_not_overwritten(memory_service, tmp_path, caplog):
    user_id = "corrupt_user"
    memory_service.add_to_watchlist(user_id, "AAPL")
    file_path = os.path.join(str(tmp_path), f"{user_id}.json")

    # 模拟磁盘上损坏的画像文件
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("{ not valid json")

    profile = memory_service.get_user_profile(user_id)
    assert profile.watchlist == []  # 回退默认画像
    backups = list(tmp_path.glob("*.corrupt"))
    assert len(backups) == 1
    with open(backups[0], encoding="utf-8") as f:
        assert f.read() == "{ not valid json"
    assert "JSONDecodeError" in caplog.text
    assert "{ not valid json" not in caplog.text


def test_non_finite_profile_is_rejected_and_legacy_file_is_backed_up(
    memory_service, tmp_path, caplog
):
    user_id = "non_finite_user"
    profile = UserProfile(user_id=user_id, preferences={"score": float("nan")})

    assert memory_service.update_user_profile(profile) is False
    file_path = tmp_path / f"{user_id}.json"
    assert not file_path.exists()

    corrupt_payload = '{"user_id":"non_finite_user","preferences":{"score":NaN}}'
    file_path.write_text(corrupt_payload, encoding="utf-8")
    recovered = memory_service.get_user_profile(user_id)

    assert recovered.preferences == {}
    backups = list(tmp_path.glob("*.corrupt"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == corrupt_payload
    assert "ValueError" in caplog.text


def test_profile_file_cannot_override_requested_user_identity(memory_service, tmp_path):
    alice_path = tmp_path / "alice.json"
    payload = {
        "user_id": "bob",
        "watchlist": ["AAPL"],
        "preferences": {"theme": "private"},
    }
    alice_path.write_text(json.dumps(payload), encoding="utf-8")

    profile = memory_service.get_user_profile("alice")

    assert profile.user_id == "alice"
    assert profile.watchlist == []
    assert not alice_path.exists()
    backups = list(tmp_path.glob("alice.json.*.corrupt"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8")) == payload
    assert not (tmp_path / "bob.json").exists()


@pytest.mark.parametrize(
    "invalid_field",
    [
        {"watchlist": "AAPL"},
        {"watchlist": ["AAPL", 7]},
        {"watchlist_meta": []},
        {"preferences": []},
    ],
)
def test_invalid_profile_field_shapes_are_backed_up(
    memory_service, tmp_path, invalid_field
):
    path = tmp_path / "shape_user.json"
    payload = {"user_id": "shape_user", **invalid_field}
    path.write_text(json.dumps(payload), encoding="utf-8")

    profile = memory_service.get_user_profile("shape_user")

    assert profile.user_id == "shape_user"
    assert profile.watchlist == []
    assert profile.preferences == {}
    assert not path.exists()
    assert len(list(tmp_path.glob("shape_user.json.*.corrupt"))) == 1


def test_concurrent_watchlist_adds_do_not_lose_updates(memory_service):
    import threading

    user_id = "concurrent_user"
    tickers = [f"T{i:03d}" for i in range(20)]

    def add(ticker):
        assert memory_service.add_to_watchlist(user_id, ticker) is True

    threads = [threading.Thread(target=add, args=(t,)) for t in tickers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    profile = memory_service.get_user_profile(user_id)
    assert sorted(profile.watchlist) == tickers


def test_watchlist_limit_allows_duplicate_updates_and_blocks_new_tickers(memory_service):
    from backend.services.memory import WatchlistLimitExceeded

    assert memory_service.add_to_watchlist("limited_user", "AAPL", max_watchlist=1) is True
    assert memory_service.add_to_watchlist(
        "limited_user",
        "AAPL",
        note="updated",
        max_watchlist=1,
    ) is True

    with pytest.raises(WatchlistLimitExceeded) as exc_info:
        memory_service.add_to_watchlist("limited_user", "MSFT", max_watchlist=1)

    assert exc_info.value.limit == 1
    assert exc_info.value.current == 1
    assert memory_service.get_user_profile("limited_user").watchlist == ["AAPL"]


def test_user_router_enforces_watchlist_quota_without_blocking_duplicates(memory_service, tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.user_router import UserRouterDeps, create_user_router
    from backend.security.auth import Principal, get_current_user
    from backend.services import entitlements

    monkeypatch.setattr(entitlements, "PLANS_FILE", tmp_path / "plans.json")
    entitlements.reset_entitlements_service_for_tests()
    entitlements.get_entitlements_service().set_plan("quota-user", "free")

    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: Principal(
        user_id="quota-user",
        role="user",
        auth_type="api_key",
    )
    app.include_router(
        create_user_router(
            UserRouterDeps(
                memory_service=memory_service,
                user_profile_cls=UserProfile,
            )
        )
    )

    try:
        with TestClient(app) as client:
            for ticker in ("AAPL", "MSFT", "NVDA", "TSLA", "AMZN"):
                assert client.post("/api/user/watchlist/add", json={"ticker": ticker}).status_code == 200

            duplicate = client.post("/api/user/watchlist/add", json={"ticker": "AAPL", "note": "updated"})
            overflow = client.post("/api/user/watchlist/add", json={"ticker": "GOOGL"})
            profile_overflow = client.post(
                "/api/user/profile",
                json={"profile": {"watchlist": ["A", "B", "C", "D", "E", "F"]}},
            )
    finally:
        entitlements.reset_entitlements_service_for_tests()

    assert duplicate.status_code == 200
    assert overflow.status_code == 429
    assert overflow.json()["detail"]["code"] == "plan_quota_exceeded"
    assert profile_overflow.status_code == 429
    assert profile_overflow.json()["detail"]["quota"] == "max_watchlist"


@pytest.mark.parametrize(
    "stored_tickers, remove_ticker",
    [
        (["aapl"], "AAPL"),
        ([" aApL "], "AAPL"),
        (["AAPL", "AAPL"], "AAPL"),
        (["aapl", "AAPL", " aApL "], " aapl "),
    ],
)
def test_watchlist_remove_legacy_variants_releases_quota(
    memory_service, tmp_path, monkeypatch, stored_tickers, remove_ticker
):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.user_router import UserRouterDeps, create_user_router
    from backend.security.auth import Principal, get_current_user
    from backend.services import entitlements

    monkeypatch.setattr(entitlements, "PLANS_FILE", tmp_path / "plans.json")
    entitlements.reset_entitlements_service_for_tests()
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: Principal(
        user_id="legacy-quota-user", role="user", auth_type="api_key"
    )
    app.include_router(create_user_router(UserRouterDeps(
        memory_service=memory_service, user_profile_cls=UserProfile,
    )))
    other_tickers = ["AAPLX", "TSLA", "AMZN", "GOOGL"][:5 - len(stored_tickers)]
    other_meta = {ticker: {"note": "keep"} for ticker in other_tickers}
    other_profile = UserProfile(user_id="other-user", watchlist=["aapl"])
    assert memory_service.update_user_profile(other_profile) is True
    other_user_data = (tmp_path / "other-user.json").read_bytes()

    try:
        with TestClient(app) as client:
            # 画像接口可以合法写入旧格式，满额时删除必须真正释放名额。
            saved = client.post("/api/user/profile", json={"profile": {
                "watchlist": stored_tickers + other_tickers,
                "watchlist_meta": {
                    **{ticker: {"note": "remove"} for ticker in stored_tickers},
                    **other_meta,
                },
                "preferences": {"theme": "dark"},
            }})
            assert saved.status_code == 200
            blocked = client.post("/api/user/watchlist/add", json={"ticker": "NVDA"})
            assert blocked.status_code == 429
            assert blocked.json()["detail"]["current"] == 5

            removed = client.post("/api/user/watchlist/remove", json={"ticker": remove_ticker})
            assert removed.status_code == 200
            assert removed.json()["success"] is True
            persisted = memory_service.get_user_profile("legacy-quota-user")
            assert persisted.watchlist == other_tickers
            assert persisted.watchlist_meta == other_meta
            assert persisted.preferences == {"theme": "dark"}
            assert (tmp_path / "other-user.json").read_bytes() == other_user_data

            added = client.post("/api/user/watchlist/add", json={"ticker": "NVDA"})
            assert added.status_code == 200
            assert client.post("/api/user/watchlist/remove", json={"ticker": remove_ticker}).status_code == 200
            assert memory_service.get_user_profile("legacy-quota-user").watchlist == other_tickers + ["NVDA"]
    finally:
        entitlements.reset_entitlements_service_for_tests()


@pytest.mark.parametrize("stored_ticker", ["aapl", " aApL "])
@pytest.mark.parametrize("operation", ["add", "update"])
def test_existing_legacy_watchlist_item_can_be_updated_at_quota(
    memory_service, stored_ticker, operation
):
    user_id = "legacy-update-user"
    profile = UserProfile(
        user_id=user_id, watchlist=[stored_ticker, "MSFT"],
        watchlist_meta={stored_ticker: {"name": "Apple", "tags": ["tech"], "note": "old"}},
    )
    assert memory_service.update_user_profile(profile) is True

    if operation == "add":
        success = memory_service.add_to_watchlist(user_id, "AAPL", note="new", max_watchlist=2)
    else:
        success = memory_service.update_watchlist_meta(user_id, "AAPL", note="new")

    assert success is True
    persisted = memory_service.get_user_profile(user_id)
    assert persisted.watchlist == [stored_ticker, "MSFT"]
    item = memory_service.list_watchlist_items(user_id)[0]
    assert item["name"] == "Apple"
    assert item["tags"] == ["tech"]
    assert item["note"] == "new"


@pytest.mark.parametrize("stored_tickers", [[], ["aapl", " AAPL "]])
def test_watchlist_remove_variants_preserves_data_on_write_failure(
    memory_service, tmp_path, monkeypatch, stored_tickers
):
    user_id = "remove-failure-user"
    profile = UserProfile(
        user_id=user_id,
        watchlist=stored_tickers + ["MSFT"],
        watchlist_meta={
            "aapl": {"note": "remove"},
            " AAPL ": {"note": "remove"},
            "MSFT": {"note": "keep"},
        },
    )
    assert memory_service.update_user_profile(profile) is True
    profile_path = tmp_path / f"{user_id}.json"
    original_data = profile_path.read_bytes()

    def fail_replace(_source, _target):
        raise PermissionError("simulated write failure")

    with monkeypatch.context() as scoped:
        scoped.setattr("backend.services.memory.os.replace", fail_replace)
        assert memory_service.remove_from_watchlist(user_id, "AAPL") is False

    assert profile_path.read_bytes() == original_data
    assert list(tmp_path.glob("*.tmp")) == []
    assert memory_service.remove_from_watchlist(user_id, "AAPL") is True
    persisted = memory_service.get_user_profile(user_id)
    assert persisted.watchlist == ["MSFT"]
    assert persisted.watchlist_meta == {"MSFT": {"note": "keep"}}
    after_removal = profile_path.read_bytes()
    assert memory_service.remove_from_watchlist(user_id, "AAPL") is True
    assert profile_path.read_bytes() == after_removal


def test_profile_save_error_log_is_redacted(memory_service, monkeypatch, caplog):
    profile = UserProfile(user_id="save_error_user")

    def fail_replace(_source, _target):
        raise OSError("private profile storage detail")

    monkeypatch.setattr("backend.services.memory.os.replace", fail_replace)
    assert memory_service.update_user_profile(profile) is False
    temp_files = [
        item.name for item in os.scandir(memory_service.storage_path)
        if item.name.endswith(".tmp")
    ]
    assert temp_files == []
    assert "private profile storage detail" not in caplog.text
    assert "OSError" in caplog.text


def test_default_storage_path_follows_env(monkeypatch, tmp_path):
    env_path = str(tmp_path / "env_memory")
    monkeypatch.setenv("MEMORY_STORAGE_PATH", env_path)
    service = MemoryService()
    assert service.storage_path == env_path


def test_explicit_storage_path_overrides_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMORY_STORAGE_PATH", str(tmp_path / "env_memory"))
    explicit_path = str(tmp_path / "explicit")
    service = MemoryService(storage_path=explicit_path)
    assert service.storage_path == explicit_path


def test_deeply_nested_profile_file_is_quarantined_not_crashing(tmp_path):
    """超深嵌套 JSON 外来落盘（写侧 json.dump 同限值先行失败，API 写不进，
    但手工/外部工具可落盘）触发 RecursionError——except 元组不含它会让
    get_user_profile 直接抛出：文件永不 .corrupt 备份、每读恒 500 死循环。
    llm_config._load_user_config 同款契约已含 RecursionError。"""
    svc = MemoryService(storage_path=str(tmp_path))
    path = tmp_path / "deep_user.json"
    path.write_text("[" * 8000 + "]" * 8000, encoding="utf-8")

    profile = svc.get_user_profile("deep_user")

    assert profile.user_id == "deep_user"
    assert profile.risk_tolerance == "medium"
    assert not path.exists()
    assert len(list(tmp_path.glob("deep_user.json.*.corrupt"))) == 1
