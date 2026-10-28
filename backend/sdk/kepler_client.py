"""Tiny Kepler client. Copy this file into your app (no dependencies beyond the stdlib).

    from kepler_client import Kepler
    k = Kepler("http://localhost:8000", "kp_...")
    k.track("signups", 1, platform="ios", region="EU")      # counts (summed per 5 min)
    k.gauge("p95_latency_ms", 182.5, endpoint="/feed")       # averages (mean per 5 min)
    k.flush()
"""
import json
import threading
import time
import urllib.request


class Kepler:
    def __init__(self, url: str, api_key: str, batch_size: int = 500):
        self.url = url.rstrip("/") + "/api/v1/ingest"
        self.key = api_key
        self.batch_size = batch_size
        self._buf: list[dict] = []
        self._lock = threading.Lock()

    def _add(self, name, value, agg, dims):
        with self._lock:
            self._buf.append({"name": name, "value": float(value), "ts": time.time(), "agg": agg,
                              "dims": {k: str(v) for k, v in dims.items()} or None})
            full = len(self._buf) >= self.batch_size
        if full:
            self.flush()

    def track(self, name: str, value: float = 1, **dims):
        """A count, e.g. one signup or one failed job."""
        self._add(name, value, "sum", dims)

    def gauge(self, name: str, value: float, **dims):
        """A measurement to average, e.g. latency."""
        self._add(name, value, "mean", dims)

    def flush(self):
        with self._lock:
            batch, self._buf = self._buf, []
        if not batch:
            return None
        req = urllib.request.Request(self.url, data=json.dumps({"metrics": batch}).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "X-Kepler-Key": self.key})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
