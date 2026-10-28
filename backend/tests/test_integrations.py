"""Each integration against a mocked copy of the vendor API (request shape is asserted, response shape is the vendor's)."""
import base64
import json
import os
import tempfile
from datetime import datetime, timezone

import httpx
import pytest

os.environ.setdefault("KEPLER_DB", os.path.join(tempfile.mkdtemp(), "integ.db"))

from kepler import db  # noqa: E402
from kepler.db import parse_segment as segdims  # noqa: E402
from kepler.integrations import REGISTRY, base  # noqa: E402
from kepler.integrations.inbound import parse_otlp, parse_segment  # noqa: E402
from kepler.integrations.outbound import dispatch, sign  # noqa: E402

T0 = 1792411200  # a bucket-aligned timestamp (2026-10-19 12:00 UTC)
T1 = T0 + 3600


class Mock:
    """Install an httpx MockTransport; `handler(request) -> (status, json)`; records requests."""

    def __init__(self, handler):
        self.requests: list[httpx.Request] = []

        def h(req):
            self.requests.append(req)
            status, body = handler(req)
            return httpx.Response(status, json=body)

        base._transport = httpx.MockTransport(h)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        base._transport = None


def by_seg(points):
    out = {}
    for ts, seg, v, n in points:
        out.setdefault(seg, []).append((ts, v, n))
    return out


# ---------------------------------------------------------------- pull

def test_prometheus():
    body = {"status": "success", "data": {"resultType": "matrix", "result": [
        {"metric": {"service": "api", "pod": "x"}, "values": [[T0, "3"], [T0 + 300, "5"], [T0 + 600, "NaN"]]}]}}
    with Mock(lambda r: (200, body)) as m:
        pts = REGISTRY["prometheus"].fetch({"url": "http://prom:9090", "query": "up", "labels": "service", "metric": "m"}, T0, T1)
    q = m.requests[0].url.params
    assert m.requests[0].url.path == "/api/v1/query_range" and q["step"] == "300" and q["start"] == str(T0)
    # increase(...[5m]) at T covers (T-5m, T], so it is filed under the bucket starting at T-5m
    assert pts == [(T0 - 300, "service=api", 3.0, 1.0), (T0, "service=api", 5.0, 1.0)]
    with Mock(lambda r: (200, body)):  # plain gauges: no shift
        raw = REGISTRY["prometheus"].fetch({"url": "http://prom:9090", "query": "up", "labels": "service", "metric": "m",
                                            "window_end": "false"}, T0, T1)
    assert raw[0][0] == T0


def test_datadog():
    body = {"status": "ok", "series": [
        {"metric": "errors", "scope": "env:prod,service:web", "tag_set": ["service:web"],
         "pointlist": [[T0 * 1000.0, 4.0], [(T0 + 300) * 1000.0, None], [(T0 + 600) * 1000.0, 9.0]]}]}
    with Mock(lambda r: (200, body)) as m:
        pts = REGISTRY["datadog"].fetch({"site": "datadoghq.eu", "api_key": "a", "app_key": "b", "query": "q", "metric": "m"}, T0, T1)
    req = m.requests[0]
    assert req.url.host == "api.datadoghq.eu" and req.headers["DD-API-KEY"] == "a" and req.headers["DD-APPLICATION-KEY"] == "b"
    assert pts == [(T0, "service=web", 4.0, 1.0), (T0 + 600, "service=web", 9.0, 1.0)]


def test_newrelic_timeseries_facet():
    results = [{"beginTimeSeconds": T0, "endTimeSeconds": T0 + 300, "facet": "checkout", "appName": "checkout", "count": 7},
               {"beginTimeSeconds": T0 + 300, "endTimeSeconds": T0 + 600, "facet": ["billing", "EU"], "count": 2}]
    with Mock(lambda r: (200, {"data": {"actor": {"account": {"nrql": {"results": results}}}}})) as m:
        pts = REGISTRY["newrelic"].fetch({"account_id": "123", "api_key": "NRAK", "nrql": "SELECT …", "facet_names": "app,region",
                                          "metric": "m"}, T0, T1)
    req = m.requests[0]
    sent = json.loads(req.content)
    assert req.url.host == "api.newrelic.com" and req.headers["API-Key"] == "NRAK"
    assert sent["variables"] == {"id": 123, "nrql": "SELECT …"}
    assert by_seg(pts) == {"app=checkout": [(T0, 7.0, 1.0)], "app=billing|region=EU": [(T0 + 300, 2.0, 1.0)]}


def test_newrelic_graphql_error():
    with Mock(lambda r: (200, {"errors": [{"message": "NRQL Syntax Error"}]})):
        with pytest.raises(ValueError, match="NRQL Syntax Error"):
            REGISTRY["newrelic"].fetch({"account_id": "1", "api_key": "k", "nrql": "x", "metric": "m"}, T0, T1)


def test_posthog_hogql():
    body = {"columns": ["ts", "os", "value"], "results": [
        ["2026-10-19T12:00:00Z", "iOS", 4], ["2026-10-19T12:00:00Z", "Android", 1], ["2026-10-19T12:05:00Z", "iOS", 6]]}
    with Mock(lambda r: (200, body)) as m:
        pts = REGISTRY["posthog"].fetch({"host": "https://eu.posthog.com", "project_id": "42", "api_key": "phx", "query": "SELECT 1",
                                         "metric": "m"}, T0, T1)
    req = m.requests[0]
    assert str(req.url) == "https://eu.posthog.com/api/projects/42/query/"
    assert req.headers["Authorization"] == "Bearer phx" and json.loads(req.content)["query"]["kind"] == "HogQLQuery"
    assert by_seg(pts) == {"os=iOS": [(T0, 4.0, 1.0), (T0 + 300, 6.0, 1.0)], "os=Android": [(T0, 1.0, 1.0)]}


def test_mixpanel_minutes_roll_up_into_5min_buckets():
    body = {"data": {"series": ["2026-10-19 12:00:00", "2026-10-19 12:01:00", "2026-10-19 12:06:00"],
                     "values": {"iOS": {"2026-10-19 12:00:00": 2, "2026-10-19 12:01:00": 3, "2026-10-19 12:06:00": 1}}}}
    with Mock(lambda r: (200, body)) as m:
        pts = REGISTRY["mixpanel"].fetch({"region": "EU", "project_id": "9", "username": "u", "secret": "s", "event": "Sign Up",
                                          "on": 'properties["$os"]', "dimension": "os", "metric": "m"}, T0, T1)
    req = m.requests[0]
    assert req.url.host == "eu.mixpanel.com" and req.url.params["unit"] == "minute"
    assert req.headers["Authorization"] == "Basic " + base64.b64encode(b"u:s").decode()
    assert pts == [(T0, "os=iOS", 5.0, 2.0), (T0 + 300, "os=iOS", 1.0, 1.0)]


def test_amplitude_realtime_grouped():
    body = {"data": {"series": [[3, 4], [1, 0]], "seriesLabels": [[0, "iOS"], [0, "Android"]],
                     "xValues": ["2026-10-19T12:00:00", "2026-10-19T12:05:00"]}}
    with Mock(lambda r: (200, body)) as m:
        pts = REGISTRY["amplitude"].fetch({"api_key": "k", "secret_key": "s", "event": "Sign Up", "group_by": "platform",
                                           "dimension": "platform", "metric": "m"}, T0, T1)
    q = m.requests[0].url.params
    assert q["i"] == "-300000" and json.loads(q["e"]) == {"event_type": "Sign Up"} and q["g"] == "platform"
    assert by_seg(pts)["platform=iOS"] == [(T0, 3.0, 1.0), (T0 + 300, 4.0, 1.0)]


def test_sentry_ungrouped_and_grouped():
    flat = {"data": [[T0, [{"count": 2}]], [T0 + 300, [{"count": 0}]]]}
    with Mock(lambda r: (200, flat)) as m:
        pts = REGISTRY["sentry"].fetch({"org": "acme", "token": "t", "metric": "m"}, T0, T1)
    assert m.requests[0].url.path == "/api/0/organizations/acme/events-stats/"
    assert pts == [(T0, "", 2.0, 1.0), (T0 + 300, "", 0.0, 1.0)]
    grouped = {"1.4.0": {"data": [[T0, [{"count": 9}]]], "order": 0}, "Other": {"data": [[T0, [{"count": 1}]]], "order": 1}}
    with Mock(lambda r: (200, grouped)) as m:
        pts = REGISTRY["sentry"].fetch({"org": "acme", "token": "t", "group_by": "release", "metric": "m"}, T0, T1)
    assert m.requests[0].url.params.get_list("field") == ["release", "count()"]
    assert pts == [(T0, "release=1.4.0", 9.0, 1.0)]


def test_cloudwatch_with_stubber():
    import boto3
    from botocore.stub import Stubber
    cw = boto3.client("cloudwatch", region_name="us-east-1", aws_access_key_id="x", aws_secret_access_key="y")
    stub = Stubber(cw)
    when = [datetime.fromtimestamp(T0, tz=timezone.utc), datetime.fromtimestamp(T0 + 300, tz=timezone.utc)]
    stub.add_response("get_metric_data", {"MetricDataResults": [
        {"Id": "k", "Label": "prod-alb", "Timestamps": when, "Values": [12.0, 3.0], "StatusCode": "Complete"}]})
    with stub:
        pts = REGISTRY["cloudwatch"].fetch({"expression": "SEARCH('x', 'Sum', 300)", "label_dimension": "lb", "metric": "m"},
                                           T0, T1, client=cw)
    assert pts == [(T0, "lb=prod-alb", 12.0, 1.0), (T0 + 300, "lb=prod-alb", 3.0, 1.0)]


def test_http_errors_surface():
    with Mock(lambda r: (403, {"errors": ["Forbidden"]})):
        with pytest.raises(ValueError, match="HTTP 403"):
            REGISTRY["datadog"].fetch({"api_key": "a", "app_key": "b", "query": "q", "metric": "m"}, T0, T1)


# ---------------------------------------------------------------- push

def test_segment_batch():
    body = {"batch": [
        {"type": "track", "event": "Signed Up", "properties": {"plan": "pro"}, "context": {"os": {"name": "iOS"}},
         "timestamp": "2026-10-19T12:01:00Z"},
        {"type": "identify", "userId": "u1"},
        {"type": "page", "properties": {}, "timestamp": "2026-10-19T12:02:00Z"}]}
    out = parse_segment(body, ["plan", "context.os.name"])
    assert set(out) == {"signed_up", "page_views"}
    ts, seg, v, n = out["signed_up"][0]
    assert ts == T0 + 60 and segdims(seg) == {"plan": "pro", "name": "iOS"} and v == 1.0


def _otlp(value, temporality=2, start="1"):
    return {"resourceMetrics": [{"resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "api"}}]},
        "scopeMetrics": [{"metrics": [
            {"name": "http.server.errors", "sum": {"aggregationTemporality": temporality, "isMonotonic": True,
             "dataPoints": [{"attributes": [{"key": "route", "value": {"stringValue": "/login"}}],
                             "startTimeUnixNano": start, "timeUnixNano": str(T0 * 10**9), "asInt": str(value)}]}},
            {"name": "queue.depth", "gauge": {"dataPoints": [{"timeUnixNano": str(T0 * 10**9), "asDouble": 4.5}]}},
        ]}]}]}


def test_otlp_cumulative_sums_are_differenced():
    db.init_db()
    with db.session(write=True) as c:
        first = parse_otlp(_otlp(100), c)
        second = parse_otlp(_otlp(130), c)
        restarted = parse_otlp(_otlp(5, start="2"), c)
    assert ("http_server_errors", "sum") not in first  # baseline only
    assert second[("http_server_errors", "sum")][0][2] == 30.0
    assert restarted[("http_server_errors", "sum")][0][2] == 5.0
    assert segdims(second[("http_server_errors", "sum")][0][1]) == {"service": "api", "route": "/login"}
    assert second[("queue_depth", "mean")][0][2] == 4.5


# ---------------------------------------------------------------- destinations

DECISION = {"decision": "anomaly", "incident_id": 7, "metric": "api_errors", "slice": None, "status": "open",
            "direction": "spike", "severity": "critical", "confidence": 0.97, "observed": 412.0, "expected": 41.0,
            "expected_range": [22.0, 60.0], "change_pct": 904.9, "z_score": 14.2,
            "where": [{"dimension": "platform", "value": "ios", "share_of_change": 0.96, "change_pct": 1176.0}],
            "started_at": T0, "last_seen_at": T0 + 900, "model": {"baseline": "Custom weekly profile"}}


def test_grafana_annotation_open_then_resolve():
    def h(req):
        return (200, {"id": 55, "message": "Annotation added"}) if req.method == "POST" else (200, {"message": "updated"})
    with Mock(h) as m:
        ref = REGISTRY["grafana"].send({"url": "https://g.example", "token": "glsa", "dashboard_uid": "abc"}, DECISION, "opened")
        REGISTRY["grafana"].send({"url": "https://g.example", "token": "glsa"}, DECISION, "resolved", ref)
    post, patch = m.requests
    body = json.loads(post.content)
    assert ref == "55" and post.url.path == "/api/annotations" and body["time"] == T0 * 1000 and body["dashboardUID"] == "abc"
    assert "platform=ios" in body["text"] and "kepler" in body["tags"]
    assert patch.method == "PATCH" and patch.url.path == "/api/annotations/55" and json.loads(patch.content)["timeEnd"] > T0 * 1000


def test_datadog_event():
    with Mock(lambda r: (202, {"status": "ok", "event": {"id": 99}})) as m:
        REGISTRY["datadog_events"].send({"api_key": "k"}, DECISION, "opened")
    body = json.loads(m.requests[0].content)
    assert body["alert_type"] == "error" and body["aggregation_key"] == "kepler-7" and "platform:ios" in body["tags"]


def test_webhook_is_signed():
    with Mock(lambda r: (200, {})) as m:
        REGISTRY["webhook"].send({"url": "https://hooks.example/x", "secret": "s3"}, DECISION, "opened")
    req = m.requests[0]
    assert req.headers["X-Kepler-Signature"] == sign("s3", req.content)
    assert json.loads(req.content)["event"] == "incident.opened"


def test_pagerduty_triggers_then_resolves_the_same_alert():
    with Mock(lambda r: (202, {"status": "success", "dedup_key": "kepler-7"})) as m:
        ref = REGISTRY["pagerduty"].send({"routing_key": "R0UT1NG", "region": "EU"}, DECISION, "opened")
        REGISTRY["pagerduty"].send({"routing_key": "R0UT1NG", "region": "EU"}, DECISION, "resolved", ref)
    trigger, resolve = (json.loads(r.content) for r in m.requests)
    assert m.requests[0].url.host == "events.eu.pagerduty.com" and m.requests[0].url.path == "/v2/enqueue"
    assert trigger["event_action"] == "trigger" and trigger["dedup_key"] == ref == "kepler-7"
    assert trigger["payload"]["severity"] == "critical" and trigger["payload"]["component"] == "api_errors"
    assert trigger["payload"]["group"] == "platform=ios" and "platform=ios" in trigger["payload"]["summary"]
    assert resolve == {"routing_key": "R0UT1NG", "event_action": "resolve", "dedup_key": "kepler-7"}


def test_pagerduty_connection_test_never_pages():
    with Mock(lambda r: (202, {"status": "success"})) as m:
        REGISTRY["pagerduty"].send({"routing_key": "R0UT1NG"}, DECISION, "test")
    assert m.requests[0].url.host == "events.pagerduty.com" and m.requests[0].url.path == "/v2/change/enqueue"
    assert "event_action" not in json.loads(m.requests[0].content)


class FakeSMTP:
    sent, log = [], []

    def __init__(self, host, port, timeout=None, context=None):
        FakeSMTP.log.append(("connect", type(self).__name__, host, port))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        FakeSMTP.log.append(("starttls",))

    def login(self, user, password):
        FakeSMTP.log.append(("login", user))

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


class FakeSMTPSSL(FakeSMTP):
    pass


def test_email_opens_then_replies_in_the_same_thread(monkeypatch):
    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTPSSL)
    FakeSMTP.sent.clear(); FakeSMTP.log.clear()
    cfg = {"host": "smtp.example.com", "port": "587", "security": "starttls", "username": "kepler", "password": "pw",
           "sender": "kepler@acme.test", "to": "oncall@acme.test; cto@acme.test"}
    ref = REGISTRY["email"].send(cfg, DECISION, "opened")
    REGISTRY["email"].send(cfg, DECISION, "resolved", ref)
    opened, resolved = FakeSMTP.sent
    assert FakeSMTP.log[:3] == [("connect", "FakeSMTP", "smtp.example.com", 587), ("starttls",), ("login", "kepler")]
    assert opened["To"] == "oncall@acme.test, cto@acme.test" and "CRITICAL: api_errors" in opened["Subject"]
    assert "platform=ios" in opened.get_content() and opened["Message-ID"] == ref
    assert resolved["In-Reply-To"] == ref and resolved["Subject"].startswith("[Kepler] Resolved")


def test_email_over_ssl_and_without_recipients(monkeypatch):
    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTPSSL)
    FakeSMTP.sent.clear(); FakeSMTP.log.clear()
    REGISTRY["email"].send({"host": "smtp.example.com", "port": "465", "security": "ssl", "sender": "k@acme.test",
                            "to": "a@acme.test"}, DECISION, "test")
    assert FakeSMTP.log == [("connect", "FakeSMTPSSL", "smtp.example.com", 465)]  # no starttls, no login
    assert "connected" in FakeSMTP.sent[0].get_content()
    with pytest.raises(ValueError):
        REGISTRY["email"].send({"host": "h", "sender": "k@acme.test", "to": " , "}, DECISION, "opened")


def test_dispatch_respects_severity_and_resolves_only_announced():
    db.init_db()
    with db.session(write=True) as c:
        c.execute("DELETE FROM destinations")
        c.execute("INSERT INTO destinations(type, name, config_json, min_severity) VALUES ('webhook','w',?, 'critical')",
                  (json.dumps({"url": "https://hooks.example/x"}),))
        with Mock(lambda r: (200, {})) as m:
            dispatch(c, {**DECISION, "incident_id": 8, "severity": "high"}, "opened")     # below threshold
            dispatch(c, {**DECISION, "incident_id": 8, "severity": "high"}, "resolved")   # never announced
            dispatch(c, DECISION, "opened")
            dispatch(c, DECISION, "resolved")
        assert [json.loads(r.content)["event"] for r in m.requests] == ["incident.opened", "incident.resolved"]
        with Mock(lambda r: (500, {"err": "boom"})):
            dispatch(c, {**DECISION, "incident_id": 9}, "opened")
        assert c.execute("SELECT last_status FROM destinations").fetchone()[0].startswith("error")


def test_alerts_link_to_the_incident_when_the_dashboard_url_is_set(monkeypatch):
    from kepler import config
    from kepler.integrations.outbound import body_text
    from kepler.notify import build_message
    link = "https://kepler.acme.test/#/incident/7"
    monkeypatch.setattr(config, "PUBLIC_URL", "")
    assert "Open in Kepler" not in body_text(DECISION) and "Open in Kepler" not in json.dumps(build_message(DECISION, "opened"))
    monkeypatch.setattr(config, "PUBLIC_URL", "https://kepler.acme.test")
    assert body_text(DECISION).endswith(f"Open in Kepler: {link}")                       # email, Grafana, Datadog
    assert f"<{link}|Open in Kepler>" in json.dumps(build_message(DECISION, "opened")[1])  # Slack
    with Mock(lambda r: (202, {"status": "success", "dedup_key": "kepler-7"})) as m:
        REGISTRY["pagerduty"].send({"routing_key": "R"}, DECISION, "opened")
        REGISTRY["webhook"].send({"url": "https://hooks.example/x"}, DECISION, "opened")
    pd, hook = (json.loads(r.content) for r in m.requests)
    assert pd["links"] == [{"href": link, "text": "Open in Kepler"}] and hook["url"] == link
