"""Destinations: put Kepler's decisions back inside the tools teams already look at.

* Grafana        - an annotation on your dashboards (closed with an end time when the incident resolves)
* Datadog Events - an event in the Datadog event stream / on dashboards and monitors
* PagerDuty      - pages on-call through the Events API v2, and resolves the alert when the incident resolves
* Email          - an email per incident over SMTP; the resolution replies in the same thread
* Webhook        - signed JSON for anything else (internal bots, Zapier…)
"""
import hashlib
import hmac
import json
import time

from .base import Field, Integration, check, http_client, register
from .pull import DD_SITES

SEV_RANK = {"medium": 0, "high": 1, "critical": 2}


def _where(d: dict) -> str:
    w = [x for x in d["where"] if x["dimension"] != "*"]
    return ", ".join(f"{x['dimension']}={x['value']}" for x in w) or "all segments"


def headline(d: dict, kind: str) -> str:
    if d.get("kind") == "no_data" and kind != "test":
        since = time.strftime("%H:%M", time.localtime(d["silent_since"] or d["started_at"]))
        return (f"Resolved: {d['metric']} is reporting again" if kind == "resolved"
                else f"NO DATA: {d['metric']} has sent nothing since {since}")
    if kind == "resolved":
        return f"Resolved: {d['metric']} back to normal ({_where(d)})"
    if kind == "test":
        return "Kepler test event: integration is connected"
    arrow = "▲" if d["direction"] == "spike" else "▼"
    return f"{d['severity'].upper()}: {d['metric']} {arrow} {d['change_pct']:+.0f}% · where {_where(d)} · {d['confidence']:.0%} confidence"


def incident_link(d: dict) -> str | None:
    """The incident's page in the dashboard, when KEPLER_PUBLIC_URL says where people reach it."""
    from .. import config
    return f"{config.PUBLIC_URL}/#/incident/{d['incident_id']}" if config.PUBLIC_URL and d.get("incident_id") else None


def body_text(d: dict) -> str:
    link = incident_link(d)
    return (f"Observed {d['observed']:g} vs expected {d['expected']:g} "
            f"(normal range {d['expected_range'][0]:g}–{d['expected_range'][1]:g}), z={d['z_score']:.1f}. "
            f"Where: {_where(d)}. Model: {d['model'].get('baseline', '')}. Kepler incident #{d['incident_id']}."
            + (f" Open in Kepler: {link}" if link else ""))


# ---------------------------------------------------------------- Grafana annotations

def send_grafana(cfg, d, kind, ref=None):
    url = cfg["url"].rstrip("/")
    headers = {"Authorization": f"Bearer {cfg['token']}"}
    tags = ["kepler", d["metric"], d["severity"]] + [t.strip() for t in (cfg.get("tags") or "").split(",") if t.strip()]
    with http_client() as c:
        if kind == "resolved" and ref:
            check(c.patch(f"{url}/api/annotations/{ref}", headers=headers,
                          json={"timeEnd": d["last_seen_at"] * 1000 + 300_000, "tags": tags + ["resolved"]}))
            return ref
        payload = {"time": d["started_at"] * 1000, "tags": tags, "text": f"<b>{headline(d, kind)}</b><br/>{body_text(d)}"}
        if kind == "test":
            payload["text"] = headline(d, kind)
        if cfg.get("dashboard_uid"):
            payload["dashboardUID"] = cfg["dashboard_uid"]
        r = check(c.post(f"{url}/api/annotations", headers=headers, json=payload))
        return str(r.json().get("id", "")) or None


register(Integration(
    "grafana", "Grafana", "observability", "destination",
    "Draws every incident as an annotation on your Grafana dashboards (with an end time once resolved).",
    [Field("url", "Grafana URL", "url", "https://yourteam.grafana.net"),
     Field("token", "Service account token", "password", help="Role: Editor (annotations:write)"),
     Field("dashboard_uid", "Dashboard UID (optional)", required=False, help="Empty = organization-wide annotation"),
     Field("tags", "Extra tags", default="", required=False)],
    send=send_grafana, docs="https://grafana.com/docs/grafana/latest/developers/http_api/annotations/"))


# ---------------------------------------------------------------- Datadog events

def send_datadog_events(cfg, d, kind, ref=None):
    alert = {"resolved": "success", "test": "info"}.get(kind, "error" if d["severity"] == "critical" else "warning")
    payload = {"title": headline(d, kind), "text": body_text(d) if kind != "test" else "Kepler is connected.",
               "alert_type": alert, "aggregation_key": f"kepler-{d['incident_id']}",
               "tags": ["source:kepler", f"metric:{d['metric']}", f"severity:{d['severity']}"]
               + [f"{w['dimension']}:{w['value']}" for w in d["where"] if w["dimension"] != "*"]}
    with http_client() as c:
        r = check(c.post(f"https://api.{cfg.get('site') or 'datadoghq.com'}/api/v1/events",
                         headers={"DD-API-KEY": cfg["api_key"]}, json=payload))
    return str(r.json().get("event", {}).get("id", "")) or ref


register(Integration(
    "datadog_events", "Datadog Events", "observability", "destination",
    "Posts incidents to the Datadog event stream, so they show on dashboards and can trigger monitors.",
    [Field("site", "Datadog site", "select", "datadoghq.com", options=DD_SITES), Field("api_key", "API key", "password")],
    send=send_datadog_events, docs="https://docs.datadoghq.com/api/latest/events/#post-an-event"))


# ---------------------------------------------------------------- PagerDuty

PD_HOSTS = {"US": "https://events.pagerduty.com", "EU": "https://events.eu.pagerduty.com"}
PD_SEVERITY = {"critical": "critical", "high": "error", "medium": "warning"}


def send_pagerduty(cfg, d, kind, ref=None):
    """Events API v2. An incident triggers an alert, deduplicated on the Kepler incident, and resolving it resolves the
    alert. The connection test sends a change event instead: it shows on the service but never pages anyone."""
    host = PD_HOSTS.get(cfg.get("region") or "US", PD_HOSTS["US"])
    key = cfg["routing_key"].strip()
    with http_client() as c:
        if kind == "test":
            check(c.post(f"{host}/v2/change/enqueue", json={"routing_key": key, "payload": {
                "summary": headline(d, kind), "source": "kepler"}}))
            return ref
        dedup = ref or f"kepler-{d['incident_id']}"
        if kind == "resolved":
            check(c.post(f"{host}/v2/enqueue", json={"routing_key": key, "event_action": "resolve", "dedup_key": dedup}))
            return dedup
        details = {k: d[k] for k in ("observed", "expected", "expected_range", "change_pct", "confidence", "z_score")}
        link = incident_link(d)
        r = check(c.post(f"{host}/v2/enqueue", json={
            "routing_key": key, "event_action": "trigger", "dedup_key": dedup,
            **({"links": [{"href": link, "text": "Open in Kepler"}]} if link else {}),
            "payload": {"summary": headline(d, kind)[:1024], "source": "kepler",
                        "severity": PD_SEVERITY.get(d["severity"], "warning"), "component": d["metric"],
                        "group": _where(d), "class": d["direction"],
                        "custom_details": {**details, "where": d["where"], "model": d["model"].get("baseline", ""),
                                           "kepler_incident": d["incident_id"]}}}))
    return r.json().get("dedup_key") or dedup


register(Integration(
    "pagerduty", "PagerDuty", "observability", "destination",
    "Pages your on-call through PagerDuty (Events API v2) and resolves the alert when the incident resolves.",
    [Field("routing_key", "Integration key", "password",
           help="In PagerDuty: Service → Integrations → Add an integration → Events API V2"),
     Field("region", "Service region", "select", "US", options=["US", "EU"])],
    send=send_pagerduty, docs="https://developer.pagerduty.com/docs/events-api-v2/overview/"))


# ---------------------------------------------------------------- Email (SMTP)

def send_email(cfg, d, kind, ref=None):
    """One email when an incident opens; its resolution replies in the same thread (In-Reply-To the opening's
    Message-ID, kept as this destination's ref). STARTTLS (587), SSL (465), or plain for a local relay."""
    from email.message import EmailMessage
    from email.utils import formatdate, make_msgid

    to = email_recipients(cfg)
    if not to:
        raise ValueError("no recipients: set 'to' (comma-separated addresses)")
    msg = EmailMessage()
    msg["Subject"] = f"[Kepler] {headline(d, kind)}"
    msg["From"] = cfg["sender"]
    msg["To"] = ", ".join(to)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = msg_id = make_msgid(domain="kepler.local")
    if ref and kind == "resolved":
        msg["In-Reply-To"] = msg["References"] = ref
    msg.set_content("Kepler is connected: alerts will arrive at this address." if kind == "test"
                    else f"{headline(d, kind)}\n\n{body_text(d)}\n")
    smtp_send(cfg, msg)
    return ref or msg_id


def email_recipients(cfg) -> list[str]:
    return [a.strip() for a in str(cfg.get("to", "")).replace(";", ",").split(",") if a.strip()]


def smtp_send(cfg, msg) -> None:
    """Send one message with an email destination's settings: STARTTLS (587), SSL (465), or plain for a local relay."""
    import smtplib
    import ssl
    security, port = cfg.get("security") or "starttls", int(cfg.get("port") or 587)
    ctx = ssl.create_default_context()
    smtp = smtplib.SMTP_SSL(cfg["host"], port, timeout=10, context=ctx) if security == "ssl" \
        else smtplib.SMTP(cfg["host"], port, timeout=10)
    with smtp as conn:
        if security == "starttls":
            conn.starttls(context=ctx)
        if cfg.get("username"):
            conn.login(cfg["username"], cfg.get("password") or "")
        conn.send_message(msg)


register(Integration(
    "email", "Email", "other", "destination",
    "An email per incident over SMTP (any provider or your own relay); the resolution replies in the same thread.",
    [Field("host", "SMTP server", default="smtp.example.com"),
     Field("port", "Port", "number", "587"),
     Field("security", "Security", "select", "starttls", options=["starttls", "ssl", "none"],
           help="starttls on 587, ssl on 465; none only for a relay on your own network"),
     Field("username", "Username", required=False),
     Field("password", "Password", "password", required=False),
     Field("sender", "From", default="kepler@yourcompany.com"),
     Field("to", "To", default="oncall@yourcompany.com", help="Comma-separated addresses")],
    send=send_email))


# ---------------------------------------------------------------- Generic signed webhook

def sign(secret: str, raw: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def send_webhook(cfg, d, kind, ref=None):
    body = {"event": f"incident.{kind}", "summary": headline(d, kind), "decision": d}
    if incident_link(d):
        body["url"] = incident_link(d)
    raw = json.dumps(body, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "Kepler/0.2"}
    if cfg.get("secret"):
        headers["X-Kepler-Signature"] = sign(cfg["secret"], raw)
    with http_client() as c:
        check(c.post(cfg["url"], content=raw, headers=headers))
    return ref


register(Integration(
    "webhook", "Webhook", "other", "destination",
    "Signed JSON (X-Kepler-Signature: sha256=HMAC) on every incident open/resolve, for bots, PagerDuty bridges or Zapier.",
    [Field("url", "URL", "url", "https://example.com/hooks/kepler"),
     Field("secret", "Signing secret", "password", required=False)],
    send=send_webhook))


# ---------------------------------------------------------------- dispatch

def dispatch(conn, d: dict, kind: str):
    """Send one decision to every enabled destination; remember refs so 'resolved' can update the same object."""
    from .base import REGISTRY
    for dest in conn.execute("SELECT * FROM destinations WHERE enabled = 1").fetchall():
        if kind == "opened" and SEV_RANK.get(d["severity"], 0) < SEV_RANK.get(dest["min_severity"] or "medium", 0):
            continue
        row = conn.execute("SELECT ref FROM destination_refs WHERE incident_id = ? AND destination_id = ?",
                           (d["incident_id"], dest["id"])).fetchone()
        if kind == "resolved" and row is None:
            continue  # never announced the opening here, so don't announce the resolution either
        try:
            ref = REGISTRY[dest["type"]].send(json.loads(dest["config_json"]), d, kind, row["ref"] if row else None)
            conn.execute("INSERT OR REPLACE INTO destination_refs(incident_id, destination_id, ref) VALUES (?,?,?)",
                         (d["incident_id"], dest["id"], ref))
            status = f"ok: {kind} #{d['incident_id']}"
        except Exception as e:  # one broken destination must not block the others
            status = f"error: {type(e).__name__}: {str(e)[:200]}"
        conn.execute("UPDATE destinations SET last_status = ? WHERE id = ?", (status, dest["id"]))
