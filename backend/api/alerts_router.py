from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.security.auth import Principal, get_current_user, require_matching_identity
from backend.services.subscription_service import get_subscription_service


def create_alerts_router() -> APIRouter:
    router = APIRouter(tags=["Alerts"])

    @router.get("/api/alerts/feed")
    async def get_alert_feed(
        email: str = Query(..., min_length=3, description="Subscriber email"),
        limit: int = Query(30, ge=1, le=200, description="Max events"),
        since: str | None = Query(None, description="ISO datetime lower bound"),
        current_user: Principal = Depends(get_current_user),
    ):
        # 身份绑定：非 dev 时强制使用认证主体的 email，防止读取他人告警事件。
        resolved_email = email if current_user.auth_type == "dev" else (current_user.email or "")
        require_matching_identity(
            principal=current_user,
            provided=email,
            expected=resolved_email,
            field_name="email",
        )

        service = get_subscription_service()
        if not service.is_valid_email(resolved_email):
            raise HTTPException(status_code=400, detail="Invalid email")

        events = service.list_alert_events(resolved_email, limit=limit, since=since)
        return {
            "success": True,
            "email": resolved_email,
            "events": events,
            "count": len(events),
        }

    return router
