from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.api.schemas import (
    SubscriptionListResponse,
    SubscriptionRequest,
    SubscriptionResponse,
    ToggleSubscriptionRequest,
    UnsubscribeRequest,
)
from backend.security.auth import Principal, get_current_user, require_admin_principal, require_matching_identity

logger = logging.getLogger(__name__)

def create_subscription_router() -> APIRouter:
    router = APIRouter(tags=["Subscription"])

    @router.post("/api/subscribe")
    async def subscribe_email(request: SubscriptionRequest, current_user: Principal = Depends(get_current_user)):
        try:
            from backend.services.subscription_service import get_subscription_service

            subscription_service = get_subscription_service()
            resolved_email = request.email if current_user.auth_type == "dev" else (current_user.email or "")
            require_matching_identity(principal=current_user, provided=request.email, expected=resolved_email, field_name="email")
            if not subscription_service.is_valid_email(resolved_email):
                raise HTTPException(status_code=400, detail="Invalid email")

            success = subscription_service.subscribe(
                email=resolved_email,
                ticker=request.ticker,
                alert_types=request.alert_types,
                price_threshold=request.price_threshold,
                alert_mode=request.alert_mode,
                price_target=request.price_target,
                direction=request.direction,
                risk_threshold=request.risk_threshold,
            )

            if success:
                return {
                    "success": True,
                    "message": f"Subscribed to {request.ticker}",
                    "email": resolved_email,
                    "ticker": request.ticker,
                }
            raise HTTPException(status_code=500, detail="Subscribe failed")
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[subscription/subscribe] failed: %s", type(exc).__name__)
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    @router.post("/api/unsubscribe")
    async def unsubscribe_email(request: UnsubscribeRequest, current_user: Principal = Depends(get_current_user)):
        try:
            from backend.services.subscription_service import get_subscription_service

            subscription_service = get_subscription_service()
            resolved_email = request.email if current_user.auth_type == "dev" else (current_user.email or "")
            require_matching_identity(principal=current_user, provided=request.email, expected=resolved_email, field_name="email")
            if not resolved_email:
                raise HTTPException(status_code=400, detail="email is required")

            success = subscription_service.unsubscribe(
                email=resolved_email,
                ticker=request.ticker,
            )

            if success:
                return {
                    "success": True,
                    "message": "Unsubscribed",
                    "email": resolved_email,
                    "ticker": request.ticker or "all",
                }
            raise HTTPException(status_code=404, detail="Subscription not found")
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[subscription/unsubscribe] failed: %s", type(exc).__name__)
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    @router.get("/api/subscriptions", response_model=SubscriptionListResponse)
    async def get_subscriptions(email: str = None, current_user: Principal = Depends(get_current_user)):
        try:
            from backend.services.subscription_service import get_subscription_service

            subscription_service = get_subscription_service()
            resolved_email = email if current_user.auth_type == "dev" and email else (current_user.email or "")
            if email:
                require_matching_identity(principal=current_user, provided=email, expected=resolved_email, field_name="email")
            if not resolved_email:
                raise HTTPException(status_code=400, detail="email is required")
            subscriptions = subscription_service.get_subscriptions(email=resolved_email)
            return {
                "success": True,
                "subscriptions": subscriptions,
                "count": len(subscriptions),
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[subscription/list] failed: %s", type(exc).__name__)
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    @router.post("/api/subscription/toggle", response_model=SubscriptionResponse)
    async def toggle_subscription(request: ToggleSubscriptionRequest, current_user: Principal = Depends(get_current_user)):
        try:
            from backend.services.subscription_service import get_subscription_service

            subscription_service = get_subscription_service()
            resolved_email = request.email if current_user.auth_type == "dev" else (current_user.email or "")
            require_matching_identity(principal=current_user, provided=request.email, expected=resolved_email, field_name="email")
            success = subscription_service.toggle_subscription(
                email=resolved_email,
                ticker=request.ticker,
                enabled=request.enabled,
            )

            if success:
                return {
                    "success": True,
                    "message": f"Subscription {'enabled' if request.enabled else 'disabled'}",
                    "email": resolved_email,
                    "ticker": request.ticker,
                }
            raise HTTPException(status_code=404, detail="Subscription not found")
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[subscription/toggle] failed: %s", type(exc).__name__)
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    @router.get("/api/admin/subscriptions", response_model=SubscriptionListResponse)
    async def get_admin_subscriptions(request: Request, current_user: Principal = Depends(require_admin_principal)):
        try:
            from backend.services.subscription_service import get_subscription_service

            subscription_service = get_subscription_service()
            subscriptions = subscription_service.get_subscriptions(email=None, allow_all=True)
            logger.info(
                "[Audit] admin subscription list user_id=%s role=%s count=%d",
                current_user.user_id,
                current_user.role,
                len(subscriptions),
            )
            return {"success": True, "subscriptions": subscriptions, "count": len(subscriptions)}
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[subscription/admin-list] failed: %s", type(exc).__name__)
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    return router
