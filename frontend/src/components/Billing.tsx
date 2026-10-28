import { useState } from "react";
import { api, type Billing as BillingT, type CheckoutStart, type Plan } from "../lib/api";
import { usePoll, useToast } from "./ui";

/** Razorpay Checkout (loaded only when someone clicks Upgrade, and only while billing is enabled). Card and bank
 *  details are typed into Razorpay's own window and never reach Kepler. */
type RazorpayCtor = new (opts: Record<string, unknown>) => { open: () => void };
declare global {
  interface Window {
    Razorpay?: RazorpayCtor;
  }
}

function loadCheckout(): Promise<RazorpayCtor> {
  return new Promise((resolve, reject) => {
    if (window.Razorpay) return resolve(window.Razorpay);
    const s = document.createElement("script");
    s.src = "https://checkout.razorpay.com/v1/checkout.js";
    s.onload = () => (window.Razorpay ? resolve(window.Razorpay) : reject(new Error("Razorpay Checkout didn't load")));
    s.onerror = () => reject(new Error("couldn't load Razorpay Checkout"));
    document.head.appendChild(s);
  });
}

function price(p: Plan) {
  if (p.amount === null) return null;
  if (p.amount === 0) return "Free";
  const major = p.amount / 100;
  return `${new Intl.NumberFormat(undefined, { style: "currency", currency: p.currency }).format(major)} / ${p.interval === "yearly" ? "year" : "month"}`;
}

export function BillingCard() {
  const { data, reload } = usePoll<BillingT>(api.billing, 0);
  const [busy, setBusy] = useState<string | null>(null);
  const toast = useToast();
  if (!data) return null;

  const upgrade = async (plan: Plan) => {
    setBusy(plan.id);
    try {
      const start: CheckoutStart = await api.checkout(plan.id);
      const Razorpay = await loadCheckout();
      new Razorpay({
        key: start.key_id,
        name: start.name,
        description: start.description,
        ...(start.subscription_id ? { subscription_id: start.subscription_id } : { order_id: start.order_id, amount: start.amount, currency: start.currency }),
        handler: async (resp: Record<string, string>) => {
          try {
            await api.verifyPayment(resp);
            toast(`You're on ${plan.name} ✓`);
            reload();
          } catch (e) {
            toast((e as Error).message);
          }
        },
        theme: { color: "#6b5ce7" },
      }).open();
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const current = data.plans.find((p) => p.id === data.plan);
  return (
    <div className="card pad stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2>Plan &amp; billing</h2>
        <span className={`chip ${data.enabled ? "accent" : "ok"}`}>{data.enabled ? `billing ${data.mode}` : "free"}</span>
      </div>
      <p className="muted small">
        You're on <strong>{current?.name ?? data.plan}</strong>
        {current?.tagline ? `: ${current.tagline}.` : "."} {data.message}
      </p>
      {current && (
        <ul className="small" style={{ margin: 0, paddingLeft: "1.2em" }}>
          {current.features.map((f) => <li key={f}>{f}</li>)}
        </ul>
      )}
      {data.enabled && (
        <div className="grid two">
          {data.plans.filter((p) => p.for_sale && p.id !== data.plan).map((p) => (
            <div key={p.id} className="card pad stack">
              <strong>{p.name}</strong>
              <span className="muted small">{p.tagline}</span>
              <span>{price(p)}</span>
              <div><button className="btn primary" disabled={busy !== null} onClick={() => upgrade(p)}>
                {busy === p.id ? "Opening…" : `Upgrade to ${p.name}`}
              </button></div>
            </div>
          ))}
        </div>
      )}
      <span className="hint">
        {data.enabled ? "Payments are processed by Razorpay." : "If paid plans are offered later, payments will go through Razorpay."} Kepler
        never sees or stores card or bank details.
      </span>
    </div>
  );
}
