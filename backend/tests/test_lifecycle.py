"""Incident lifecycle: the proportional recovery hold (detector.resolve_after)."""
import numpy as np

from kepler import connectors, db
from kepler.db import BUCKET, DAY
from kepler.engine import detector
from kepler.engine.detector import RESOLVE_AFTER, RESOLVE_HOLD_MAX, resolve_after


def _inc(buckets: int) -> dict:
    return {"start_ts": 0, "end_ts": (buckets - 1) * BUCKET}


def test_a_blip_resolves_after_a_few_normal_buckets():
    assert resolve_after(_inc(1)) == RESOLVE_AFTER == 3


def test_a_longer_incident_needs_as_much_calm_as_it_lasted():
    assert resolve_after(_inc(6)) == 6


def test_the_hold_is_at_most_an_hour():
    assert resolve_after(_inc(100)) == RESOLVE_HOLD_MAX == 12


def test_a_brief_dip_inside_a_long_episode_does_not_split_it(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "kepler.db")
    db.init_db()
    db.set_setting("demo_mode", "0")
    start = 1_790_000_000 // (DAY * BUCKET) * (DAY * BUCKET)
    n = 21 * DAY
    lam = np.full(n, 50.0)
    burst = 20 * DAY + 100
    lam[burst:burst + 12] *= 4          # an hour at 4x...
    lam[burst + 17:burst + 29] *= 4     # ...25 minutes back to normal, then another hour at 4x
    v = np.random.default_rng(3).poisson(lam)
    csv = "timestamp,value\n" + "".join(f"{start + k * BUCKET},{x}\n" for k, x in enumerate(v))
    connectors.import_csv(csv.encode(), "episode", "sum", "up")
    with db.session(write=True) as c:
        c.execute("UPDATE metrics SET last_scored_ts = 0")
        detector.train_all(c, now=start + 14 * DAY * BUCKET)
        m = c.execute("SELECT * FROM metrics WHERE name = 'episode'").fetchone()
        detector.backfill(c, m, start + 14 * DAY * BUCKET, start + (n - 1) * BUCKET)
        incs = c.execute("SELECT start_ts, end_ts FROM incidents WHERE start_ts >= ? AND start_ts < ?",
                         (start + (burst - 6) * BUCKET, start + (burst + 30) * BUCKET)).fetchall()
    assert len(incs) == 1, [(i["start_ts"], i["end_ts"]) for i in incs]
    assert incs[0]["end_ts"] >= start + (burst + 25) * BUCKET  # it covers both halves


def test_a_lone_bucket_needs_a_bigger_surprise_than_a_run():
    from kepler.engine.classifier import prior
    assert prior(4.5, 1.0, duration=1) < 0.5 < prior(4.5, 1.0, duration=2)  # moderate: confirmed 5 minutes later
    assert prior(7.0, 1.0, duration=1) > 0.9                                # strong: alerts at once

