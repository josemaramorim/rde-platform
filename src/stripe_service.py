import stripe
from datetime import datetime, timedelta
from fastapi import Request
from src.database.session import SessionLocal
from src.models.user import User, Plan, PlanHistory
from src.core.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY or ""
WEBHOOK_SECRET = settings.STRIPE_WEBHOOK_SECRET or ""

PRICE_IDS = {
    "Pro": settings.STRIPE_PRICE_PRO,
    "VIP": settings.STRIPE_PRICE_VIP,
}

SUCCESS_URL = f"{settings.FRONTEND_URL}/dashboard?status=success"
CANCEL_URL = f"{settings.FRONTEND_URL}/pricing?status=cancelled"


def _require_stripe():
    if not stripe.api_key or "REPLACE" in stripe.api_key:
        raise ValueError("❌ STRIPE_SECRET_KEY not configured in .env")
    if not WEBHOOK_SECRET or "REPLACE" in WEBHOOK_SECRET:
        raise ValueError("❌ STRIPE_WEBHOOK_SECRET not configured in .env")


def create_checkout_session(user_email: str, plan_name: str) -> str:
    _require_stripe()
    if plan_name not in PRICE_IDS or not PRICE_IDS[plan_name]:
        raise ValueError(f"Unknown or unconfigured plan '{plan_name}'. Valid: {list(PRICE_IDS.keys())}")

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        customer_email=user_email,
        line_items=[{"price": PRICE_IDS[plan_name], "quantity": 1}],
        mode="subscription",
        success_url=SUCCESS_URL,
        cancel_url=CANCEL_URL,
        metadata={"plan_name": plan_name},
    )
    return session.url


async def handle_webhook(request: Request):
    _require_stripe()
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig, WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        return {"error": "Invalid signature"}

    if event["type"] == "checkout.session.completed":
        session_obj = event["data"]["object"]
        email = session_obj.get("customer_email")
        plan_name = session_obj.get("metadata", {}).get("plan_name")

        if email and plan_name:
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.email == email).first()
                plan = db.query(Plan).filter(Plan.name == plan_name).first()

                if user and plan:
                    old_plan_name = user.plan.name if user.plan else "None"
                    user.plan = plan
                    user.plan_expires_at = datetime.utcnow() + timedelta(days=30)
                    db.add(PlanHistory(
                        user_id=user.id,
                        old_plan=old_plan_name,
                        new_plan=plan_name,
                        changed_by="stripe",
                    ))
                    db.commit()
            finally:
                db.close()

    return {"status": "ok"}
