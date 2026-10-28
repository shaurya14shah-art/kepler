"""Razorpay, through its REST API (no SDK). Every call that talks to Razorpay goes through billing.guard() first, so
none of it runs while billing is disabled (today: always).

  checkout(plan)                 → what the browser's Razorpay Checkout needs (a subscription, or an order)
  verify_checkout(...)           → check the signature Checkout returns, then mark the plan active
  handle_webhook(body, headers)  → check X-Razorpay-Signature, apply each event once (by X-Razorpay-Event-Id)

Signatures (Razorpay docs): payments  HMAC-SHA256(order_id + "|" + payment_id, key_secret)
                            subscriptions HMAC-SHA256(payment_id + "|" + subscription_id, key_secret)
                            webhooks  HMAC-SHA256(raw request body, webhook_secret), hex
Card and bank details never reach Kepler: Razorpay's own Checkout page collects them.
"""
import hashlib
import hmac
import json
import time

from . import BillingDisabled, guard, keys, plans

API = "https://api.razorpay.com/v1"
TIMEOUT = 20.0
EVENT_STATUS = {  # webhook event → subscription status
    "subscription.authenticated": "created", "subscription.activated": "active", "subscription.charged": "active",
    "subscription.resumed": "active", "subscription.pending": "active", "subscription.halted": "halted",
    "subscription.paused": "halted", "subscription.cancelled": "cancelled", "subscription.completed": "completed",
    "order.paid": "active",
}


class CheckoutError(Exception):
    pass


# ---------------------------------------------------------------- signatures (pure, safe to call any time)

def _hmac(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def signature_ok(expected_hex: str, given: str | None) -> bool:
    return bool(given) and hmac.compare_digest(expected_hex, given.strip())


def payment_signature(order_id: str, payment_id: str, key_secret: str) -> str:
    return _hmac(key_secret, f"{order_id}|{payment_id}".encode())


def subscription_signature(payment_id: str, subscription_id: str, key_secret: str) -> str:
    return _hmac(key_secret, f"{payment_id}|{subscription_id}".encode())


def webhook_signature(body: bytes, webhook_secret: str) -> str:
    return _hmac(webhook_secret, body)


# ---------------------------------------------------------------- talking to Razorpay (guarded)

def _post(path: str, payload: dict) -> dict:
    guard()
    import httpx
    k = keys()
    try:
        r = httpx.post(f"{API}{path}", json=payload, auth=(k["key_id"], k["key_secret"]), timeout=TIMEOUT)
    except httpx.HTTPError as e:
        raise CheckoutError(f"couldn't reach Razorpay: {type(e).__name__}") from None
    if r.status_code >= 400:
        try:
            msg = r.json().get("error", {}).get("description") or r.text[:200]
        except ValueError:
            msg = r.text[:200]
        raise CheckoutError(f"Razorpay said: {msg}")
    return r.json()


def checkout(plan_id: str, workspace: str = "default") -> dict:
    """Start a purchase. Refuses unless billing is enabled and the plan has a price."""
    guard()
    plan = plans.get(plan_id)
    if not plan or not plan.for_sale:
        raise CheckoutError(f"the plan '{plan_id}' isn't for sale (it has no price)")
    notes = {"workspace": workspace, "plan": plan.id}
    if plan.razorpay_plan_id:  # recurring: a Razorpay subscription on the plan you created in their dashboard
        sub = _post("/subscriptions", {"plan_id": plan.razorpay_plan_id, "total_count": 120 if plan.interval == "monthly" else 10,
                                       "customer_notify": 1, "notes": notes})
        _record(plan.id, "created", sub["id"])
        return {"key_id": keys()["key_id"], "subscription_id": sub["id"], "plan": plan.id, "name": "Kepler",
                "description": f"Kepler {plan.name}"}
    order = _post("/orders", {"amount": plan.amount, "currency": plan.currency, "receipt": f"kepler-{plan.id}-{int(time.time())}",
                              "notes": notes})
    _record(plan.id, "created", order["id"])
    return {"key_id": keys()["key_id"], "order_id": order["id"], "amount": plan.amount, "currency": plan.currency,
            "plan": plan.id, "name": "Kepler", "description": f"Kepler {plan.name}"}


def verify_checkout(payment_id: str, signature: str, order_id: str = "", subscription_id: str = "") -> str:
    """Called with what Razorpay Checkout hands the browser after a payment. Returns the activated plan."""
    guard()
    secret = keys()["key_secret"]
    if subscription_id:
        ok, ref = signature_ok(subscription_signature(payment_id, subscription_id, secret), signature), subscription_id
    elif order_id:
        ok, ref = signature_ok(payment_signature(order_id, payment_id, secret), signature), order_id
    else:
        raise CheckoutError("missing the order or subscription ID")
    if not ok:
        raise CheckoutError("the payment signature doesn't match: not activating anything")
    plan = _plan_for(ref)
    _record(plan, "active", ref)
    return plan


def handle_webhook(body: bytes, headers) -> dict:
    """Apply one Razorpay webhook. Returns {'applied': bool, 'event': type}."""
    guard()
    if not signature_ok(webhook_signature(body, keys()["webhook_secret"]), headers.get("x-razorpay-signature")):
        raise CheckoutError("bad webhook signature")
    event = json.loads(body)
    etype = str(event.get("event", ""))
    event_id = headers.get("x-razorpay-event-id") or hashlib.sha256(body).hexdigest()[:32]
    entity = (event.get("payload") or {})
    ref = (((entity.get("subscription") or {}).get("entity") or {}).get("id")
           or ((entity.get("order") or {}).get("entity") or {}).get("id"))
    from .. import db
    with db.session(write=True) as c:
        if c.execute("SELECT 1 FROM billing_events WHERE event_id = ?", (event_id,)).fetchone():
            return {"applied": False, "event": etype, "reason": "already applied"}
        c.execute("INSERT INTO billing_events(event_id, type, ref, received) VALUES (?, ?, ?, ?)",
                  (event_id, etype, ref, int(time.time())))
    status = EVENT_STATUS.get(etype)
    if status and ref:
        _record(_plan_for(ref), status, ref)
        return {"applied": True, "event": etype, "status": status}
    return {"applied": False, "event": etype, "reason": "not an event Kepler acts on"}


# ---------------------------------------------------------------- records

def _plan_for(ref: str) -> str:
    from .. import db
    with db.session() as c:
        row = c.execute("SELECT plan FROM billing_subscriptions WHERE provider_ref = ? ORDER BY updated DESC LIMIT 1", (ref,)).fetchone()
    return row["plan"] if row else plans.DEFAULT_PLAN


def _record(plan: str, status: str, ref: str) -> None:
    from .. import db
    with db.session(write=True) as c:
        row = c.execute("SELECT id FROM billing_subscriptions WHERE provider_ref = ?", (ref,)).fetchone()
        if row:
            c.execute("UPDATE billing_subscriptions SET status = ?, plan = ?, updated = ? WHERE id = ?",
                      (status, plan, int(time.time()), row["id"]))
        else:
            c.execute("INSERT INTO billing_subscriptions(plan, status, provider, provider_ref, updated) VALUES (?, ?, 'razorpay', ?, ?)",
                      (plan, status, ref, int(time.time())))


__all__ = ["BillingDisabled", "CheckoutError", "checkout", "verify_checkout", "handle_webhook"]
