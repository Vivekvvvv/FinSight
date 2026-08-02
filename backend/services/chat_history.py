# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
import os
import re
import threading
from hashlib import sha256
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.utils.strict_json import json_loads_strict
from backend.utils.quote import safe_int


_DEFAULT_LIMIT = 100
_MAX_MESSAGES_PER_SESSION = 200
_MAX_CONTENT_CHARS = 20_000
_MAX_EVIDENCE_BYTES = 64 * 1024
_MAX_HISTORY_FILE_BYTES = 20 * 1024 * 1024
_STORE_LOCK = threading.RLock()

logger = logging.getLogger(__name__)


def _reject_non_finite_json(value: str) -> None:
    raise ValueError(f"non-finite JSON value: {value}")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_session_filename(session_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", session_id.strip())
    digest = sha256(session_id.encode("utf-8")).hexdigest()[:12]
    prefix = cleaned[:120] or "default"
    return f"{prefix}-{digest}"


def _clean_content(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) > _MAX_CONTENT_CHARS:
        return text[:_MAX_CONTENT_CHARS]
    return text


def _validate_evidence(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not value:
        return None
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > _MAX_EVIDENCE_BYTES:
        raise ValueError("chat history evidence is too large")
    return value


class ChatHistoryStore:
    """Small JSON-backed chat history store keyed by normalized session id."""

    def __init__(self, storage_path: str | os.PathLike[str] | None = None) -> None:
        base = storage_path or os.getenv("CHAT_HISTORY_STORAGE_PATH", "data/chat_history")
        self.storage_path = Path(base)

    def list_messages(self, *, session_id: str, limit: int = _DEFAULT_LIMIT) -> list[dict[str, Any]]:
        safe_limit = max(1, min(safe_int(limit, _DEFAULT_LIMIT) or _DEFAULT_LIMIT, _MAX_MESSAGES_PER_SESSION))
        with _STORE_LOCK:
            payload = self._read_payload(session_id)
            messages = payload.get("messages") if isinstance(payload, dict) else []
            if not isinstance(messages, list):
                return []
            return [self._public_message(item) for item in messages[-safe_limit:] if isinstance(item, dict)]

    def append_turn(
        self,
        *,
        session_id: str,
        user_content: str,
        assistant_content: str,
        evidence: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        user_text = _clean_content(user_content)
        assistant_text = _clean_content(assistant_content)
        safe_evidence = _validate_evidence(evidence)
        if not user_text and not assistant_text:
            return self.list_messages(session_id=session_id)

        now = _utc_now()
        additions: list[dict[str, Any]] = []
        if user_text:
            additions.append(
                {
                    "id": f"user-{uuid4().hex}",
                    "role": "user",
                    "content": user_text,
                    "status": "done",
                    "created_at": now,
                }
            )
        if assistant_text:
            assistant: dict[str, Any] = {
                "id": f"assistant-{uuid4().hex}",
                "role": "assistant",
                "content": assistant_text,
                "status": "done",
                "created_at": now,
            }
            if safe_evidence is not None:
                assistant["evidence"] = safe_evidence
            additions.append(assistant)

        with _STORE_LOCK:
            payload = self._read_payload(session_id)
            messages = payload.get("messages") if isinstance(payload, dict) else []
            if not isinstance(messages, list):
                messages = []
            messages = [item for item in messages if isinstance(item, dict)]
            messages.extend(additions)
            messages = messages[-_MAX_MESSAGES_PER_SESSION:]
            payload = {
                "session_id": session_id,
                "updated_at": now,
                "messages": messages,
            }
            self._write_payload(session_id, payload)
            return [self._public_message(item) for item in messages]

    def clear(self, *, session_id: str) -> None:
        with _STORE_LOCK:
            path = self._path_for_session(session_id)
            if path.exists():
                path.unlink()

    def _path_for_session(self, session_id: str) -> Path:
        return self.storage_path / f"{_safe_session_filename(session_id)}.json"

    def _read_payload(self, session_id: str) -> dict[str, Any]:
        path = self._path_for_session(session_id)
        if not path.exists():
            return {"session_id": session_id, "messages": []}
        try:
            if path.stat().st_size > _MAX_HISTORY_FILE_BYTES:
                raise ValueError("chat history file is too large")
            data = json_loads_strict(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("chat history payload must be a JSON object")
            messages = data.get("messages", [])
            if not isinstance(messages, list) or any(
                not isinstance(item, dict) for item in messages
            ):
                raise ValueError("chat history messages must be a list of objects")
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            backup_path = path.with_name(f"{path.name}.{uuid4().hex}.corrupt")
            os.replace(path, backup_path)
            logger.warning('Backed up corrupt chat history file')
            return {"session_id": session_id, "messages": []}
        data.setdefault("session_id", session_id)
        data.setdefault("messages", [])
        return data

    def _write_payload(self, session_id: str, payload: dict[str, Any]) -> None:
        self.storage_path.mkdir(parents=True, exist_ok=True)
        path = self._path_for_session(session_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8",
        )
        tmp.replace(path)

    @staticmethod
    def _public_message(item: dict[str, Any]) -> dict[str, Any]:
        role = str(item.get("role") or "").strip()
        if role not in {"user", "assistant"}:
            role = "assistant"
        content = _clean_content(item.get("content"))
        result: dict[str, Any] = {
            "id": str(item.get("id") or f"{role}-{uuid4().hex}"),
            "role": role,
            "content": content,
            "status": str(item.get("status") or "done"),
        }
        created_at = item.get("created_at")
        if isinstance(created_at, str) and created_at.strip():
            result["created_at"] = created_at.strip()
        evidence = item.get("evidence")
        if isinstance(evidence, dict) and evidence:
            result["evidence"] = evidence
        return result


__all__ = ["ChatHistoryStore"]
