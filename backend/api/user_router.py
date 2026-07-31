from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from backend.security.auth import Principal, get_current_user, require_matching_identity
from backend.services.memory import WatchlistLimitExceeded
from backend.utils.quote import safe_int


logger = logging.getLogger(__name__)
_MAX_PROFILE_BYTES = 256 * 1024


def _log_error(message: str, exc: BaseException) -> None:
    error = getattr(logger, "error", None)
    if not callable(error):
        return
    try:
        error("%s: %s", message, type(exc).__name__)
    except Exception:
        pass


@dataclass(frozen=True)
class UserRouterDeps:
    memory_service: Any
    user_profile_cls: Any


def create_user_router(deps: UserRouterDeps) -> APIRouter:
    router = APIRouter(tags=["User"])

    def _watchlist_entitlement(principal: Principal) -> tuple[int, str]:
        from backend.services.entitlements import get_entitlements_service

        entitlements = get_entitlements_service().get_entitlements(
            principal.user_id,
            role=principal.role,
        )
        limit = safe_int((entitlements.get("limits") or {}).get("max_watchlist"), 0) or 0
        return limit, str(entitlements.get("plan") or "free")

    def _raise_watchlist_quota(*, limit: int, current: int, plan: str) -> None:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "plan_quota_exceeded",
                "quota": "max_watchlist",
                "plan": plan,
                "limit": limit,
                "current": current,
                "message": "Watchlist quota reached. Upgrade to continue.",
            },
        )

    def _watchlist_request_error(request: dict) -> str | None:
        ticker = request.get("ticker")
        if not isinstance(ticker, str) or not ticker.strip() or len(ticker.strip()) > 32:
            return "Invalid ticker"

        tags = request.get("tags")
        if tags is not None:
            if not isinstance(tags, list):
                return "tags must be a list"
            if len(tags) > 20 or any(not isinstance(tag, str) or len(tag) > 64 for tag in tags):
                return "Invalid tags"

        for field, limit in (
            ("name", 128),
            ("note", 2000),
            ("group", 64),
            ("watch_reason", 1000),
            ("research_status", 32),
        ):
            value = request.get(field)
            if value is not None and (not isinstance(value, str) or len(value) > limit):
                return f"Invalid {field}"

        priority = request.get("priority")
        if priority is not None and (not isinstance(priority, int) or isinstance(priority, bool) or not 1 <= priority <= 5):
            return "Invalid priority"
        return None

    def _provided_user_id(value: str | None) -> str | None:
        text = str(value or "").strip()
        return None if text in {"", "default_user"} else text

    @router.get("/api/user/profile")
    async def get_user_profile(user_id: str = "default_user", current_user: Principal = Depends(get_current_user)):
        if not deps.memory_service:
            return JSONResponse(status_code=503, content={"error": "MemoryService not initialized"})

        try:
            require_matching_identity(principal=current_user, provided=_provided_user_id(user_id), expected=current_user.user_id, field_name="user_id")
            resolved_user_id = user_id if current_user.auth_type == "dev" and user_id else current_user.user_id
            profile = deps.memory_service.get_user_profile(resolved_user_id)
            return {"success": True, "profile": profile.to_dict()}
        except HTTPException:
            raise
        except Exception as exc:
            _log_error("user profile load failed", exc)
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Internal server error"},
            )

    @router.post("/api/user/profile")
    async def update_user_profile(request: dict, current_user: Principal = Depends(get_current_user)):
        if not deps.memory_service:
            return JSONResponse(status_code=503, content={"error": "MemoryService not initialized"})

        try:
            user_id = request.get("user_id", "default_user")
            require_matching_identity(principal=current_user, provided=_provided_user_id(user_id), expected=current_user.user_id, field_name="user_id")
            resolved_user_id = user_id if current_user.auth_type == "dev" and user_id else current_user.user_id
            profile_data = request.get("profile", {})
            if not isinstance(profile_data, dict):
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "profile must be an object"},
                )
            profile_data = dict(profile_data)
            try:
                encoded_profile = json.dumps(
                    profile_data,
                    ensure_ascii=False,
                    allow_nan=False,
                ).encode("utf-8")
            except (TypeError, ValueError):
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "Invalid profile payload"},
                )
            if len(encoded_profile) > _MAX_PROFILE_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"success": False, "error": "profile is too large"},
                )
            watchlist = profile_data.get("watchlist", [])
            if not isinstance(watchlist, list):
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "watchlist must be a list"},
                )
            if any(not isinstance(ticker, str) or not ticker.strip() or len(ticker) > 32 for ticker in watchlist):
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "Invalid watchlist ticker"},
                )
            for field in ("watchlist_meta", "preferences"):
                value = profile_data.get(field, {})
                if not isinstance(value, dict):
                    return JSONResponse(
                        status_code=400,
                        content={"success": False, "error": f"{field} must be an object"},
                    )
            max_watchlist, plan = _watchlist_entitlement(current_user)
            if max_watchlist >= 0 and len(watchlist) > max_watchlist:
                _raise_watchlist_quota(
                    limit=max_watchlist,
                    current=len(watchlist),
                    plan=plan,
                )
            profile_data["user_id"] = resolved_user_id

            profile = deps.user_profile_cls.from_dict(profile_data)
            success = deps.memory_service.update_user_profile(profile)
            return {"success": success}
        except HTTPException:
            raise
        except Exception as exc:
            _log_error("user profile save failed", exc)
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Internal server error"},
            )

    @router.post("/api/user/watchlist/add")
    async def add_watchlist(request: dict, current_user: Principal = Depends(get_current_user)):
        if not deps.memory_service:
            return JSONResponse(status_code=503, content={"error": "MemoryService not initialized"})

        try:
            user_id = request.get("user_id", "default_user")
            require_matching_identity(principal=current_user, provided=_provided_user_id(user_id), expected=current_user.user_id, field_name="user_id")
            resolved_user_id = user_id if current_user.auth_type == "dev" and user_id else current_user.user_id
            ticker = request.get("ticker")
            if not ticker:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "Ticker is required"},
                )

            name = request.get("name")
            tags = request.get("tags")
            note = request.get("note")
            research_status = request.get("research_status")
            if tags is not None and not isinstance(tags, list):
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "tags must be a list"},
                )
            request_error = _watchlist_request_error(request)
            if request_error:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": request_error},
                )

            max_watchlist, plan = _watchlist_entitlement(current_user)
            try:
                success = deps.memory_service.add_to_watchlist(
                    resolved_user_id,
                    ticker,
                    name=name,
                    tags=tags,
                    note=note,
                    group=request.get("group"),
                    priority=request.get("priority"),
                    watch_reason=request.get("watch_reason"),
                    research_status=research_status,
                    max_watchlist=max_watchlist,
                )
            except WatchlistLimitExceeded as exc:
                _raise_watchlist_quota(
                    limit=exc.limit,
                    current=exc.current,
                    plan=plan,
                )
            return {"success": success}
        except HTTPException:
            raise
        except Exception as exc:
            _log_error("watchlist add failed", exc)
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Internal server error"},
            )

    @router.post("/api/user/watchlist/update")
    async def update_watchlist_meta(request: dict, current_user: Principal = Depends(get_current_user)):
        """Update a watchlist entry's name/tags/note (ticker must already be in watchlist)."""
        if not deps.memory_service:
            return JSONResponse(status_code=503, content={"error": "MemoryService not initialized"})

        try:
            user_id = request.get("user_id", "default_user")
            require_matching_identity(principal=current_user, provided=_provided_user_id(user_id), expected=current_user.user_id, field_name="user_id")
            resolved_user_id = user_id if current_user.auth_type == "dev" and user_id else current_user.user_id
            ticker = request.get("ticker")
            if not ticker:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "Ticker is required"},
                )
            tags = request.get("tags")
            if tags is not None and not isinstance(tags, list):
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "tags must be a list"},
                )
            request_error = _watchlist_request_error(request)
            if request_error:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": request_error},
                )

            success = deps.memory_service.update_watchlist_meta(
                resolved_user_id,
                ticker,
                name=request.get("name"),
                tags=tags,
                note=request.get("note"),
                group=request.get("group"),
                priority=request.get("priority"),
                watch_reason=request.get("watch_reason"),
                research_status=request.get("research_status"),
            )
            if not success:
                raise HTTPException(status_code=404, detail="Ticker not in watchlist")
            return {"success": True}
        except HTTPException:
            raise
        except Exception as exc:
            _log_error("watchlist update failed", exc)
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Internal server error"},
            )

    @router.get("/api/user/watchlist")
    async def list_watchlist(user_id: str = "default_user", q: str = Query("", max_length=128), current_user: Principal = Depends(get_current_user)):
        """List watchlist entries with name/tags/note metadata. Optionally filter by q (ticker/name)."""
        if not deps.memory_service:
            return JSONResponse(status_code=503, content={"error": "MemoryService not initialized"})

        try:
            require_matching_identity(principal=current_user, provided=_provided_user_id(user_id), expected=current_user.user_id, field_name="user_id")
            resolved_user_id = user_id if current_user.auth_type == "dev" and user_id else current_user.user_id
            items = deps.memory_service.list_watchlist_items(resolved_user_id)
            if q.strip():
                q_lower = q.strip().lower()
                items = [
                    it for it in items
                    if q_lower in it.get("ticker", "").lower()
                    or q_lower in (it.get("name") or "").lower()
                ]
            return {"success": True, "items": items, "count": len(items)}
        except HTTPException:
            raise
        except Exception as exc:
            _log_error("watchlist list failed", exc)
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Internal server error"},
            )

    @router.post("/api/user/watchlist/remove")
    async def remove_watchlist(request: dict, current_user: Principal = Depends(get_current_user)):
        if not deps.memory_service:
            return JSONResponse(status_code=503, content={"error": "MemoryService not initialized"})

        try:
            user_id = request.get("user_id", "default_user")
            require_matching_identity(principal=current_user, provided=_provided_user_id(user_id), expected=current_user.user_id, field_name="user_id")
            resolved_user_id = user_id if current_user.auth_type == "dev" and user_id else current_user.user_id
            ticker = request.get("ticker")
            if not ticker:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "Ticker is required"},
                )

            success = deps.memory_service.remove_from_watchlist(resolved_user_id, ticker)
            return {"success": success}
        except HTTPException:
            raise
        except Exception as exc:
            _log_error("watchlist remove failed", exc)
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Internal server error"},
            )

    return router
