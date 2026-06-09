# -*- coding: utf-8 -*-
"""Legacy conversation-agent experience scenarios.

The old ``backend.conversation.agent`` implementation was retired during the
LangGraph consolidation. Current chat coverage lives in the FastAPI/LangGraph
tests; this placeholder keeps the historical test entry explicit without
importing deleted modules.
"""

import pytest


def test_legacy_conversation_experience_retired() -> None:
    pytest.skip(
        "Legacy ConversationAgent experience tests are retired; use current "
        "FastAPI/LangGraph chat tests for active coverage."
    )
