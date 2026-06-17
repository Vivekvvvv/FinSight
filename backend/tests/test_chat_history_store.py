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
