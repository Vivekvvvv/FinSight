from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from backend.graph.capability_registry import REPORT_AGENT_CANDIDATES
from backend.security.auth import Principal, get_current_user, require_matching_identity

_VALID_DEPTHS = {"standard", "deep", "off"}
_MAX_ROUNDS_MIN = 1
_MAX_ROUNDS_MAX = 10
_MAX_ROUNDS_DEFAULT = 3
logger = logging.getLogger(__name__)


def _log_error(message: str, exc: BaseException) -> None:
    error = getattr(logger, "error", None)
    if not callable(error):
        return
    try:
        error("%s: %s", message, type(exc).__name__)
    except Exception:
        pass


def _provided_user_id(value: str | None) -> str | None:
    text = str(value or "").strip()
    return None if text in {"", "default_user"} else text


@dataclass(frozen=True)
class AgentRouterDeps:
    memory_service: Any


def _default_preferences() -> dict[str, Any]:
    return {
        "agents": {name: "standard" for name in REPORT_AGENT_CANDIDATES},
        "maxRounds": _MAX_ROUNDS_DEFAULT,
        "concurrentMode": True,
    }


def _normalize_preferences(raw: Any) -> dict[str, Any]:
    defaults = _default_preferences()
    if not isinstance(raw, dict):
        return defaults

    normalized_agents = dict(defaults["agents"])
    raw_agents = raw.get("agents")
    if isinstance(raw_agents, dict):
        for name, depth in raw_agents.items():
            if not isinstance(name, str) or name not in normalized_agents:
                continue
            depth_text = str(depth).strip().lower()
            if depth_text in _VALID_DEPTHS:
                normalized_agents[name] = depth_text

    max_rounds = raw.get("maxRounds", defaults["maxRounds"])
    try:
        max_rounds_value = int(max_rounds)
    except Exception:
        max_rounds_value = defaults["maxRounds"]
    max_rounds_value = max(_MAX_ROUNDS_MIN, min(_MAX_ROUNDS_MAX, max_rounds_value))

    concurrent_mode = raw.get("concurrentMode", defaults["concurrentMode"])
    if not isinstance(concurrent_mode, bool):
        concurrent_mode = defaults["concurrentMode"]

    return {
        "agents": normalized_agents,
        "maxRounds": max_rounds_value,
        "concurrentMode": concurrent_mode,
    }


def create_agent_router(deps: AgentRouterDeps) -> APIRouter:
    router = APIRouter(tags=["Agent"])

    @router.get("/api/agents/preferences")
    async def get_agent_preferences(
        user_id: str = "default_user",
        current_user: Principal = Depends(get_current_user),
    ):
        if not deps.memory_service:
            return JSONResponse(
                status_code=503,
                content={"success": False, "error": "MemoryService not initialized"},
            )

        try:
            require_matching_identity(
                principal=current_user,
                provided=_provided_user_id(user_id),
                expected=current_user.user_id,
                field_name="user_id",
            )
            resolved_user_id = user_id if current_user.auth_type == "dev" and user_id else current_user.user_id
            profile = deps.memory_service.get_user_profile(resolved_user_id)
            prefs = profile.preferences if isinstance(profile.preferences, dict) else {}
            agent_preferences = _normalize_preferences(prefs.get("agent_preferences"))
            return {"success": True, "user_id": resolved_user_id, "preferences": agent_preferences}
        except HTTPException:
            raise
        except Exception as exc:
            _log_error("agent preferences load failed", exc)
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Internal server error"},
            )

    @router.put("/api/agents/preferences")
    async def update_agent_preferences(
        request: dict,
        current_user: Principal = Depends(get_current_user),
    ):
        if not deps.memory_service:
            return JSONResponse(
                status_code=503,
                content={"success": False, "error": "MemoryService not initialized"},
            )

        try:
            user_id = str(request.get("user_id") or "default_user").strip() or "default_user"
            require_matching_identity(
                principal=current_user,
                provided=_provided_user_id(user_id),
                expected=current_user.user_id,
                field_name="user_id",
            )
            resolved_user_id = user_id if current_user.auth_type == "dev" and user_id else current_user.user_id
            profile = deps.memory_service.get_user_profile(resolved_user_id)
            profile.preferences = profile.preferences if isinstance(profile.preferences, dict) else {}

            normalized = _normalize_preferences(request.get("preferences"))
            profile.preferences["agent_preferences"] = normalized

            success = deps.memory_service.update_user_profile(profile)
            return {"success": bool(success), "user_id": resolved_user_id, "preferences": normalized}
        except HTTPException:
            raise
        except Exception as exc:
            _log_error("agent preferences save failed", exc)
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Internal server error"},
            )

    return router
