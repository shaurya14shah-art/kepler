# Billing (Razorpay): disabled

**Kepler is free right now, and it cannot charge anyone.** The billing code is there so that you can switch on paid
plans later without a rewrite, but every path that could move money is locked. No Razorpay account, keys or bank
details are set up anywhere in this repository; you add those yourself, when you decide to.

Check the state at any time:

```bash
kepler billing            # plan, provider, and every reason charging is off
curl -H "X-Kepler-Key: $KEY" http://127.0.0.1:8000/api/billing
```

The dashboard shows the same thing under **Settings → Plan & billing**.

## The five locks

Charging needs **all five** open at the same time. Today the first one is shut in the code itself, so no setting,
environment variable or key can turn billing on by accident.

| # | Lock | Today | Where |
|---|------|-------|-------|
| 1 | `CHARGING_ALLOWED = True` | `False` | `backend/kepler/billing/__init__.py` (a code change, so it goes through review and a new release) |
| 2 | `KEPLER_BILLING=on` | `off` | the server's environment (`.env`, `docker-compose.yml`, the `Dockerfile` default) |
| 3 | `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` | not set | the server's environment only, never the repository |
| 4 | live keys (`rzp_live_…`) also need `KEPLER_BILLING_LIVE=yes` | not set | the server's environment |
| 5 | the plan being bought has a price | every paid plan's price is `None` | `backend/kepler/billing/plans.py` |

While any lock is shut:

- `POST /api/billing/checkout` and `POST /api/billing/verify` answer **403** before doing anything.
- `POST /api/billing/webhook/razorpay` answers **404**.
- No request is ever sent to Razorpay. The single function that talks to Razorpay calls `billing.guard()` first, and
  the tests check that no network call is made.
- Prices are never shown in the API, CLI or dashboard, and the dashboard has no upgrade buttons.
- Nothing is stored about payments, because nothing can happen.

`backend/tests/test_billing.py` checks each of these, and also that keys plus environment variables alone can't turn
billing on while lock 1 is shut.

## What's built

- **Plan catalog** (`billing/plans.py`): Free (in use, price 0), plus example Pro and Business plans with no price.
  Rename them, change their features, and set prices when you're ready.
- **Razorpay client** (`billing/razorpay.py`) over Razorpay's REST API, with no SDK. It handles one-off orders, or
  subscriptions when a Razorpay plan ID is configured.
- **Signature checks**:
  - Checkout responses: HMAC-SHA256 of `order_id|payment_id`, or of `payment_id|subscription_id`.
  - Webhooks: HMAC-SHA256 of the raw body with your webhook secret, compared in constant time.
- **Idempotent webhooks**: each `X-Razorpay-Event-Id` is applied once, and redeliveries are ignored.
- **The plan record**: the `billing_subscriptions` table holds the server's current plan (`kepler billing`, the
  dashboard). The `billing_events` table holds the webhook event IDs already applied.
- **Dashboard**: when billing is on, upgrade buttons open Razorpay Checkout, Razorpay's own hosted payment form. Card
  and bank details go straight to Razorpay; Kepler never sees or stores them.

## Where billing can run

Your Razorpay key secret must only ever live on a server **you** operate. That decides how you can sell:

- **Hosted Kepler** (you run the server for a customer): use the in-app checkout described here. The keys are in
  your server's environment, and the customer only ever sees Razorpay Checkout.
- **Self-hosted copies** (the customer runs Kepler): **never** give a customer your keys, and never ship them inside
  a build. Take payment outside the product, for example with a Razorpay Payment Page or Payment Link (no code
  needed), then send the download. Leave `KEPLER_BILLING=off` in the copies you ship.

Each Kepler server has one plan for the whole workspace. Kepler doesn't have per-user or multi-tenant accounts yet.

## Turning it on later

Do these in order, and stay in **test mode** until the whole flow works end to end. Test keys (`rzp_test_…`) never
move real money.

1. **Get ready.**
   - Decide your prices.
   - Fill in and publish the legal pages (`legal/`, see `legal/README.md`). Razorpay expects a live website with
     terms, privacy, refund/cancellation, delivery and contact pages before it activates an account.
   - Have them reviewed by a lawyer.
   - Sort out tax (for example GST) and invoicing with an accountant.
2. **Razorpay account.**
   - Sign up at razorpay.com yourself.
   - Complete their activation (KYC). Razorpay asks for your business and bank details at this step, in its own
     dashboard. Nothing in Kepler ever asks for them.
3. **Test keys.**
   - In the Razorpay dashboard, switch to Test Mode and generate an API key.
   - Put the key ID and secret in the server's environment, never in a file you commit:
     ```bash
     RAZORPAY_KEY_ID=rzp_test_…
     RAZORPAY_KEY_SECRET=…
     ```
4. **Webhook.**
   - In the Razorpay dashboard's Webhooks settings, add
     `https://<your-domain>/api/billing/webhook/razorpay`. It must be public HTTPS: see [deploy.md](deploy.md).
   - Choose a webhook secret and set the same value as `RAZORPAY_WEBHOOK_SECRET`.
   - Select these events: `order.paid`, `subscription.authenticated`, `subscription.activated`,
     `subscription.charged`, `subscription.pending`, `subscription.halted`, `subscription.paused`,
     `subscription.resumed`, `subscription.cancelled`, `subscription.completed`.
   - This path doesn't need the Kepler access key. Razorpay's signature authenticates it instead, and unsigned or
     wrongly signed requests are refused.
5. **Prices.**
   - In `backend/kepler/billing/plans.py`, set `amount` on each plan you sell. The amount is in the currency's
     smallest unit: paise for INR, so ₹999 is `99900`.
   - For recurring billing, create the same plan in Razorpay (Subscriptions → Plans) at the same price. Then set its
     ID as `RAZORPAY_PLAN_<ID>`, for example `RAZORPAY_PLAN_PRO=plan_…`.
   - Without a plan ID, checkout creates a one-off order for the amount instead.
6. **The code switch.**
   - Set `CHARGING_ALLOWED = True` in `backend/kepler/billing/__init__.py`.
   - Start the server with `KEPLER_BILLING=on`.
   - `kepler billing` should now say *enabled · test*.
7. **Test the whole flow.**
   - Upgrade from Settings → Plan & billing, and pay with one of Razorpay's published test methods.
   - Check that the plan changes, and that `kepler billing` shows it.
   - Cancel the subscription in the Razorpay dashboard and check that the webhook moves the plan back.
8. **Go live.**
   - Generate live keys in the Razorpay dashboard and replace the test keys.
   - Set `KEPLER_BILLING_LIVE=yes` as well. Without it, live keys are refused.
   - Start with a small real payment of your own, and refund it from the Razorpay dashboard.

To switch it all off again, set `KEPLER_BILLING=off` (it takes effect on restart), or set `CHARGING_ALLOWED` back to
`False`.

## Keeping keys safe

- Keys only go in the server's environment: `.env` (git-ignored), your container platform's secrets, or a secret
  manager.
- Kepler never prints, logs or returns the key secret or webhook secret. The API shows only a masked key ID
  (`rzp_test_…AB`).
- If a key leaks, regenerate it in the Razorpay dashboard straight away and update the environment.
