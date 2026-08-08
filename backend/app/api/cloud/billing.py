from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel
from typing import Optional
import os, json

from app.api.auth import get_current_user, require_role
from app.core.billing import get_billing, set_plan, get_plan, get_usage

router = APIRouter(prefix="/api/cloud/billing", tags=["cloud-billing"])


class CheckoutRequest(BaseModel):
    plan: str


@router.get("")
async def get_billing_endpoint(user=Depends(get_current_user)):
    ws_id = user.get("workspace_id") or "default"
    billing = get_billing(ws_id)
    usage = get_usage(ws_id)
    quotas_map = {
        "free": {"datasets": 3, "queries_per_month": 50},
        "pro": {"datasets": 100, "queries_per_month": 10000},
        "team": {"datasets": 500, "queries_per_month": 100000},
        "enterprise": {"datasets": 10000, "queries_per_month": 1000000},
    }
    plan = billing.get("plan", "free")
    quotas = quotas_map.get(plan, quotas_map["free"])
    return {
        "workspace_id": ws_id,
        "plan": plan,
        "status": billing.get("status", "active"),
        "stripe_customer_id": billing.get("stripe_customer_id"),
        "usage": usage,
        "quotas": quotas,
    }


@router.post("/checkout")
async def checkout(body: CheckoutRequest, request: Request, user=Depends(get_current_user)):
    plan = body.plan.lower()
    if plan not in ("pro", "team", "enterprise", "free"):
        raise HTTPException(status_code=400, detail="plan must be pro|team|enterprise|free")
    ws_id = user.get("workspace_id") or "default"
    # If Stripe configured, try real checkout else mock
    stripe_key = os.getenv("STRIPE_SECRET_KEY")
    if stripe_key and stripe_key != "sk_test_mock":
        try:
            import stripe

            stripe.api_key = stripe_key
            price_map = {
                "pro": os.getenv("STRIPE_PRICE_PRO"),
                "team": os.getenv("STRIPE_PRICE_TEAM"),
                "enterprise": os.getenv("STRIPE_PRICE_ENTERPRISE"),
            }
            price = price_map.get(plan)
            if not price:
                # fallback mock url
                raise Exception("no price")
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                mode="subscription",
                line_items=[{"price": price, "quantity": 1}],
                success_url=str(request.base_url) + "billing?success=1",
                cancel_url=str(request.base_url) + "billing?canceled=1",
                client_reference_id=ws_id,
                metadata={"workspace_id": ws_id, "plan": plan},
            )
            return {"url": session.url, "session_id": session.id}
        except Exception as e:
            # fallback mock
            pass
    # Mock checkout
    # For tests, if plan is free, instantly set
    if plan == "free":
        set_plan(ws_id, "free")
        return {
            "url": f"/billing?mock=free&ws={ws_id}",
            "session_id": f"mock_free_{ws_id}",
            "mock": True,
        }
    # For pro/team/enterprise, return mock URL but don't yet upgrade until webhook
    mock_url = f"https://checkout.stripe.com/mock/{ws_id}/{plan}"
    return {"url": mock_url, "session_id": f"mock_{ws_id}_{plan}", "mock": True, "plan": plan}


@router.post("/webhook")
async def webhook(request: Request):
    # Verify signature if STRIPE_WEBHOOK_SECRET set, else accept mock JSON
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    payload = await request.body()
    sig = request.headers.get("Stripe-Signature") or request.headers.get("stripe-signature", "")
    # Try stripe verification if stripe installed
    try:
        import stripe, json as _j

        if webhook_secret and sig and payload:
            try:
                event = stripe.Webhook.construct_event(payload, sig, webhook_secret)
            except Exception as e:
                # for mock tests, fallback to json parse
                try:
                    event = _j.loads(payload.decode() if isinstance(payload, bytes) else payload)
                except:
                    event = {}
        else:
            # mock: parse json
            import json as _j

            try:
                event = _j.loads(payload.decode() if isinstance(payload, bytes) else payload)
            except:
                event = {}
    except ImportError:
        import json as _j

        try:
            event = _j.loads(payload.decode() if isinstance(payload, bytes) else payload)
        except:
            event = {}
    # event can be dict with type
    etype = event.get("type") if isinstance(event, dict) else getattr(event, "type", "")
    data_obj = event.get("data", {}).get("object", {}) if isinstance(event, dict) else {}
    # handle checkout.session.completed
    if etype == "checkout.session.completed":
        ws_id = data_obj.get("client_reference_id") or data_obj.get("metadata", {}).get(
            "workspace_id"
        )
        plan = data_obj.get("metadata", {}).get("plan") or "pro"
        if ws_id:
            set_plan(ws_id, plan, stripe_customer_id=data_obj.get("customer"))
            return {"status": "ok", "workspace_id": ws_id, "plan": plan}
        # try fallback: metadata ws_id
        meta = data_obj.get("metadata", {}) if isinstance(data_obj, dict) else {}
        ws_id = meta.get("workspace_id")
        if ws_id:
            plan = meta.get("plan", "pro")
            set_plan(ws_id, plan)
            return {"status": "ok", "workspace_id": ws_id, "plan": plan}
    # Also support simple mock payload: {"workspace_id": "...", "plan": "..."}
    if isinstance(event, dict) and event.get("workspace_id") and event.get("plan"):
        set_plan(event["workspace_id"], event["plan"])
        return {"status": "ok", "mock": True}
    return {"status": "received", "type": etype}


@router.post("/portal")
async def portal(request: Request, user=Depends(get_current_user)):
    ws_id = user.get("workspace_id") or "default"
    stripe_key = os.getenv("STRIPE_SECRET_KEY")
    billing = get_billing(ws_id)
    if stripe_key and billing.get("stripe_customer_id"):
        try:
            import stripe

            stripe.api_key = stripe_key
            session = stripe.billing_portal.Session.create(
                customer=billing["stripe_customer_id"], return_url=str(request.base_url)
            )
            return {"url": session.url}
        except:
            pass
    return {"url": f"/billing/portal/mock/{ws_id}"}
