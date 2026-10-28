"""Push integrations: tools send data to Kepler.

* Segment  - add Kepler as a Webhook destination; every track/page event becomes a 5-minute count.
* OpenTelemetry - point an OTel SDK or Collector's OTLP/HTTP exporter (JSON encoding) at Kepler.
"""
import math
import re

from .base import Field, Integration, register, segment_key, to_epoch


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:80] or "event"


def _dig(obj: dict, path: str):
    for part in path.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


# ---------------------------------------------------------------- Segment

def _safe_epoch(value) -> int | None:
    """Event time, or None (= time received) when missing or unparseable."""
    if value in (None, "", 0):
        return None
    try:
        return to_epoch(value) or None
    except (ValueError, TypeError, OverflowError):
        return None


def parse_segment(body: dict, dims: list[str], prefix: str = "") -> dict[str, list[tuple]]:
    """Returns {metric_name: [(ts, segment, 1, 1)]}. Dims are property names or dotted paths (context.os.name)."""
    events = body.get("batch") if isinstance(body, dict) and isinstance(body.get("batch"), list) else [body]
    out: dict[str, list] = {}
    for ev in events:
        if not isinstance(ev, dict):
            continue
        etype = ev.get("type")
        if etype == "track" and ev.get("event"):
            name = _slug(ev["event"])
        elif etype in ("page", "screen"):
            name = f"{etype}_views"
        else:
            continue  # identify / group / alias carry no countable signal
        d = {}
        for path in dims:
            v = _dig(ev, path) if "." in path else (ev.get("properties") or {}).get(path)
            if v not in (None, "", [], {}):
                d[path.split(".")[-1] if path.startswith("context.") else path] = str(v)[:60]
        ts = _safe_epoch(ev.get("timestamp") or ev.get("sentAt") or ev.get("receivedAt"))
        out.setdefault(prefix + name, []).append((ts, segment_key(d), 1.0, 1.0))
    return out


register(Integration(
    "segment", "Segment", "product analytics", "push",
    "Add a Webhook destination in Segment pointing at Kepler. Each track event becomes a metric (e.g. 'Signed Up' -> signed_up).",
    [Field("dims", "Properties to keep as dimensions", default="plan,context.os.name", required=False)],
    docs="https://segment.com/docs/connections/destinations/catalog/actions-webhook/"))


# ---------------------------------------------------------------- OpenTelemetry (OTLP/HTTP, JSON)

def _attr_value(v: dict):
    for k in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if k in v:
            return v[k]
    return None


def _attrs(lst) -> dict:
    return {a["key"]: str(_attr_value(a.get("value", {}))) for a in lst or [] if _attr_value(a.get("value", {})) is not None}


def _num(dp: dict, *keys):
    """A finite number from the first present key; None for missing / unparseable / NaN / inf."""
    for k in keys:
        if k in dp and dp[k] is not None:
            try:
                v = float(dp[k])
            except (TypeError, ValueError):
                return None
            return v if math.isfinite(v) else None
    return None


def _is_cumulative(temporality) -> bool:
    return temporality in (2, "2", "AGGREGATION_TEMPORALITY_CUMULATIVE")


def parse_otlp(body: dict, conn, keep_attrs: int = 4) -> dict[tuple[str, str], list[tuple]]:
    """Returns {(metric_name, agg): [(ts, segment, value_sum, n)]}.

    gauge -> mean; sum -> 5-minute counts (cumulative series are differenced); histogram -> <name>_count + <name>_avg.
    """
    out: dict[tuple[str, str], list] = {}

    def emit(name, agg, ts, seg, v, n=1.0):
        out.setdefault((name, agg), []).append((ts, seg, v, n))

    def delta(key, value, start_ns):
        row = conn.execute("SELECT value, start_ns FROM otlp_state WHERE key = ?", (key,)).fetchone()
        conn.execute("INSERT OR REPLACE INTO otlp_state(key, value, start_ns) VALUES (?,?,?)", (key, value, start_ns))
        if row is None:
            return None  # first sight of a cumulative series: it becomes the baseline
        if start_ns != row["start_ns"] or value < row["value"]:
            return value  # counter restarted
        return value - row["value"]

    for rm in body.get("resourceMetrics", []):
        res = _attrs(rm.get("resource", {}).get("attributes"))
        base = {"service": res["service.name"]} if "service.name" in res else {}
        for sm in rm.get("scopeMetrics", []) or rm.get("instrumentationLibraryMetrics", []):
            for m in sm.get("metrics", []):
                name = re.sub(r"[^A-Za-z0-9_]", "_", m.get("name", "metric"))
                for kind in ("gauge", "sum", "histogram"):
                    if kind not in m:
                        continue
                    block = m[kind]
                    cumulative = _is_cumulative(block.get("aggregationTemporality"))
                    for dp in block.get("dataPoints", []):
                        attrs = dict(list(_attrs(dp.get("attributes")).items())[:keep_attrs])
                        seg = segment_key({**base, **attrs})
                        try:
                            ts = int(int(dp.get("timeUnixNano", 0) or 0) // 1_000_000_000) or None
                            start_ns = int(dp.get("startTimeUnixNano", 0) or 0)
                        except (TypeError, ValueError):
                            continue
                        if kind == "gauge":
                            v = _num(dp, "asDouble", "asInt")
                            if v is not None:
                                emit(name, "mean", ts, seg, v)
                        elif kind == "sum":
                            v = _num(dp, "asDouble", "asInt")
                            if v is None:
                                continue
                            if cumulative and block.get("isMonotonic", True):
                                v = delta(f"{name}|{seg}", v, start_ns)
                            if v is not None:
                                emit(name, "sum", ts, seg, v)
                        else:  # histogram
                            cnt, tot = _num(dp, "count"), _num(dp, "sum")
                            if cnt is None:
                                continue
                            if cumulative:
                                dc = delta(f"{name}#count|{seg}", cnt, start_ns)
                                ds = delta(f"{name}#sum|{seg}", tot or 0.0, start_ns) if tot is not None else None
                                cnt, tot = dc, ds
                            if cnt:
                                emit(f"{name}_count", "sum", ts, seg, cnt)
                                if tot is not None:
                                    emit(f"{name}_avg", "mean", ts, seg, tot, cnt)
    return out


register(Integration(
    "otlp", "OpenTelemetry", "observability", "push",
    "Point any OTel SDK or Collector's OTLP/HTTP exporter (JSON encoding) at Kepler's /v1/metrics. "
    "Gauges, sums (delta or cumulative) and histograms are supported.",
    [], docs="https://opentelemetry.io/docs/specs/otlp/#otlphttp"))
