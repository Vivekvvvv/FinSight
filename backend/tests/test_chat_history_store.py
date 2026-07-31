import logging
import threading

import pytest

from backend.services.chat_history import ChatHistoryStore


def test_chat_history_store_appends_and_lists_messages(tmp_path):
    store = ChatHistoryStore(storage_path=tmp_path)

    messages = store.append_turn(
        session_id="tenant:user:thread-1",
        user_content="AAPL 怎么样？",
        assistant_content="AAPL 需要结合估值和盈利质量观察。",
    )

    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["status"] == "done"

    listed = store.list_messages(session_id="tenant:user:thread-1")
    assert [item["content"] for item in listed] == [item["content"] for item in messages]


def test_chat_history_store_limits_and_clears_session(tmp_path):
    store = ChatHistoryStore(storage_path=tmp_path)

    for index in range(105):
        store.append_turn(
            session_id="tenant:user:thread-2",
            user_content=f"Q{index}",
            assistant_content=f"A{index}",
        )

    listed = store.list_messages(session_id="tenant:user:thread-2", limit=10)
    assert len(listed) == 10
    assert listed[0]["content"] == "Q100"
    assert listed[-1]["content"] == "A104"

    store.clear(session_id="tenant:user:thread-2")
    assert store.list_messages(session_id="tenant:user:thread-2") == []


def test_chat_history_store_sanitizes_session_filename(tmp_path):
    store = ChatHistoryStore(storage_path=tmp_path)

    store.append_turn(
        session_id="tenant:user:bad/slash",
        user_content="hello",
        assistant_content="world",
    )

    assert not (tmp_path / "tenant:user:bad/slash.json").exists()
    assert store.list_messages(session_id="tenant:user:bad/slash")[0]["content"] == "hello"


def test_chat_history_store_avoids_sanitized_name_collisions(tmp_path):
    store = ChatHistoryStore(storage_path=tmp_path)

    store.append_turn(session_id="a:b", user_content="colon", assistant_content="one")
    store.append_turn(session_id="a_b", user_content="underscore", assistant_content="two")

    assert store.list_messages(session_id="a:b")[0]["content"] == "colon"
    assert store.list_messages(session_id="a_b")[0]["content"] == "underscore"


@pytest.mark.parametrize(
    ("corrupt_payload", "error_type"),
    [
        ("{invalid json", "JSONDecodeError"),
        ('{"messages": "not-a-list"}', "ValueError"),
        ('{"messages": ["not-an-object"]}', "ValueError"),
        ('{"messages": [], "score": NaN}', "ValueError"),
    ],
)
def test_chat_history_store_backs_up_corrupt_payload_before_recovery(
    tmp_path, caplog, corrupt_payload, error_type
):
    store = ChatHistoryStore(storage_path=tmp_path)
    session_id = "tenant:user:corrupt"
    path = store._path_for_session(session_id)
    path.write_text(corrupt_payload, encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="backend.services.chat_history"):
        assert store.list_messages(session_id=session_id) == []

    backups = list(tmp_path.glob("*.corrupt"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == corrupt_payload
    assert not path.exists()
    assert error_type in caplog.text
    assert corrupt_payload not in caplog.text

    store.append_turn(
        session_id=session_id,
        user_content="recovered question",
        assistant_content="recovered answer",
    )
    assert path.exists()
    assert backups[0].read_text(encoding="utf-8") == corrupt_payload


def test_chat_history_store_backs_up_oversized_file_before_parsing(
    tmp_path, monkeypatch
):
    import backend.services.chat_history as chat_history

    monkeypatch.setattr(chat_history, "_MAX_HISTORY_FILE_BYTES", 32)
    store = ChatHistoryStore(storage_path=tmp_path)
    session_id = "tenant:user:oversized"
    path = store._path_for_session(session_id)
    payload = '{"messages":[],"padding":"' + ("x" * 64) + '"}'
    path.write_text(payload, encoding="utf-8")

    assert store.list_messages(session_id=session_id) == []
    assert not path.exists()
    backups = list(tmp_path.glob("*.corrupt"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == payload


def test_chat_history_store_rejects_non_finite_evidence(tmp_path):
    store = ChatHistoryStore(storage_path=tmp_path)
    session_id = "tenant:user:non-finite"

    with pytest.raises(ValueError, match="Out of range float values"):
        store.append_turn(
            session_id=session_id,
            user_content="question",
            assistant_content="answer",
            evidence={"score": float("nan")},
        )

    assert not store._path_for_session(session_id).exists()


@pytest.mark.parametrize(
    ("evidence", "message"),
    [
        ({"blob": "x" * (64 * 1024)}, "evidence is too large"),
        ({"unsupported": object()}, "is not JSON serializable"),
    ],
)
def test_chat_history_store_rejects_invalid_evidence(tmp_path, evidence, message):
    store = ChatHistoryStore(storage_path=tmp_path)

    with pytest.raises((TypeError, ValueError), match=message):
        store.append_turn(
            session_id="tenant:user:invalid-evidence",
            user_content="question",
            assistant_content="answer",
            evidence=evidence,
        )

    assert not store._path_for_session("tenant:user:invalid-evidence").exists()


def test_chat_history_store_instances_share_read_modify_write_lock(tmp_path, monkeypatch):
    first = ChatHistoryStore(storage_path=tmp_path)
    second = ChatHistoryStore(storage_path=tmp_path)
    session_id = "tenant:user:shared"
    first_read_started = threading.Event()
    release_first_read = threading.Event()
    second_read_started = threading.Event()
    first_read = first._read_payload
    second_read = second._read_payload

    def blocking_first_read(current_session_id):
        first_read_started.set()
        assert release_first_read.wait(timeout=2)
        return first_read(current_session_id)

    def observed_second_read(current_session_id):
        second_read_started.set()
        return second_read(current_session_id)

    monkeypatch.setattr(first, "_read_payload", blocking_first_read)
    monkeypatch.setattr(second, "_read_payload", observed_second_read)

    first_thread = threading.Thread(
        target=first.append_turn,
        kwargs={
            "session_id": session_id,
            "user_content": "first question",
            "assistant_content": "first answer",
        },
    )
    second_thread = threading.Thread(
        target=second.append_turn,
        kwargs={
            "session_id": session_id,
            "user_content": "second question",
            "assistant_content": "second answer",
        },
    )

    first_thread.start()
    assert first_read_started.wait(timeout=2)
    second_thread.start()
    assert not second_read_started.wait(timeout=0.1)

    release_first_read.set()
    first_thread.join(timeout=2)
    second_thread.join(timeout=2)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert second_read_started.is_set()
    assert len(first.list_messages(session_id=session_id)) == 4
