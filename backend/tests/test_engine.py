"""End-to-end engine tests on the simulated startup. Run: .venv/bin/python -m pytest -q"""
import json
import os
import time

import numpy as np
import pytest

from kepler import db, simulator
from kepler.db import BUCKET, DAY, WEEK
from kepler.engine import detector
from kepler.engine.drilldown import LOCATE_CONF, drilldown
from kepler.engine.seasonal import BaseModel, CustomModel, _finish, _poisson_z, _window_z, pooled_z

# The simulated clock. Fixed by default (Tuesday 15:00 UTC) so `make test` gives the same answer every run (the simulator's
# noise follows its clock). KEPLER_TEST_NOW=<epoch seconds> replays a moment; KEPLER_TEST_NOW=now uses the clock.
_CLOCK = os.environ.get("KEPLER_TEST_NOW", "1792508400")
NOW = int(time.time() if _CLOCK == "now" else _CLOCK) // BUCKET * BUCKET - BUCKET


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    old, db.DB_PATH = db.DB_PATH, tmp_path_factory.mktemp("engine") / "kepler.db"  # its own database and settings
    db.init_db()
    report = simulator.seed(now=NOW + BUCKET)
    truth = simulator.history_incidents(NOW - 21 * DAY * BUCKET, NOW, np.random.default_rng(42))
    yield report, truth
    db.DB_PATH = old


def _overlaps(inc, t):
    return inc["start_ts"] <= t["end"] + 3 * BUCKET and inc["end_ts"] >= t["start"] - 3 * BUCKET


def test_poisson_z_is_signed_and_sane():
    z = _poisson_z(np.array([0, 20, 10]), np.array([13.5, 5.0, 10.0]))
    assert z[0] < -4 and z[1] > 4 and abs(z[2]) < 0.5


def test_pooled_z_is_calibrated_on_days_the_profile_was_not_trained_on():
    """The weekly profile is a median of 3 weeks smoothed over 5 neighbouring buckets, so its error is shared by the
    buckets a pooled window adds up: on fresh days a 12-bucket sum strays from it further than its Poisson noise allows
    (sd 1.16 here, as if the profile were exact). Pooled z counts the profile's own error, so it stays ~N(0, 1).
    Deterministic: a small slice with a daily cycle, fixed seed."""
    k = np.arange(5 * WEEK)
    ts = (1792508400 // BUCKET + k) * BUCKET
    v = np.random.default_rng(3).poisson(6 * (1 + 0.6 * np.cos(2 * np.pi * k / DAY))).astype(float)
    pool = CustomModel.fit(ts[:3 * WEEK], v[:3 * WEEK], "sum").score(ts, v, "sum")["pool"]
    fresh = slice(3 * WEEK + DAY, None)  # the two weeks after the three it was trained on
    for w in (3, 6, 12):
        assert 0.85 < np.std(_window_z(pool, w)[fresh]) < 1.05
    assert np.std(_window_z(dict(pool, ev=None), 12)[fresh]) > 1.1


def _slice_after_outage(v, expected=20.0):
    """A small slice (20 expected per bucket) scored like the engine does, with a whole-metric outage at buckets
    10-15 already reported."""
    v = np.asarray(v, dtype=float)
    e = np.full(len(v), expected)
    scored = _finish(v, e, np.sqrt(e), "sum", "custom")
    scored.update(ts=np.arange(len(v)) * BUCKET, slice="platform=ios")
    return scored, [dict(id=1, direction="drop", start_ts=10 * BUCKET, end_ts=15 * BUCKET)]


def test_outage_tail_is_not_pooled_again_but_a_new_drop_is():
    """Deterministic (no clock) version of the post-outage duplicate: the slice recovers slower than the rest."""
    outage = [20] * 10 + [0] * 6
    # still low right after the outage: its tail, not new evidence
    scored, reported = _slice_after_outage(outage + [11] * 8 + [20] * 10)
    assert scored["z"][23] < -detector.Z_MIN_SLICE  # the raw pooled score would re-report the outage
    assert detector.unreported_z(scored, 23, reported) == scored["pool"]["z0"][23]
    # back to normal for a while, then low again: a new drop, pooled as usual
    scored, reported = _slice_after_outage(outage + [11] * 3 + [20] * 3 + [11] * 6 + [20] * 5)
    assert detector.unreported_z(scored, 27, reported) == scored["z"][27] < -detector.Z_MIN_SLICE
    # still low an hour later: a problem of its own (the tail lasts one pooling lookback at most)
    scored, reported = _slice_after_outage(outage + [11] * 24)
    assert detector.unreported_z(scored, 21, reported) == scored["pool"]["z0"][21]
    assert detector.unreported_z(scored, 33, reported) < -detector.Z_MIN_SLICE  # (pooled over the hour since)


def test_a_slice_still_broken_after_the_incident_is_not_its_tail():
    """The incident that reported a break closes (the total looks normal again) while a quiet slice (4 expected per
    bucket) is still at zero: the outage is still going on for it, so its own fresh buckets pool as usual and only the
    incident's buckets stay off limits. Before, they counted as a 'tail' for up to an hour, and a slice whose single
    buckets can never pass the threshold (0 events is z -2.1 here) could not alert while it stayed broken."""
    scored, reported = _slice_after_outage([4] * 10 + [0] * 14, expected=4.0)
    assert detector.unreported_z(scored, 23, reported) == pooled_z(scored, 23, range(10, 16))  # (the incident's)
    assert detector.unreported_z(scored, 23, reported) < -detector.Z_MIN_SLICE < scored["pool"]["z0"][23]
    # ... while one coming back (1 event a bucket after the zeros: still low, but recovering) is the outage's tail
    scored, reported = _slice_after_outage([4] * 10 + [0] * 6 + [1] * 7 + [0], expected=4.0)
    assert detector.unreported_z(scored, 23, reported) == scored["pool"]["z0"][23] > -detector.Z_MIN_SLICE > scored["z"][23]


def test_seed_trains_custom_models_and_filter(seeded):
    report, _ = seeded
    assert all(m["status"] == "trained" for m in report["metrics"])
    assert report["feedback"]["status"] == "trained"


def test_detects_real_incidents(seeded):
    _, truth = seeded
    with db.session() as c:
        incs = c.execute("SELECT m.name, i.* FROM incidents i JOIN metrics m ON m.id = i.metric_id").fetchall()
    real = [t for t in truth if t["real"] and t["start"] >= NOW - 14 * DAY * BUCKET]
    found = sum(any(i["name"] == t["metric"] and _overlaps(i, t) for i in incs) for t in real)
    assert found / len(real) >= 0.85


def test_drilldown_names_the_broken_slice(seeded):
    _, truth = seeded
    ok = n = 0
    with db.session() as c:
        for i in c.execute("SELECT m.name, i.* FROM incidents i JOIN metrics m ON m.id = i.metric_id").fetchall():
            t = next((t for t in truth if t["real"] and t["metric"] == i["name"] and _overlaps(i, t)), None)
            if t:
                w = json.loads(i["where_json"])[0]
                ok += {w["dimension"]: w["value"]} == t["where"]
                n += 1
    assert n and ok / n >= 0.85


@pytest.mark.parametrize("scenario", list(simulator.SCENARIOS))
def test_live_injection_opens_incident_in_right_place(seeded, scenario):
    """Detected while it lasts, in the right place. The injection rewrites the last 30 minutes and keeps going for 45
    more; the simulator and the detector keep running bucket by bucket until it is found or over. At quiet hours the
    first 30 minutes of a small slice are not enough evidence (android at ~2 signups per bucket carries about 3 sigma
    by then, below the alerting bar), so detection there takes a few buckets longer."""
    info = simulator.inject(scenario)
    with db.session() as c:
        t = int(db.get_settings(c)["sim_last_ts"])  # (the simulator's clock: earlier scenarios may have moved it on)
    while True:
        with db.session(write=True) as c:
            m = c.execute("SELECT * FROM metrics WHERE name = ?", (info["metric"],)).fetchone()
            detector.score_latest(c, m, t)
            inc = c.execute("SELECT * FROM incidents WHERE metric_id = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
                            (m["id"],)).fetchone()
        where = {(w["dimension"], w["value"]) for w in detector.decision(inc, m)["where"]} if inc else set()
        if set(info["where"].items()) <= where or t >= info["until"]:
            break
        t += BUCKET
        simulator.step(now=t + BUCKET)
    assert inc is not None, f"{scenario} not detected while it lasted"
    d = detector.decision(inc, m)
    assert set(info["where"].items()) <= where, d["where"]
    assert d["direction"] == ("spike" if simulator.SCENARIOS[scenario]["mult"] > 1 else "drop")



# after a total outage: one slice stays mildly low (the lab's duplicate ios alert), or everything comes back ~15% low
AFTER_OUTAGE = {"slice_mildly_low": ({"platform": "ios"}, 0.6), "slow_recovery": ({}, 0.85)}


def _backfill_stretch(c, m, rows, base, end, since):
    """Write rows over the buckets after base, score them from scratch, and return the drop incidents from `since`."""
    c.execute("UPDATE incidents SET status = 'resolved' WHERE metric_id = ?", (m["id"],))
    db.add_points(c, m["id"], rows, mode="replace")
    detector.backfill(c, m, base + BUCKET, end)
    return c.execute("SELECT * FROM incidents WHERE metric_id = ? AND direction = 'drop' AND start_ts >= ? "
                     "ORDER BY start_ts, id", (m["id"], since)).fetchall()


@pytest.mark.parametrize("after", list(AFTER_OUTAGE))
def test_outage_evidence_is_not_reused_after_it_is_reported(seeded, after):
    """A total outage opens one incident that resolves soon after recovery. Its zeros still sit in the 6/12-bucket
    pooled windows afterwards: they must not keep it open, nor let a slice report the same outage again.
    What follows recovery can still alert on evidence of its own: at a quiet hour, the low slice plus Poisson noise
    sometimes does, with or without an outage before it. So the same data is first replayed with normal traffic in
    place of the outage, and only incidents the outage adds count."""
    base = NOW + list(AFTER_OUTAGE).index(after) * 60 * BUCKET  # each case on its own stretch of fresh buckets
    outage, recovery = base + 13 * BUCKET, base + 19 * BUCKET  # 30 min of nothing on every segment
    end = recovery + 18 * BUCKET
    where, mult = AFTER_OUTAGE[after]
    effects = [dict(metric="signups", where={}, mult=0.0, start=outage, end=recovery - BUCKET),
               dict(metric="signups", where=where, mult=mult, start=recovery, end=recovery + 7 * BUCKET)]
    # include the seeded start so the simulator's slow growth trend continues where history left off
    ts = np.concatenate([[NOW - 21 * DAY * BUCKET], np.arange(base + BUCKET, end + BUCKET, BUCKET)]).astype(np.int64)
    rows = [r for r in simulator.generate("signups", ts, effects, np.random.default_rng(7)) if r[0] > base]
    calm = {(r[0], r[1]): r for r in simulator.generate("signups", ts, [], np.random.default_rng(8))}
    replay = [calm[r[:2]] if outage <= r[0] < recovery else r for r in rows]  # the same, but no outage
    with db.session(write=True) as c:
        m = c.execute("SELECT * FROM metrics WHERE name = 'signups'").fetchone()
        last = c.execute("SELECT COALESCE(MAX(id), 0) FROM incidents").fetchone()[0]
        own = _backfill_stretch(c, m, replay, base, end, outage - BUCKET)
        c.execute("DELETE FROM incidents WHERE id > ?", (last,))  # (the replay's)
        incs = _backfill_stretch(c, m, rows, base, end, outage - BUCKET)
        # what the dashboard shows for the low series after recovery agrees: not 'hot' on the outage's zeros
        series = "|".join(f"{k}={v}" for k, v in where.items())
        sc = detector.score_window(c, m, end, slice_=series)
        i0 = int(np.searchsorted(sc["ts"], recovery))
        shown = detector.shown_z(c, m, sc, i0)
    # a later incident that also opens without the outage is the later data's own (on any series: one drop incident per
    # metric is open at a time, so which series carries it depends on what else is open)
    added = incs[:1] + [i for i in incs[1:] if not any(_overlaps(i, dict(start=o["start_ts"], end=o["end_ts"]))
                                                       for o in own)]
    def spans(xs):  # (series, first and last bucket counted from the outage)
        return [(x["slice"], (x["start_ts"] - outage) // BUCKET, (x["end_ts"] - outage) // BUCKET) for x in xs]
    assert len(added) == 1, (spans(incs), "without the outage:", spans(own))
    inc = incs[0]
    assert inc["status"] == "resolved"  # (pinned on whichever series showed the outage most clearly)
    assert inc["end_ts"] < recovery + 3 * BUCKET  # last anomalous bucket: resolves within ~15 min of recovery
    masked = shown != sc["z"][i0:]  # buckets whose pooled windows reached back into the outage
    assert np.nanmin(np.where(masked, shown, 0)) > -(detector.Z_MIN_SLICE if series else detector.Z_MIN), \
        (np.round(shown, 1), np.round(sc["z"][i0:], 1))


@pytest.fixture
def blank_db(tmp_path):
    old, db.DB_PATH = db.DB_PATH, tmp_path / "kepler.db"
    db.init_db()
    yield
    db.DB_PATH = old


# events per 5-min bucket and segment at a quiet hour: android is a quarter of the metric
QUIET = {"platform=web|region=US": 2, "platform=web|region=EU": 1, "platform=android|region=US": 1}


def _window_metric(c, name, history, now, buckets=3):
    """A metric with 7 days of `history` (events per bucket and segment, same time of day) and then a window of
    `buckets` buckets at `now`. Returns (metric, window)."""
    mid = db.ensure_metric(c, name, agg="sum", source="push")
    window = [1792508400 + k * BUCKET for k in range(buckets)]
    db.add_points(c, mid, [(t - day * DAY * BUCKET, seg, float(now[seg] if day == 0 else n), 1.0)
                           for t in window for day in range(8) for seg, n in history.items()], mode="replace")
    return c.execute("SELECT * FROM metrics WHERE id = ?", (mid,)).fetchone(), window


def test_drilldown_says_traffic_is_too_low_instead_of_guessing(blank_db):
    """The same break (android goes to zero) at a quiet hour and at 10x the traffic. With 9 events in the window no
    segment can be named with confidence, so the decision says so plainly; with 90 it is android. A metric-wide drop
    at high traffic is 'all segments'. Deterministic: no clock, no random numbers."""
    def scaled(k, android=1.0, rest=1.0):
        return {s: n * k * (android if "android" in s else rest) for s, n in QUIET.items()}

    with db.session(write=True) as c:
        quiet = drilldown(c, *_window_metric(c, "signups_quiet", scaled(1), scaled(1, android=0)))
        busy = drilldown(c, *_window_metric(c, "signups_busy", scaled(10), scaled(10, android=0)))
        spread = drilldown(c, *_window_metric(c, "signups_spread", scaled(100), scaled(100, android=0.5, rest=0.5)))
        assert [(w["dimension"], w["value"]) for w in quiet] == [("traffic", "too low to localize")]
        assert quiet[0]["localized"] is False and quiet[0]["confidence"] < LOCATE_CONF
        assert [(w["dimension"], w["value"]) for w in busy] == [("platform", "android")]
        assert busy[0]["confidence"] >= LOCATE_CONF and busy[0]["share_of_change"] == 1.0
        assert [(w["dimension"], w["value"]) for w in spread] == [("*", "all segments")]
        assert spread[0]["confidence"] >= LOCATE_CONF

        # the decision says it plainly, with the lower confidence ...
        m = c.execute("SELECT * FROM metrics WHERE name = 'signups_quiet'").fetchone()
        cur = c.execute("INSERT INTO incidents(metric_id, slice, start_ts, end_ts, peak_ts, observed, expected, lower, "
                        "upper, z, confidence, severity, direction, where_json) VALUES (?, '', ?, ?, ?, 3, 4, 0, 8, -3.2, "
                        "0.6, 'medium', 'drop', ?)", (m["id"], 1792508400, 1792508400, 1792508400, json.dumps(quiet)))
        inc = c.execute("SELECT * FROM incidents WHERE id = ?", (cur.lastrowid,)).fetchone()
        d = detector.decision(inc, m)
        assert d["where_confidence"] == quiet[0]["confidence"] < LOCATE_CONF
        assert any("traffic too low to localize" in step for step in detector.reasoning(c, inc, m)["steps"])
        # ... until a later window of the open incident can localize it; a weaker one never replaces a named segment
        assert detector._refresh_where(c, inc, busy)
        inc = c.execute("SELECT * FROM incidents WHERE id = ?", (inc["id"],)).fetchone()
        assert not detector._refresh_where(c, inc, quiet)
        assert detector.decision(inc, m)["where"] == busy


# the manual test's tweet_mentions (Numenta Anomaly Benchmark): each company's share of the tweets
TWEETS = {"AAPL": 0.42, "AMZN": 0.26, "GOOG": 0.1, "FB": 0.09, "KO": 0.06, "UPS": 0.027, "IBM": 0.022, "CRM": 0.016,
          "PFE": 0.004, "CVS": 0.002}
SPIKE_T = 1792508400  # Tue 15:00 UTC


def _tweets(c, extra: dict):
    """15 days of tweets per company and 5 minutes, bursty like real ones (gamma-Poisson), about 210 at this hour with a
    normal range of roughly 80-340. IBM is 2.2% of the day but quiet at this hour: about 1 a bucket. `extra`: rows
    {(segment, bucket from SPIKE_T): value} written over that. Returns the metric, scored up to the bucket before."""
    rng = np.random.default_rng(5)
    ts = SPIKE_T + np.arange(-15 * DAY, 3) * BUCKET
    hour = (ts % 86400) / 3600
    rows = []
    for co, share in TWEETS.items():
        peak, amp = (3, 0.66) if co == "IBM" else (16, 0.6)  # (IBM's busiest hours are elsewhere)
        lam = 134 * share * (1 + amp * np.cos(2 * np.pi * (hour - peak) / 24)) * rng.gamma(3, 1 / 3, len(ts))
        rows += [(int(t), f"company={co}", float(n), 1.0) for t, n in zip(ts, rng.poisson(lam))]
    mid = db.ensure_metric(c, "tweet_mentions", agg="sum", bad_direction="up", source="csv")
    db.add_points(c, mid, rows, mode="replace")
    db.add_points(c, mid, [(SPIKE_T + k * BUCKET, seg, float(v), 1.0) for (seg, k), v in extra.items()], mode="replace")
    c.execute("UPDATE metrics SET last_scored_ts = ? WHERE id = ?", (SPIKE_T - BUCKET, mid))
    return c.execute("SELECT * FROM metrics WHERE id = ?", (mid,)).fetchone()


def test_a_strong_spike_in_a_small_segment_is_caught(blank_db):
    """The manual test's miss: IBM, 2.2% of tweet_mentions, went from about 1 mention per 5 minutes to 84 and 72. Too
    small to be watched on its own, and the total (about +80 on ~210, normal range 80-340) can't tell it from noise.
    A screening pass over small segments promotes IBM for those buckets, and its own model calls it a spike."""
    with db.session(write=True) as c:
        m = _tweets(c, {("company=IBM", 0): 84, ("company=IBM", 1): 72})
        assert "company=IBM" not in detector.slices(c, m, SPIKE_T)  # (a small segment: the gap this covers)
        assert detector.score_window(c, m, SPIKE_T, slice_="")["z"][-1] < detector.Z_MIN
        detector.score_latest(c, m, SPIKE_T + BUCKET)
        incs = c.execute("SELECT * FROM incidents WHERE metric_id = ?", (m["id"],)).fetchall()
    assert [(i["slice"], i["direction"], i["start_ts"], i["end_ts"]) for i in incs] == \
        [("company=IBM", "spike", SPIKE_T, SPIKE_T + BUCKET)]
    assert incs[0]["observed"] == 84 and incs[0]["expected"] < 5
    assert json.loads(incs[0]["where_json"])[0]["value"] == "IBM"


def test_tiny_and_one_off_segments_still_cannot_alert(blank_db):
    """Small segments only reach the full model when their change is as large as a watched slice's whole volume (5% of
    the metric then), and must pass a bar that gives all of them together one watched slice's false-alarm rate. So a
    burst of 8 in CVS (0.2% of the metric: wildly unlikely for it, but 8 tweets) and a one-off value with 84 (a user id
    seen once: not a segment that recurs) open nothing, while the same data with IBM's spike is promoted."""
    with db.session(write=True) as c:
        m = _tweets(c, {("company=CVS", 0): 8, ("user=u4711", 0): 84, ("company=IBM", 2): 84})
        watched = detector.slices(c, m, SPIKE_T)
        assert watched == ["", "company=AAPL", "company=AMZN", "company=FB", "company=GOOG", "company=KO"]
        small = detector.small_slices(c, m, SPIKE_T, SPIKE_T + 2 * BUCKET, watched)
        assert list(small) == ["company=IBM"] and small["company=IBM"][1] == {SPIKE_T + 2 * BUCKET}
        # 5 small companies screened: each must clear p = 3.2e-5 / 5 instead of 3.2e-5 (z 4.0)
        assert 4.3 < small["company=IBM"][0] < 4.4
        detector.score_latest(c, m, SPIKE_T + BUCKET)
        assert not c.execute("SELECT * FROM incidents WHERE metric_id = ?", (m["id"],)).fetchall()


def test_a_bursty_small_segment_is_judged_by_its_own_spread():
    """A segment that is quiet and Poisson at night but bursty in its busy hours (±60% from bucket to bucket). The model
    keeps one spread for the whole day, which the quiet hours set, and scales the Poisson tail by it: an ordinary 2.5x
    burst then scores z ~11. A promoted small segment is judged by small_z instead: that bucket alone, with the spread it
    shows at that time of day and the negative binomial tail. The burst is ordinary there; 20x is still a spike."""
    rng = np.random.default_rng(11)
    ts = SPIKE_T + np.arange(-15 * DAY, 1) * BUCKET
    busy = ((ts % 86400) // 3600 >= 12) & ((ts % 86400) // 3600 < 20)
    v = rng.poisson(np.where(busy, 40 * rng.gamma(3, 1 / 3, len(ts)), 3.0)).astype(float)
    for x, ordinary in ((100, True), (800, False)):
        v[-1] = x
        scored = dict(BaseModel().score(ts, v, "sum"), v=v)
        assert scored["z"][-1] > 10
        assert (detector.small_z(scored, len(ts) - 1) < detector.Z_MIN_SLICE) == ordinary
