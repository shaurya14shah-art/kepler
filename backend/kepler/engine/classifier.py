"""Alert filter: given a statistical deviation, is it a *real* incident?

Shared prior: a fixed curve over z-score and size of change (works for everyone).
Custom part:  a logistic-regression model trained on the team's own 👍/👎 feedback,
              blended in as more labels arrive.
"""
import json
import math
import time

import numpy as np

from ..db import BUCKET, dumps

FEATURES = ["abs_z", "abs_base_z", "log_rel_change", "duration", "hour_sin", "hour_cos", "weekend", "spike", "is_mean"]
MIN_LABELS = 8


def features(z: float, base_z: float, rel: float, duration: int, ts: int, agg: str) -> list[float]:
    hour = (ts % 86400) / 3600
    dow = ((ts // 86400) + 3) % 7  # 0 = Monday
    return [
        min(abs(z), 30.0),
        min(abs(base_z), 30.0) if math.isfinite(base_z) else 0.0,
        math.log1p(min(abs(rel), 20.0)),
        float(min(duration, 12)),
        math.sin(2 * math.pi * hour / 24),
        math.cos(2 * math.pi * hour / 24),
        1.0 if dow >= 5 else 0.0,
        1.0 if z > 0 else 0.0,
        1.0 if agg == "mean" else 0.0,
    ]


LONE_BUCKET_Z = 1.0  # a lone anomalous bucket needs this much more |z| than a run: heavy tails live in single buckets


def prior(z: float, rel: float, duration: float = 1) -> float:
    """Statistical prior: bigger deviations and *sustained* ones (consecutive buckets, up to 30 min) are likelier real.
    A single bucket on its own must be clearly stronger: a moderate real problem confirms itself 5 minutes later, while
    a lone blip of that size is what ordinary bursty traffic produces (on real data: most false alarms, few real ones)."""
    logit = (abs(z) - 4.0 - (LONE_BUCKET_Z if duration <= 1 else 0.0)) * 1.2 + 0.3 * (min(max(duration, 1), 6) - 1)
    return 1 / (1 + math.exp(-logit)) * min(1.0, abs(rel) / 0.25) ** 0.5


class LinearScorer:
    """A fitted scaler + logistic regression kept as plain numbers, so it is stored as JSON rather than pickle."""

    def __init__(self, mean, scale, coef, intercept):
        self.mean = np.asarray(mean, dtype=float)
        self.scale = np.asarray(scale, dtype=float)
        self.coef = np.asarray(coef, dtype=float)
        self.intercept = float(intercept)
        if not (self.mean.shape == self.scale.shape == self.coef.shape == (len(FEATURES),)):
            raise ValueError("stored feedback model does not match the feature set")

    @classmethod
    def from_pipeline(cls, pipe) -> "LinearScorer":
        return cls(pipe[0].mean_, pipe[0].scale_, pipe[-1].coef_[0], pipe[-1].intercept_[0])

    def probability(self, feats) -> float:
        x = (np.asarray(feats, dtype=float) - self.mean) / np.where(self.scale == 0, 1.0, self.scale)
        return float(1 / (1 + np.exp(-(x @ self.coef + self.intercept))))

    def to_json(self) -> str:
        return json.dumps({"mean": self.mean.tolist(), "scale": self.scale.tolist(),
                           "coef": self.coef.tolist(), "intercept": self.intercept})

    @classmethod
    def from_json(cls, raw) -> "LinearScorer":
        d = json.loads(raw)
        return cls(d["mean"], d["scale"], d["coef"], d["intercept"])


class FeedbackModel:
    def __init__(self, pipe=None, meta=None):
        self.pipe = pipe
        self.meta = meta or {"n_labels": 0}

    @property
    def weight(self) -> float:
        # trust grows with the number of labels: 29 labels -> 0.42, 100 -> 0.6 (cap). (Counting balanced evidence
        # instead, 2 x the rarer label, was tried: on the NAB benchmark with simulated labels it bought back at most one
        # timely catch for 80-150 more false alarms.)
        n = self.meta["n_labels"]
        return 0.0 if self.pipe is None else min(0.6, n / (n + 40))

    def confidence(self, feats: list[float], z: float, rel: float) -> tuple[float, float, float | None]:
        p0 = prior(z, rel, feats[3])  # feats[3] = duration in buckets
        if self.pipe is None:
            return p0, p0, None
        p1 = self.pipe.probability(feats)
        w = self.weight
        return (1 - w) * p0 + w * p1, p0, p1

    @staticmethod
    def load(conn) -> "FeedbackModel":
        row = conn.execute("SELECT data, meta_json FROM blobs WHERE key = 'feedback_model'").fetchone()
        if not row:
            return FeedbackModel()
        try:
            scorer = LinearScorer.from_json(row["data"])
        except (ValueError, TypeError, KeyError, UnicodeDecodeError):
            return FeedbackModel()  # old (pickled) or unreadable model: ignore it; the next training rewrites it
        return FeedbackModel(scorer, json.loads(row["meta_json"]))

    @staticmethod
    def train(conn) -> dict:
        # sklearn (~1 s and ~70 MB to import) only for training: processes that only score (engine/compare) skip it
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import cross_val_score
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        rows = conn.execute(
            "SELECT i.*, m.agg FROM incidents i JOIN metrics m ON m.id = i.metric_id WHERE feedback IS NOT NULL"
        ).fetchall()
        y = np.array([r["feedback"] for r in rows])
        meta = {"n_labels": len(rows), "positives": int(y.sum()) if len(y) else 0,
                "negatives": int(len(y) - y.sum()) if len(y) else 0, "trained_at": int(time.time())}
        if len(rows) < MIN_LABELS or meta["positives"] == 0 or meta["negatives"] == 0:
            meta["status"] = f"needs at least {MIN_LABELS} labels incl. both 👍 and 👎"
            conn.execute("DELETE FROM blobs WHERE key = 'feedback_model'")
            return meta
        # train on the features exactly as they looked when the alert was decided
        X = np.array([
            json.loads(r["features_json"]) if r["features_json"] else
            features(r["z"], r["base_z"] if r["base_z"] is not None else r["z"],
                     (r["observed"] - r["expected"]) / max(abs(r["expected"]), 1e-9),
                     (r["end_ts"] - r["start_ts"]) // BUCKET + 1, r["peak_ts"], r["agg"])
            for r in rows
        ])
        pipe = make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", C=0.5, max_iter=500))
        folds = min(5, meta["positives"], meta["negatives"])
        if folds >= 2:
            meta["cv_accuracy"] = round(float(cross_val_score(pipe, X, y, cv=folds).mean()), 3)
        pipe.fit(X, y)
        coefs = pipe[-1].coef_[0]
        meta["top_features"] = sorted(
            [{"feature": f, "weight": round(float(c), 3)} for f, c in zip(FEATURES, coefs)],
            key=lambda d: -abs(d["weight"]))[:4]
        meta["status"] = "trained"
        conn.execute("INSERT OR REPLACE INTO blobs(key, data, meta_json, updated_at) VALUES ('feedback_model', ?, ?, ?)",
                     (LinearScorer.from_pipeline(pipe).to_json(), dumps(meta), int(time.time())))
        return meta
