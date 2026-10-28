"""Pull integrations: Kepler polls the tool's API on a schedule and turns results into 5-minute points.

Each fetch(cfg, start, end) returns [(bucket_ts, segment, value_sum, n)] for the window.
"""
import json
from datetime import datetime, timezone

import pandas as pd

from .base import (Field, Integration, bucketize, check, http_client, records_to_points, register, segment_key, span,
                   to_epoch)

METRIC = Field("metric", "Metric name in Kepler", help="How this series is named in Kepler")


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _labels(cfg) -> list[str]:
    return [l.strip() for l in (cfg.get("labels") or "").split(",") if l.strip()]


# ---------------------------------------------------------------- Prometheus (and Grafana Mimir / Cortex / Thanos / VictoriaMetrics)

def fetch_prometheus(cfg, start, end):
    start, end = span(start, end)
    headers = {"Authorization": f"Bearer {cfg['token']}"} if cfg.get("token") else {}
    with http_client() as c:
        r = check(c.get(cfg["url"].rstrip("/") + "/api/v1/query_range", headers=headers,
                        params={"query": cfg["query"], "start": start, "end": end, "step": 300}))
    body = r.json()
    if body.get("status") != "success":
        raise ValueError(body.get("error", "Prometheus query failed"))
    keep, out = _labels(cfg), []
    # increase()/rate() over [5m] evaluated at T describes the window (T-5m, T]: file it under the bucket starting at T-5m
    shift = 300 if str(cfg.get("window_end", "true")).lower() not in ("false", "0", "no") else 0
    for series in body["data"]["result"]:
        seg = segment_key({k: v for k, v in series["metric"].items() if k in keep})
        for ts, val in series.get("values", []):
            if val not in ("NaN", "+Inf", "-Inf"):
                out.append((int(float(ts)) - shift, seg, float(val), 1.0))
    return bucketize(out)


register(Integration(
    "prometheus", "Prometheus", "observability", "pull",
    "PromQL range queries. Also works with Grafana Mimir, Cortex, Thanos and VictoriaMetrics.",
    [Field("url", "Prometheus URL", "url", "http://prometheus:9090"),
     Field("query", "PromQL query", "textarea", 'sum by (service) (increase(http_requests_total{status=~"5.."}[5m]))',
           help="Wrap counters in increase(...[5m]) so each point is a 5-minute count"),
     Field("labels", "Labels to keep as dimensions", default="service", required=False),
     Field("token", "Bearer token", "password", required=False),
     Field("backfill_days", "Import history on first pull (days)", "number", "14", required=False,
           help="So Kepler can learn a baseline right away (max ~38 days at 5-minute steps)"), METRIC],
    fetch=fetch_prometheus, default_bad="up",
    docs="https://prometheus.io/docs/prometheus/latest/querying/api/#range-queries"))


# ---------------------------------------------------------------- Postgres (and any warehouse that speaks the PG protocol)

def fetch_postgres(cfg, start, end):
    import psycopg
    with psycopg.connect(cfg["dsn"], connect_timeout=8) as pg:
        pg.read_only = True
        with pg.cursor() as cur:
            cur.execute("SET statement_timeout = 15000")
            cur.execute(cfg["query"])
            cols = [d.name.lower() for d in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchmany(50000)]
    return records_to_points(rows)


register(Integration(
    "postgres", "Postgres", "database", "pull",
    "Run a read-only SQL query on a schedule. Works with Postgres, Supabase, Neon, Redshift and TimescaleDB.",
    [Field("dsn", "Connection string", "password", "postgresql://readonly:password@db.internal:5432/app"),
     Field("query", "SQL query", "textarea",
           "SELECT date_bin('5 minutes', created_at, '2000-01-01') AS ts, platform, count(*) AS value\n"
           "FROM users WHERE created_at > now() - interval '3 hours'\nGROUP BY 1, 2",
           help="Return columns ts, value and optional dimension columns"), METRIC],
    fetch=fetch_postgres, default_bad="down"))


# ---------------------------------------------------------------- Datadog

DD_SITES = ["datadoghq.com", "us3.datadoghq.com", "us5.datadoghq.com", "datadoghq.eu", "ap1.datadoghq.com", "ddog-gov.com"]


def _dd_tags(series) -> dict:
    tags = series.get("tag_set") or [t for t in (series.get("scope") or "").split(",") if ":" in t]
    return dict(t.split(":", 1) for t in tags if ":" in t)


def fetch_datadog(cfg, start, end):
    start, end = span(start, end)
    headers = {"DD-API-KEY": cfg["api_key"], "DD-APPLICATION-KEY": cfg["app_key"]}
    with http_client() as c:
        r = check(c.get(f"https://api.{cfg.get('site') or 'datadoghq.com'}/api/v1/query", headers=headers,
                        params={"from": start, "to": end, "query": cfg["query"]}))
    body = r.json()
    if body.get("status") == "error":
        raise ValueError(body.get("error", "Datadog query failed"))
    out = []
    for s in body.get("series", []):
        seg = segment_key(_dd_tags(s))
        for ts_ms, val in s.get("pointlist", []):
            if val is not None:
                out.append((int(ts_ms / 1000), seg, float(val), 1.0))
    return bucketize(out)


register(Integration(
    "datadog", "Datadog", "observability", "pull",
    "Any Datadog metric query. Tags in 'by {…}' become dimensions.",
    [Field("site", "Datadog site", "select", "datadoghq.com", options=DD_SITES),
     Field("api_key", "API key", "password"), Field("app_key", "Application key", "password"),
     Field("query", "Metric query", "textarea", "sum:trace.http.request.errors{env:prod} by {service}.as_count().rollup(sum, 300)",
           help="Use .rollup(sum, 300) for counts or .rollup(avg, 300) for gauges"), METRIC],
    fetch=fetch_datadog, default_bad="up",
    docs="https://docs.datadoghq.com/api/latest/metrics/#query-timeseries-points"))


# ---------------------------------------------------------------- New Relic (NerdGraph + NRQL)

NR_GQL = "query($id: Int!, $nrql: Nrql!) { actor { account(id: $id) { nrql(query: $nrql) { results } } } }"
NR_SKIP = {"beginTimeSeconds", "endTimeSeconds", "facet", "timestamp"}


def fetch_newrelic(cfg, start, end):
    host = "api.eu.newrelic.com" if cfg.get("region") == "EU" else "api.newrelic.com"
    with http_client() as c:
        r = check(c.post(f"https://{host}/graphql", headers={"API-Key": cfg["api_key"]},
                         json={"query": NR_GQL, "variables": {"id": int(cfg["account_id"]), "nrql": cfg["nrql"]}}))
    body = r.json()
    if body.get("errors"):
        raise ValueError("; ".join(e.get("message", "") for e in body["errors"])[:300])
    results = body["data"]["actor"]["account"]["nrql"]["results"] or []
    facet_names = [f.strip() for f in (cfg.get("facet_names") or "facet").split(",")]
    out = []
    for row in results:
        if "beginTimeSeconds" not in row:
            continue
        key = cfg.get("value_field") or next((k for k, v in row.items() if k not in NR_SKIP and isinstance(v, (int, float))), None)
        val = row.get(key)
        if isinstance(val, dict):  # e.g. percentile(...) -> {"95": 123}
            val = next(iter(val.values()), None)
        if val is None:
            continue
        facet = row.get("facet")
        values = facet if isinstance(facet, list) else ([facet] if facet is not None else [])
        dims = {n: str(v) for n, v in zip(facet_names, values)}
        out.append((int(row["beginTimeSeconds"]), segment_key(dims), float(val), 1.0))
    return bucketize(out)


register(Integration(
    "newrelic", "New Relic", "observability", "pull",
    "Any NRQL query with TIMESERIES 5 minutes. FACET values become dimensions.",
    [Field("region", "Region", "select", "US", options=["US", "EU"]),
     Field("account_id", "Account ID", "number"), Field("api_key", "User API key", "password"),
     Field("nrql", "NRQL", "textarea", "SELECT count(*) FROM TransactionError FACET appName SINCE 3 hours ago TIMESERIES 5 minutes"),
     Field("facet_names", "Dimension name(s) for FACET", default="app", required=False), METRIC],
    fetch=fetch_newrelic, default_bad="up",
    docs="https://docs.newrelic.com/docs/apis/nerdgraph/examples/nerdgraph-nrql-tutorial/"))


# ---------------------------------------------------------------- PostHog (HogQL)

def fetch_posthog(cfg, start, end):
    host = (cfg.get("host") or "https://us.posthog.com").rstrip("/")
    with http_client() as c:
        r = check(c.post(f"{host}/api/projects/{cfg['project_id']}/query/",
                         headers={"Authorization": f"Bearer {cfg['api_key']}"},
                         json={"query": {"kind": "HogQLQuery", "query": cfg["query"]}}))
    body = r.json()
    cols = [str(c).lower() for c in body.get("columns", [])]
    return records_to_points([dict(zip(cols, row)) for row in body.get("results", [])])


register(Integration(
    "posthog", "PostHog", "product analytics", "pull",
    "A HogQL query over your events, e.g. sign-ups per 5 minutes by OS.",
    [Field("host", "PostHog host", "url", "https://us.posthog.com", help="https://eu.posthog.com for EU cloud, or your self-hosted URL"),
     Field("project_id", "Project ID"), Field("api_key", "Personal API key", "password", help="Needs the query:read scope"),
     Field("query", "HogQL query", "textarea",
           "SELECT toStartOfFiveMinute(timestamp) AS ts, properties.$os AS os, count() AS value\n"
           "FROM events WHERE event = 'user signed up' AND timestamp > now() - INTERVAL 3 HOUR\nGROUP BY ts, os"),
     METRIC],
    fetch=fetch_posthog, default_bad="down",
    docs="https://posthog.com/docs/api/queries"))


# ---------------------------------------------------------------- Mixpanel (Segmentation API)

MP_HOSTS = {"US": "mixpanel.com", "EU": "eu.mixpanel.com", "IN": "in.mixpanel.com"}


def fetch_mixpanel(cfg, start, end):
    host = MP_HOSTS.get(cfg.get("region") or "US", "mixpanel.com")
    params = {"project_id": cfg["project_id"], "event": cfg["event"], "unit": "minute", "type": "general",
              "from_date": datetime.fromtimestamp(start, tz=timezone.utc).strftime("%Y-%m-%d"),
              "to_date": datetime.fromtimestamp(end, tz=timezone.utc).strftime("%Y-%m-%d")}
    if cfg.get("on"):
        params["on"] = cfg["on"]
    with http_client() as c:
        r = check(c.get(f"https://{host}/api/query/segmentation", params=params,
                        auth=(cfg["username"], cfg["secret"])))
    values = r.json().get("data", {}).get("values", {})
    dim = cfg.get("dimension") or "segment"
    tz = cfg.get("timezone") or "UTC"
    out = []
    for seg_value, series in values.items():
        seg = segment_key({dim: seg_value}) if cfg.get("on") else ""
        for when, count in series.items():
            ts = pd.Timestamp(when)
            ts = ts.tz_localize(tz) if ts.tzinfo is None else ts
            t = int(ts.timestamp())
            if start <= t <= end and count is not None:
                out.append((t, seg, float(count), 1.0))
    return bucketize(out)


register(Integration(
    "mixpanel", "Mixpanel", "product analytics", "pull",
    "Per-minute event counts from the Segmentation API, optionally split by a property.",
    [Field("region", "Data residency", "select", "US", options=list(MP_HOSTS)),
     Field("project_id", "Project ID"), Field("username", "Service account username"),
     Field("secret", "Service account secret", "password"),
     Field("event", "Event name", default="Sign Up"),
     Field("on", "Split by (optional)", default='properties["$os"]', required=False),
     Field("dimension", "Dimension name for the split", default="os", required=False),
     Field("timezone", "Project timezone", default="UTC", required=False,
           help="Mixpanel returns times in the project's timezone, e.g. America/Los_Angeles"),
     METRIC],
    fetch=fetch_mixpanel, default_bad="down",
    docs="https://developer.mixpanel.com/reference/segmentation-query"))


# ---------------------------------------------------------------- Amplitude (Dashboard REST: event segmentation, real-time 5-min)

def fetch_amplitude(cfg, start, end):
    host = "analytics.eu.amplitude.com" if cfg.get("region") == "EU" else "amplitude.com"
    params = {"e": json.dumps({"event_type": cfg["event"]}), "m": "totals", "i": "-300000",
              "start": datetime.fromtimestamp(start, tz=timezone.utc).strftime("%Y%m%d"),
              "end": datetime.fromtimestamp(end, tz=timezone.utc).strftime("%Y%m%d")}
    if cfg.get("group_by"):
        params["g"] = cfg["group_by"]
    with http_client() as c:
        r = check(c.get(f"https://{host}/api/2/events/segmentation", params=params,
                        auth=(cfg["api_key"], cfg["secret_key"])))
    data = r.json().get("data", {})
    xs = data.get("xValues", [])
    dim = cfg.get("dimension") or "group"
    out = []
    for label, series in zip(data.get("seriesLabels") or [None] * len(data.get("series", [])), data.get("series", [])):
        if isinstance(label, list):
            label = label[-1]
        seg = segment_key({dim: str(label)}) if cfg.get("group_by") and label not in (None, "") else ""
        for x, v in zip(xs, series):
            t = to_epoch(x)
            if start <= t <= end and v is not None:
                out.append((t, seg, float(v), 1.0))
    return bucketize(out)


register(Integration(
    "amplitude", "Amplitude", "product analytics", "pull",
    "Real-time (5-minute) event totals from the Event Segmentation API, optionally grouped by a property.",
    [Field("region", "Region", "select", "US", options=["US", "EU"]),
     Field("api_key", "API key"), Field("secret_key", "Secret key", "password"),
     Field("event", "Event type", default="Sign Up"),
     Field("group_by", "Group by property (optional)", default="platform", required=False,
           help="Use gp:<name> for custom user properties"),
     Field("dimension", "Dimension name", default="platform", required=False), METRIC],
    fetch=fetch_amplitude, default_bad="down",
    docs="https://amplitude.com/docs/apis/analytics/dashboard-rest"))


# ---------------------------------------------------------------- Sentry (events-stats)

def _sentry_rows(series, seg):
    out = []
    for ts, counts in series:
        v = sum(c.get("count", 0) or 0 for c in counts) if isinstance(counts, list) else counts
        out.append((int(ts), seg, float(v or 0), 1.0))
    return out


def fetch_sentry(cfg, start, end):
    start, end = span(start, end)
    host = (cfg.get("host") or "https://sentry.io").rstrip("/")
    params = [("interval", "5m"), ("start", _iso(start)), ("end", _iso(end)), ("yAxis", "count()"),
              ("query", cfg.get("query") or "")]
    if cfg.get("dataset"):
        params.append(("dataset", cfg["dataset"]))
    if cfg.get("group_by"):
        params += [("field", cfg["group_by"]), ("field", "count()"), ("topEvents", "5"), ("sort", "-count()")]
    with http_client() as c:
        r = check(c.get(f"{host}/api/0/organizations/{cfg['org']}/events-stats/",
                        headers={"Authorization": f"Bearer {cfg['token']}"}, params=params))
    body = r.json()
    if "data" in body:  # ungrouped: {"data": [[ts, [{"count": n}]], ...]}
        return bucketize(_sentry_rows(body["data"], ""))
    out = []  # grouped: {"<value>": {"data": [...], "order": 0}, ...}
    for group, payload in body.items():
        if isinstance(payload, dict) and "data" in payload and group != "Other":
            out += _sentry_rows(payload["data"], segment_key({cfg["group_by"]: group}))
    return bucketize(out)


register(Integration(
    "sentry", "Sentry", "errors", "pull",
    "Error counts per 5 minutes, optionally split by a tag such as release or os.name.",
    [Field("host", "Sentry URL", "url", "https://sentry.io", help="Or your self-hosted / EU (https://de.sentry.io) URL"),
     Field("org", "Organization slug"), Field("token", "Auth token", "password", help="Needs org:read"),
     Field("query", "Search query", default="event.type:error", required=False),
     Field("group_by", "Split by tag (optional)", default="release", required=False),
     Field("dataset", "Dataset (optional)", default="", required=False), METRIC],
    fetch=fetch_sentry, default_bad="up",
    docs="https://docs.sentry.io/api/"))


# ---------------------------------------------------------------- AWS CloudWatch

def _cw_client(cfg):
    import boto3
    kw = {"region_name": cfg.get("region") or "us-east-1"}
    if cfg.get("access_key_id"):
        kw.update(aws_access_key_id=cfg["access_key_id"], aws_secret_access_key=cfg["secret_access_key"])
    return boto3.client("cloudwatch", **kw)


def fetch_cloudwatch(cfg, start, end, client=None):
    start, end = span(start, end)
    cw = client or _cw_client(cfg)
    if cfg.get("expression"):  # e.g. SEARCH('{AWS/ApplicationELB,LoadBalancer} HTTPCode_Target_5XX_Count', 'Sum', 300)
        q = {"Id": "k", "Expression": cfg["expression"], "ReturnData": True}
    else:
        dims = [dict(zip(("Name", "Value"), d.split("=", 1))) for d in (cfg.get("dimensions") or "").split(",") if "=" in d]
        q = {"Id": "k", "ReturnData": True, "MetricStat": {
            "Metric": {"Namespace": cfg["namespace"], "MetricName": cfg["metric_name"], "Dimensions": dims},
            "Period": 300, "Stat": cfg.get("stat") or "Sum"}}
    resp = cw.get_metric_data(MetricDataQueries=[q], StartTime=datetime.fromtimestamp(start, tz=timezone.utc),
                              EndTime=datetime.fromtimestamp(end, tz=timezone.utc), ScanBy="TimestampAscending")
    dim = cfg.get("label_dimension") or "series"
    out = []
    for res in resp.get("MetricDataResults", []):
        seg = segment_key({dim: res["Label"]}) if cfg.get("expression") else ""
        for t, v in zip(res.get("Timestamps", []), res.get("Values", [])):
            out.append((to_epoch(t), seg, float(v), 1.0))
    return bucketize(out)


register(Integration(
    "cloudwatch", "AWS CloudWatch", "cloud", "pull",
    "A CloudWatch metric (or a SEARCH expression, where each matching series becomes a dimension value).",
    [Field("region", "AWS region", default="us-east-1"),
     Field("access_key_id", "Access key ID", required=False, help="Leave empty to use the server's IAM role"),
     Field("secret_access_key", "Secret access key", "password", required=False),
     Field("namespace", "Namespace", default="AWS/ApplicationELB", required=False),
     Field("metric_name", "Metric name", default="HTTPCode_Target_5XX_Count", required=False),
     Field("dimensions", "Dimensions", default="LoadBalancer=app/prod-alb/123abc", required=False, help="Name=Value, comma-separated"),
     Field("stat", "Statistic", "select", "Sum", options=["Sum", "Average", "Maximum", "p95", "SampleCount"]),
     Field("expression", "…or a SEARCH expression", "textarea", "", required=False),
     Field("label_dimension", "Dimension name for SEARCH results", default="target", required=False), METRIC],
    fetch=fetch_cloudwatch, default_bad="up",
    docs="https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_GetMetricData.html"))
