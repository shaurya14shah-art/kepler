"""Learned tail calibration (CustomModel.fit → _learn_tail): bursty series need a bigger surprise, others don't change."""
import numpy as np

from kepler.db import BUCKET, DAY
from kepler.engine.seasonal import CustomModel, _too_wild

START = 1_790_000_000 // (DAY * BUCKET) * (DAY * BUCKET)


def series(days=14, seed=1, bursts=0.0, incident=None):
    ts = START + np.arange(days * DAY, dtype=np.int64) * BUCKET
    tod = np.arange(len(ts)) % DAY
    lam = 20 * (1 + 0.5 * np.sin(2 * np.pi * tod / DAY))
    rng = np.random.default_rng(seed)
    if bursts:  # retweet-storm style: a few short bursts every day
        lam = np.where(rng.random(len(ts)) < bursts, lam * rng.uniform(3, 6, len(ts)), lam)
    if incident:  # (first bucket, buckets, multiplier): one real anomaly
        a, n, k = incident
        lam = lam.copy()
        lam[a:a + n] *= k
    return ts, rng.poisson(lam).astype(float)


def test_a_well_behaved_series_keeps_its_scores():
    ts, v = series()
    m = CustomModel.fit(ts, v, "sum")
    assert m.tail[0] < 1.3 and m.tail[1] < 1.3


def test_a_bursty_series_learns_a_heavier_upper_tail_only():
    ts, v = series(bursts=0.02)
    m = CustomModel.fit(ts, v, "sum")
    assert m.tail[0] > 1.5, m.tail
    assert m.tail[1] < 1.3, m.tail


def test_one_real_incident_does_not_make_the_model_deaf():
    ts, v = series(incident=(5 * DAY + 100, 36, 6.0))  # 3 hours at 6x on one day
    m = CustomModel.fit(ts, v, "sum")
    assert m.tail[0] < 1.3, m.tail


def test_bursts_stop_alerting_but_a_real_spike_still_does():
    ts, v = series(days=21, bursts=0.02)
    m = CustomModel.fit(ts[: 14 * DAY], v[: 14 * DAY], "sum")
    test_ts, test_v = ts[14 * DAY:], v[14 * DAY:].copy()
    z = m.score(test_ts, test_v, "sum")["z"]
    assert np.nanmean(np.abs(z) > 4) < 0.01  # ordinary bursts: rarely a strong signal any more
    test_v[3 * DAY: 3 * DAY + 12] *= 20       # an hour at 20x
    z = m.score(test_ts, test_v, "sum")["z"]
    assert np.nanmax(z[3 * DAY: 3 * DAY + 12]) > 6


def test_models_trained_before_tails_score_as_before():
    ts, v = series()
    m = CustomModel.fit(ts, v, "sum")
    old = {k: val for k, val in m.params.items() if k != "tail"}
    assert CustomModel(old).tail is None
    untailed = CustomModel({**old, "tail": [1.0, 1.0]}).score(ts, v, "sum")["z"]
    assert np.allclose(CustomModel(old).score(ts, v, "sum")["z"], untailed, equal_nan=True)


def test_training_drops_at_most_the_two_percent_most_extreme_points():
    """NYC taxi's case: the untrained model's noise is far too small for ~2,000 per bucket, so |z| > 4 flagged a third
    of the training data, and the noise was then estimated from the few points that happened to fit."""
    rng = np.random.default_rng(0)
    taxi_like = np.abs(rng.normal(0, 4, 10_000))
    assert np.mean(taxi_like > 4) > 0.25 and np.mean(_too_wild(taxi_like)) <= 0.021
    calm = np.abs(rng.normal(0, 1, 10_000))
    calm[:50] = 9.0  # a well-modelled series with a real incident: exactly the |z| > 4 rule
    assert np.array_equal(_too_wild(calm), calm > 4)


def test_native_step_recognises_coarse_metrics_only():
    from kepler.engine.seasonal import native_step
    rng = np.random.default_rng(2)
    hourly_gauge = np.repeat(rng.normal(50, 5, 7 * 24), 12)          # one reading an hour, held
    half_hour_counts = np.repeat(rng.poisson(3000, 7 * 48) / 6, 6)   # one count per 30 min, spread
    quiet_counts = rng.poisson(0.4, 7 * DAY).astype(float)           # mostly 0s and 1s, every 5 minutes
    noisy_gauge = rng.normal(40, 3, 7 * DAY)
    assert native_step(hourly_gauge) == 12 and native_step(half_hour_counts) == 6
    assert native_step(quiet_counts) == 1 and native_step(noisy_gauge) == 1
    held_with_gaps = hourly_gauge.copy()
    held_with_gaps[100:400] = np.nan
    assert native_step(held_with_gaps) == 12


def test_a_held_reading_does_not_count_as_many():
    """An hourly gauge held over 12 buckets: one shifted reading must not pool into 12 buckets' worth of evidence."""
    ts = START + np.arange(21 * DAY, dtype=np.int64) * BUCKET
    rng = np.random.default_rng(4)
    v = np.repeat(rng.normal(50, 5, 21 * 24), 12)
    m = CustomModel.fit(ts[: 14 * DAY], v[: 14 * DAY], "mean")
    m.tail = None  # (pooling alone: a learned tail factor would partly hide over-counting)
    test = v[14 * DAY:].copy()
    test[3 * DAY: 3 * DAY + 12] += 12                                  # one reading 2.4 sigma high
    z = m.score(ts[14 * DAY:], test, "mean")["z"]
    assert np.nanmax(np.abs(z[3 * DAY: 3 * DAY + 12])) < 4             # (12 buckets of it would pool to ~8)
