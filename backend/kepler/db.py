"""SQLite storage. One file, WAL mode, a fresh connection per unit of work."""
import json
import os
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

BUCKET = 300  # seconds per time bucket (5 minutes)
DAY = 86400 // BUCKET  # buckets per day (288)
WEEK = 7 * DAY  # buckets per week (2016)

DB_PATH = Path(os.environ.get("KEPLER_DB", Path.home() / ".kepler" / "kepler.db"))  # override with KEPLER_DB

_write_lock = threading.RLock()

# In-process change log, used by the engine's score cache: (version, buckets touched) per metric.
# A cached window [start, end] stays valid as long as no later change touched a bucket inside it.
DATA_VERSION: dict[int, int] = {}
CHANGES: dict[int, list[tuple[int, tuple]]] = {}
_CHANGES_KEEP = 2000


def bump_data(metric_id: int, buckets=()):
    """buckets: the buckets written. Stored exactly when few, else as a (min, max) range."""
    v = DATA_VERSION.get(metric_id, 0) + 1
    DATA_VERSION[metric_id] = v
    b = sorted(set(buckets))
    touched = ("set", tuple(b)) if len(b) <= 32 else ("range", (b[0], b[-1]))
    log = CHANGES.setdefault(metric_id, [])
    log.append((v, touched))
    if len(log) > _CHANGES_KEEP:
        del log[: len(log) - _CHANGES_KEEP]


def changed_since(metric_id: int, version: int, start: int, end: int) -> bool:
    """Did any write after `version` touch a bucket within [start, end]?"""
    if DATA_VERSION.get(metric_id, 0) == version:
        return False
    log = CHANGES.get(metric_id, [])
    if not log or log[0][0] > version + 1:  # history trimmed: be safe
        return True
    for v, (kind, data) in log:
        if v <= version:
            continue
        if kind == "range":
            if data[0] <= end and data[1] >= start:
                return True
        elif any(start <= t <= end for t in data):
            return True
    return False


def changed_spans(metric_id: int, version: int, start: int, end: int, limit: int = 32) -> list[tuple[int, int]]:
    """The bucket spans [lo, hi] within [start, end] that writes after `version` touched (empty if none did), merged
    and sorted; at most `limit` of them (else one covering span), the whole window if the log no longer reaches back."""
    if DATA_VERSION.get(metric_id, 0) == version:
        return []
    log = CHANGES.get(metric_id, [])
    if not log or log[0][0] > version + 1:
        return [(start, end)]
    spans = []
    for v, (kind, data) in log:
        if v <= version:
            continue
        if kind == "range":
            if data[0] <= end and data[1] >= start:
                spans.append((max(data[0], start), min(data[1], end)))
        else:
            spans += [(t, t) for t in data if start <= t <= end]
    merged: list[tuple[int, int]] = []
    for lo, hi in sorted(spans):
        if merged and lo <= merged[-1][1] + BUCKET:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged if len(merged) <= limit else [(merged[0][0], merged[-1][1])]


SCHEMA = """
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    unit TEXT DEFAULT '',
    agg TEXT DEFAULT 'sum',              -- sum | mean
    bad_direction TEXT DEFAULT 'both',   -- up | down | both
    description TEXT DEFAULT '',
    source TEXT DEFAULT 'push',
    last_scored_ts INTEGER DEFAULT 0,
    tier TEXT,                           -- orbit | area | time; NULL = workspace default
    muted_until INTEGER DEFAULT 0        -- alerts paused until this time (epoch seconds); detection goes on
);
CREATE TABLE IF NOT EXISTS points (
    metric_id INTEGER NOT NULL,
    ts INTEGER NOT NULL,
    segment TEXT NOT NULL DEFAULT '',    -- 'dim=val|dim=val' (sorted) or '' when undimensioned
    value_sum REAL NOT NULL,
    n REAL NOT NULL DEFAULT 1,
    PRIMARY KEY (metric_id, ts, segment)
);
CREATE INDEX IF NOT EXISTS idx_points_ts ON points(metric_id, ts);
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY,
    metric_id INTEGER NOT NULL,
    slice TEXT NOT NULL DEFAULT '',      -- '' = whole metric, else 'dim=val'
    start_ts INTEGER NOT NULL,
    end_ts INTEGER NOT NULL,
    peak_ts INTEGER NOT NULL,
    observed REAL, expected REAL, lower REAL, upper REAL,
    z REAL, base_z REAL,
    confidence REAL,
    severity TEXT,
    direction TEXT,
    where_json TEXT DEFAULT '[]',
    model_json TEXT DEFAULT '{}',
    features_json TEXT,                  -- classifier features at the peak (training uses these)
    status TEXT DEFAULT 'open',          -- open | resolved
    feedback INTEGER,                    -- 1 real, 0 false alarm, NULL unlabeled
    created_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_incidents_metric ON incidents(metric_id, end_ts);
CREATE TABLE IF NOT EXISTS models (
    metric_id INTEGER NOT NULL,
    slice TEXT NOT NULL DEFAULT '',
    kind TEXT,
    trained_at INTEGER,
    n_points INTEGER,
    params_json TEXT,
    PRIMARY KEY (metric_id, slice)
);
CREATE TABLE IF NOT EXISTS blobs (
    key TEXT PRIMARY KEY,
    data BLOB,
    meta_json TEXT,
    updated_at INTEGER
);
CREATE TABLE IF NOT EXISTS connectors (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    config_json TEXT NOT NULL,
    interval_s INTEGER DEFAULT 300,
    enabled INTEGER DEFAULT 1,
    last_run INTEGER DEFAULT 0,
    last_status TEXT DEFAULT '',
    last_ok INTEGER DEFAULT 0            -- last *successful* pull: buckets after it may still be incomplete
);
CREATE TABLE IF NOT EXISTS incident_notes (
    id INTEGER PRIMARY KEY,
    incident_id INTEGER NOT NULL,
    text TEXT NOT NULL,                  -- what the team found or did ("rolled back deploy 4.2")
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS incident_notes_incident ON incident_notes(incident_id);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY,
    incident_id INTEGER,
    channel TEXT,
    kind TEXT,                           -- opened | resolved
    text TEXT,
    delivered INTEGER,
    error TEXT,
    created_at INTEGER
);
CREATE TABLE IF NOT EXISTS destinations (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,                  -- grafana | datadog_events | webhook
    name TEXT NOT NULL,
    config_json TEXT NOT NULL,
    min_severity TEXT DEFAULT 'medium',
    enabled INTEGER DEFAULT 1,
    last_status TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS destination_refs (
    incident_id INTEGER NOT NULL,
    destination_id INTEGER NOT NULL,
    ref TEXT,                            -- e.g. the Grafana annotation id, so 'resolved' can close it
    PRIMARY KEY (incident_id, destination_id)
);
CREATE TABLE IF NOT EXISTS otlp_state (
    key TEXT PRIMARY KEY,                -- metric + attributes of a cumulative OTLP series
    value REAL,
    start_ns INTEGER
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
-- Billing (disabled by default, see kepler/billing). Only plan names and the payment provider's own IDs are kept:
-- never card numbers, bank details, or customer contact data.
CREATE TABLE IF NOT EXISTS billing_subscriptions (
    id INTEGER PRIMARY KEY,
    plan TEXT NOT NULL,
    status TEXT NOT NULL,                -- created | active | halted | cancelled | completed
    provider TEXT NOT NULL,              -- razorpay
    provider_ref TEXT,                   -- the provider's subscription or order ID
    period_end INTEGER,
    updated INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS billing_events (
    event_id TEXT PRIMARY KEY,           -- webhook event ID: each event is applied once
    type TEXT NOT NULL,
    ref TEXT,
    received INTEGER NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "sensitivity": "0.5",       # min confidence for an alert
    "slack_webhook_url": "",
    "demo_mode": os.environ.get("KEPLER_DEMO", "1"),  # KEPLER_DEMO=0 starts a real (empty) workspace
    "min_change_pct": "15",     # ignore deviations smaller than this
    "model_tier": "area",       # orbit | area | time (see engine/tiers.py)
    "muted_until": "0",         # maintenance mode: every alert paused until then (epoch seconds); detection goes on
}


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


@contextmanager
def session(write: bool = False):
    conn = connect()
    try:
        if write:
            with _write_lock:
                yield conn
                conn.commit()
        else:
            yield conn
    finally:
        conn.close()


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with session(write=True) as c:
        c.executescript(SCHEMA)
        # migrations for databases created by older versions
        cols = {r["name"] for r in c.execute("PRAGMA table_info(connectors)")}
        if "last_ok" not in cols:
            c.execute("ALTER TABLE connectors ADD COLUMN last_ok INTEGER DEFAULT 0")
        if "tier" not in {r["name"] for r in c.execute("PRAGMA table_info(metrics)")}:
            c.execute("ALTER TABLE metrics ADD COLUMN tier TEXT")  # NULL = workspace default model
        if "muted_until" not in {r["name"] for r in c.execute("PRAGMA table_info(metrics)")}:
            c.execute("ALTER TABLE metrics ADD COLUMN muted_until INTEGER DEFAULT 0")
        for k, v in DEFAULT_SETTINGS.items():
            c.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
        c.execute("INSERT OR IGNORE INTO settings(key, value) VALUES ('api_key', ?)", ("kp_" + secrets.token_hex(16),))
        from . import config
        if config.API_KEY:  # KEPLER_API_KEY pins the access key (deployments, CI); it wins on every start
            c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('api_key', ?)", (config.API_KEY,))


def get_settings(conn=None) -> dict:
    if conn is None:
        with session() as c:
            return get_settings(c)
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}


def set_setting(key: str, value: str):
    with session(write=True) as c:
        c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", (key, value))


def segment_key(dims: dict | None) -> str:
    if not dims:
        return ""
    return "|".join(f"{k}={dims[k]}" for k in sorted(dims) if dims[k] not in (None, ""))


def parse_segment(seg: str) -> dict:
    if not seg:
        return {}
    return dict(part.split("=", 1) for part in seg.split("|"))


def ensure_metric(conn, name: str, agg: str = "sum", unit: str = "", bad_direction: str = "both",
                  description: str = "", source: str = "push") -> int:
    row = conn.execute("SELECT id FROM metrics WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO metrics(name, agg, unit, bad_direction, description, source) VALUES (?,?,?,?,?,?)",
        (name, agg, unit, bad_direction, description, source),
    )
    return cur.lastrowid


def bucket_of(ts: float) -> int:
    return int(ts // BUCKET) * BUCKET


def add_points(conn, metric_id: int, rows, mode: str = "add"):
    """rows: iterable of (ts, segment, value_sum, n). mode 'add' accumulates, 'replace' overwrites."""
    rows = list(rows)
    bump_data(metric_id, (bucket_of(r[0]) for r in rows))
    if mode == "replace":
        conn.executemany(
            "INSERT OR REPLACE INTO points(metric_id, ts, segment, value_sum, n) VALUES (?,?,?,?,?)",
            [(metric_id, bucket_of(ts), seg, v, n) for ts, seg, v, n in rows],
        )
    else:
        conn.executemany(
            "INSERT INTO points(metric_id, ts, segment, value_sum, n) VALUES (?,?,?,?,?) "
            "ON CONFLICT(metric_id, ts, segment) DO UPDATE SET value_sum = value_sum + excluded.value_sum, n = n + excluded.n",
            [(metric_id, bucket_of(ts), seg, v, n) for ts, seg, v, n in rows],
        )


def dumps(obj) -> str:
    return json.dumps(obj, separators=(",", ":"))
