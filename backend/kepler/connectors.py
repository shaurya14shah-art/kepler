"""CSV import and the scheduler-facing runner for pull integrations (see kepler/integrations)."""
import io
import json
import time

import pandas as pd

from . import db
from .db import BUCKET, bucket_of, segment_key  # noqa: F401

RESERVED = {"timestamp", "ts", "time", "metric", "value", "agg"}


# ---------------------------------------------------------------- CSV

def import_csv(raw: bytes, default_metric: str | None = None, agg: str = "sum", bad_direction: str = "both") -> dict:
    """Long format: timestamp, metric, value, [any other columns become dimensions].
    `metric` may be omitted if default_metric is given."""
    df = pd.read_csv(io.BytesIO(raw))
    df.columns = [c.strip().lower() for c in df.columns]
    tcol = next((c for c in ("timestamp", "ts", "time") if c in df.columns), None)
    if tcol is None or "value" not in df.columns:
        raise ValueError("CSV needs a 'timestamp' column and a 'value' column")
    if "metric" not in df.columns:
        if not default_metric:
            raise ValueError("CSV has no 'metric' column: enter a metric name")
        df["metric"] = default_metric
    ts = pd.to_datetime(df[tcol], utc=True, errors="coerce") if not pd.api.types.is_numeric_dtype(df[tcol]) \
        else pd.to_datetime(df[tcol], unit="s", utc=True)
    # resolution-independent epoch seconds (pandas may store ns or us)
    df["_ts"] = (ts - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1)
    df = df[ts.notna() & pd.to_numeric(df["value"], errors="coerce").notna()]
    dims = [c for c in df.columns if c not in RESERVED and not c.startswith("_")]
    summary = {"rows": int(len(df)), "metrics": {}, "dimensions": dims}
    with db.session(write=True) as c:
        for name, g in df.groupby("metric"):
            mid = db.ensure_metric(c, str(name), agg=agg, bad_direction=bad_direction, source="csv")
            rows = [(int(r["_ts"]), segment_key({d: str(r[d]) for d in dims if pd.notna(r[d])}), float(r["value"]), 1.0)
                    for _, r in g.iterrows()]
            db.add_points(c, mid, rows, mode="add")
            # historical data should not fire live alerts: mark it as already scored
            c.execute("UPDATE metrics SET last_scored_ts = MAX(last_scored_ts, ?) WHERE id = ?",
                      (bucket_of(g["_ts"].max()), mid))
            summary["metrics"][str(name)] = {"points": len(rows),
                                             "from": int(g["_ts"].min()), "to": int(g["_ts"].max())}
    return summary


# ---------------------------------------------------------------- scheduled pull integrations

def fetch(ctype: str, cfg: dict, since: int | None = None) -> list[tuple]:
    from .integrations import REGISTRY
    integ = REGISTRY.get(ctype)
    if integ is None or integ.fetch is None:
        raise ValueError(f"unknown pull integration {ctype}")
    missing = [f.label for f in integ.fields if f.required and not str(cfg.get(f.name, "")).strip()]
    if missing:
        raise ValueError("missing: " + ", ".join(missing))
    now = int(time.time())
    return integ.fetch(cfg, since or now - 3 * 3600, now)


def run(conn_row) -> tuple[bool, str, int]:
    cfg = json.loads(conn_row["config_json"])
    try:
        if conn_row["last_ok"] if "last_ok" in conn_row.keys() else conn_row["last_run"]:
            since = (conn_row["last_ok"] or conn_row["last_run"]) - 2 * BUCKET
        elif cfg.get("backfill_days"):
            since = int(time.time()) - int(float(cfg["backfill_days"]) * 86400)  # first pull: import history
        else:
            since = None
        points = fetch(conn_row["type"], cfg, since)
        with db.session(write=True) as c:
            from .integrations import REGISTRY
            integ = REGISTRY[conn_row["type"]]
            mid = db.ensure_metric(c, cfg["metric"], agg=cfg.get("agg") or integ.default_agg,
                                   bad_direction=cfg.get("bad_direction") or integ.default_bad, source=conn_row["type"])
            # these sources re-compute whole buckets, so overwrite instead of accumulating
            db.add_points(c, mid, points, mode="replace")
            msg = f"ok: {len(points)} points"
            now = int(time.time())
            c.execute("UPDATE connectors SET last_run = ?, last_ok = ?, last_status = ? WHERE id = ?",
                      (now, now, msg, conn_row["id"]))
        return True, msg, len(points)
    except Exception as e:  # surface any driver/HTTP/SQL error to the UI
        msg = f"error: {type(e).__name__}: {str(e)[:300]}"
        with db.session(write=True) as c:
            c.execute("UPDATE connectors SET last_run = ?, last_status = ? WHERE id = ?",
                      (int(time.time()), msg, conn_row["id"]))
        return False, msg, 0
