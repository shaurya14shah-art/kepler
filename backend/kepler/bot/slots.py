"""Slot extraction: pull typed values (metric, incident id, duration, …) out of a message and delexicalise it."""
import difflib
import re
from dataclasses import dataclass, field

from .model import TOKENS

SCENARIO_WORDS = {
    "ios_release_bug": ["ios", "release", "iphone"],
    "android_signup_broken": ["android", "signup form", "sign-up form", "sign up form"],
    "eu_db_slow": ["eu", "europe", "database", "db", "replica", "latency"],
    "webhook_queue_stuck": ["webhook", "queue", "workers", "job"],
    "india_cdn_outage": ["india", "cdn", "in region", "sessions"],
}
SEVERITIES = ["critical", "high", "medium"]
STOP = {"the", "a", "an", "is", "are", "my", "for", "of", "on", "in", "to", "and", "me", "show", "why", "did", "it",
        "what", "how", "last", "over", "by", "with", "this", "that", "was", "be", "so", "up", "down", "per", "time",
        "open", "all", "any", "kepler"}


@dataclass
class Context:
    metrics: list[str] = field(default_factory=list)
    slices: dict[str, list[str]] = field(default_factory=dict)   # metric -> ['platform=ios', ...]
    tools: dict[str, str] = field(default_factory=dict)          # alias -> integration type
    scenarios: list[str] = field(default_factory=list)


def _aliases(metric: str) -> list[str]:
    base = metric.lower()
    words = [w for w in re.split(r"[_\-.]+", base) if w]
    out = {base, " ".join(words)}
    core = [w for w in words if not re.fullmatch(r"p\d+|ms|s|sec|count|total|rate|pct", w)]
    if core:
        out.add(" ".join(core))
        if len(core) == 1:
            out.add(core[0])
            if core[0].endswith("s"):
                out.add(core[0][:-1])  # "signups" -> "signup"
    if len(words) > 1 and words[-1].endswith("s"):
        out.add(" ".join(words[:-1] + [words[-1][:-1]]))  # "job failures" -> "job failure"
    return sorted(out, key=len, reverse=True)


def _find(text: str, phrase: str):
    return re.search(rf"(?<![\w=]){re.escape(phrase)}(?![\w=])", text)


def extract(text: str, ctx: Context) -> tuple[dict, str]:
    """Returns (slots, delexicalised_text)."""
    t = " " + text.lower().strip() + " "
    slots: dict = {}
    spans: list[tuple[int, int, str]] = []

    def take(m, token):
        spans.append((m.start(), m.end(), token))

    # incident id: "#40", "incident 40", "inc 40"
    m = re.search(r"(?:#|\bincident\s*#?|\binc\s*#?)(\d{1,7})\b", t)
    if m:
        slots["incident"] = int(m.group(1))
        take(m, "numx" if m.group(0).startswith("#") else f"incident {TOKENS['id']}")

    # durations
    m = re.search(r"\b(\d+(?:\.\d+)?)\s*(minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|w)\b", t)
    if m:
        n, u = float(m.group(1)), m.group(2)[0]
        slots["hours"] = max(1, round(n * {"m": 1 / 60, "h": 1, "d": 24, "w": 168}[u]))
        take(m, TOKENS["dur"])
    else:
        for phrase, h in (("this week", 168), ("past week", 168), ("last week", 168), ("week", 168), ("yesterday", 48),
                          ("today", 24), ("last day", 24), ("hour", 1)):
            m = _find(t, phrase)
            if m:
                slots["hours"] = h
                if phrase not in ("today", "yesterday"):
                    take(m, TOKENS["dur"])
                break

    # percentages / thresholds
    m = re.search(r"\b(\d{1,3}(?:\.\d+)?)\s*(%|percent)", t) or re.search(r"\b(0\.\d+)\b", t)
    if m:
        v = float(m.group(1))
        slots["pct"] = v / 100 if v > 1 else v
        take(m, TOKENS["pct"])

    # "last 5 incidents"
    m = re.search(r"\b(?:last|top|latest)\s+(\d{1,3})\b", t)
    if m and "hours" not in slots:
        slots["n"] = int(m.group(1))

    for s in SEVERITIES:
        if _find(t, s):
            slots["severity"] = s
            break
    if _find(t, "open") or _find(t, "still open") or _find(t, "active"):
        slots["open"] = True

    # metric names (longest alias wins), with a fuzzy fallback for typos.
    # Single words of multi-word names ("sessions" -> active_sessions) count too when only one metric has them.
    word_owner: dict[str, list[str]] = {}
    for metric in ctx.metrics:
        for w in set(re.split(r"[_\-.]+", metric.lower())):
            if len(w) >= 4 and w not in STOP:
                word_owner.setdefault(w, []).append(metric)
                if w.endswith("s"):
                    word_owner.setdefault(w[:-1], []).append(metric)
    extra = {m: [w for w, owners in word_owner.items() if owners == [m]] for m in ctx.metrics}
    best = None
    for metric in ctx.metrics:
        for a in _aliases(metric) + extra.get(metric, []):
            mm = _find(t, a)
            if mm and (best is None or len(a) > best[2]):
                best = (metric, mm, len(a))
    if best:
        slots["metric"] = best[0]
        take(best[1], TOKENS["metric"])
    else:
        alias_map = {a: m for m in ctx.metrics for a in _aliases(m) if " " not in a and len(a) > 3}
        for wm in re.finditer(r"[a-z_]{4,}", t):
            w = wm.group(0)
            if w in STOP:
                continue
            hit = difflib.get_close_matches(w, list(alias_map), n=1, cutoff=0.82)
            if hit:
                slots["metric"] = alias_map[hit[0]]
                slots["metric_guess"] = w
                take(wm, TOKENS["metric"])  # the match itself: a re-search with stricter boundaries can miss it
                break

    # slices: explicit dim=value, or a known slice value ("ios", "eu")
    m = re.search(r"\b([a-z_]+)\s*=\s*([\w/\-.]+)", t)
    pool = ctx.slices.get(slots.get("metric"), []) or sorted({s for v in ctx.slices.values() for s in v})
    if m:
        slots["slice"] = f"{m.group(1)}={m.group(2)}"
        take(m, TOKENS["slice"])
    else:
        for s in pool:
            val = s.split("=", 1)[1].lower()
            mm = _find(t, val)
            if mm and len(val) >= 2 and not any(a <= mm.start() < b for a, b, _ in spans):
                slots["slice"] = s
                break

    # tools / integrations
    for alias in sorted(ctx.tools, key=len, reverse=True):
        mm = _find(t, alias)
        if mm:
            slots["tool"] = ctx.tools[alias]
            take(mm, TOKENS["tool"])
            break

    # model tiers (Orbit / Area / Time); "time" also appears in ordinary sentences, so only take it near "model"
    for name in ("orbit", "area", "time"):
        mm = _find(t, name)
        if mm and (name != "time" or re.search(r"\b(model|tier|switch|use|upgrade|downgrade|plan)\b", t)):
            slots["tier"] = name
            take(mm, TOKENS["tier"])
            break

    # demo scenarios (only meaningful for the demo intent; never delexicalised)
    for sc, words in SCENARIO_WORDS.items():
        if sc in ctx.scenarios and any(_find(t, w) for w in words):
            slots["scenario"] = sc
            break

    # build the delexicalised text from non-overlapping spans
    out, pos = [], 0
    for a, b, tok in sorted(spans):
        if a < pos:
            continue
        out.append(t[pos:a])
        out.append(f" {tok} ")
        pos = b
    out.append(t[pos:])
    return slots, re.sub(r"\s+", " ", "".join(out)).strip()
