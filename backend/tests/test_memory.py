import pytest
import os
import json
from backend.services.memory import MemoryService, UserProfile

@pytest.fixture
def memory_service(tmp_path):
    # Use a temporary directory for tests
    return MemoryService(storage_path=str(tmp_path))

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
