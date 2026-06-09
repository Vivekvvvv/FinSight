# -*- coding: utf-8 -*-
"""
Conversation 模块
保留对话上下文管理组件；ConversationRouter / ConversationAgent 路径已被 LangGraph runner 取代并退役。
"""

from backend.conversation.context import ContextManager, ConversationTurn, MessageRole

__all__ = [
    'ContextManager',
    'ConversationTurn',
    'MessageRole',
]
