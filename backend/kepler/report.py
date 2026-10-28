"""The weekly report: what Kepler saw over a period, for the team. `kepler report`, GET /api/report, and --send
(POST /api/report/send) to Slack and every email destination. Run it from cron for a weekly digest."""
import json
import statistics
import time

from .db import get_settings


def build(conn, days: int = 7, now: float | None = None) -> dict:
    now = int(now or time.time())
    since, before = now - days * 86400, now - 2 * days * 86400
    rows = conn.execute(
        "SELECT i.*, m.name AS metric FROM incidents i JOIN metrics m ON m.id = i.metric_id WHERE i.start_ts >= ? "
        "ORDER BY i.start_ts", (since,)).fetchall()
    previous = conn.execute("SELECT COUNT(*) n FROM incidents WHERE start_ts >= ? AND start_ts < ?",
                            (before, since)).fetchone()["n"]
    kind = lambda r: json.loads(r["model_json"] or "{}").get("kind", "anomaly")  # noqa: E731
    anomalies = [r for r in rows if kind(r) != "no_data"]
    by_metric: dict[str, int] = {}
    for r in anomalies:
        by_metric[r["metric"]] = by_metric.get(r["metric"], 0) + 1
    resolved = [r for r in anomalies if r["status"] == "resolved"]
    real = sum(1 for r in rows if r["feedback"] == 1)
    false = sum(1 for r in rows if r["feedback"] == 0)
    muted = [m["name"] for m in conn.execute("SELECT name, muted_until FROM metrics WHERE muted_until > ?", (now,))]
    notes = conn.execute("SELECT COUNT(*) n FROM incident_notes n JOIN incidents i ON i.id = n.incident_id "
                         "WHERE i.start_ts >= ?", (since,)).fetchone()["n"]
    return {
        "days": days, "from": since, "to": now,
        "incidents": len(anomalies), "previous_period": previous,
        "by_severity": {s: sum(1 for r in anomalies if r["severity"] == s) for s in ("critical", "high", "medium")},
        "top_metrics": sorted(by_metric.items(), key=lambda kv: -kv[1])[:5],
        "open_now": sum(1 for r in rows if r["status"] == "open"),
        # how long incidents lasted, start to last anomalous bucket (+5 min for that bucket)
        "median_minutes": round(statistics.median((r["end_ts"] - r["start_ts"] + 300) / 60 for r in resolved))
        if resolved else None,
        "data_outages": [r["metric"] for r in rows if kind(r) == "no_data"],
        "labelled": {"real": real, "false": false, "precision": round(real / (real + false), 2) if real + false else None},
        "unlabelled": sum(1 for r in anomalies if r["feedback"] is None),
        "muted": muted, "notes": notes,
    }


def text(r: dict) -> str:
    """Plain text, readable in Slack, email and a terminal."""
    span = f"{time.strftime('%a %d %b', time.localtime(r['from']))} – {time.strftime('%a %d %b', time.localtime(r['to']))}"
    trend = r["incidents"] - r["previous_period"]
    lines = [f"Kepler report, last {r['days']} days ({span})", ""]
    if not r["incidents"] and not r["data_outages"]:
        lines.append("No incidents. All quiet.")
    else:
        sev = ", ".join(f"{n} {s}" for s, n in r["by_severity"].items() if n) or "none"
        lines.append(f"Incidents: {r['incidents']} ({sev}); {'+' if trend > 0 else ''}{trend} vs the {r['days']} days before")
        if r["top_metrics"]:
            lines.append("Most incidents: " + ", ".join(f"{m} ({n})" for m, n in r["top_metrics"]))
        if r["median_minutes"] is not None:
            lines.append(f"Typical incident lasted {r['median_minutes']} min")
        if r["open_now"]:
            lines.append(f"Open right now: {r['open_now']}")
        if r["data_outages"]:
            lines.append(f"Data outages (stopped reporting): {', '.join(sorted(set(r['data_outages'])))}")
    lab = r["labelled"]
    if lab["precision"] is not None:
        lines.append(f"Your labels: {lab['real']} real, {lab['false']} false alarms ({lab['precision']:.0%} precision)")
    if r["unlabelled"]:
        lines.append(f"Unlabelled: {r['unlabelled']}. Label them (👍/👎) so Kepler learns what your team cares about")
    if r["muted"]:
        lines.append(f"Muted: {', '.join(r['muted'])}")
    if r["notes"]:
        lines.append(f"Notes written: {r['notes']}")
    from . import config
    if config.PUBLIC_URL:
        lines += ["", f"Dashboard: {config.PUBLIC_URL}/#/incidents"]
    return "\n".join(lines)


def send(conn, r: dict) -> list[dict]:
    """Post the report to Slack (when configured) and every enabled email destination. One result per channel."""
    import httpx
    from email.message import EmailMessage
    from email.utils import formatdate

    from .integrations.outbound import email_recipients, smtp_send
    body = text(r)
    out = []
    url = get_settings(conn).get("slack_webhook_url", "").strip()
    if url:
        try:
            res = httpx.post(url, json={"text": body}, timeout=10)
            out.append({"channel": "slack", "ok": res.status_code == 200, "detail": f"HTTP {res.status_code}"})
        except httpx.HTTPError as e:
            out.append({"channel": "slack", "ok": False, "detail": str(e)[:200]})
    for dest in conn.execute("SELECT * FROM destinations WHERE enabled = 1 AND type = 'email'").fetchall():
        cfg = json.loads(dest["config_json"])
        msg = EmailMessage()
        msg["Subject"] = f"[Kepler] Report: {r['incidents']} incident{'s' if r['incidents'] != 1 else ''} in {r['days']} days"
        msg["From"], msg["To"], msg["Date"] = cfg["sender"], ", ".join(email_recipients(cfg)), formatdate(localtime=True)
        msg.set_content(body + "\n")
        try:
            smtp_send(cfg, msg)
            out.append({"channel": f"email: {dest['name']}", "ok": True, "detail": msg["To"]})
        except Exception as e:  # noqa: BLE001 - one broken channel must not stop the others
            out.append({"channel": f"email: {dest['name']}", "ok": False, "detail": f"{type(e).__name__}: {str(e)[:200]}"})
    return out
