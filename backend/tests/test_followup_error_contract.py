from backend.handlers.followup_handler import FollowupHandler


class _FailingLLM:
    def __init__(self, secret: str) -> None:
        self.secret = secret

    def invoke(self, _messages):
        raise RuntimeError(self.secret)


def test_followup_llm_error_is_redacted(caplog):
    secret = "PRIVATE_FOLLOWUP_ERROR_SENTINEL"
    handler = FollowupHandler(llm=_FailingLLM(secret), orchestrator=None)

    result = handler._handle_with_llm(
        query="why",
        followup_type="why",
        last_response="previous",
        current_focus="AAPL",
        cached_data={},
        context=None,
    )

    assert result == {
        "success": False,
        "response": "Unable to process follow-up",
        "error": "internal_error",
        "intent": "followup",
    }
    assert secret not in str(result)
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_report_followup_llm_error_is_redacted_from_log(caplog):
    secret = "PRIVATE_REPORT_FOLLOWUP_ERROR_SENTINEL"
    handler = FollowupHandler(llm=_FailingLLM(secret), orchestrator=None)

    result = handler._handle_report_followup("summary", "first paragraph\nsecond paragraph")

    assert result["success"] is True
    assert result["degraded"] is True
    assert secret not in str(result)
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text
