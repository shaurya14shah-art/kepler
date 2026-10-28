"""Slack alerts via incoming webhook. Every alert is also kept in the notifications log."""
import json
import time

import httpx

from .db import get_settings
from .engine.detector import decision, related_incidents
from .integrations.outbound import incident_link

SEV_EMOJI = {"critical": "🔴", "high": "🟠", "medium": "🟡"}


def _fmt(x: float) -> str:
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:,.2f}".rstrip("0").rstrip(".")


def build_message(d: dict, kind: str, metric_unit: str = "") -> tuple[str, list]:
    if d.get("kind") == "no_data":  # the metric stopped reporting: no change to show, just since when
        since = time.strftime("%H:%M", time.localtime(d["silent_since"] or d["started_at"]))
        text = (f"✅ Resolved: {d['metric']} is reporting again" if kind == "resolved"
                else f"📭 NO DATA: {d['metric']} has sent nothing since {since} (Kepler incident #{d['incident_id']})")
        link = incident_link(d)
        return text, [{"type": "section", "text": {"type": "mrkdwn", "text": text + (f" · <{link}|Open in Kepler>" if link else "")}}]
    where = [w for w in d["where"] if w["dimension"] != "*"]
    where_txt = " · ".join(f"*{w['dimension']}={w['value']}*" for w in where) or "all segments"
    arrow = "▲" if d["direction"] == "spike" else "▼"
    if kind == "resolved":
        text = f"✅ Resolved: {d['metric']} back to normal ({where_txt})"
        return text, [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]
    text = (f"{SEV_EMOJI.get(d['severity'], '⚪')} {d['severity'].upper()}: {d['metric']} {arrow} "
            f"{d['change_pct']:+.0f}% · where: {where_txt}")
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"{SEV_EMOJI.get(d['severity'], '')} {d['metric']} {d['direction']}"}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*Observed*\n{_fmt(d['observed'])} {metric_unit}"},
            {"type": "mrkdwn", "text": f"*Expected*\n{_fmt(d['expected'])} ({_fmt(d['expected_range'][0])}–{_fmt(d['expected_range'][1])})"},
            {"type": "mrkdwn", "text": f"*Change*\n{arrow} {d['change_pct']:+.0f}%"},
            {"type": "mrkdwn", "text": f"*Confidence*\n{d['confidence']:.0%} · {d['severity']}"},
        ]},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Where:* {where_txt}"}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": f"Kepler incident #{d['incident_id']} · {d['model'].get('baseline', '')}"
                                          + (f" · <{incident_link(d)}|Open in Kepler>" if incident_link(d) else "")}]},
    ]
    return text, blocks


def notify(conn, incident_id: int, kind: str):
    inc = conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
    metric = conn.execute("SELECT * FROM metrics WHERE id = ?", (inc["metric_id"],)).fetchone()
    # muted (this metric, or the whole workspace in maintenance mode): recorded as usual, but nothing goes out
    muted = max(metric["muted_until"] or 0, int(float(get_settings(conn).get("muted_until") or 0)))
    if muted > time.time():
        until = time.strftime("%a %d %b %H:%M", time.localtime(muted))
        conn.execute("INSERT INTO notifications(incident_id, channel, kind, text, delivered, error, created_at) "
                     "VALUES (?,?,?,?,?,?,?)", (incident_id, "all", kind, "", 0, f"muted until {until}", int(time.time())))
        return
    if kind == "resolved" and conn.execute(
            "SELECT 1 FROM notifications WHERE incident_id = ? AND kind = 'opened' AND error LIKE 'muted until%'",
            (incident_id,)).fetchone():
        return  # it opened while muted: nobody was told, so there's nothing to resolve for anyone
    d = decision(inc, metric)
    text, blocks = build_message(d, kind, metric["unit"])
    if kind == "opened":
        from .cli.render import change_text
        related = related_incidents(conn, inc)
        if related:  # likely one problem: say so in the first message
            also = ", ".join(f"{r['metric']} {change_text(r)}" for r in related[:4])
            text += f"\nAlso now: {also}"
            blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"*Also now:* {also}"}]})
    from .integrations.outbound import dispatch
    dispatch(conn, d, kind)  # Grafana / Datadog / webhooks
    url = get_settings(conn).get("slack_webhook_url", "").strip()
    delivered, error = 0, None
    if url:
        try:
            r = httpx.post(url, json={"text": text, "blocks": blocks}, timeout=5)
            delivered = int(r.status_code == 200)
            error = None if delivered else f"HTTP {r.status_code}: {r.text[:200]}"
        except httpx.HTTPError as e:
            error = str(e)[:200]
    else:
        error = "no Slack webhook configured (logged only)"
    conn.execute(
        "INSERT INTO notifications(incident_id, channel, kind, text, delivered, error, created_at) VALUES (?,?,?,?,?,?,?)",
        (incident_id, "slack", kind, json.dumps({"text": text, "blocks": blocks}), delivered, error, int(time.time())),
    )


def send_test(url: str) -> tuple[bool, str]:
    try:
        r = httpx.post(url, json={"text": "👋 Kepler is connected. Anomaly alerts will appear here."}, timeout=5)
        return r.status_code == 200, f"HTTP {r.status_code}"
    except httpx.HTTPError as e:
        return False, str(e)[:200]
