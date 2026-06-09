from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.security.auth import Principal, get_current_user, require_matching_identity


@dataclass(frozen=True)
class UserRouterDeps:
    memory_service: Any
    user_profile_cls: Any


def create_user_router(deps: UserRouterDeps) -> APIRouter:
    router = APIRouter(tags=["User"])

    def _provided_user_id(value: str | None) -> str | None:
        text = str(value or "").strip()
        return None if text in {"", "default_user"} else text

    @router.get("/api/user/profile")
    async def get_user_profile(user_id: str = "default_user", current_user: Principal = Depends(get_current_user)):
        if not deps.memory_service:
            return {"error": "MemoryService not initialized"}

        try:
            require_matching_identity(principal=current_user, provided=_provided_user_id(user_id), expected=current_user.user_id, field_name="user_id")
            resolved_user_id = user_id if current_user.auth_type == "dev" and user_id else current_user.user_id
            profile = deps.memory_service.get_user_profile(resolved_user_id)
            return {"success": True, "profile": profile.to_dict()}
        except HTTPException:
            raise
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @router.post("/api/user/profile")
    async def update_user_profile(request: dict, current_user: Principal = Depends(get_current_user)):
        if not deps.memory_service:
            return {"error": "MemoryService not initialized"}

        try:
            user_id = request.get("user_id", "default_user")
            require_matching_identity(principal=current_user, provided=_provided_user_id(user_id), expected=current_user.user_id, field_name="user_id")
            resolved_user_id = user_id if current_user.auth_type == "dev" and user_id else current_user.user_id
            profile_data = request.get("profile", {})
            profile_data["user_id"] = resolved_user_id

            profile = deps.user_profile_cls.from_dict(profile_data)
            success = deps.memory_service.update_user_profile(profile)
            return {"success": success}
        except HTTPException:
            raise
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @router.post("/api/user/watchlist/add")
    async def add_watchlist(request: dict, current_user: Principal = Depends(get_current_user)):
        if not deps.memory_service:
            return {"error": "MemoryService not initialized"}

        try:
            user_id = request.get("user_id", "default_user")
            require_matching_identity(principal=current_user, provided=_provided_user_id(user_id), expected=current_user.user_id, field_name="user_id")
            resolved_user_id = user_id if current_user.auth_type == "dev" and user_id else current_user.user_id
            ticker = request.get("ticker")
            if not ticker:
                return {"success": False, "error": "Ticker is required"}

            name = request.get("name")
            tags = request.get("tags")
            note = request.get("note")
            if tags is not None and not isinstance(tags, list):
                return {"success": False, "error": "tags must be a list"}

            success = deps.memory_service.add_to_watchlist(
                resolved_user_id,
                ticker,
                name=name,
                tags=tags,
                note=note,
            )
            return {"success": success}
        except HTTPException:
            raise
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @router.post("/api/user/watchlist/update")
    async def update_watchlist_meta(request: dict, current_user: Principal = Depends(get_current_user)):
        """Update a watchlist entry's name/tags/note (ticker must already be in watchlist)."""
        if not deps.memory_service:
            return {"error": "MemoryService not initialized"}

        try:
            user_id = request.get("user_id", "default_user")
            require_matching_identity(principal=current_user, provided=_provided_user_id(user_id), expected=current_user.user_id, field_name="user_id")
            resolved_user_id = user_id if current_user.auth_type == "dev" and user_id else current_user.user_id
            ticker = request.get("ticker")
            if not ticker:
                return {"success": False, "error": "Ticker is required"}
            tags = request.get("tags")
            if tags is not None and not isinstance(tags, list):
                return {"success": False, "error": "tags must be a list"}

            success = deps.memory_service.update_watchlist_meta(
                resolved_user_id,
                ticker,
                name=request.get("name"),
                tags=tags,
                note=request.get("note"),
            )
            if not success:
                raise HTTPException(status_code=404, detail="Ticker not in watchlist")
            return {"success": True}
        except HTTPException:
            raise
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @router.get("/api/user/watchlist")
    async def list_watchlist(user_id: str = "default_user", q: str = "", current_user: Principal = Depends(get_current_user)):
        """List watchlist entries with name/tags/note metadata. Optionally filter by q (ticker/name)."""
        if not deps.memory_service:
            return {"error": "MemoryService not initialized"}

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
            return {"success": False, "error": str(exc)}

    @router.post("/api/user/watchlist/remove")
    async def remove_watchlist(request: dict, current_user: Principal = Depends(get_current_user)):
        if not deps.memory_service:
            return {"error": "MemoryService not initialized"}

        try:
            user_id = request.get("user_id", "default_user")
            require_matching_identity(principal=current_user, provided=_provided_user_id(user_id), expected=current_user.user_id, field_name="user_id")
            resolved_user_id = user_id if current_user.auth_type == "dev" and user_id else current_user.user_id
            ticker = request.get("ticker")
            if not ticker:
                return {"success": False, "error": "Ticker is required"}

            success = deps.memory_service.remove_from_watchlist(resolved_user_id, ticker)
            return {"success": success}
        except HTTPException:
            raise
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    return router
