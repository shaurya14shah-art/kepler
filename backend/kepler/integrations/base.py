"""Shared plumbing for integrations: a registry, form-field schemas, HTTP client, point helpers."""
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable

import httpx
import pandas as pd

from ..db import BUCKET, bucket_of, segment_key

RESERVED = {"timestamp", "ts", "time", "metric", "value", "agg"}

# tests swap this for an httpx.MockTransport
_transport: httpx.BaseTransport | None = None


def http_client(**kw) -> httpx.Client:
    return httpx.Client(timeout=kw.pop("timeout", 20), transport=_transport, **kw)


@dataclass
class Field:
    name: str
    label: str
    kind: str = "text"            # text | password | url | number | select | textarea
    default: str = ""
    required: bool = True
    help: str = ""
    options: list[str] = field(default_factory=list)


@dataclass
class Integration:
    type: str
    label: str
    category: str                 # observability | product analytics | errors | cloud | database
    direction: str                # pull | push | destination
    summary: str
    fields: list[Field] = field(default_factory=list)
    default_agg: str = "sum"
    default_bad: str = "both"
    fetch: Callable | None = None     # pull: fetch(cfg, start, end) -> [(ts, segment, value_sum, n)]
    send: Callable | None = None      # destination: send(cfg, decision, kind, ref) -> ref | None
    docs: str = ""

    def public(self) -> dict:
        d = asdict(self)
        d.pop("fetch")
        d.pop("send")
        return d

    def secret_fields(self) -> set[str]:
        return {f.name for f in self.fields if f.kind == "password"}


REGISTRY: dict[str, Integration] = {}


def register(i: Integration) -> Integration:
    REGISTRY[i.type] = i
    return i


# ---------------------------------------------------------------- point helpers

def to_epoch(t) -> int:
    """Seconds since epoch from datetime / ISO string / epoch s or ms."""
    if isinstance(t, (int, float)):
        return int(t / 1000) if t > 1e11 else int(t)
    if isinstance(t, datetime):
        return int((t if t.tzinfo else t.replace(tzinfo=timezone.utc)).timestamp())
    ts = pd.Timestamp(str(t))
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return int(ts.timestamp())


def bucketize(rows) -> list[tuple]:
    """Combine finer-grained rows (e.g. per-minute) into 5-minute buckets per segment."""
    acc = defaultdict(lambda: [0.0, 0.0])
    for ts, seg, v, n in rows:
        a = acc[(bucket_of(ts), seg)]
        a[0] += v
        a[1] += n
    return [(t, s, v, n) for (t, s), (v, n) in sorted(acc.items())]


def records_to_points(records: list[dict], agg: str = "sum") -> list[tuple]:
    """Rows with ts/timestamp/time + value + any other columns as dimensions."""
    out = []
    for r in records:
        t = r.get("ts") or r.get("timestamp") or r.get("time")
        if t is None or r.get("value") is None:
            continue
        dims = {k: str(v) for k, v in r.items() if k not in RESERVED and v not in (None, "")}
        out.append((to_epoch(t), segment_key(dims), float(r["value"]), 1.0))
    return bucketize(out)


def span(start: int, end: int) -> tuple[int, int]:
    """Align a fetch window to bucket boundaries so the first bucket isn't partial."""
    return bucket_of(start), end


def check(r: httpx.Response) -> httpx.Response:
    if r.status_code >= 400:
        raise ValueError(f"HTTP {r.status_code} from {r.request.url.host}: {r.text[:240]}")
    return r


__all__ = ["BUCKET", "Field", "Integration", "REGISTRY", "register", "http_client", "to_epoch", "bucketize",
           "records_to_points", "span", "check", "segment_key"]
