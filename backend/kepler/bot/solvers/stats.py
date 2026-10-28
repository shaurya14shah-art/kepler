"""Statistics and probability word problems in plain English, answered exactly with worked steps and a check.

"find the mean and sd of 2, 4, 4, 4, 5, 5, 7, 9", "probability of at least one six in 4 rolls", "two aces in a row
without replacement", "how many ways can you arrange MISSISSIPPI", "1% have the disease, the test catches 99% and has a
5% false positive rate, P(disease | positive)?", "X ~ N(100, 15), P(X > 130)?" → reads the setting and its numbers out
of chatty English, computes exactly (fractions for counting and probability, Φ for the normal curve) and explains it:
the formula, what is known, the substitution, the result and, where there is a natural one, a check.

What it reads
  data           mean / median / mode(s) / range / variance / sd of a list (sample n − 1, population n; both when
                 unspecified, sample first) · geometric and harmonic means · weighted means · the score needed for a
                 target average
  dice           sums, products, differences, doubles, "at least one six in n rolls", faces on one die, expected rolls
  coins          exactly / at least / at most k heads in n flips (fair or biased), runs in a row, expected heads
  cards          one card (P(king | face card)), several without or with replacement, k-card hands (probability and
                 how many)
  counting       committees (also "exactly 2 women"), roles and podiums, arrangements, letters with repeats, nCr / nPr
  expectation    raffles, games with a cost to play (net gain per play), tables of values and probabilities
  Bayes          base rate, detection rate and false positive rate (or specificity) → P(condition | positive)
  distributions  normal P(X < a), P(X > a), P(a < X < b), z-scores, percentiles; binomial probabilities, mean, variance

Each reader fires only when the message names its setting and gives the numbers it needs, so Kepler commands ("is
signups ok", "set sensitivity to 80%") and definition questions ("what is a z-score") return None.
"""
import math
import re
from collections import Counter
from fractions import Fraction as F
from itertools import product

import sympy as sp
from scipy.special import ndtr, ndtri

from ..fields import fmt as fmt4
from ..fields import money
from ..reasoning import Solution
from ..reasoning import fmt as sym_fmt

NUM = r"(?:\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)"
SNUM = rf"-?{NUM}"
PNUM = r"(?:\d+\s*/\s*\d+|\d*\.\d+\s*%?|\d+\s*%|[01](?![\d.]))"
CMPW = (r"exactly|precisely|at least|at most|no more than|not more than|no fewer than|no less than|not less than|"
        r"more than|fewer than|less than|greater than|over|under|up to")
MAX_N = 2000  # largest count of trials / items we compute exactly

# ---------------------------------------------------------------- reading the message

_SMALL = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                     "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split(), 2)}
_BIG = {"hundred": 100, "thousand": 1000, "million": 10 ** 6}
_FACES = {"ones": "1s", "twos": "2s", "threes": "3s", "fours": "4s", "fives": "5s", "sixes": "6s"}
_ORDINAL = {w: i for i, w in enumerate("zeroth first second third fourth fifth sixth seventh eighth ninth tenth eleventh "
                                       "twelfth".split())}


def _normalise(text: str) -> str:
    t = text.lower()
    for a, b in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'), ("−", "-"), ("–", "-"), ("—", " - "), ("≤", "<="),
                 ("≥", ">="), (" ", " "), ("×", " x ")):
        t = t.replace(a, b)
    digit_words = "|".join(k for k, v in _SMALL.items() if 0 < v < 10)
    t = re.sub(rf"\b({'|'.join(_TENS)})[- ]({digit_words})\b", lambda m: str(_TENS[m[1]] + _SMALL[m[2]]), t)
    t = re.sub(r"\b(?:a|one)\s+(hundred|thousand|million)\b", lambda m: str(_BIG[m[1]]), t)
    t = re.sub(r"\b(" + "|".join(_FACES) + r")\b", lambda m: _FACES[m[1]], t)
    t = re.sub(r"\b(" + "|".join(list(_SMALL) + list(_TENS)) + r")\b",
               lambda m: str(_SMALL.get(m[1], _TENS.get(m[1]))), t)
    t = re.sub(r"\b(\d+)\s+(hundred|thousand|million)\b", lambda m: str(int(m[1]) * _BIG[m[2]]), t)
    t = re.sub(r"\ba dozen\b|\bdozen\b", "12", t)
    t = re.sub(r"\bonce\b", "1 time", t)
    t = re.sub(r"\btwice\b", "2 times", t)
    t = re.sub(r"\bthrice\b", "3 times", t)
    t = re.sub(r"\ba pair of\b", "2", t)
    t = re.sub(r"\s+", " ", t)
    return f" {t.strip()} "


class _Prec:
    """How the user wants decimals: "4 sig figs", "to 2 decimal places", "nearest whole number"; default 4 s.f."""

    def __init__(self, t: str):
        self.sig = self.dp = None
        m = re.search(r"\b(\d{1,2})\s*(?:sig(?:nificant)?\.?\s*(?:fig(?:ure)?s?|digits?)|s\.?f\.?)(?![a-z])", t)
        if m:
            self.sig = max(1, min(int(m[1]), 12))
        m = re.search(r"\b(\d{1,2})\s*(?:decimal places?|decimal digits?|decimals?|d\.?\s?p\.?)(?![a-z])", t)
        if m:
            self.dp = min(int(m[1]), 12)
        elif re.search(r"\bnearest (?:whole number|integer|whole|unit)\b", t):
            self.dp = 0
        else:
            for word, dp in (("tenth", 1), ("hundredth", 2), ("thousandth", 3)):
                if re.search(rf"\bnearest {word}\b", t):
                    self.dp = dp

    @property
    def custom(self) -> bool:
        return self.sig is not None or self.dp is not None

    def dec(self, x: float) -> str:
        if self.dp is not None:
            return f"{x:,.{self.dp}f}"
        if self.sig is not None:
            return _sig(x, self.sig)
        return fmt4(x)


def _sig(x: float, n: int) -> str:
    if x == 0 or not math.isfinite(x):
        return "0" if x == 0 else str(x)
    e = math.floor(math.log10(abs(x)))
    if e >= 15 or e < -6:
        return f"{x:.{n - 1}e}"
    d = n - 1 - e
    return f"{x:,.{d}f}" if d > 0 else f"{round(x, d):,.0f}"


def _strip_chatter(t: str) -> str:
    """Numbers that aren't part of the problem: "4 sig figs", "2 dp", "question 3", "#5"."""
    t = re.sub(r"\b\d{1,2}\s*(?:sig(?:nificant)?\.?\s*(?:fig(?:ure)?s?|digits?)|s\.?f\.?)(?![a-z])", " ", t)
    t = re.sub(r"\b\d{1,2}\s*(?:decimal places?|decimal digits?|decimals?|d\.?\s?p\.?)(?![a-z])", " ", t)
    t = re.sub(r"\b(?:question|problem|exercise|ex|q|hw|task)\s*#?\s*\d+[a-z]?\b", " ", t)
    t = re.sub(r"#\s*\d+", " ", t)
    return t


def _money_text(t: str) -> str:
    t = re.sub(r"[£€₹]", "$", t)
    t = re.sub(r"\brs\.?\s*(?=\d)", "$", t)
    t = re.sub(rf"({NUM})\s*(?:cents?|pence)\b", lambda m: f"${float(m[1].replace(',', '')) / 100:.2f}", t)
    t = re.sub(rf"(?<!\$)({NUM})\s*(?:dollars?|bucks|pounds|quid|euros?|rupees?)\b", r"$\1", t)
    return re.sub(r"\$\s+", "$", t)


def _currency(text: str) -> str:
    low = text.lower()
    if "£" in low or re.search(r"\b(?:pounds|quid|pence)\b", low):
        return "£"
    if "€" in low or re.search(r"\beuros?\b", low):
        return "€"
    if "₹" in low or re.search(r"\brupees?\b|\brs\.?\s*\d", low):
        return "₹"
    return "$"


class _Ctx:
    def __init__(self, text: str):
        self.text = text.strip()
        t = _normalise(text)
        self.pr = _Prec(t)
        self.c = _strip_chatter(t)
        self.m = _money_text(self.c)
        self.cur = _currency(text)


def _q(s: str) -> F:
    """'0.3', '30%', '1/6', '1,200' → an exact fraction."""
    s = s.replace(",", "").replace(" ", "")
    if s.endswith("%"):
        return F(s[:-1]) / 100
    return F(s)


def _term(x: F, maxd: int = 6) -> str | None:
    """The exact decimal of a fraction that terminates within maxd places (with thousands separators), else None."""
    d, a, b = x.denominator, 0, 0
    while d % 2 == 0:
        d, a = d // 2, a + 1
    while d % 5 == 0:
        d, b = d // 5, b + 1
    if d != 1 or max(a, b) > maxd:
        return None
    k = max(a, b)
    ip, fp = divmod(abs(x.numerator) * 10 ** k // x.denominator, 10 ** k)
    return ("-" if x < 0 else "") + f"{ip:,}" + (f".{fp:0{k}d}" if k else "")


def _show(x: F) -> str:
    """Compact exact form for knowns and substitutions: 0.3, 1/6, 12."""
    if x.denominator == 1:
        return str(x.numerator)
    return _term(x, 8) or f"{x.numerator}/{x.denominator}"


def _val(x: F, pr: _Prec) -> str:
    """An exact statistic: 7, 6.5, or 32/7 ≈ 4.571."""
    if x.denominator == 1:
        return f"{x.numerator:,}"
    term = _term(x)
    if term and not pr.custom:
        return term
    d = pr.dec(float(x))
    if term or x.denominator > 10 ** 9:
        return d
    return f"{x.numerator}/{x.denominator} ≈ {d}"


def _prob(p, pr: _Prec, pct: bool = False) -> str:
    """A probability: 5/16 = 0.3125, 1/221 ≈ 0.004525, 0.8944 (89.44%) for the normal curve."""
    if isinstance(p, F):
        if p.denominator == 1:
            s = str(p.numerator)
        elif p.denominator > 10 ** 12:
            s = pr.dec(float(p))
        else:
            fr, term, d = f"{p.numerator}/{p.denominator}", _term(p), pr.dec(float(p))
            s = f"{fr} = {term}" if term and (not pr.custom or d == term) else f"{fr} ≈ {d}"
    else:
        s = pr.dec(p)
    if pct:
        s += f" ({pr.dec(float(p) * 100)}%)"
    return s


def _cash(x, cur: str) -> str:
    v = round(float(x), 2)
    if v == 0:
        return f"{cur}0.00"
    return ("-" if v < 0 else "") + f"{cur}{money(abs(v))}"


def _int(n: int) -> str:
    return f"{n:,}"


def _sol(kind: str, ctx: _Ctx, formula: str, known, subs, answer: str, check: str = "") -> Solution:
    steps = [f"formula: {formula}"]
    if known:
        steps.append("known: " + (known if isinstance(known, str) else ", ".join(known)))
    for s in [subs] if isinstance(subs, str) else subs:
        steps.append(f"substitute: {s}")
    steps.append(f"result: {answer}")
    return Solution(kind, ctx.text, answer, steps, check=check, confidence=0.97)


def _asks_prob(t: str) -> bool:
    return bool(re.search(r"\bprobabilit|\bprob\b|\bchances?\b|\bodds\b|\blikel|\bp\s*\(|\bhow often\b|"
                          r"\bwhat (?:fraction|proportion|percent|percentage|share)\b|\bpercentage\b", t))


def _blank(t: str, spans) -> str:
    for a, b in spans:
        t = t[:a] + " " * (b - a) + t[b:]
    return t


# ---------------------------------------------------------------- lists of numbers in a sentence

_GAP = re.compile(r"(?:\s|[,;&|$£€₹%()\[\]{}]|\band\b|\bthen\b|\b(?:cm|mm|km|kg|g|lbs?|secs?|mins?|hrs?|pts|points|marks|"
                  r"years?|yrs|ms|ml|dollars|euros|rupees|inches|ft|feet|degrees|minutes|seconds|hours|days|kmh|"
                  r"mph)\b|°[cf]?)*")


def _runs(s: str) -> list[list[tuple[F, int, int, bool]]]:
    """Maximal runs of numbers separated only by commas, 'and', spaces or a repeated unit: the data in a sentence.

    Each item is (value, start, end, has_currency). With "1,200, 1,500" (comma-space somewhere) a tight comma before
    three digits is a thousands separator; with "3,7,8" every comma separates."""
    thousands = bool(re.search(r"\d,\s", s))
    core = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?" if thousands else r"\d+(?:\.\d+)?"
    tok = re.compile(rf"(?<![\w.])(-?(?:{core}(?:/\d+)?|\.\d+))(?![\w.]*[\w])")
    toks = []
    for m in tok.finditer(s):
        raw = m[1].replace(",", "")
        try:
            v = F(raw)
        except (ValueError, ZeroDivisionError):
            continue
        cur = s[max(0, m.start() - 2):m.start()].strip().endswith(("$", "£", "€", "₹"))
        toks.append((v, m.start(), m.end(), cur))
    runs: list[list] = []
    for tk in toks:
        if runs and _GAP.fullmatch(s[runs[-1][-1][2]:tk[1]]):
            runs[-1].append(tk)
        else:
            runs.append([tk])
    return runs


def _best_run(s: str, minimum: int = 2):
    runs = [r for r in _runs(s) if len(r) >= minimum]
    if not runs:
        return None
    longest = max(len(r) for r in runs)
    return [r for r in runs if len(r) == longest][-1]


# ---------------------------------------------------------------- descriptive statistics of a list

_STATS = (("gmean", r"\bgeometric (?:mean|average)\b"), ("hmean", r"\bharmonic (?:mean|average)\b"),
          ("mean", r"(?<!geometric )(?<!harmonic )\b(?:arithmetic )?(?:mean|average|avg)\b"),
          ("median", r"\bmedian\b"), ("mode", r"\bmodes?\b|\bmodal\b|\bmost (?:common|frequent)\b"),
          ("range", r"\brange\b"), ("variance", r"\bvariances?\b|\bvar\b"),
          ("sd", r"\bstandard deviations?\b|\bstd\.? ?dev\b|\bstdev\b|\bstd\b|\bs\.d\b\.?|\bsd\b|\bsigma\b|σ"))
_ALL_STATS = re.compile(r"\b(?:summary|descriptive|basic) stat(?:istic)?s\b|\ball (?:the |of the )?stat(?:istic)?s\b|"
                        r"\bdescribe (?:the |this |my )?data\b")
_NOT_DATA = re.compile(r"\baverage (?:speed|velocity|rate|acceleration|value of|power|cost per)\b|\bmean value theorem\b|"
                       r"\b(?:moving|rolling|running|exponential) average\b|[a-z]\s*\(\s*[a-z]\s*\)|\b[xy]\s*[=^]|\^|"
                       r"\bdomain\b|\bfunctions?\b|\bintegral\b|\bderivative\b|\bequation\b|\bweight|\bfrequenc|"
                       r"\bneeds? (?:on|to (?:get|score|earn|make|average)|an?\b|at least)|\bto average\b|\bnext (?:test|exam|quiz|game|score)\b|\bmean free path\b|"
                       r"\b(?:mean|average) of (?:the )?\d+ (?:numbers|values|scores|tests|items|integers|marks|"
                       r"observations|results|data points|exams|quizzes|students)\b|\bprobabilit|\bdice\b|\bcoins?\b")
_LABEL = {"mean": "mean", "median": "median", "mode": "mode", "range": "range", "gmean": "geometric mean",
          "hmean": "harmonic mean"}


def _sqrt_exact(v: F) -> F | None:
    a, b = math.isqrt(v.numerator), math.isqrt(v.denominator)
    return F(a, b) if a * a == v.numerator and b * b == v.denominator else None


def describe(ctx: _Ctx) -> Solution | None:
    t = ctx.c
    want = [k for k, rx in _STATS if re.search(rx, t)]
    if _ALL_STATS.search(t):
        want = ["mean", "median", "mode", "range", "variance", "sd"]
    if not want or _NOT_DATA.search(t):
        return None
    run = _best_run(t)
    if not run or len(run) > 500:
        return None
    xs = [v for v, *_ in run]
    money_data = any(c for *_, c in run)
    n, pr = len(xs), ctx.pr
    lst = ", ".join(_show(x) for x in xs)
    show = (lambda v: _cash(v, ctx.cur)) if money_data else (lambda v: _val(v, pr))
    total = sum(xs)
    mean = total / n
    pop = bool(re.search(r"\bpopulation\b", t))
    samp = bool(re.search(r"\bsample\b", t))
    if not pop and not samp:
        samp = pop = True
    parts: list[tuple[str, str, bool]] = []  # (label, value, exact)
    steps = [f"known: n = {n} values: {lst}" if n <= 20 else f"known: n = {n} values"]
    checks = []
    for k in want:
        if k == "mean":
            steps += ["formula: x̄ = Σx / n",
                      f"substitute: x̄ = {(' + '.join(_show(x) for x in xs) + ' = ') if n <= 10 else ''}{_show(total)} / {n}"]
            parts.append(("mean", show(mean), True))
            checks.append(f"Σ(x − x̄) = {_show(sum(x - mean for x in xs))} ✓")
        elif k == "median":
            ys = sorted(xs)
            mid = n // 2
            med = ys[mid] if n % 2 else (ys[mid - 1] + ys[mid]) / 2
            how = (f"middle (position {mid + 1}) = {_show(med)}" if n % 2 else
                   f"two middle values (positions {mid} and {mid + 1}): ({_show(ys[mid - 1])} + {_show(ys[mid])}) / 2")
            steps += ["formula: median = middle value of the sorted list (mean of the two middle values when n is even)",
                      f"substitute: sorted {', '.join(_show(y) for y in ys) if n <= 20 else '…'} → {how}"]
            parts.append(("median", show(med), True))
        elif k == "mode":
            counts = Counter(xs)
            top = max(counts.values())
            modes = sorted(v for v, c in counts.items() if c == top)
            steps.append("formula: mode = the most frequent value(s)")
            if top == 1:
                steps.append("substitute: every value appears once")
                parts.append(("mode", "no mode (every value appears once)", True))
            else:
                steps.append("substitute: counts " + ", ".join(f"{_show(v)} ×{c}" for v, c in sorted(counts.items()) if c > 1))
                words = " and ".join(show(v) for v in modes)
                parts.append(("modes" if len(modes) > 1 else "mode",
                              words + (f" (each appears {top} times)" if len(modes) > 1 else ""), True))
        elif k == "range":
            steps += ["formula: range = max − min", f"substitute: {_show(max(xs))} − {_show(min(xs))}"]
            parts.append(("range", show(max(xs) - min(xs)), True))
        elif k == "gmean":
            if any(x <= 0 for x in xs):
                return None
            g = math.exp(sum(math.log(x) for x in xs) / n)
            ge = sp.nsimplify(sp.Mul(*[sp.Rational(x.numerator, x.denominator) for x in xs]) ** sp.Rational(1, n))
            exact = ge.is_Rational
            steps += ["formula: G = (x₁ · x₂ · … · xₙ)^(1/n)",
                      f"substitute: G = ({' × '.join(_show(x) for x in xs)})^(1/{n})"]
            parts.append(("geometric mean", _val(F(int(ge.p), int(ge.q)), pr) if exact else pr.dec(g), bool(exact)))
        elif k == "hmean":
            if any(x == 0 for x in xs):
                return None
            h = n / sum(1 / x for x in xs)
            steps += ["formula: H = n / Σ(1/x)", f"substitute: H = {n} / ({' + '.join('1/' + _show(x) for x in xs)})"]
            parts.append(("harmonic mean", show(h), True))
        elif k in ("variance", "sd"):
            if n < 2:
                return None
            ss = sum((x - mean) ** 2 for x in xs)
            if "variance" in want and "sd" in want and k == "sd":
                pass  # the variance step already showed the working
            else:
                steps += ["formula: s² = Σ(x − x̄)² / (n − 1) for a sample, σ² = Σ(x − x̄)² / n for a population",
                          f"substitute: x̄ = {_show(mean)}, squared deviations "
                          f"{', '.join(_show((x - mean) ** 2) for x in xs[:12])}{' …' if n > 12 else ''} → "
                          f"Σ(x − x̄)² = {_show(ss)}"]
                checks.append(f"Σx² − n·x̄² = {_show(sum(x * x for x in xs))} − {n} × {_show(mean * mean)} = {_show(ss)} ✓")
            for name, on, div in (("sample", samp, n - 1), ("population", pop, n)):
                if not on:
                    continue
                var = ss / div
                if k == "variance":
                    steps.append(f"substitute: {name} variance = {_show(ss)} / {div} = {_val(var, pr)}")
                    parts.append((f"{name} variance", _val(var, pr), True))
                else:
                    root = _sqrt_exact(var)
                    exact_form = sym_fmt(sp.sqrt(sp.Rational(var.numerator, var.denominator)))
                    steps.append(f"substitute: {name} sd = √({_show(ss)} / {div}) = √{_show(var)}"
                                 + ("" if root is not None else f" = {exact_form}"))
                    if root is not None:
                        parts.append((f"{name} sd", show(root), True))
                    else:
                        v = math.sqrt(float(var))
                        parts.append((f"{name} sd", _cash(v, ctx.cur) if money_data else pr.dec(v), False))
    if not parts:
        return None
    if len(parts) == 1:
        answer = parts[0][1]
    else:
        answer = "; ".join(f"{lab} {'=' if exact else '≈'} {v}" for lab, v, exact in parts)
    steps.append(f"result: {answer}")
    kind = "statistics"
    return Solution(kind, ctx.text, answer, steps, check="; ".join(checks), confidence=0.97)


# ---------------------------------------------------------------- weighted mean and the value needed for an average

def weighted(ctx: _Ctx) -> Solution | None:
    t = ctx.c
    if not re.search(r"\bweight(?:s|ed|ing|ings)?\b|\bworth\b|\bfrequenc(?:y|ies)\b|\bcounts? (?:for|as)\b|"
                     r"\b(?:appears|occurs)\b|\bscored\b", t):
        return None
    if not re.search(r"\b(?:mean|average|avg|grade|gpa|overall|final mark|final score|weighted)\b", t):
        return None
    pairs: list[tuple[F, F]] = []
    pct = False
    for m in re.finditer(rf"(?<![\w.])({SNUM})\s*(%)?\s*(?:\(\s*|,\s*)?(?:with\s+)?(?:an?\s+)?(?:weight(?:ing)?|weighted|"
                         rf"worth|counts? for|counting for|w)\s*(?:of|=|:|at|as)?\s*({NUM})\s*(%)?", t):
        pairs.append((_q(m[1]), _q(m[3])))
        pct = pct or bool(m[4])
    if len(pairs) < 3:
        par = [(_q(m[1]), _q(m[2])) for m in re.finditer(
            rf"(?<![\w.])({SNUM})\s*\(\s*(?:(?:weight(?:ed|ing)?|worth|w)\s*(?:of|=|:|at)?\s*)?({NUM})\s*%\s*\)", t)]
        if len(par) > len(pairs) and len(par) >= 2:
            pairs, pct = par, True
    if len(pairs) < 2:
        lab = _labelled_weights(t)
        if lab:
            pairs, pct = lab, True
    if len(pairs) < 2:
        pairs = [(_q(m[1]), _q(m[2])) for m in re.finditer(
            rf"(?<![\w.])({SNUM})\s+(?:appears|occurs|shows up|comes up)\s+(\d+)\s+times?\b", t)]
    if len(pairs) < 2:
        pairs = [(_q(m[2]), _q(m[1])) for m in re.finditer(
            rf"(?<![\w.])(\d+)\s+(?:\w+\s+)?(?:scored|got|earned|have|had)\s+(?:an?\s+)?({SNUM})(?!\s*%)", t)]
    if len(pairs) < 2:
        runs = [r for r in _runs(t) if len(r) >= 2]
        after = []
        for kw in re.finditer(r"\b(?:weights?|weighted|weightings?|frequenc(?:y|ies))\b", t):
            after = [r for r in runs if r[0][1] >= kw.end() and r[0][1] - kw.end() < 25] or after
        if not after:
            return None
        ws = after[0]
        vals = [r for r in runs if r is not ws and len(r) == len(ws)]
        if not vals:
            return None
        vs = vals[0]
        pct = "%" in t[ws[0][1]:ws[-1][2] + 1]
        pairs = [(v[0], w[0]) for v, w in zip(vs, ws)]
    if any(w < 0 for _, w in pairs) or sum(w for _, w in pairs) == 0 or len(pairs) > 100:
        return None
    sw = sum(w for _, w in pairs)
    swx = sum(w * x for x, w in pairs)
    mean = swx / sw
    pr = ctx.pr
    wshow = (lambda w: f"{_show(w)}%") if pct else _show
    terms = " + ".join(f"{wshow(w)} × {_show(x)}" for x, w in pairs)
    lo, hi = min(x for x, _ in pairs), max(x for x, _ in pairs)
    return _sol("statistics", ctx, "x̄ = Σ(w · x) / Σw  (weighted mean)",
                [f"values {', '.join(_show(x) for x, _ in pairs)}", f"weights {', '.join(wshow(w) for _, w in pairs)}"],
                [f"Σ(w · x) = {terms} = {_show(swx)}{'%' if pct else ''}",
                 f"Σw = {wshow(sw)}, so x̄ = {_show(swx)} / {_show(sw)}"],
                _val(mean, pr), f"{_val(mean, pr)} lies between the smallest ({_show(lo)}) and largest ({_show(hi)}) value ✓")


def _labelled_weights(t: str) -> list[tuple[F, F]] | None:
    """"homework 20%, midterm 30%, final exam 50% ... 88 on homework, 75 on the midterm, 92 on the final"."""
    skip = r"(?:\s+(?:exam|test|grade|score|mark|paper|assignment)s?)?"
    ws: dict[str, F] = {}
    for m in re.finditer(rf"\b([a-z]+){skip}\s*(?:is|=|:|counts for|worth|weighted at|at)?\s*({NUM})\s*%", t):
        if m[1] not in ("is", "and", "the", "of", "at", "for", "worth", "by", "weighted", "follows", "as"):
            ws.setdefault(m[1], _q(m[2]))
    if len(ws) < 2:
        return None
    vs: dict[str, F] = {}
    for m in re.finditer(rf"(?<![\w.])({NUM})(?!\s*%)\s+(?:on|in|for)\s+(?:the\s+|her\s+|his\s+|my\s+|their\s+)?([a-z]+)", t):
        vs.setdefault(m[2], _q(m[1]))
    for m in re.finditer(rf"\b([a-z]+){skip}\s*(?:score|grade|mark|average)?\s*(?:of|was|is|=|:)?\s*({NUM})\b(?!\s*%)", t):
        if m[1] in ws:
            vs.setdefault(m[1], _q(m[2]))
    if not all(k in vs for k in ws):
        return None
    return [(vs[k], w) for k, w in ws.items()]


def missing_value(ctx: _Ctx) -> Solution | None:
    """"The mean of 5 numbers is 12; four are 10, 11, 13, 14 — the fifth?" and "what do I need on the next test to
    average 85?" → n · target − (sum of the others)."""
    t = ctx.c
    m = re.search(rf"\b(?:mean|average)\s+of\s+(?:the\s+|these\s+|my\s+)?(\d+)\s+(?:\w+\s+)?(?:numbers|values|scores|tests|"
                  rf"items|integers|marks|observations|results|data points|exams|quizzes|students|games)\s+"
                  rf"(?:is|was|=|equals|comes to)\s+({SNUM})", t)
    if m:
        n, target, span = int(m[1]), _q(m[2]), m.span()
    else:
        m = re.search(rf"\b(?:need|needs|needed|have to|has to|must)\b.*?\b(?:to\s+(?:get|have|reach|end up with|bring\s+\w+\s+up\s+to|"
                      rf"raise\s+\w+\s+to)\s+(?:an?\s+)?(?:\w+\s+)?(?:average|mean)\s+(?:of\s+)?|to\s+average\s+|"
                      rf"(?:an?\s+)?(?:average|mean)\s+of\s+)({SNUM})", t)
        if not m or not re.search(r"\b(?:next|final|last|another|1 more|one more|remaining|\d+(?:st|nd|rd|th)|"
                                  r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\b", t):
            return None
        n, target, span = None, _q(m[1]), m.span(1)
    rest = _blank(t, [span])
    run = _best_run(rest, 1)
    if not run:
        return None
    xs = [v for v, *_ in run]
    if n is None:
        o = re.search(r"\b(\d+)(?:st|nd|rd|th)\b|\b(" + "|".join(_ORDINAL) + r")\b", rest)
        n = int(o[1]) if o and o[1] else (_ORDINAL[o[2]] if o and o[2] not in ("first",) else len(xs) + 1)
    if n != len(xs) + 1 or n < 2:
        return None
    need = n * target - sum(xs)
    pr = ctx.pr
    note = ""
    if re.search(r"\b(?:test|exam|quiz|score|mark|grade)s?\b", t) and need > 100 and all(x <= 100 for x in xs):
        note = " (more than 100, so not reachable on a 100-point test)"
    return _sol("statistics", ctx, "missing value = n × target mean − (sum of the others)",
                [f"n = {n}", f"target mean = {_show(target)}", f"others {', '.join(_show(x) for x in xs)} (sum {_show(sum(xs))})"],
                f"{n} × {_show(target)} − {_show(sum(xs))} = {_show(n * target)} − {_show(sum(xs))}",
                _val(need, pr) + note,
                f"({_show(sum(xs))} + {_show(need)}) / {n} = {_show((sum(xs) + need) / n)} ✓")


# ---------------------------------------------------------------- binomial engine (coins, dice faces, trials)

def _binom_terms(n: int, p: F, ks) -> F:
    q = 1 - p
    return sum(math.comb(n, k) * p ** k * q ** (n - k) for k in ks)


def _binom_float(n: int, p: float, ks) -> float:
    if p in (0, 1):
        return float(sum(1 for k in ks if k == (n if p == 1 else 0)))
    lp, lq = math.log(p), math.log1p(-p)
    return sum(math.exp(math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1) + k * lp + (n - k) * lq)
               for k in ks)


def _event_range(cmp: str | None, k: int, n: int) -> tuple[int, int] | None:
    cmp = (cmp or "exactly").strip()
    if cmp in ("exactly", "precisely"):
        lo, hi = k, k
    elif cmp in ("at least", "no fewer than", "no less than", "not less than"):
        lo, hi = k, n
    elif cmp in ("at most", "no more than", "not more than", "up to"):
        lo, hi = 0, k
    elif cmp in ("more than", "greater than", "over"):
        lo, hi = k + 1, n
    elif cmp in ("fewer than", "less than", "under"):
        lo, hi = 0, k - 1
    else:
        return None
    return (lo, hi) if 0 <= lo <= hi <= n else None


def _event_label(lo: int, hi: int, n: int) -> str:
    if lo == hi:
        return f"X = {lo}"
    if hi == n:
        return f"X ≥ {lo}"
    if lo == 0:
        return f"X ≤ {hi}"
    return f"{lo} ≤ X ≤ {hi}"


def _binomial(ctx: _Ctx, kind: str, n: int, p: F, lo: int, hi: int, known: list[str], what: str,
              fair_count: tuple[int, str] | None = None) -> Solution | None:
    """P(lo ≤ X ≤ hi) for X ~ B(n, p), summing the shorter side (direct or complement) and checking with the other."""
    if not 0 <= lo <= hi <= n or n > MAX_N or not 0 <= p <= 1:
        return None
    pr, q = ctx.pr, 1 - p
    label = _event_label(lo, hi, n)
    inside = range(lo, hi + 1)
    outside = [k for k in range(n + 1) if k < lo or k > hi]
    exact = n <= 400
    if exact:
        val = _binom_terms(n, p, inside)
        other = 1 - _binom_terms(n, p, outside)
    else:
        val = _binom_float(n, float(p), inside)
        other = 1 - _binom_float(n, float(p), outside)
    ps, qs = _show(p), _show(q)
    if lo == hi:
        sub = (f"P({label}) = C({n}, {lo}) × ({ps})^{lo} × ({qs})^{n - lo}"
               + (f" = {math.comb(n, lo)} × {_show(p ** lo)} × {_show(q ** (n - lo))}" if exact and n <= 60 else ""))
    elif len(inside) <= len(outside) + 1 or len(outside) > 6:
        shown = ", ".join(f"P({k})" for k in list(inside)[:6]) + (" …" if len(inside) > 6 else "")
        sub = f"P({label}) = sum of {shown}" if len(inside) > 1 else f"P({label}) = P({lo})"
        if exact and len(inside) <= 6 and n <= 60:
            sub += " = " + " + ".join(_show(_binom_terms(n, p, [k])) for k in inside)
    else:
        comp = _event_label(*((0, lo - 1) if lo > 0 else (hi + 1, n)), n) if len(outside) and (lo == 0 or hi == n) else \
            "the rest"
        sub = (f"P({label}) = 1 − P({comp}) = 1 − ("
               + " + ".join(_show(_binom_terms(n, p, [k])) if exact else f"P({k})" for k in outside) + ")")
    answer = _prob(val, pr)
    if fair_count:
        total_outcomes, unit = fair_count
        fav = val * total_outcomes
        check = f"counting: {_int(int(fav))} of the {_int(total_outcomes)} equally likely {unit} ✓" if \
            isinstance(fav, F) and fav.denominator == 1 else ""
    else:
        check = ""
    if not check:
        check = f"the complement gives the same: 1 − P(not {label}) = {_prob(other, pr)} ✓"
    return _sol(kind, ctx, "P(X = k) = C(n, k) · p^k · (1 − p)^(n − k)  (binomial: n independent trials, success "
                           "probability p)", known + [f"want P({label}), X = {what}"], sub, answer, check)


def _binom_moments(ctx: _Ctx, kind: str, n: int, p: F, known: list[str], what: str) -> Solution | None:
    t, pr = ctx.c, ctx.pr
    want_var = bool(re.search(r"\bvariance\b|\bvar\b", t))
    want_sd = bool(re.search(r"\bstandard deviation\b|\bsd\b|\bs\.d\b|\bstd\b|\bstdev\b|\bspread\b", t))
    want_mean = bool(re.search(r"\bmean\b|\bexpect|\baverage\b|\be\s*\(\s*x\s*\)", t)) or not (want_var or want_sd)
    mean, var = n * p, n * p * (1 - p)
    parts, subs = [], []
    if want_mean:
        subs.append(f"E(X) = n·p = {n} × {_show(p)} = {_show(mean)}")
        parts.append(("mean", _val(mean, pr), True))
    if want_var or want_sd:
        subs.append(f"Var(X) = n·p·(1 − p) = {n} × {_show(p)} × {_show(1 - p)} = {_show(var)}")
    if want_var:
        parts.append(("variance", _val(var, pr), True))
    if want_sd:
        root = _sqrt_exact(var)
        if root is None:
            subs.append(f"SD = √{_show(var)} = {sym_fmt(sp.sqrt(sp.Rational(var.numerator, var.denominator)))}")
        parts.append(("sd", _val(root, pr) if root is not None else pr.dec(math.sqrt(var)), root is not None))
    answer = parts[0][1] if len(parts) == 1 else "; ".join(f"{a} {'=' if e else '≈'} {b}" for a, b, e in parts)
    return _sol(kind, ctx, "E(X) = n·p, Var(X) = n·p·(1 − p), SD = √Var  (binomial)", known + [f"X = {what}"], subs,
                answer, f"0 ≤ {_show(mean)} ≤ n = {n} ✓" if want_mean else "")


# ---------------------------------------------------------------- the binomial distribution, written out

def binomial(ctx: _Ctx) -> Solution | None:
    t = ctx.c
    m = re.search(rf"(?:~\s*|\b)(?:b|bin|binom|binomial)\s*\(\s*(\d+)\s*,\s*({PNUM})\s*\)", t)
    if m:
        n, p = int(m[1]), _q(m[2])
        span = m.span()
    elif re.search(r"\bbinomial", t):
        mn = re.search(r"\bn\s*=\s*(\d+)\b", t) or re.search(r"\b(\d+)\s+(?:independent\s+)?(?:trials|attempts|tries)\b", t)
        mp = re.search(rf"\bp\s*=\s*({PNUM})", t) or re.search(
            rf"\b(?:probability|chance)\s+(?:of\s+(?:a\s+)?success\s+)?(?:is\s+|=\s*|of\s+)?({PNUM})", t)
        if not (mn and mp):
            return None
        n, p = int(mn[1]), _q(mp[1])
        span = (min(mn.start(), mp.start()), max(mn.end(), mp.end()))
    else:
        return None
    if not 0 <= p <= 1 or n < 1 or n > MAX_N:
        return None
    known = [f"n = {n}", f"p = {_show(p)}"]
    rest = _blank(t, [span])
    q = _cmp_query(rest, n)
    if q:
        return _binomial(ctx, "probability", n, p, q[0], q[1], known, "number of successes")
    if re.search(r"\bmean\b|\bexpect|\baverage\b|\bvariance\b|\bstandard deviation\b|\bsd\b|\bstd\b|\be\s*\(\s*x", rest):
        return _binom_moments(ctx, "probability", n, p, known, "number of successes")
    return None


def _cmp_query(s: str, n: int) -> tuple[int, int] | None:
    """P(X = 3), P(X ≥ 8), 'exactly 3', 'at least 8', '7 or more', 'between 2 and 4' → (lo, hi)."""
    m = re.search(r"p\s*\(\s*x\s*(<=|>=|=|<|>)\s*(\d+)\s*\)", s)
    if m:
        k = int(m[2])
        return _event_range({"=": "exactly", "<=": "at most", ">=": "at least", "<": "fewer than", ">": "more than"}[m[1]], k, n)
    m = re.search(r"p\s*\(\s*(\d+)\s*(<=|<)\s*x\s*(<=|<)\s*(\d+)\s*\)", s)
    if m:
        lo = int(m[1]) + (m[2] == "<")
        hi = int(m[4]) - (m[3] == "<")
        return (lo, hi) if 0 <= lo <= hi <= n else None
    m = re.search(r"\bbetween\s+(\d+)\s+and\s+(\d+)\b", s)
    if m:
        lo, hi = int(m[1]), int(m[2])
        return (lo, hi) if 0 <= lo <= hi <= n else None
    m = re.search(r"\b(\d+)\s+or\s+(more|greater|higher|fewer|less|lower)\b", s)
    if m:
        k = int(m[1])
        return _event_range("at least" if m[2] in ("more", "greater", "higher") else "at most", k, n)
    m = re.search(rf"\b({CMPW})\s+(\d+)\b", s)
    if m:
        return _event_range(m[1], int(m[2]), n)
    return None


# ---------------------------------------------------------------- coins

_SIDE = r"(heads?|tails?)"


def coins(ctx: _Ctx) -> Solution | None:
    t = ctx.c
    if not re.search(r"\bcoins?\b|\bheads?\b|\btails?\b|\bflip|\btoss", t):
        return None
    if re.search(r"\bdice\b|\bdie\b|\bcards?\b|\bdeck\b|\$|\bwin\b|\blose\b", ctx.m):
        return None
    if not re.search(r"\bcoins?\b|\bheads\b|\btails\b", t):
        return None
    p_heads, p_note = F(1, 2), "fair coin"
    bm = re.search(rf"(?:p\s*\(\s*(heads?|h|tails?|t)\s*\)|probability of (?:getting |landing |a |an )*{_SIDE}|"
                   rf"chance of (?:a |an )?{_SIDE}|{_SIDE} (?:with )?(?:a )?(?:probability|chance)(?: of)?|"
                   rf"lands? (?:on )?{_SIDE}|comes? up {_SIDE}|shows? {_SIDE})\s*(?:is|=|of|:)?\s*({PNUM})", t)
    spans = []
    if bm:
        side = next(g for g in bm.groups()[:-1] if g)
        v = _q(bm.groups()[-1])
        if not 0 <= v <= 1:
            return None
        p_heads = v if side.startswith("h") else 1 - v
        p_note = f"P(heads) = {_show(p_heads)}"
        spans.append(bm.span())
    elif re.search(r"\b(?:biased|unfair|weighted|loaded)\b", t):
        mp = re.search(rf"\bp\s*=\s*({PNUM})", t)
        if not mp:
            return None
        p_heads, p_note = _q(mp[1]), f"P(heads) = {_show(_q(mp[1]))}"
        spans.append(mp.span())
    t2 = _blank(t, spans)
    fair = p_heads == F(1, 2)
    # what is asked: count of heads/tails
    target = lo = hi = None
    kspan = None
    for rx, kindk in ((rf"\bbetween\s+(\d+)\s+and\s+(\d+)\s+{_SIDE}", "between"),
                      (rf"\b(\d+)\s+or\s+(more|fewer|less|greater|higher|lower)\s+{_SIDE}", "ormore"),
                      (rf"\b(\d+)\s+{_SIDE}\s+in a row\b|\b{_SIDE}\s+(\d+)\s+times\s+in a row\b", "row"),
                      (rf"\bmore\s+(heads|tails)\s+than\s+(heads|tails)\b", "more"),
                      (rf"\b(?:same|equal)\s+number\s+of\s+(heads|tails)\s+(?:and|as)\s+(?:heads|tails)\b|"
                       rf"\bas many (heads|tails) as\b", "equal"),
                      (rf"\ball\s+{_SIDE}\b|\b{_SIDE}\s+(?:every time|each time|on (?:every|each|all)\b)", "all"),
                      (rf"\b(?:no|zero|0)\s+{_SIDE}\b|\bnever\s+(?:get\s+|land\s+|see\s+|lands?\s+(?:on\s+)?)?{_SIDE}", "none"),
                      (rf"\b(?:({CMPW})\s+)?(\d+)\s+(?:of\s+(?:them|the\s+\w+)\s+(?:are\s+|being\s+|land(?:ing)?\s+(?:on\s+)?|"
                       rf"show(?:ing)?\s+|come up\s+)?)?{_SIDE}\b(?:\s+or\s+(more|fewer|less|greater|higher|lower))?", "cmp"),
                      (rf"\b{_SIDE}\s+(?:({CMPW})\s+)?(\d+)\s+times?\b(?:\s+or\s+(more|fewer|less))?", "times"),
                      (r"\b([ht](?:\s*,?\s*[ht]){1,11})\b(?=.*\b(?:order|sequence|exactly that|in that order|followed)\b)|"
                       r"\b(?:order|sequence)\b.*?\b([ht](?:\s*,?\s*[ht]){1,11})\b", "seq")):
        m = re.search(rx, t2)
        if m:
            kspan = m.span()
            target = kindk
            km = m
            break
    if target is None:
        return None
    rest = _blank(t2, [kspan])
    mn = (re.search(r"\b(\d+)\s+(?:fair\s+|biased\s+)?(?:coin\s+)?(?:flips|tosses|throws|times|trials|tries|coins)\b", rest)
          or re.search(r"\b(?:flip|flipped|flipping|flips|toss|tossed|tossing|tosses|throw|throws|thrown)\s+(?:it\s+|a\s+|the\s+)?"
                       r"(?:fair\s+|biased\s+|unfair\s+)?(?:coin\s+)?(\d+)\s+times\b", rest))
    n = int(mn[1]) if mn else None
    side_of = (lambda s: "heads" if s.startswith("h") else "tails")
    if target == "seq":
        letters = re.sub(r"[^ht]", "", km[1] or km[2])
        if n is not None and n != len(letters):
            return None
        h, tl = letters.count("h"), letters.count("t")
        val = p_heads ** h * (1 - p_heads) ** tl
        return _sol("probability", ctx, "P(sequence) = product of the probabilities of each flip  (independent flips)",
                    [p_note, f"sequence {letters.upper()}"],
                    " × ".join(_show(p_heads if c == "h" else 1 - p_heads) for c in letters), _prob(val, ctx.pr),
                    f"1 of the 2^{len(letters)} = {2 ** len(letters)} equally likely sequences ✓" if fair else "")
    if target == "row":
        r = int(km[1] or km[4])
        side = side_of(km[2] or km[3])
        ps = p_heads if side == "heads" else 1 - p_heads
        if n is None or n == r:
            val = ps ** r
            return _sol("probability", ctx, "P(r in a row) = p^r  (independent flips)", [p_note, f"r = {r} {side}"],
                        f"({_show(ps)})^{r}", _prob(val, ctx.pr),
                        f"1 of the 2^{r} = {2 ** r} equally likely sequences ✓" if fair else "")
        if n < r or n > 200:
            return None
        # at least one run of r in n flips: track the current run length
        state = [F(0)] * r
        state[0] = F(1)
        done = F(0)
        for _ in range(n):
            new = [F(0)] * r
            for run_len, pr_ in enumerate(state):
                if not pr_:
                    continue
                if run_len + 1 == r:
                    done += pr_ * ps
                else:
                    new[run_len + 1] += pr_ * ps
                new[0] += pr_ * (1 - ps)
            state = new
        return _sol("probability", ctx, "P(a run of r in n flips) = 1 − P(no run of r), tracking the current run length "
                                        "flip by flip", [p_note, f"n = {n} flips", f"run of {r} {side}"],
                    f"after {n} flips, P(no run) = {_show(sum(state))}", _prob(done, ctx.pr),
                    f"{_show(done)} + {_show(sum(state))} = 1 ✓")
    if n is None:
        if target in ("cmp", "times") and re.search(r"\b(?:a|the|1)\s+(?:fair\s+)?coin\b", t) and not re.search(r"\btimes\b", rest):
            n = 1
        else:
            return None
    if n < 1 or n > MAX_N:
        return None
    if target == "between":
        lo, hi, side = int(km[1]), int(km[2]), side_of(km[3])
    elif target == "ormore":
        side = side_of(km[3])
        rng = _event_range("at least" if km[2] in ("more", "greater", "higher") else "at most", int(km[1]), n)
        if not rng:
            return None
        lo, hi = rng
    elif target == "more":
        side = side_of(km[1])
        lo, hi = n // 2 + 1, n
    elif target == "equal":
        if n % 2:
            return None
        side, lo, hi = "heads", n // 2, n // 2
    elif target == "all":
        side, lo, hi = side_of(km[1] or km[2]), n, n
    elif target == "none":
        side, lo, hi = side_of(km[1] or km[2]), 0, 0
    elif target == "cmp":
        side = side_of(km[3])
        cmpw = km[1]
        if km[4]:
            cmpw = "at least" if km[4] in ("more", "greater", "higher") else "at most"
        rng = _event_range(cmpw, int(km[2]), n)
        if not rng:
            return None
        lo, hi = rng
    else:  # times
        side = side_of(km[1])
        cmpw = km[2]
        if km[4]:
            cmpw = "at least" if km[4] == "more" else "at most"
        rng = _event_range(cmpw, int(km[3]), n)
        if not rng:
            return None
        lo, hi = rng
    p = p_heads if side == "heads" else 1 - p_heads
    if re.search(r"\bexpect|\bmean\b|\baverage number\b|\bvariance\b|\bstandard deviation\b", rest) and target == "cmp" \
            and not re.search(rf"\b(?:{CMPW})\b", t2):
        pass
    known = [f"n = {n} flip{'s' if n > 1 else ''}", f"p = {_show(p)} ({side}, {p_note})"]
    return _binomial(ctx, "probability", n, p, lo, hi, known, f"number of {side}",
                     (2 ** n, "sequences") if fair and n <= 30 else None)


def coin_moments(ctx: _Ctx) -> Solution | None:
    t = ctx.c
    m = re.search(rf"\b(?:expected|mean|average)\s+(?:number|count|value)?\s*(?:of\s+)?(?:the\s+)?(?:number\s+of\s+)?{_SIDE}|"
                  rf"\bhow many {_SIDE}\s+(?:would|should|do|can|will|might)\s+(?:you|i|we|one)\s+expect|"
                  rf"\b(?:variance|standard deviation|sd)\s+(?:of\s+)?(?:the\s+)?(?:number\s+of\s+)?{_SIDE}", t)
    if not m or re.search(r"\bdice\b|\bdie\b|\bcards?\b|\$", ctx.m):
        return None
    side = "heads" if (m[1] or m[2] or m[3]).startswith("h") else "tails"
    mn = re.search(r"\b(\d+)\s+(?:coin\s+)?(?:flips|tosses|throws|times|trials|coins)\b", t)
    if not mn:
        return None
    n = int(mn[1])
    p = F(1, 2)
    bm = re.search(rf"\bp\s*(?:\(\s*(?:heads?|h)\s*\))?\s*=\s*({PNUM})|\b(?:lands?|comes? up)\s+heads\s+({PNUM})", t)
    if bm:
        p = _q(bm[1] or bm[2])
    if side == "tails":
        p = 1 - p
    return _binom_moments(ctx, "probability", n, p, [f"n = {n} flips", f"p = {_show(p)} ({side})"], f"number of {side}")


# ---------------------------------------------------------------- dice

_FACE_PHRASE = (r"(?:not\s+(?:a\s+|an\s+)?)?(?:(?:an?\s+)?(?:even|odd|prime)(?:\s+number)?|(?:an?\s+)?(?:number\s+)?(?:greater than|"
                r"more than|bigger than|higher than|larger than|less than|smaller than|lower than|fewer than|at least|at most|"
                r"over|under|above|below)\s+(?:an?\s+)?\d+|(?:an?\s+)?multiple of \d+|(?:an?\s+)?\d+(?:\s*(?:,|or)\s*(?:an?\s+)?\d+)*)")


def _face_set(phrase: str, sides: int) -> set[int] | None:
    s = phrase.strip()
    neg = bool(re.match(r"not\s", s))
    s = re.sub(r"^not\s+(?:a\s+|an\s+)?", "", s)
    s = re.sub(r"^an?\s+", "", s)
    faces = set(range(1, sides + 1))
    if s.startswith("even"):
        out = {f for f in faces if f % 2 == 0}
    elif s.startswith("odd"):
        out = {f for f in faces if f % 2}
    elif s.startswith("prime"):
        out = {f for f in faces if f > 1 and all(f % d for d in range(2, int(f ** 0.5) + 1))}
    elif m := re.match(r"multiple of (\d+)", s):
        out = {f for f in faces if f % int(m[1]) == 0}
    elif m := re.match(r"(?:number\s+)?(greater than|more than|bigger than|higher than|larger than|over|above|less than|"
                       r"smaller than|lower than|fewer than|under|below|at least|at most)\s+(?:an?\s+)?(\d+)", s):
        k = int(m[2])
        w = m[1]
        if w == "at least":
            out = {f for f in faces if f >= k}
        elif w == "at most":
            out = {f for f in faces if f <= k}
        elif w in ("less than", "smaller than", "lower than", "fewer than", "under", "below"):
            out = {f for f in faces if f < k}
        else:
            out = {f for f in faces if f > k}
    else:
        vals = {int(x) for x in re.findall(r"\d+", s)}
        if not vals or not vals <= faces:
            return None
        out = vals
    return faces - out if neg else out


def _sum_counts(nd: int, sides: int) -> list[int]:
    counts = [1]
    for _ in range(nd):
        new = [0] * (len(counts) + sides)
        for i, c in enumerate(counts):
            if c:
                for f in range(1, sides + 1):
                    new[i + f] += c
        counts = new
    return counts  # counts[s] = ways to roll a total of s


_SUMCMP = (r"exactly|at least|at most|no more than|no less than|not more than|more than|greater than|bigger than|larger than|"
           r"higher than|over|above|less than|fewer than|smaller than|lower than|under|below")


def _num_pred(cmpw: str | None, vals: list[int], tail: str | None):
    if tail:
        cmpw = "at least" if tail in ("more", "higher", "greater", "above", "over") else "at most"
    k = vals[0]
    if not cmpw or cmpw == "exactly":
        sv = set(vals)
        return (lambda s: s in sv), " or ".join(str(v) for v in vals)
    if cmpw == "at least" or cmpw in ("no less than",):
        return (lambda s: s >= k), f"≥ {k}"
    if cmpw in ("at most", "no more than", "not more than"):
        return (lambda s: s <= k), f"≤ {k}"
    if cmpw in ("less than", "fewer than", "smaller than", "lower than", "under", "below"):
        return (lambda s: s < k), f"< {k}"
    return (lambda s: s > k), f"> {k}"


def dice(ctx: _Ctx) -> Solution | None:
    t = ctx.c
    if not re.search(r"\bdice\b|\bdie\b|\b\d*d\d+\b|\bsnake eyes\b|\bboxcars\b|\brolls\b|\brolling\b", t):
        return None
    if re.search(r"\bcoins?\b|\bcards?\b|\bdeck\b|\bdie (?:out|off|down)\b|\$|\bwin\b|\bprize\b", ctx.m):
        return None
    sides, nd = 6, None
    md = re.search(r"\b(\d+)?\s?d(\d+)\b", t)
    if md and int(md[2]) >= 2:
        sides, nd = int(md[2]), int(md[1]) if md[1] else 1
    ms = re.search(r"\b(\d+)[- ]?(?:sided|faced)\b", t)
    if ms:
        sides = int(ms[1])
    adj = r"(?:(?:fair|standard|regular|ordinary|normal|unbiased|identical|\d+[- ]?(?:sided|faced))\s+)*"
    mn = re.search(rf"\b(\d+)\s+{adj}(?:dice|die)\b", t)
    if mn:
        nd = int(mn[1])
    elif nd is None and re.search(rf"\b(?:a|an|the|one|single|1)\s+{adj}(?:die|dice)\b|\bdie\b", t) and \
            not re.search(r"\b(?:the|two|pair|both)\s+dice\b", t):
        nd = 1
    if not 2 <= sides <= 100 or (nd is not None and not 1 <= nd <= 50):
        return None
    mr = re.search(r"\b(\d+)\s+(?:rolls|throws|tosses|times|goes|turns|tries|attempts)\b", t)
    rolls = int(mr[1]) if mr else None
    pr = ctx.pr
    count_mode = bool(re.search(r"\bhow many (?:ways|outcomes|combinations|possibilities)\b|\bnumber of (?:ways|outcomes)\b", t))
    t2 = re.sub(rf"\b(sum|total|product|difference)\s+of\s+(?:the\s+)?(?:\d+\s+)?{adj}(?:dice|die|numbers(?:\s+(?:rolled|shown|showing))?|"
                rf"faces|rolls|scores|values)\b", r"\1", t)

    # expected value / variance of a roll or of the sum
    if re.search(r"\bexpect|\bmean\b|\baverage\b|\be\s*\(\s*x\s*\)|\bvariance\b", t) and not _asks_prob(t):
        mf = re.search(r"\b(?:number of|many)\s+(\d+)s\b", t)
        if mf and rolls:
            p = F(1, sides)
            return _binom_moments(ctx, "probability", rolls * (nd or 1), p,
                                  [f"n = {rolls * (nd or 1)} rolls", f"p = 1/{sides} (a {mf[1]})"], f"number of {mf[1]}s")
        k = nd or (2 if re.search(r"\bdice\b", t) and re.search(r"\bsum|\btotal", t) else 1)
        mean = F(k * (sides + 1), 2)
        var = F(k * (sides * sides - 1), 12)
        if re.search(r"\bvariance\b", t):
            return _sol("probability", ctx, f"Var(one {sides}-sided die) = (s² − 1) / 12; variances add for independent dice",
                        [f"s = {sides}", f"{k} di{'ce' if k > 1 else 'e'}"],
                        f"{k} × ({sides}² − 1) / 12 = {_show(var)}", _val(var, pr))
        return _sol("probability", ctx, "E(one die) = (1 + 2 + … + s) / s = (s + 1) / 2; expectations add",
                    [f"s = {sides}", f"{k} di{'ce' if k > 1 else 'e'}"],
                    f"{k} × ({sides} + 1) / 2 = {_show(mean)}", _val(mean, pr),
                    f"the outcomes are symmetric about {_show(mean)} ✓")

    def finish(favourable: int, total: int, formula: str, known: list[str], listing: str, check: str = ""):
        if count_mode:
            return _sol("probability", ctx, formula.replace("P = favourable / total", "count the favourable outcomes"),
                        known, listing or f"{favourable} outcomes", _int(favourable), check)
        val = F(favourable, total)
        return _sol("probability", ctx, formula, known, (listing + "; " if listing else "") + f"P = {favourable} / {total}",
                    _prob(val, pr), check)

    def repeat(p1: F, what: str, n: int, mode: str):
        if mode == "all":
            val = p1 ** n
            return _sol("probability", ctx, "P(it happens every time) = p^n  (independent rolls)",
                        [f"p = {_show(p1)} ({what})", f"n = {n}"], f"({_show(p1)})^{n}", _prob(val, pr))
        if mode == "none":
            val = (1 - p1) ** n
            return _sol("probability", ctx, "P(never) = (1 − p)^n  (independent rolls)",
                        [f"p = {_show(p1)} ({what})", f"n = {n}"], f"(1 − {_show(p1)})^{n} = ({_show(1 - p1)})^{n}",
                        _prob(val, pr))
        val = 1 - (1 - p1) ** n
        chk = ""
        if p1.denominator ** n <= 10 ** 12:
            tot = p1.denominator ** n
            chk = f"counting: {_int(tot)} − {_int((p1.denominator - p1.numerator) ** n)} = {_int(int(val * tot))} of {_int(tot)} outcomes ✓"
        return _sol("probability", ctx, "P(at least once) = 1 − P(never) = 1 − (1 − p)^n  (independent rolls)",
                    [f"p = {_show(p1)} ({what})", f"n = {n}"], f"1 − ({_show(1 - p1)})^{n} = 1 − {_show((1 - p1) ** n)}",
                    _prob(val, pr), chk)

    rep_mode = None
    if rolls and rolls > 1:
        if re.search(r"\bin a row\b|\bevery time\b|\beach time\b|\ball \d+ times\b|\b(?:each|every|all) (?:of the )?(?:\d+ )?(?:rolls|throws)\b|\bconsecutive", t):
            rep_mode = "all"
        elif re.search(r"\bat least 1 time\b|\bat least once\b|\bat least 1\b", t):
            rep_mode = "least"
        elif re.search(r"\bnever\b|\bnot once\b|\bno(?:ne of the)? (?:rolls|throws)\b", t):
            rep_mode = "none"

    # doubles
    mdbl = re.search(r"\b(not\s+(?:\w+\s+)?)?(?:doubles?|the same (?:number|value|face|result)|matching (?:numbers|dice|faces))\b|"
                     r"\bboth (?:dice\s+)?(?:show|land on|are|come up|give)?\s*the same\b", t)
    mdouble_face = re.search(r"\bdouble\s+(\d+)s?\b|\bsnake eyes\b|\bboxcars\b", t)
    if mdouble_face or mdbl:
        k = nd or 2
        if k < 2 or sides ** k > 10 ** 6:
            return None
        total = sides ** k
        if mdouble_face:
            face = int(mdouble_face[1]) if mdouble_face[1] else (1 if "snake" in mdouble_face[0] else sides)
            if not 1 <= face <= sides:
                return None
            fav, what = 1, f"double {face}"
        else:
            fav, what = sides, "doubles"
        p1 = F(fav, total)
        if mdbl and mdbl[1]:
            p1, what, fav = 1 - p1, "not doubles", total - fav
        known = [f"{k} fair {sides}-sided dice: {sides}^{k} = {total} equally likely outcomes"]
        if rep_mode and rolls:
            return repeat(p1, what, rolls, rep_mode)
        return finish(fav, total, "P = favourable / total  (all outcomes equally likely)", known,
                      f"{what}: {fav} outcome{'s' if fav != 1 else ''}",
                      f"each of the {sides} first-die values has exactly 1 matching second value: {sides} / {total} ✓"
                      if what == "doubles" else "")

    # sum / product / difference of several dice
    msum = (re.search(rf"\b(sum|total|product|difference)\s*(?:is|=|equals?|equal to|being|to be|that is|will be|was|shown|of)?\s*"
                      rf"(?:a\s+)?(?:({_SUMCMP})\s+)?(\d+)((?:\s*(?:,|or)\s*\d+)*)(?:\s+or\s+(more|higher|greater|above|over|"
                      rf"less|lower|fewer|below|under))?", t2)
            or re.search(rf"\b(adds? up to|adding up to|totals?|totalling|totaling)\s+(?:({_SUMCMP})\s+)?(\d+)((?:\s*(?:,|or)\s*\d+)*)"
                         rf"(?:\s+or\s+(more|higher|greater|less|lower|fewer))?", t2))
    mpar = re.search(r"\b(sum|total|product)\s*(?:is\s+|being\s+|will be\s+)?(?:an?\s+)?(even|odd|prime)(?:\s+number)?\b|"
                     r"\b(sum|total|product)\s*(?:is\s+)?(?:an?\s+)?(?:multiple of|divisible by)\s+(\d+)", t2)
    k_dice = nd or (2 if re.search(r"\bdice\b", t) else None)
    if (msum or mpar) and k_dice and k_dice >= 2:
        op = (msum[1] if msum else (mpar[1] or mpar[3]))
        op = {"adds up to": "sum", "add up to": "sum", "adding up to": "sum", "total": "sum", "totals": "sum",
              "totalling": "sum", "totaling": "sum"}.get(op, op)
        if mpar and not msum:
            if mpar[2]:
                pred = {"even": lambda s: s % 2 == 0, "odd": lambda s: s % 2 == 1,
                        "prime": lambda s: s > 1 and all(s % d for d in range(2, int(s ** 0.5) + 1))}[mpar[2]]
                desc = mpar[2]
            else:
                d = int(mpar[5])
                pred, desc = (lambda s: s % d == 0), f"a multiple of {d}"
        else:
            vals = [int(msum[3])] + [int(x) for x in re.findall(r"\d+", msum[4] or "")]
            pred, desc = _num_pred(msum[2], vals, msum[5])
        total = sides ** k_dice
        if op == "sum":
            counts = _sum_counts(k_dice, sides)
            fav_sums = [s for s in range(k_dice, k_dice * sides + 1) if pred(s)]
            fav = sum(counts[s] for s in fav_sums)
            listing = ""
            if k_dice == 2 and fav <= 12:
                outs = [(a, b) for a in range(1, sides + 1) for b in range(1, sides + 1) if pred(a + b)]
                listing = "favourable " + ", ".join(f"({a}, {b})" for a, b in outs)
            else:
                listing = "ways: " + ", ".join(f"total {s} → {counts[s]}" for s in fav_sums[:8]) + (" …" if len(fav_sums) > 8 else "")
            check = ""
            if k_dice == 2 and sides == 6 and len(fav_sums) == 1:
                s0 = fav_sums[0]
                check = f"two dice make a total of s in 6 − |s − 7| ways: 6 − |{s0} − 7| = {6 - abs(s0 - 7)} ✓"
            elif k_dice == 2:
                check = f"the totals {k_dice}…{k_dice * sides} have counts adding to {sum(counts)} = {total} ✓"
        else:
            if total > 10 ** 6 or (op == "difference" and k_dice != 2):
                return None
            fn = (lambda r: math.prod(r)) if op == "product" else (lambda r: abs(r[0] - r[1]))
            outs = [r for r in product(range(1, sides + 1), repeat=k_dice) if pred(fn(r))]
            fav = len(outs)
            listing = ("favourable " + ", ".join(str(r) for r in outs)) if fav <= 12 else f"{fav} favourable outcomes"
            check = ""
        if fav == 0 and not count_mode:
            return None
        known = [f"{k_dice} fair {sides}-sided dice: {sides}^{k_dice} = {_int(total)} equally likely outcomes",
                 f"want {op} {desc}"]
        if rep_mode and rolls:
            return repeat(F(fav, total), f"{op} {desc}", rolls, rep_mode)
        return finish(fav, total, "P = favourable / total  (all outcomes equally likely)", known, listing, check)

    # counts of a face over several dice or rolls: "at least one six in 4 rolls", "exactly 2 sixes with 5 dice"
    trials = (rolls or 1) * (nd or 1) if (rolls or (nd and nd > 1)) else None
    mfc = (re.search(r"\b(?:a|an)\s+(\d+)\s+(?:(exactly|at least|at most)\s+)?(\d+)\s+times?\b", t)
           or re.search(r"\b(?:(exactly|at least|at most|no more than|more than|fewer than|less than)\s+)?(\d+|no|zero)\s+"
                        r"(?:dice\s+|die\s+)?(?:shows?\s+|showing\s+|lands?\s+on\s+)?(?:an?\s+)?(\d+)(?:s|'s)?(?![\w-])"
                        r"(?!\s*(?:sided|faced|dice|die|rolls?|times|throws|tosses))", t))
    if mfc and trials:
        if mfc.re.pattern.startswith(r"\b(?:a|an)"):
            face, cmpw, k = int(mfc[1]), mfc[2], int(mfc[3])
        else:
            cmpw, k, face = mfc[1], (0 if mfc[2] in ("no", "zero") else int(mfc[2])), int(mfc[3])
        if 1 <= face <= sides and k <= trials:
            if re.search(r"\bin a row\b", t) and not cmpw:
                return repeat(F(1, sides), f"a {face}", trials, "all")
            rng = _event_range(cmpw, k, trials)
            if not rng:
                return None
            known = [f"n = {trials} roll{'s' if trials > 1 else ''}", f"p = 1/{sides} (a {face} on each roll)"]
            if rng == (1, trials):
                return repeat(F(1, sides), f"a {face}", trials, "least")
            if rng == (0, 0):
                return repeat(F(1, sides), f"a {face}", trials, "none")
            return _binomial(ctx, "probability", trials, F(1, sides), rng[0], rng[1], known, f"number of {face}s",
                             (sides ** trials, "outcomes") if sides ** trials <= 10 ** 9 else None)

    # one face (or a set of faces) on a roll, maybe repeated
    mone = re.search(rf"\b(?:roll(?:s|ed|ing)?|get(?:s|ting)?|throw(?:s|ing|n)?|land(?:s|ing)?\s+on|show(?:s|ing)?|obtain(?:ing)?|"
                     rf"comes?\s+up(?:\s+with)?|probability of|chance of|odds of|p\s*\()\s+({_FACE_PHRASE})(?![\w-])", t)
    mone = mone or re.search(rf"\b(?:the\s+)?(?:result|outcome|number|score)\s+(?:is|being|will be)\s+({_FACE_PHRASE})(?![\w-])", t)
    if mone:
        fs = _face_set(mone[1], sides)
        if fs is None or not fs:
            return None
        if nd and nd >= 2 and re.fullmatch(r"(?:an?\s+)?\d+", mone[1].strip()) and int(re.findall(r"\d+", mone[1])[0]) > sides:
            return None
        p1 = F(len(fs), sides)
        what = mone[1].strip()
        if (nd or 1) > 1 and not rolls:
            if re.fullmatch(r"(?:an?\s+)?\d+", what):  # "rolling a 7 with two dice" is the total
                s0 = int(re.findall(r"\d+", what)[0])
                counts = _sum_counts(nd, sides)
                if s0 >= len(counts) or counts[s0] == 0:
                    return None
                total = sides ** nd
                return finish(counts[s0], total, "P = favourable / total  (all outcomes equally likely)",
                              [f"{nd} fair {sides}-sided dice: {_int(total)} equally likely outcomes",
                               f"reading '{what}' with {nd} dice as the total"], f"ways to total {s0}: {counts[s0]}")
            return None
        if rep_mode and rolls:
            return repeat(p1, what, rolls, rep_mode)
        if rolls and rolls > 1:
            return None
        listed = ", ".join(str(f) for f in sorted(fs))
        return finish(len(fs), sides, "P = favourable / total  (one fair die, each face equally likely)",
                      [f"{sides} faces", f"favourable faces {listed}"], "", f"{len(fs)} + {sides - len(fs)} = {sides} faces ✓")
    return None


# ---------------------------------------------------------------- playing cards

DECK = [(r, s) for s in "hdcs" for r in range(1, 14)]
_RANK_WORD = {"ace": {1}, "king": {13}, "queen": {12}, "jack": {11}, "face": {11, 12, 13}, "picture": {11, 12, 13},
              "court": {11, 12, 13}, "royal": {11, 12, 13}, "number": set(range(2, 11)), "numbered": set(range(2, 11))}
_SUIT_WORD = {"heart": "h", "diamond": "d", "club": "c", "spade": "s"}
_CARD1 = (r"(?:(?:red|black)\s+)?(?:(?:aces?|kings?|queens?|jacks?|10s?|[2-9]s?)(?:\s+of\s+(?:hearts|diamonds|clubs|spades))?|"
          r"(?:face|picture|court|royal|number(?:ed)?)\s+cards?|hearts?|diamonds?|clubs?|spades?|(?:red|black)\s+cards?)(?![\w-])|"
          r"(?:red|black)(?:\s+ones?)?(?![\w-])")
CAT = rf"(?:not\s+(?:a\s+|an\s+)?)?(?:{_CARD1})(?:\s+or\s+(?:a\s+|an\s+)?(?:{_CARD1}))*"


def _card_one(a: str) -> set:
    color = suit = ranks = None
    if m := re.search(r"\b(red|black)\b", a):
        color = "hd" if m[1] == "red" else "cs"
    if m := re.search(r"\b(heart|diamond|club|spade)s?\b", a):
        suit = _SUIT_WORD[m[1]]
    if m := re.search(r"\b(ace|king|queen|jack|face|picture|court|royal|numbered|number)s?\b", a):
        ranks = _RANK_WORD[m[1]]
    elif m := re.search(r"\b(10|[2-9])s?\b", a):
        ranks = {int(m[1])}
    return {(r, s) for r, s in DECK if (color is None or s in color) and (suit is None or s == suit)
            and (ranks is None or r in ranks)}


def _card_set(phrase: str) -> tuple[set, str]:
    p = phrase.strip()
    neg = bool(re.match(r"not\s", p))
    p = re.sub(r"^not\s+(?:a\s+|an\s+)?", "", p)
    out: set = set()
    for a in re.split(r"\s+or\s+(?:a\s+|an\s+)?", p):
        out |= _card_one(a)
    if neg:
        out = set(DECK) - out
    return out, ("not " if neg else "") + p


def _hand_size(t: str) -> int | None:
    m = re.search(r"\b(\d+)[- ]card\s+(?:poker\s+|bridge\s+)?hands?\b|\bhands?\s+of\s+(\d+)\s+cards\b|"
                  r"\b(\d+)\s+cards?\s+(?:are\s+)?(?:dealt|in (?:a|the|your|my) hand)\b|\bdealt\s+(\d+)\s+cards\b", t)
    if m:
        return int(next(g for g in m.groups() if g))
    if re.search(r"\bpoker hands?\b", t):
        return 5
    if re.search(r"\bbridge hands?\b", t):
        return 13
    return None


def cards(ctx: _Ctx) -> Solution | None:
    t = ctx.c
    suity = r"\b(?:aces?|kings?|queens?|jacks?|hearts|spades|diamonds|clubs|face cards?)\b"
    drawy = r"\bwithout replacement\b|\bwith replacement\b|\bin a row\b|\bdraw(?:n|s|ing)?\b|\bdrew\b|\bdealt\b"
    if not re.search(r"\bcards?\b|\bdeck\b|\bpoker\b|\bbridge hand", t) and not (
            re.search(suity, t) and re.search(drawy, t)):
        return None
    if re.search(r"\bjokers?\b|\bdice\b|\bdie\b|\bcoins?\b|\btarot\b|\buno\b|\$|\bwin\b", ctx.m):
        return None
    pr = ctx.pr
    counting = bool(re.search(r"\bhow many\b|\bnumber of (?:ways|possible|different|distinct)\b|\bin how many ways\b", t))
    asks = _asks_prob(t) or bool(re.search(r"\bin a row\b|\bwithout replacement\b", t) and not counting)
    if not (counting or asks):
        return None
    repl = bool(re.search(r"\bwith replacement\b|\breplac(?:ed|ing) (?:it|the card|each)\b|\bput(?:s|ting)? (?:it|the card|each card) back\b|"
                          r"\breturn(?:ed|ing|s)? (?:it|the card|each card)\b|\breshuffl", t)) and \
        not re.search(r"\bwithout replacement\b|\bnot (?:replaced|put back|returned)\b|\bno replacement\b", t)
    hand = _hand_size(t)

    # conditional: P(king | face card)
    tc = re.sub(r"\s*\([^()|]*\)", "", t)
    tc = re.sub(r"\bwhats\b", "what's", tc)
    tc = re.sub(r"\bprob\b", "probability", tc)
    tc = re.sub(r"\bits\b", "it's", tc)
    for rx, ev_first in ((rf"p\s*\(\s*({CAT})\s*\|\s*({CAT})\s*\)", True),
                         (rf"(?:probability|chance|odds)\s+(?:that\s+)?(?:it(?:'s| is| was)\s+|the card is\s+|(?:of\s+)?(?:drawing\s+|getting\s+|picking\s+)?)"
                          rf"(?:a\s+|an\s+)?({CAT})\s*,?\s*(?:given|if|knowing)\s+(?:that\s+)?(?:it(?:'s| is| was)\s+|the card (?:is|was)\s+|"
                          rf"you(?:'ve)?\s+(?:drew|drawn|draw|got|have)\s+)?(?:a\s+|an\s+)?({CAT})", True),
                         (rf"(?:given|if|knowing)\s+(?:that\s+)?(?:it(?:'s| is| was)\s+|the card (?:is|was)\s+|a card is\s+|you(?:'ve)?\s+(?:drew|drawn|draw|got)\s+)?"
                          rf"(?:a\s+|an\s+)?({CAT})\s*,?\s*(?:what(?:'s| is)\s+)?(?:the\s+)?(?:probability|chance|odds)\s+(?:that\s+)?"
                          rf"(?:it(?:'s| is)\s+|the card is\s+)?(?:a\s+|an\s+)?({CAT})", False),
                         (rf"(?:it(?:'s| is| was)|turns out to be|is known to be)\s+(?:a\s+|an\s+)({CAT})\b.*?(?:probability|chance)\s+"
                          rf"(?:that\s+)?(?:it(?:'s| is)|the card is)\s+(?:a\s+|an\s+)?({CAT})", False)):
        m = re.search(rx, tc)
        if m:
            ev, given = (m[1], m[2]) if ev_first else (m[2], m[1])
            A, a_lab = _card_set(ev)
            B, b_lab = _card_set(given)
            if not B or not A:
                return None
            both = A & B
            val = F(len(both), len(B))
            return _sol("probability", ctx, "P(A | B) = |A and B| / |B|  (one card from a standard 52-card deck)",
                        [f"B = {b_lab}: {len(B)} cards", f"A and B = {a_lab} among them: {len(both)} cards"],
                        f"P = {len(both)} / {len(B)}", _prob(val, pr),
                        f"P(A and B) / P(B) = ({len(both)}/52) / ({len(B)}/52) = {_show(val)} ✓")

    def draws(k: int, A: set, lab: str):
        a = len(A)
        if k < 1 or k > 52 or (not repl and k > a):
            return None
        if repl:
            val = F(a, 52) ** k
            return _sol("probability", ctx, "P = (|A| / 52)^k  (with replacement: every draw is from a full deck)",
                        [f"A = {lab}: {a} of 52 cards", f"k = {k} draws"], f"({a}/52)^{k} = ({_show(F(a, 52))})^{k}",
                        _prob(val, pr))
        num = math.prod(range(a - k + 1, a + 1))
        den = math.prod(range(52 - k + 1, 53))
        val = F(num, den)
        factors = " × ".join(f"{a - i}/{52 - i}" for i in range(k))
        return _sol("probability", ctx, "multiply the chances draw by draw  (without replacement: one fewer card of "
                                        "that kind, and one fewer card, each time)",
                    [f"A = {lab}: {a} of 52 cards", f"k = {k} draws"], f"{factors} = {_int(num)} / {_int(den)}",
                    _prob(val, pr), f"C({a}, {k}) / C(52, {k}) = {_int(math.comb(a, k))} / {_int(math.comb(52, k))} = {_show(val)} ✓")

    # two in a row of different kinds: "an ace and then a king", "first a heart, second a spade"
    m = (re.search(rf"\b(?:an?\s+)?({CAT})\s+(?:and\s+)?then\s+(?:an?\s+|another\s+)?({CAT})", t)
         or re.search(rf"\bfirst\s+(?:card\s+)?(?:is\s+|being\s+|drawn\s+is\s+)?(?:an?\s+)?({CAT})\s*,?\s*(?:and\s+)?(?:the\s+)?second\s+"
                      rf"(?:card\s+)?(?:is\s+|being\s+)?(?:an?\s+|another\s+)?({CAT})", t))
    if m and asks and not hand:
        A, a_lab = _card_set(m[1])
        B, b_lab = _card_set(m[2])
        if not A or not B:
            return None
        if repl:
            val = F(len(A) * len(B), 52 * 52)
            sub = f"{len(A)}/52 × {len(B)}/52"
        else:
            num = len(A) * len(B) - len(A & B)
            val = F(num, 52 * 51)
            sub = (f"{len(A)}/52 × {len(B)}/51" if not A & B else
                   f"({len(A)} × {len(B)} − {len(A & B)} cards that are both) / (52 × 51) = {num} / 2652")
        return _sol("probability", ctx, "P(A then B) = P(A) × P(B | A)" + ("" if repl else "  (without replacement)"),
                    [f"A = {a_lab}: {len(A)} cards", f"B = {b_lab}: {len(B)} cards"], sub, _prob(val, pr))

    # hands: "all hearts in a 5-card hand", "exactly 2 aces", "how many 5-card hands"
    if hand:
        if not 1 <= hand <= 52:
            return None
        total = math.comb(52, hand)
        cnt = None
        if re.search(r"\b(?:all\s+(?:the\s+)?same\s+suit|(?:all\s+)?(?:of\s+)?(?:one|a single|1)\s+suit|a flush|flush)\b", t):
            if hand > 13:
                return None
            cnt = 4 * math.comb(13, hand)
            desc = f"one suit: 4 suits × C(13, {hand})"
            sub = f"4 × {_int(math.comb(13, hand))} = {_int(cnt)}"
        else:
            mm = (re.search(rf"\ball\s+(?:(?:the|\d+|five|four|three|two|six|seven)\s+)*(?:cards?\s+)?(?:are\s+|being\s+|of them\s+(?:are\s+)?)?({CAT})", t)
                  or re.search(rf"\b(?:are|is|be)\s+all\s+({CAT})", t))
            if mm:
                A, lab = _card_set(mm[1])
                if hand > len(A):
                    return None
                cnt = math.comb(len(A), hand)
                desc = f"all {lab}: C({len(A)}, {hand})"
                sub = f"C({len(A)}, {hand}) = {_int(cnt)}"
            else:
                mm = (re.search(rf"\b({CMPW}|no|exactly)?\s*(\d+|no)\s+({CAT})\b", _blank(t, [m.span() for m in re.finditer(r"\b\d+[- ]card\b|\bhands? of \d+ cards\b|\b\d+ cards\b", t)])))
                if mm and not re.fullmatch(r"cards?", mm[3]):
                    A, lab = _card_set(mm[3])
                    a = len(A)
                    k = 0 if mm[2] == "no" else int(mm[2])
                    rng = _event_range("exactly" if mm[1] in (None, "", "no") else mm[1], k, hand)
                    if not rng or not A:
                        return None
                    ways = [math.comb(a, j) * math.comb(52 - a, hand - j) for j in range(rng[0], rng[1] + 1)]
                    cnt = sum(ways)
                    js = list(range(rng[0], rng[1] + 1))
                    desc = f"{_event_label(*rng, hand).replace('X', lab)} ({a} {lab}, {52 - a} others)"
                    sub = " + ".join(f"C({a}, {j}) × C({52 - a}, {hand - j})" for j in js[:4]) + (" + …" if len(js) > 4 else "") \
                        + f" = {_int(cnt)}"
                elif counting and not asks:
                    return _sol("combinatorics", ctx, "C(n, r) = n! / (r! · (n − r)!)  (a hand is unordered)",
                                [f"n = 52 cards", f"r = {hand}"], f"C(52, {hand}) = {_int(total)}", _int(total),
                                f"C(52, {hand}) = C(52, {52 - hand}) ✓")
        if cnt is None:
            return None
        if counting and not asks:
            return _sol("combinatorics", ctx, "count the hands with the property (a hand is unordered)", [f"{hand}-card hand",
                        desc], sub, _int(cnt))
        val = F(cnt, total)
        return _sol("probability", ctx, "P = favourable hands / all hands  (every hand equally likely)",
                    [f"{hand}-card hand from 52: C(52, {hand}) = {_int(total)} hands", desc],
                    f"{sub}; P = {_int(cnt)} / {_int(total)}", _prob(val, pr))

    # several draws all of one kind: "two aces in a row", "draw 3 cards, all hearts"
    mk = re.search(rf"\b(\d+)\s+({CAT})\s+in a row\b", t)
    if mk and not re.fullmatch(r"cards?", mk[2]):
        A, lab = _card_set(mk[2])
        return draws(int(mk[1]), A, lab)
    mk = re.search(rf"\b(\d+)\s+cards?\b", t)
    if mk:
        mm = re.search(rf"\b(?:both|all(?:\s+\d+)?|each|they|every one)\s+(?:of them\s+|cards\s+)?(?:are\s+|being\s+|is\s+|will be\s+|were\s+|"
                       rf"come up\s+|turn out to be\s+)?(?:an?\s+)?({CAT})", t)
        if mm:
            A, lab = _card_set(mm[1])
            return draws(int(mk[1]), A, lab)
    mk = re.search(rf"\b(?:draw(?:s|ing|n)?|drew|pick(?:s|ing|ed)?|deal(?:s|t|ing)?|choos(?:e|ing)|chose|select(?:s|ing|ed)?|"
                   rf"tak(?:e|ing)|get(?:s|ting)?|pull(?:s|ing|ed)?)\s+(\d+)\s+({CAT})", t)
    if mk and not re.fullmatch(r"cards?", mk[2]) and asks:
        A, lab = _card_set(mk[2])
        return draws(int(mk[1]), A, lab)

    # one card
    if not asks:
        return None
    m1 = (re.search(rf"(?:probability|chance|odds|likelihood)\s+(?:of\s+|that\s+)?(?:you\s+|i\s+|we\s+)?(?:will\s+)?(?:draw(?:ing|s)?|pick(?:ing|s)?|"
                    rf"get(?:ting|s)?|pull(?:ing|s)?|select(?:ing|s)?|choos(?:e|ing|es)|turn(?:ing)? over)?\s*(?:a\s+|an\s+|the\s+)?({CAT})", t)
          or re.search(rf"(?:probability|chance|odds)\s+(?:that\s+)?(?:it|the card|the first card|this card)\s+(?:is|will be|was)\s+(?:a\s+|an\s+)?({CAT})", t)
          or re.search(rf"\bp\s*\(\s*({CAT})\s*\)", t))
    if not m1 or re.fullmatch(r"cards?", m1[1].strip()):
        return None
    A, lab = _card_set(m1[1])
    if not A:
        return None
    val = F(len(A), 52)
    ans = _prob(val, pr)
    if re.search(r"\bodds\b", t) and val < 1:
        g = math.gcd(len(A), 52 - len(A))
        ans += f"; odds {len(A) // g}:{(52 - len(A)) // g} in favour"
    return _sol("probability", ctx, "P = favourable cards / 52  (one card from a standard deck)",
                [f"{lab}: {len(A)} cards"], f"P = {len(A)} / 52", ans, f"{len(A)} + {52 - len(A)} = 52 cards ✓")


# ---------------------------------------------------------------- counting: committees, roles, arrangements, letters

_CONSTRAINTS = re.compile(r"\btogether\b|\badjacent\b|\bnext to\b|\bbeside\b|\bbegins?\b|\bstarts?\b|\bends?\b|\bvowels?\b|"
                          r"\bconsonants?\b|\bnot\b|\bno two\b|\bapart\b|\bmust\b|\bcan't\b|\bcannot\b|\bwon't\b|\brefuses?\b|"
                          r"\bexcept\b|\bunless\b|\bonly if\b|\bif\b|\bneither\b|\beither\b|\bboth\b|\bwithout\b|\bforbidden\b|"
                          r"\bdon't\b|\bdoesn't\b|\bpalindrom|\binsist|\brepeat|\brepetition|\bidentical\b|\bindistinguishable\b|"
                          r"\bat least\b|\bat most\b")


def _comb_steps(n: int, r: int) -> str:
    if r <= 6 and n <= 60:
        top = " × ".join(str(n - i) for i in range(r))
        bot = " × ".join(str(r - i) for i in range(r))
        return f"C({n}, {r}) = ({top}) / ({bot}) = {_int(math.prod(range(n - r + 1, n + 1)))} / {_int(math.factorial(r))}"
    return f"C({n}, {r}) = {n}! / ({r}! · {n - r}!)"


def _perm_steps(n: int, r: int) -> str:
    if r <= 8:
        return f"P({n}, {r}) = " + " × ".join(str(n - i) for i in range(r))
    return f"P({n}, {r}) = {n}! / {n - r}!"


def _choose(ctx: _Ctx, n: int, r: int, what: str = "") -> Solution | None:
    if not 0 <= r <= n <= 1000:
        return None
    v = math.comb(n, r)
    return _sol("combinatorics", ctx, "C(n, r) = n! / (r! · (n − r)!)  (order doesn't matter)",
                [f"n = {n}{' ' + what if what else ''}", f"r = {r} chosen"], _comb_steps(n, r), _int(v),
                f"C({n}, {r}) = C({n}, {n - r}) = {_int(math.comb(n, n - r))} ✓")


def _arrange(ctx: _Ctx, n: int, r: int, what: str = "", formula: str = "") -> Solution | None:
    if not 0 <= r <= n <= 1000:
        return None
    v = math.perm(n, r)
    return _sol("combinatorics", ctx, formula or "P(n, r) = n! / (n − r)!  (order matters)",
                [f"n = {n}{' ' + what if what else ''}", f"r = {r} {'places' if r != n else 'all of them, in order'}"],
                _perm_steps(n, r), _int(v),
                f"C({n}, {r}) × {r}! = {_int(math.comb(n, r))} × {_int(math.factorial(r))} = {_int(v)} ✓")


_PEOPLE = (r"(?:people|persons|students|members|players|employees|candidates|applicants|friends|runners|horses|competitors|"
           r"contestants|athletes|swimmers|racers|teams|cars|participants|entrants|finalists|drivers|dogs|riders|"
           r"children|kids|boys|girls|men|women|workers|teachers|guests|books|songs|items|objects|letters|digits|"
           r"flowers|toppings|flavors|flavours|dishes|questions|cards|colors|colours|shirts|movies|films|cities|"
           r"dancers|singers|actors|volunteers|nominees|scientists|doctors|nurses|judges|delegates|senators|things|"
           r"marbles|balls|beads|pictures|paintings|photos|courses|subjects|classes|games|tasks|jobs|names)")
_ROLES = (r"vice[- ]?presidents?|vps?|presidents?|secretar(?:y|ies)|treasurers?|vice[- ]?captains?|captains?|vice[- ]?chair\w*|"
          r"chair(?:person|man|woman)?s?|managers?|assistant managers?|leaders?|deputy|deputies|coach|spokesperson|"
          r"goalkeeper|editor|director|head|clerk|auditor|historian|sergeant at arms")


def counting(ctx: _Ctx) -> Solution | None:
    t = ctx.c
    # explicit nCr / nPr
    m = (re.search(r"\b(\d+)(?:c| c )(\d+)\b", t)
         or re.search(r"(?<![a-z])c\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)", t) or re.search(r"\b(\d+)\s+choose\s+(\d+)\b", t)
         or re.search(r"\bn\s*c\s*r\s*\(?\s*(\d+)\s*,\s*(\d+)", t)
         or re.search(r"\bcombinations?\s+of\s+(\d+)\s+(?:\w+\s+)?(?:taken|chosen)\s+(\d+)\s+at a time", t))
    if m:
        return _choose(ctx, int(m[1]), int(m[2]))
    m = (re.search(r"\b(\d+)p(\d+)\b", t) or re.search(r"(?<![a-z])p\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)", t)
         or re.search(r"\bn\s*p\s*r\s*\(?\s*(\d+)\s*,\s*(\d+)", t)
         or re.search(r"\bpermutations?\s+of\s+(\d+)\s+(?:\w+\s+)?(?:taken\s+)?(\d+)\s+at a time", t))
    if m:
        return _arrange(ctx, int(m[1]), int(m[2]))
    if not re.search(r"\bhow many\b|\bnumber of\b|\bin how many\b|\bcount\b|\bways\b|\barrangements?\b|\bpermutations?\b|"
                     r"\bcombinations?\b", t):
        return None
    if re.search(r"\bprobabilit|\bchance|\bodds\b|\bdice\b|\bdie\b|\bcoins?\b|\bdeck\b|\bcards? from\b", t):
        return None
    sol = _letters(ctx)
    if sol:
        return sol
    sol = _fixed_member(ctx)
    if sol:
        return sol
    if _CONSTRAINTS.search(t) and not re.search(r"\bexactly\b|\bat least\b|\bat most\b", t):
        return None
    # handshakes
    if re.search(r"\bhandshakes?\b|\bshakes? hands\b|\bshake hands\b", t):
        mp = re.search(rf"\b(\d+)\s+(?:\w+\s+)?{_PEOPLE}\b", t) or re.search(r"\b(\d+)\b", t)
        if mp:
            return _choose(ctx, int(mp[1]), 2, "people (each handshake is a pair)")
    # committees with groups: "a committee of 4 from 6 men and 5 women with exactly 2 women"
    sol = _groups(ctx)
    if sol:
        return sol
    if _CONSTRAINTS.search(t):
        return None
    ordered = bool(re.search(r"\border (?:matters|is important|counts)\b|\bin order\b|\bordered\b|\branked\b|\bin a (?:row|line|queue)\b|"
                             r"\bline(?:d)? up\b|\barrange|\bpermutation|\bsequence|\bpodium\b|\bfinish\b|\bplaces?\b|\bpositions?\b|"
                             r"\bgold\b|\bsilver\b|\bbronze\b|\b1st\b|\bfirst\b|\bseat|\bsit\b|\bshelf\b|\bplaylist|\bschedule|"
                             r"\bmedals?\b", t)) and not re.search(r"\border (?:doesn't|does not|don't|do not|isn't|is not) matter\b|\bunordered\b", t)
    # roles
    roles = re.findall(rf"\b(?:{_ROLES})\b", t)
    roles = list(dict.fromkeys(re.sub(r"s$|ies$", "", r.replace("-", " ")) for r in roles))
    n = _pool(t)
    if len(roles) >= 2 and n:
        return _arrange(ctx, n, len(roles), "people", f"P(n, r) = n! / (n − r)!  (distinct roles: {', '.join(roles)})")
    # podium / places
    places = re.findall(r"\b(?:gold|silver|bronze)\b", t)
    if len(set(places)) >= 2:
        k = len(set(places))
    else:
        ords = [o for o in ("1st|first", "2nd|second", "3rd|third", "4th|fourth", "5th|fifth") if re.search(rf"\b(?:{o})\b", t)]
        k = len(ords) if len(ords) >= 2 else None
        if k is None:
            mt = re.search(r"\btop\s+(\d+)\b", t)
            k = int(mt[1]) if mt and ordered else (3 if re.search(r"\bpodium\b", t) else None)
    if k and n:
        return _arrange(ctx, n, k, "competitors", "P(n, r) = n! / (n − r)!  (each place is a different outcome)")
    # arrange n things (in a circle: (n − 1)!)
    ma = (re.search(rf"\b(?:arrange[ds]?|arranging|order(?:ed|ing)?|line(?:d)? up|seat(?:ed|ing)?|sit|rank(?:ed|ing)?|permute|shuffle|stack|"
                    rf"park|display|place|schedule|play)\s+(?:the\s+|all\s+)?(\d+)\s+(?:different\s+|distinct\s+)?(\w+)", t)
          or re.search(rf"\b(\d+)\s+(?:different\s+|distinct\s+)?(\w+)\s+(?:be\s+|are\s+)?(?:arranged|ordered|lined up|seated|ranked|sat|"
                       rf"placed|stacked|displayed|parked|scheduled|played)", t)
          or re.search(rf"\b(\d+)\s+(?:different\s+|distinct\s+)?(\w+)\b[^.?!]{{0,40}}?\b(?:arrange|order|line|seat|rank|stack|shuffle)\s+"
                       rf"(?:them|these|those)\b", t))
    if ma:
        total = int(ma[1])
        mr = re.search(r"\b(\d+)\s+of\s+(?:the\s+|them\b)|\b(\d+)\s+at a time\b|\bin a row of\s+(\d+)\b|\b(\d+)\s+(?:spaces|spots|seats|slots|places)\b", t)
        r = next((int(g) for g in mr.groups() if g), None) if mr else None
        if re.search(r"\bround table\b|\bcircular\b|\bcircle\b|\baround a table\b", t):
            if r is not None or total < 1:
                return None
            v = math.factorial(total - 1)
            return _sol("combinatorics", ctx, "(n − 1)!  (around a circle only the order relative to each other counts)",
                        [f"n = {total} {ma[2]}"], f"({total} − 1)! = {total - 1}!", _int(v),
                        f"{total}! / {total} rotations = {_int(math.factorial(total))} / {total} = {_int(v)} ✓")
        if r is not None and r != total:
            return _arrange(ctx, total, r, ma[2])
        if total > 1000:
            return None
        v = math.factorial(total)
        return _sol("combinatorics", ctx, "n!  (arrangements of n different things in a row)", [f"n = {total} {ma[2]}"],
                    f"{total}! = " + (" × ".join(str(i) for i in range(total, 0, -1)) if total <= 10 else f"{total}!"), _int(v),
                    f"P({total}, {total}) = {_int(math.perm(total, total))} ✓")
    # choosing r from n
    coll = (r"(?:committee|subcommittee|team|group|panel|jury|board|squad|delegation|subset|selection|sample|crew|council|"
            r"bouquet|combination|hand|set|batch|bunch|collection|lineup|line-up|party|pair|trio|quartet)s?")
    mc = (re.search(rf"\b{coll}\s+of\s+(\d+)\b", t)
          or re.search(rf"\b(\d+)[- ](?:person|people|member|man|men|player|student|people)\s+{coll}\b", t))
    r = int(mc[1]) if mc else None
    if r is None:
        mc = re.search(rf"\b(?:choose|chose|choosing|chosen|select|selecting|selected|pick|picking|picked|elect|form|draw|take|"
                       rf"invite|hire|appoint|get|buy|order|try|award|eat|visit|read|watch|answer)\s+(?:a\s+(?:group|team|committee|set)\s+of\s+)?"
                       rf"(?:any\s+)?(\d+)\b", t)
        r = int(mc[1]) if mc else None
    if r is None:
        return None
    rest = _blank(t, [mc.span()])
    n = _pool(rest)
    if not n:
        return None
    if ordered and not re.search(r"\bcommittee|\bteam\b|\bgroup\b|\bsubset|\bpanel\b", t):
        return _arrange(ctx, n, r, "")
    return _choose(ctx, n, r, "")


def _fixed_member(ctx: _Ctx) -> Solution | None:
    """"A committee of 4 from 12; Ann must be on it" → C(n − 1, r − 1); "... must not be on it" → C(n − 1, r)."""
    t = ctx.c
    mf = re.search(r"\b([a-z]+)\s+(must|has to|will|must not|mustn't|cannot|can't|will not|won't|refuses to)\s+"
                   r"(?:be\s+(?:on|in|included|chosen|selected|picked|part of)|serve|join)\b|"
                   r"\b([a-z]+)\s+is\s+(?:always\s+)?(included|excluded)\b", t)
    if not mf:
        return None
    who = mf[1] or mf[3]
    if who in ("he", "she", "it", "they", "who", "which", "that", "person", "one", "member", "committee", "team", "group"):
        return None
    out = bool(re.search(r"not|n't|refuses|excluded", mf[2] or mf[4]))
    rest = _blank(t, [mf.span()])
    if _CONSTRAINTS.search(rest):
        return None
    coll = r"(?:committee|subcommittee|team|group|panel|jury|board|squad|delegation|council|crew)s?"
    mc = (re.search(rf"\b{coll}\s+of\s+(\d+)\b", rest)
          or re.search(rf"\b(\d+)[- ](?:person|people|member|player|student)\s+{coll}\b", rest)
          or re.search(r"\b(?:choose|select|pick|form|elect)\s+(\d+)\b", rest))
    if not mc:
        return None
    r = int(mc[1])
    n = _pool(_blank(rest, [mc.span()]))
    if not n or not 1 <= r <= n:
        return None
    if out:
        v = math.comb(n - 1, r)
        return _sol("combinatorics", ctx, "leave the excluded person out: C(n − 1, r)",
                    [f"n = {n}, {who} excluded → {n - 1} left", f"r = {r} chosen"], _comb_steps(n - 1, r), _int(v),
                    f"C({n}, {r}) − C({n - 1}, {r - 1}) = {_int(math.comb(n, r))} − {_int(math.comb(n - 1, r - 1))} = {_int(v)} ✓")
    v = math.comb(n - 1, r - 1)
    return _sol("combinatorics", ctx, f"{who} is already in: choose the other r − 1 from the n − 1 left, C(n − 1, r − 1)",
                [f"n = {n}, {who} fixed → {n - 1} others", f"r = {r}, so {r - 1} more to choose"],
                _comb_steps(n - 1, r - 1), _int(v),
                f"C({n}, {r}) − C({n - 1}, {r}) (committees without {who}) = {_int(math.comb(n, r))} − "
                f"{_int(math.comb(n - 1, r))} = {_int(v)} ✓")


def _pool(t: str) -> int | None:
    m = (re.search(rf"\b(?:from|out of|among|of)\s+(?:a\s+(?:group|class|club|pool|set|team|panel|total|department|staff|list|"
                   rf"batch|selection|menu|bag|box|shelf|field|choice|range|committee|board|race|squad|league)\s+of\s+)?(?:the\s+|these\s+|"
                   rf"his\s+|her\s+|my\s+|their\s+|our\s+)?(\d+)\b", t)
         or re.search(rf"\b(\d+)\s+(?:\w+\s+){{0,2}}?{_PEOPLE}\b", t)
         or re.search(r"\b(?:has|have|with|there are|contains?|of)\s+(\d+)\b", t))
    return int(m[1]) if m else None


def _stem(w: str) -> str:
    w = {"men": "man", "women": "woman", "children": "child", "people": "person"}.get(w, w)
    return re.sub(r"(?:es|s)$", "", w) if len(w) > 3 else w


def _groups(ctx: _Ctx) -> Solution | None:
    t = ctx.c
    mg = re.search(r"\b(?:from|out of|among)\s+(?:a\s+group\s+of\s+|a\s+class\s+of\s+)?(\d+)\s+(\w+)\s*(?:,\s*|\s+and\s+)(\d+)\s+(\w+)", t)
    if not mg:
        return None
    g = {_stem(mg[2]): int(mg[1]), _stem(mg[4]): int(mg[3])}
    if len(g) != 2:
        return None
    (n1, c1), (n2, c2) = g.items()
    rest = _blank(t, [mg.span()])
    msize = re.search(r"\b(?:committee|team|group|panel|jury|board|squad|delegation|selection|sample|council)\s+of\s+(\d+)\b", rest) or \
        re.search(r"\b(?:choose|select|pick|form|elect)\s+(\d+)\b", rest)
    two = re.search(r"\b(?:of|with|consisting of|containing|made up of|has|have|having|includes?|including)?\s*(\d+)\s+(\w+)\s+and\s+(\d+)\s+(\w+)", rest)
    if two and _stem(two[2]) in g and _stem(two[4]) in g and _stem(two[2]) != _stem(two[4]):
        a, b = int(two[1]), int(two[3])
        wa, wb = _stem(two[2]), _stem(two[4])
        if msize and int(msize[1]) != a + b:
            return None
        ways = math.comb(g[wa], a) * math.comb(g[wb], b)
        return _sol("combinatorics", ctx, "multiply the choices from each group: C(n₁, k₁) × C(n₂, k₂)",
                    [f"{g[wa]} {two[2]}, choose {a}", f"{g[wb]} {two[4]}, choose {b}"],
                    f"C({g[wa]}, {a}) × C({g[wb]}, {b}) = {_int(math.comb(g[wa], a))} × {_int(math.comb(g[wb], b))}",
                    _int(ways))
    if not msize:
        return None
    r = int(msize[1])
    mc = re.search(rf"\b({CMPW}|no)\s*(\d+)?\s*(\w+)", _blank(rest, [msize.span()]))
    while mc and _stem(mc[3]) not in g:
        mc = re.search(rf"\b({CMPW}|no)\s*(\d+)?\s*(\w+)", _blank(rest, [msize.span()])[mc.end():])
    if not mc:
        return None
    who = _stem(mc[3])
    other = n2 if who == n1 else n1
    k = 0 if mc[1] == "no" else int(mc[2]) if mc[2] else None
    if k is None:
        return None
    rng = _event_range("exactly" if mc[1] == "no" else mc[1], k, r)
    if not rng:
        return None
    js = [j for j in range(rng[0], rng[1] + 1) if j <= g[who] and r - j <= g[other]]
    if not js:
        return None
    terms = [math.comb(g[who], j) * math.comb(g[other], r - j) for j in js]
    total = sum(terms)
    sub = " + ".join(f"C({g[who]}, {j}) × C({g[other]}, {r - j})" for j in js)
    check = ""
    if len(js) > 1:
        excluded = [j for j in range(0, r + 1) if j not in js and j <= g[who] and r - j <= g[other]]
        rest_ways = sum(math.comb(g[who], j) * math.comb(g[other], r - j) for j in excluded)
        check = (f"all C({n1 and g[who] + g[other]}, {r}) = {_int(math.comb(g[who] + g[other], r))} committees minus the "
                 f"{_int(rest_ways)} others = {_int(math.comb(g[who] + g[other], r) - rest_ways)} ✓")
    return _sol("combinatorics", ctx, "Σ C(group, j) × C(others, r − j) over the allowed j",
                [f"{g[who]} {mc[3]}, {g[other]} others", f"r = {r}", f"{mc[1]} {k if mc[1] != 'no' else ''} {mc[3]}".replace("  ", " ")],
                sub + (f" = {' + '.join(_int(x) for x in terms)}" if len(terms) > 1 else ""), _int(total), check)


def _letters(ctx: _Ctx) -> Solution | None:
    t = ctx.c
    if not re.search(r"\barrang|\bpermut|\breorder|\brearrang|\bscrambl|\banagram|\b(?:distinct|different|unique)\s+(?:words|orderings|"
                     r"strings|ways|arrangements|codes)|\bhow many ways\b|\bnumber of ways\b|\bin how many ways\b", t):
        return None
    if not re.search(r"\bletters?\b|\bword\b|\banagrams?\b|\bspell", t):
        return None
    word = None
    m = re.search(r"\b(?:letters?\s+(?:of|in|from)\s+(?:the\s+)?(?:word\s+)?|the\s+word\s+|anagrams?\s+of\s+(?:the\s+word\s+)?|"
                  r"arrangements?\s+of\s+(?:the\s+word\s+)?|arrange\s+(?:the\s+word\s+)?)[\"']?([a-z]{2,20})[\"']?(?![\w-])", t)
    stop = {"the", "word", "letters", "letter", "a", "an", "it", "this", "that", "each", "all", "its", "these"}
    if m and m[1] not in stop:
        word = m[1]
    if word is None:
        m = re.search(r"[\"']([a-z]{2,20})[\"']", t) or re.search(r"\b([A-Z]{3,20})\b", ctx.text)
        if m and m[1].lower() not in stop:
            word = m[1].lower()
    if not word:
        return None
    if re.search(r"\btogether\b|\badjacent\b|\bnext to\b|\bbegins?\b|\bstarts?\b|\bends?\b|\bvowels?\b|\bconsonants?\b|\bnot\b|"
                 r"\bno two\b|\bapart\b|\bcircle\b|\bround\b|\bmust\b|\bcan't\b|\bcannot\b|\bexcept\b|\bpalindrom|\bfirst\b|"
                 r"\blast\b|\bwithout\b|\bif\b|\bmiddle\b", t):
        return None
    counts = Counter(word)
    n = len(word)
    mk = re.search(r"\busing\s+(?:only\s+)?(\d+)\s+(?:of\s+(?:the|its)\s+)?letters\b|\b(\d+)[- ]letter\s+(?:words|arrangements|strings|codes)|\b(\d+)\s+letters at a time\b", t)
    k = next((int(g) for g in mk.groups() if g), None) if mk else None
    reps = {c: v for c, v in counts.items() if v > 1}
    show_counts = ", ".join(f"{c.upper()} ×{v}" for c, v in sorted(counts.items(), key=lambda kv: (-kv[1], word.index(kv[0]))))
    if k is not None and k != n:
        if not 0 < k < n:
            return None
        if not reps:
            return _arrange(ctx, n, k, f"different letters in {word.upper()}")
        poly = [F(1)]
        for c in counts.values():
            term = [F(1, math.factorial(j)) for j in range(c + 1)]
            new = [F(0)] * (len(poly) + c)
            for i, a in enumerate(poly):
                for j, b in enumerate(term):
                    new[i + j] += a * b
            poly = new
        v = int(poly[k] * math.factorial(k))
        return _sol("combinatorics", ctx, "k! × [x^k] Π (1 + x + x²/2! + … + x^c/c!)  (k-letter arrangements of letters "
                                          "with repeats)", [f"{word.upper()}: {show_counts}", f"k = {k}"],
                    f"coefficient × {k}! = {v}", _int(v))
    denom = math.prod(math.factorial(v) for v in counts.values())
    v = math.factorial(n) // denom
    if not reps:
        return _sol("combinatorics", ctx, "n!  (all the letters are different)", [f"{word.upper()}: {n} different letters"],
                    f"{n}! = {_int(math.factorial(n))}", _int(v))
    chk, left, parts = 1, n, []
    for c, cnt in counts.items():
        chk *= math.comb(left, cnt)
        parts.append(f"C({left}, {cnt})")
        left -= cnt
    return _sol("combinatorics", ctx, "n! / (n₁! · n₂! · …)  (arrangements of n letters, dividing out the repeats)",
                [f"{word.upper()}: {n} letters, {show_counts}"],
                f"{n}! / ({' · '.join(f'{c}!' for c in reps.values())}) = {_int(math.factorial(n))} / {_int(denom)}", _int(v),
                f"place the letters kind by kind: {' × '.join(parts)} = {_int(chk)} ✓")


# ---------------------------------------------------------------- expected value: raffles, games, tables

_EV_ASK = re.compile(r"\bexpected (?:value|net gain|net|gain|winnings?|profit|loss|payout|payoff|return|amount|earnings?)\b|"
                     r"\bexpectation\b|\bev\b|\be\s*\(\s*x\s*\)|\bfair (?:game|price|bet)\b|\bworth (?:playing|it|buying)\b|"
                     r"\bon average\b|\bexpect to (?:win|lose|gain|make|get)\b|\bnet gain\b|\blong run\b|\bis (?:this|it|the game) fair\b|"
                     r"\baverage (?:winnings?|gain|profit|loss|payout)\b")


def expected_value(ctx: _Ctx) -> Solution | None:
    t = ctx.m
    if not _EV_ASK.search(t):
        return None
    return _ev_table(ctx) or _raffle(ctx) or _game(ctx)


def _ev_table(ctx: _Ctx) -> Solution | None:
    t = ctx.m
    pairs: list[tuple[F, F]] = []
    for m in re.finditer(rf"(?:p\s*\(\s*x\s*=\s*(\$?{SNUM})\s*\)\s*=\s*({PNUM}))|"
                         rf"(?<![\w.])(-?\$?{NUM})\s+(?:with|w/|at)\s+(?:a\s+)?(?:probability|prob\.?|p|chance)\s*(?:of|=|:)?\s*({PNUM})", t):
        v, p = (m[1], m[2]) if m[1] else (m[3], m[4])
        pairs.append((_q(v.replace("$", "")), _q(p)))
    if len(pairs) < 2:
        kw = re.search(r"\bprobabilit(?:y|ies)\b|\bprobs?\b|\bp\s*\(\s*x\s*\)|\bchances\b", t)
        if not kw:
            return None
        runs = [r for r in _runs(t) if len(r) >= 2]
        after = [r for r in runs if r[0][1] >= kw.end() and r[0][1] - kw.end() < 25]
        if not after:
            return None
        ps = after[0]
        vals = [r for r in runs if r is not ps and len(r) == len(ps) and r[-1][2] <= kw.start()]
        if not vals:
            return None
        pairs = [(v[0], p[0]) for v, p in zip(vals[-1], ps)]
    if any(not 0 <= p <= 1 for _, p in pairs) or sum(p for _, p in pairs) != 1:
        return None
    pr = ctx.pr
    mean = sum(v * p for v, p in pairs)
    money_vals = "$" in t
    terms = " + ".join(f"{_show(v)} × {_show(p)}" for v, p in pairs)
    if re.search(r"\bvariance\b|\bstandard deviation\b|\bsd\b", t):
        ex2 = sum(v * v * p for v, p in pairs)
        var = ex2 - mean * mean
        sd_txt = ""
        if re.search(r"\bstandard deviation\b|\bsd\b", t):
            root = _sqrt_exact(var)
            sd_txt = f"; sd {'=' if root is not None else '≈'} {_val(root, pr) if root is not None else pr.dec(math.sqrt(var))}"
        return _sol("probability", ctx, "E(X) = Σ x·p, Var(X) = Σ x²·p − E(X)²",
                    [", ".join(f"P({_show(v)}) = {_show(p)}" for v, p in pairs)],
                    [f"E(X) = {terms} = {_show(mean)}", f"E(X²) = {_show(ex2)}, Var(X) = {_show(ex2)} − {_show(mean)}² = {_show(var)}"],
                    f"mean = {_val(mean, pr)}; variance = {_val(var, pr)}{sd_txt}",
                    f"the probabilities add to {_show(sum(p for _, p in pairs))} ✓")
    ans = _cash(mean, ctx.cur) if money_vals else _val(mean, pr)
    return _sol("probability", ctx, "E(X) = Σ x · P(x)", [", ".join(f"P({_show(v)}) = {_show(p)}" for v, p in pairs)],
                f"{terms} = {_show(mean)}", ans, f"the probabilities add to {_show(sum(p for _, p in pairs))} ✓")


def _raffle(ctx: _Ctx) -> Solution | None:
    t = ctx.m
    if not re.search(r"\braffle|\blottery|\btickets?\b|\bdraw\b", t) or not re.search(r"\bprizes?\b|\bwin|\bjackpot\b|\baward", t):
        return None
    mn = re.search(r"\b(\d[\d,]*)\s+(?:raffle\s+|lottery\s+|\$\d+(?:\.\d+)?\s+)?tickets?\b", t)
    if not mn:
        return None
    mb = re.search(r"\b(?:buy|buys|bought|purchase[sd]?|get|gets|got)\s+(\d+)\s+(?:raffle\s+|lottery\s+)?tickets?\b", t)
    if mb and mb.start(1) == mn.start(1):
        mn = re.search(r"\b(\d[\d,]*)\s+(?:raffle\s+|lottery\s+)?tickets?\b(?!.*\bbuy)", t[:mb.start()] + " " * (mb.end() - mb.start()) + t[mb.end():])
        if not mn:
            return None
    n_tickets = int(mn[1].replace(",", ""))
    bought = int(mb[1]) if mb else 1
    money = [(m.start(), m.end(), _q(m[1])) for m in re.finditer(rf"\$({NUM})", t)]
    price = None
    for a, b, v in money:
        after, before = t[b:b + 30], t[max(0, a - 40):a]
        if re.match(r"\s*(?:each|apiece|a piece|per ticket|a ticket|per entry|for each|tickets?\b|raffle tickets?\b)", after) or \
                re.search(r"(?:tickets?\s+(?:cost|costs|are|is|sell(?:s)? for|sold (?:at|for)|priced at|go for|at)|cost(?:s)? of a ticket(?: is)?|"
                          r"ticket price(?: is| of)?|each ticket costs?|(?:sold|sell|selling)\s+(?:for|at))\s*$", before):
            price = (a, b, v)
            break
    if price is None:
        return None
    prizes: list[tuple[int, F]] = []
    for a, b, v in money:
        if (a, b, v) == price:
            continue
        before = t[max(0, a - 30):a]
        mm = re.search(r"\b(\d+)\s+(?:prizes?\s+of\s+|awards?\s+of\s+)?$", before)
        count = int(mm[1]) if mm and (not re.search(r"tickets?\s*$", before)) else 1
        prizes.append((count, v))
    if not prizes:
        return None
    cur = ctx.cur
    pool = sum(c * v for c, v in prizes)
    ev = pool / n_tickets - price[2]
    listing = ", ".join((f"{c} × " if c > 1 else "") + _cash(v, cur) for c, v in prizes)
    ans = f"{_cash(ev, cur)} per ticket"
    if bought > 1:
        ans = f"{_cash(ev * bought, cur)} for {bought} tickets ({_cash(ev, cur)} each)"
    if re.search(r"\bfair\b", t):
        ans += "; fair" if ev == 0 else "; not fair"
    return _sol("probability", ctx, "E(net gain per ticket) = (total prize money) / (tickets sold) − ticket price  "
                                    "(every ticket equally likely to win each prize)",
                [f"{_int(n_tickets)} tickets", f"price {_cash(price[2], cur)}", f"prizes {listing} = {_cash(pool, cur)}"],
                f"{_show(pool)} / {_int(n_tickets)} − {_show(price[2])} = {_show(pool / n_tickets)} − {_show(price[2])} = {_show(ev)}",
                ans, f"ticket sales {_cash(n_tickets * price[2], cur)} − prizes {_cash(pool, cur)} = "
                     f"{_cash(n_tickets * price[2] - pool, cur)} kept = {_int(n_tickets)} × {_cash(-ev, cur)} ✓")


_OUTCOME = re.compile(rf"\b(win|wins|winning|won|gain|gains|gaining|get|gets|getting|receive|receives|receiving|collect|collects|"
                      rf"paid|lose|loses|losing|lost|pay|pays|paying|pay out|pays out)\s+(?:you\s+)?(?:back\s+)?"
                      rf"(?:an?\s+(?:prize|payout|reward)\s+of\s+)?\$({NUM})")


def _event_prob(phrase: str, t: str) -> F | None:
    p = phrase.strip()
    if re.match(r"heads?\b", p) or re.match(r"tails?\b", p):
        return F(1, 2) if re.search(r"\bcoins?\b|\bflip|\btoss", t) or True else None
    if re.search(r"\bcards?\b|\bdeck\b", t):
        mm = re.match(rf"(?:an?\s+|the\s+)?({CAT})", p)
        if mm:
            A, _ = _card_set(mm[1])
            return F(len(A), 52) if A else None
        return None
    if re.search(r"\bdie\b|\bdice\b", t):
        if re.match(r"doubles?\b", p):
            return F(1, 6)
        ms = re.search(r"\b(\d+)[- ]?sided\b", t)
        sides = int(ms[1]) if ms else 6
        mm = re.match(_FACE_PHRASE, p)
        if mm:
            fs = _face_set(mm[0], sides)
            return F(len(fs), sides) if fs else None
    mspin = re.search(r"\bspinner\b.*?\b(\d+)\s+(?:equal\s+)?(?:sections|parts|sectors|segments|regions|slices)\b", t)
    if mspin:
        mm = re.match(r"(?:an?\s+|the\s+)?(\d+)\b", p)
        if mm:
            return F(1, int(mspin[1]))
    return None


def _game(ctx: _Ctx) -> Solution | None:
    t = ctx.m
    cur = ctx.cur
    cost, cost_span = F(0), None
    mc = (re.search(r"\b(?:costs?|costing|pay|pays|paying|it's|it is|fee(?:\s+is|\s+of)?|price(?:\s+is|\s+of)?|charges?|spend)\s+(?:of\s+)?(?:you\s+)?"
                    rf"\$({NUM})\s*(?:to\s+(?:play|enter|participate|spin|roll|flip|draw|take part|have a go|try|buy in)|per\s+(?:game|play|turn|spin|"
                    rf"roll|go|try|round|entry)|each\s+(?:time|game|play|turn|round)|a\s+(?:game|play|go|turn|spin|round|try)|for\s+(?:each|every|a)\s+"
                    rf"(?:game|play|turn|spin|round|try)|entry|admission)", t)
          or re.search(rf"\$({NUM})\s+(?:to\s+(?:play|enter)|entry fee|entrance fee|per\s+(?:game|play|turn|spin|roll|go|try)|a\s+(?:game|play|go|"
                       rf"turn|spin)|each\s+time)", t)
          or re.search(rf"\b(?:entry|entrance|playing|participation)\s+(?:fee|cost|price)\s*(?:is|of|=|:)?\s*\$({NUM})", t))
    if mc:
        cost, cost_span = _q(mc[1]), mc.span()
    s = _blank(t, [cost_span]) if cost_span else t
    outs = list(_OUTCOME.finditer(s))
    if not outs:
        return None
    spec: list[list] = []  # [value, prob | None | "rest", label]
    for i, m in enumerate(outs):
        sign = -1 if m[1].startswith(("lose", "los", "lost", "pay")) and not m[1].startswith("pay out") and m[1] != "paid" else 1
        if m[1] in ("pay", "pays", "paying") and re.match(r"\s*(?:you|out)", s[m.end(1):m.end(1) + 5]):
            sign = 1
        v = sign * _q(m[2])
        after = s[m.end():outs[i + 1].start() if i + 1 < len(outs) else len(s)]
        before = s[outs[i - 1].end() if i else 0:m.start()]
        p = None
        label = ""
        ma = (re.match(rf"\s*(?:,\s*)?(?:with|at)\s+(?:an?\s+)?(?:probability|prob\.?|chance|likelihood|p)\s*(?:of|=|:)?\s*({PNUM})", after)
              or re.match(rf"\s*(?:,\s*)?({PNUM})\s*(?:of the time|chance|probability)", after))
        if ma:
            p = _q(ma[1])
            label = f"probability {_show(p)}"
        if p is None:
            me = re.match(r"\s*(?:,\s*)?(?:if|when|whenever|for|on)\s+(?:you\s+|it\s+|the\s+\w+\s+|a\s+)?(?:roll(?:s|ed)?|get(?:s)?|flip(?:s|ped)?|"
                          r"toss(?:es|ed)?|draw(?:s|n)?|spin(?:s)?|land(?:s)?(?:\s+on)?|show(?:s)?|come(?:s)?\s+up|pick(?:s)?|throw(?:s)?|is)?\s*"
                          r"(?:up\s+|on\s+)?(.{1,40})", after)
            if me and not re.match(r"\s*(?:,\s*)?(?:otherwise|else)", after):
                ep = _event_prob(me[1], t)
                if ep is not None:
                    p, label = ep, me[1].strip(" ,.")
        if p is None:
            mb = list(re.finditer(rf"({PNUM})\s*(?:chance|probability|likelihood)\b", before))
            if mb:
                p = _q(mb[-1][1])
                label = f"probability {_show(p)}"
        if p is None:
            mb = re.search(r"(?:if|when|whenever)\s+(?:you\s+|it\s+|the\s+\w+\s+|a\s+)?(?:roll(?:s|ed)?|get(?:s)?|flip(?:s|ped)?|toss(?:es|ed)?|"
                           r"draw(?:s|n)?|spin(?:s)?|land(?:s)?(?:\s+on)?|show(?:s)?|come(?:s)?\s+up|pick(?:s)?|throw(?:s)?|is)?\s*(?:up\s+|on\s+)?"
                           r"(.{1,40}?)\s*,?\s*(?:then\s+)?(?:you\s+|they\s+|the player\s+)?$", before)
            mh = re.search(r"(?:^|[,;.]\s*|\bif\s+(?:it(?:'s| is|\s+lands)?\s+)?|\bon\s+)(heads|tails)\s*,?\s*(?:you\s+)?$", before)
            if mh:
                p, label = F(1, 2), mh[1]
            elif mb:
                ep = _event_prob(mb[1], t)
                if ep is not None:
                    p, label = ep, mb[1].strip(" ,.")
        if p is None and re.search(r"\b(?:otherwise|else|if not|any other|anything else|for all other|in all other)\b",
                                   before[-30:] + " " + after[:30]):
            p, label = "rest", "otherwise"
        if p is None:
            return None
        spec.append([v, p, label])
    known_sum = sum(p for _, p, _ in spec if p != "rest")
    if known_sum > 1:
        return None
    rest_n = sum(1 for _, p, _ in spec if p == "rest")
    if rest_n > 1:
        return None
    for row in spec:
        if row[1] == "rest":
            row[1] = 1 - known_sum
    if rest_n == 0 and known_sum < 1:
        spec.append([F(0), 1 - known_sum, "otherwise nothing"])
    gross = sum(v * p for v, p, _ in spec)
    ev = gross - cost
    unit = next((u for u in ("spin", "roll", "ticket", "game", "draw", "flip", "bet") if re.search(rf"\b{u}s?\b", t)), "play")
    unit = {"draw": "play", "flip": "play", "bet": "bet"}.get(unit, unit)
    ans = f"{_cash(ev, cur)} per {unit}"
    if re.search(r"\bfair\b", t):
        ans += "; fair" if ev == 0 else ("; not fair (favours the player)" if ev > 0 else "; not fair (favours the house)")
    known = [f"{'win' if v >= 0 else 'lose'} {_cash(abs(v), cur)} with probability {_show(p)} ({lab})" for v, p, lab in spec]
    if cost:
        known.append(f"cost {_cash(cost, cur)} a {unit}")
    terms = " + ".join(f"({_show(v)}) × {_show(p)}" for v, p, _ in spec) + (f" − {_show(cost)}" if cost else "")
    check = ""
    if cost:
        net_terms = " + ".join(f"({_show(v - cost)}) × {_show(p)}" for v, p, _ in spec)
        check = f"net outcomes: {net_terms} = {_show(sum((v - cost) * p for v, p, _ in spec))} ✓"
    return _sol("probability", ctx, "E(net gain) = Σ (amount × probability) − cost to play", known,
                f"{terms} = {_show(ev)}", ans, check)


# ---------------------------------------------------------------- Bayes' theorem for tests

_RATE_RX = (re.compile(rf"(?<![\w.])({NUM})\s*(?:%|percent\b|per ?cent\b)"),
            re.compile(r"(?<![\w.])(\d[\d,]*)\s+(?:in|out of)\s+(?:every\s+)?(\d[\d,]*)\b"),
            re.compile(r"(?<![\w.%])(0?\.\d+)(?![\d%])"))
_CUES = (("spec", r"\bspecific|\btrue negative|\bcorrectly\b.*\b(?:healthy|without|don't have|do not have|uninfected|negative|non)|"
                  r"\b(?:healthy|without|uninfected|don't have|do not have)\b.*\b(?:tests?|come back|show) negative\b|"
                  r"\bnegative (?:for|in) .*\b(?:healthy|without)\b"),
         ("fn", r"\bfalse negatives?\b|\bmiss(?:es|ed)?\b"),
         ("fp", r"\bfalse[- ]?positives?\b|\bfalse[- ]alarms?\b|\bhealthy\b|\bwithout\b|\bdon't have\b|\bdo not have\b|\bdoesn't have\b|"
                r"\bdoes not have\b|\bnot (?:have|infected|sick|spam|guilty|defective|fraudulent)\b|\bnon[- ]?\w+|\blegit\w*|\binnocent\b|"
                r"\bclean\b|\bwrongly\b|\bincorrectly\b|\bmistakenly\b|\buninfected\b|\bnormal (?:emails|messages|transactions)\b|"
                r"\bgenuine\b|\bharmless\b|\bfine\b"),
         ("sens", r"\bsensitiv|\btrue positive|\bdetect|\bcatch(?:es)?\b|\bcaught\b|\brecall\b|\bhit rate\b|\bidentif|\bflags?\b|\bpicks? up\b|"
                  r"\bcorrectly\b|\bof (?:those|people|patients|the ones|cases) (?:with|who have|who are)\b|"
                  r"\bif (?:you|they|someone|a person|the patient|a patient|it) (?:has|have|is)\b|\bwho (?:has|have) (?:it|the)\b|\bpositive\b"),
         ("acc", r"\baccura"),
         ("base", r"\bprevalen|\bbase rate\b|\baffect|\bpopulation\b|\bincidence\b|\bprior\b|\bcarr(?:y|ies|iers?)\b|\bsuffer|"
                  r"\b(?:have|has|had)\b|\b(?:are|is)\b|\binfected\b|\bspam\b|\bdefective\b|\bfraud"))


def _clause(t: str, a: int, b: int, comma: bool = True) -> str:
    seps = r"[.;?!:]|,|\band\b|\bbut\b|\bwhile\b|\bwhereas\b|\bhowever\b" if comma else r"[.;?!]"
    starts = [m.end() for m in re.finditer(seps, t[:a])]
    m2 = re.search(seps, t[b:])
    return t[starts[-1] if starts else 0: b + (m2.start() if m2 else len(t) - b)]


def bayes(ctx: _Ctx) -> Solution | None:
    t = ctx.c
    if not re.search(r"\bpositive\b|\bflag(?:s|ged)?\b|\balarms?\b|\bbayes\b|\bdetect\w*|\bnegative\b|\bidentif\w+|\bfires?\b|\btriggers?\b", t):
        return None
    if not (_asks_prob(t) or re.search(r"\bhow likely\b|\bwhat percent", t)):
        return None
    rates = []
    for rx in _RATE_RX:
        for m in rx.finditer(t):
            if any(m.start() < e and s < m.end() for _, s, e in rates):
                continue
            v = _q(m[1]) / 100 if rx is _RATE_RX[0] else (F(int(m[1].replace(",", "")), int(m[2].replace(",", ""))) if rx is _RATE_RX[1] else _q(m[1]))
            if not 0 <= v <= 1:
                return None
            rates.append((v, m.start(), m.end()))
    rates.sort(key=lambda r: r[1])
    if not 2 <= len(rates) <= 4:
        return None
    roles: dict[str, F] = {}
    unassigned = []
    for v, a, b in rates:
        cl = _clause(t, a, b)
        cat = None
        for name, rx in _CUES:
            if name == "base" and not re.search(r"\bprevalen|\bbase rate\b|\baffect|\bpopulation\b|\bincidence\b|\bprior\b|\bcarr|\bsuffer", cl) \
                    and re.search(r"\d+\s+(?:in|out of)\s+\d", t[a:b]) is None and cat is None:
                continue
            if re.search(rx, cl):
                cat = name
                break
        if cat in (None, "sens") and re.fullmatch(r".*\bpositive\b.*", cl) and not re.search(_CUES[3][1].replace(r"|\bpositive\b", ""), cl):
            prev = _clause(t, a, b, comma=False)
            if re.search(_CUES[2][1], prev[:prev.find(t[a:b])] if t[a:b] in prev else prev):
                cat = "fp"
        if cat is None and re.search(_CUES[5][1], cl):
            cat = "weak_base"
        if cat == "spec":
            roles.setdefault("fp", 1 - v)
        elif cat == "fn":
            roles.setdefault("sens", 1 - v)
        elif cat == "acc":
            roles.setdefault("sens", v)
            roles.setdefault("acc", v)
        elif cat in ("fp", "sens", "base") and cat not in roles:
            roles[cat] = v
        else:
            unassigned.append((v, cat))
    for v, cat in unassigned:
        for role in (["base"] if cat == "weak_base" else []) + ["base", "sens", "fp"]:
            if role not in roles:
                roles[role] = v
                break
    if "fp" not in roles and "acc" in roles:
        roles["fp"] = 1 - roles["acc"]
    if not {"base", "sens", "fp"} <= set(roles):
        return None
    b, s, f = roles["base"], roles["sens"], roles["fp"]
    pr = ctx.pr
    sents = [x for x in re.split(r"(?<=[.?!])\s+", t.strip()) if x]
    question = next((x for x in reversed(sents) if re.search(r"\bprobabilit|\bchance|\blikel|\bpercent|\bodds|\bp\s*\(|\bwhat\b", x)), t)
    negative = re.search(r"\bnegative\b", question) and not re.search(r"\bfalse negative", question)
    total_q = re.search(r"\btests? positive\b|\bpositive (?:result|test)\b|\bflagged\b", question) and not re.search(
        r"\bgiven\b|\bif\b|\bwho\b|\bthat (?:tests?|tested|are|is|was|were|gets?|got)\b|\bafter\b|\bwhen\b|\bactually\b|\breally\b|\btruly\b|"
        r"\bhas\b|\bhave\b|\bis (?:spam|infected|sick|guilty|defective|fraud\w*)\b|\|", question)
    complement = re.search(r"\b(?:doesn't|does not|don't|do not|not actually|isn't|is not|aren't|are not)\s+(?:actually\s+|really\s+)?"
                           r"(?:have|has|sick|infected|spam|guilty|defective|carry)\b|\bhealthy\b|\bfalse alarm\b", question)
    known = [f"P(D) = {_show(b)} (base rate)", f"P(+ | D) = {_show(s)} (detection rate)", f"P(+ | not D) = {_show(f)} (false positive rate)"]
    if total_q and not negative:
        tot = s * b + f * (1 - b)
        return _sol("probability", ctx, "P(+) = P(+ | D)·P(D) + P(+ | not D)·P(not D)  (law of total probability)", known,
                    f"{_show(s)} × {_show(b)} + {_show(f)} × {_show(1 - b)} = {_show(s * b)} + {_show(f * (1 - b))}",
                    _prob(tot, pr, pct=True))
    if negative:
        num, other = (1 - s) * b, (1 - f) * (1 - b)
        val = num / (num + other)
        formula = "P(D | −) = P(− | D)·P(D) / [P(− | D)·P(D) + P(− | not D)·P(not D)]  (Bayes' theorem)"
        sub = f"{_show(1 - s)} × {_show(b)} / ({_show(1 - s)} × {_show(b)} + {_show(1 - f)} × {_show(1 - b)}) = {_show(num)} / {_show(num + other)}"
        what = "D | −"
    else:
        num, other = s * b, f * (1 - b)
        val = num / (num + other)
        formula = "P(D | +) = P(+ | D)·P(D) / [P(+ | D)·P(D) + P(+ | not D)·P(not D)]  (Bayes' theorem)"
        sub = f"{_show(s)} × {_show(b)} / ({_show(s)} × {_show(b)} + {_show(f)} × {_show(1 - b)}) = {_show(num)} / {_show(num + other)}"
        what = "D | +"
    if num + other == 0:
        return None
    ans_val = 1 - val if complement else val
    if complement:
        sub += f"; P(not {what}) = 1 − {_show(val)}"
    check = ""
    denoms = [x.denominator for x in (b, s * b, f * (1 - b), (1 - s) * b, (1 - f) * (1 - b))]
    pop = math.lcm(*denoms)
    while pop < 1000:
        pop *= 10
    if pop <= 10 ** 9:
        has, pos_has, pos_not = b * pop, (s * b if not negative else (1 - s) * b) * pop, (f if not negative else 1 - f) * (1 - b) * pop
        sign = "+" if not negative else "−"
        check = (f"out of {_int(pop)} people: {_int(int(has))} have it and {_int(int(pos_has))} of them test {sign}; "
                 f"{_int(int(pop - has))} don't and {_int(int(pos_not))} of them test {sign}; "
                 f"{_int(int(pos_has))} / {_int(int(pos_has + pos_not))} = {_show(val)} ✓")
    return _sol("probability", ctx, formula, known, sub, _prob(ans_val, pr, pct=True), check)


# ---------------------------------------------------------------- the normal distribution

_UNIT_AFTER = re.compile(r"\s*(cm|mm|km|kg|g|grams|lbs?|pounds|inches|in|ft|feet|hours?|hrs?|minutes?|mins?|seconds?|secs?|s|days?|"
                         r"years?|points|marks|mph|km/h|ml|mg|mg/dl|°c|°f|degrees|ms|kmh|m|l)(?![\w/])")
_LT = (r"(?:(?<!no )(?<!not )less than|(?<!no )fewer than|lower than|smaller than|shorter than|lighter than|younger than|cheaper than|below|"
       r"under|at most|no more than|not more than|up to|not exceeding|does(?:n't| not) exceed|<=?)")
_GT = (r"(?:(?<!no )(?<!not )more than|greater than|higher than|larger than|bigger than|taller than|heavier than|longer than|older than|"
       r"above|over|at least|no less than|not less than|no fewer than|exceed(?:s|ing)?|in excess of|>=?)")
_QUAL = r"(?:an?\s+)?(?:(?:score|value|height|weight|time|iq|mark|result|reading|length|life(?:time)?|temperature|level|rate|amount)\s+(?:of\s+)?)?"


def normal(ctx: _Ctx) -> Solution | None:
    t = ctx.c
    pr = ctx.pr
    mw = re.search(r"\bwithin\s+(\d+(?:\.\d+)?)\s+(?:standard deviations?|sds?|s\.d\.?|sigmas?|σ)", t)
    if mw and re.search(r"\bnormal|\bbell|\bgaussian", t):
        k = float(mw[1])
        p = 2 * float(ndtr(k)) - 1
        return _sol("statistics", ctx, "P(|Z| < k) = 2Φ(k) − 1  (normal distribution)", [f"k = {mw[1]}"],
                    f"2 × Φ({mw[1]}) − 1 = 2 × {float(ndtr(k)):.6f} − 1", _prob(p, pr, pct=True),
                    "matches the 68–95–99.7 rule ✓" if mw[1] in ("1", "2", "3") else "")
    mu = sigma = None
    spans = []
    note = ""
    unit = ""
    money_q = False
    m = re.search(rf"(?<![a-z])n\s*\(\s*({SNUM})\s*,\s*({NUM})\s*(\^\s*2|²|\*\*\s*2)?\s*\)", t)
    if m:
        mu, sv = _q(m[1]), _q(m[2])
        if m[3]:
            sigma, note = sv, f"N({_show(mu)}, {_show(sv)}²): σ = {_show(sv)}"
        elif re.search(r"\bvariance\b", t):
            sigma, note = None, ""
            sigma_f = math.sqrt(float(sv))
            sigma = F(sigma_f).limit_denominator(10 ** 9)
            note = f"N({_show(mu)}, {_show(sv)}) with variance {_show(sv)}: σ = √{_show(sv)}"
        else:
            sigma, note = sv, f"reading N({_show(mu)}, {_show(sv)}) as mean {_show(mu)}, standard deviation {_show(sv)}"
        spans.append(m.span())
    else:
        mb = re.search(rf"\bmean and (?:a |the )?(?:standard deviation|sd|s\.d\.|std)\s*(?:of|are|=|is|:)?\s*({SNUM})\s*(?:and|,)\s*({NUM})", t)
        if mb:
            mu, sigma = _q(mb[1]), _q(mb[2])
            spans.append(mb.span())
        else:
            mm = re.search(rf"(?:\bmean\b|\baverage\b|\bavg\b|μ|\bmu\b|\bexpected value\b|\bcent(?:er|re)d (?:at|on|around)\b)(?:\s+[a-z]+){{0,4}}?\s*"
                           rf"(?:of|is|=|:|at|being|around|about|approximately|equal to|was|equals)?\s*(?:about\s+|around\s+|approximately\s+|of\s+)?"
                           rf"(\$\s*)?({SNUM})", t)
            ms = re.search(rf"(?:\bstandard deviation\b|\bstd\.?\s*dev\.?|\bstdev\b|\bstd\b|\bs\.?d\b\.?|σ(?!\s*(?:\^|²))|\bsigma\b(?!\s*(?:\^|²|squared)))"
                           rf"(?:\s+[a-z]+){{0,2}}?\s*(?:of|is|=|:|being|was|equal to)?\s*(?:about\s+|of\s+)?(\$\s*)?({NUM})", t)
            mv = re.search(rf"(?:\bvariance\b|σ\s*(?:\^\s*2|²)|\bsigma\s*(?:\^\s*2|²|squared))\s*(?:of|is|=|:|being|was)?\s*({NUM})", t)
            if not mm or not (ms or mv):
                return None
            mu = _q(mm[2])
            money_q = bool(mm[1])
            spans.append(mm.span())
            if ms and not (mv and mv.start() <= ms.start() <= mv.end()):
                sigma = _q(ms[2])
                spans.append(ms.span())
            else:
                var = _q(mv[1])
                sigma = F(math.sqrt(float(var))).limit_denominator(10 ** 9) if _sqrt_exact(var) is None else _sqrt_exact(var)
                note = f"σ = √{_show(var)} = {pr.dec(float(sigma))}"
                spans.append(mv.span())
            mu_end = mm.end()
            mu_unit = _UNIT_AFTER.match(t, mu_end)
            if mu_unit:
                unit = " " + mu_unit[1]
    if sigma is None or sigma <= 0:
        return None
    longest = max((len(r) for r in _runs(t)), default=0)
    if longest >= 3:
        return None  # a data list ("mean and sd of 2, 4, 6"), not a distribution
    rest = _blank(t, spans)
    muf, sf = float(mu), float(sigma)
    ms_, ss_ = _show(mu), (_show(sigma) if sigma.denominator < 1000 else pr.dec(sf))
    known = [f"μ = {ms_}", f"σ = {ss_}"] + ([note] if note else [])
    cash = (lambda v: _cash(v, ctx.cur)) if money_q or "$" in t else (lambda v: pr.dec(v) + unit)

    def phi(z):
        return float(ndtr(z))

    def scale(p: float, ans: str) -> str:
        if not re.search(r"\bhow many\b", rest):
            return ans
        mN = re.search(r"\b(?:out of|among|of the|in a (?:class|group|sample|population|batch|school|town|city|year) of|sample of|population of|"
                       r"group of|class of|batch of)\s+(\d[\d,]*)\b", rest) or re.search(rf"\b(\d[\d,]*)\s+{_PEOPLE}\b", rest) or \
            re.search(r"\b(\d[\d,]*)\s+(?:bulbs|parts|batteries|babies|apples|bottles|boxes|customers|patients|eggs|bags|cans|adults|scores|"
                      r"test takers|trees|fish|bolts|phones|chips|packets|units)\b", rest)
        if not mN:
            return ans
        N = int(mN[1].replace(",", ""))
        return f"about {_int(round(N * p))} ({_int(N)} × {pr.dec(p)} = {pr.dec(N * p)}; probability {ans})"

    num = rf"(\$\s*)?({SNUM})"
    # percentile and cut-offs: value with a given area below it
    mp = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:st|nd|rd|th)?\s+percentile\b", rest)
    mtop = re.search(rf"\b(?:top|highest|upper|best|largest|biggest|tallest|heaviest|longest|fastest)\s+({NUM})\s*%", rest)
    mbot = re.search(rf"\b(?:bottom|lowest|lower|worst|smallest|shortest|lightest|slowest)\s+({NUM})\s*%", rest)
    mmid = re.search(rf"\b(?:middle|central)\s+({NUM})\s*%", rest)
    if mmid:
        c = float(_q(mmid[1])) / 100
        if not 0 < c < 1:
            return None
        z = float(ndtri(0.5 + c / 2))
        lo, hi = muf - z * sf, muf + z * sf
        return _sol("statistics", ctx, "x = μ ± z·σ with z = Φ⁻¹(0.5 + c/2)  (central area c of a normal distribution)",
                    known + [f"c = {mmid[1]}%"], [f"z = Φ⁻¹({0.5 + c / 2:g}) = {z:.4f}", f"{ms_} ± {z:.4f} × {ss_}"],
                    f"{cash(lo)} to {cash(hi)}", f"Φ({z:.4f}) − Φ(−{z:.4f}) = {phi(z) - phi(-z):.4f} ✓")
    area = None
    if mp and not re.search(r"\bwhat percentile\b|\bwhich percentile\b", rest):
        area, what = float(mp[1]) / 100, f"{mp[1]}th percentile"
    elif mtop:
        area, what = 1 - float(_q(mtop[1])) / 100, f"top {mtop[1]}% cut-off"
    elif mbot:
        area, what = float(_q(mbot[1])) / 100, f"bottom {mbot[1]}% cut-off"
    if area is not None:
        if not 0 < area < 1:
            return None
        z = float(ndtri(area))
        x = muf + z * sf
        return _sol("statistics", ctx, "x = μ + z·σ with z = Φ⁻¹(p)  (p = area below x)", known + [f"p = {area:g} ({what})"],
                    [f"z = Φ⁻¹({area:g}) = {z:.4f}", f"x = {ms_} + ({z:.4f}) × {ss_} = {x:.4f}"], cash(x),
                    f"Φ(({x:.4f} − {ms_}) / {ss_}) = Φ({z:.4f}) = {phi(z):.4f} ✓")
    # inverse z: the value with a given z-score
    mzi = re.search(rf"\bz(?:[- ]?(?:score|value))?\s*(?:of|=|is|:)\s*({SNUM})", rest)
    if mzi and abs(float(_q(mzi[1]))) <= 6 and re.search(
            r"\b(?:what|which|find|give)\b.{0,40}\b(?:value|score|x|raw|height|weight|number|time|mark|iq)\b|\bcorrespond|\b(?:has|with|have) a z", rest):
        z = float(_q(mzi[1]))
        x = muf + z * sf
        return _sol("statistics", ctx, "x = μ + z·σ", known + [f"z = {mzi[1]}"], f"x = {ms_} + ({mzi[1]}) × {ss_}", cash(x),
                    f"z = ({pr.dec(x)} − {ms_}) / {ss_} = {(x - muf) / sf:g} ✓")
    # z-score of a value
    if re.search(r"\bz[- ]?(?:score|value)s?\b|\bzscore\b|\bstandard(?:i[sz]ed)? (?:score|value)\b|\bstandardi[sz]e\b|"
                 r"\bhow many (?:standard deviations|sds?|sigmas?)\b|\bwhat percentile\b|\bwhich percentile\b|\bpercentile rank\b", rest) and \
            not re.search(rf"{_LT}\s*{_QUAL}{num}|{_GT}\s*{_QUAL}{num}|\bbetween\b", rest):
        mx = re.search(rf"(?<![\w.])({SNUM})(?![\w.]*\d)(?!\s*%)(?!\s*(?:st|nd|rd|th)\b)", rest)
        if not mx:
            return None
        x = _q(mx[1])
        z = (x - mu) / sigma
        zf = float(z)
        pct = phi(zf) * 100
        if re.search(r"\bpercentile\b", rest):
            return _sol("statistics", ctx, "percentile = Φ(z) × 100 with z = (x − μ) / σ", known + [f"x = {_show(x)}"],
                        [f"z = ({_show(x)} − {ms_}) / {ss_} = {_val(z, pr)}", f"Φ({pr.dec(zf)}) = {phi(zf):.4f}"],
                        f"about the {pr.dec(pct)}th percentile", f"z {'>' if zf > 0 else '<' if zf < 0 else '='} 0, so "
                        f"{'above' if zf > 0 else 'below' if zf < 0 else 'at'} the median ✓")
        side = "above" if zf > 0 else "below" if zf < 0 else "at"
        return _sol("statistics", ctx, "z = (x − μ) / σ", known + [f"x = {_show(x)}"], f"z = ({_show(x)} − {ms_}) / {ss_}",
                    f"z = {_val(z, pr)}", f"{_show(x)} is {pr.dec(abs(zf))} standard deviations {side} the mean; Φ(z) = "
                                          f"{phi(zf):.4f}, so {pr.dec(pct)}% of values are below it ✓")
    # probabilities: between, below, above
    mbtw = (re.search(rf"\bbetween\s+{_QUAL}{num}\s*(?:[a-z]+\s+)?(?:and|-|to)\s+{num}", rest)
            or re.search(rf"\bfrom\s+{num}\s*(?:[a-z]+\s+)?(?:to|-)\s+{num}", rest)
            or re.search(rf"{num}\s*<=?\s*x\s*<=?\s*{num}", rest))
    mlt = re.search(rf"{_LT}\s*{_QUAL}{num}", rest) or re.search(rf"{num}\s*(?:[a-z]+\s+)?or (?:less|fewer|lower|below|under|smaller|shorter)\b", rest)
    mgt = re.search(rf"{_GT}\s*{_QUAL}{num}", rest) or re.search(rf"{num}\s*(?:[a-z]+\s+)?or (?:more|higher|greater|above|over|longer|taller)\b", rest)
    asks = _asks_prob(rest) or re.search(r"\bhow many\b|\bwhat (?:percent|proportion|fraction)|\bpercentage\b|\bproportion\b|\bfraction\b", rest)
    if not asks:
        return None
    if mbtw:
        a, b = sorted((_q(mbtw[2]), _q(mbtw[4])))
        za, zb = (a - mu) / sigma, (b - mu) / sigma
        p = phi(float(zb)) - phi(float(za))
        return _sol("statistics", ctx, "P(a < X < b) = Φ((b − μ)/σ) − Φ((a − μ)/σ)  (normal distribution)",
                    known + [f"a = {_show(a)}", f"b = {_show(b)}"],
                    [f"z_a = ({_show(a)} − {ms_}) / {ss_} = {_val(za, pr)}, z_b = ({_show(b)} − {ms_}) / {ss_} = {_val(zb, pr)}",
                     f"Φ({pr.dec(float(zb))}) − Φ({pr.dec(float(za))}) = {phi(float(zb)):.4f} − {phi(float(za)):.4f}"],
                    scale(p, _prob(p, pr, pct=True)),
                    f"P(X < {_show(a)}) + P({_show(a)} < X < {_show(b)}) + P(X > {_show(b)}) = "
                    f"{phi(float(za)):.4f} + {p:.4f} + {1 - phi(float(zb)):.4f} = 1 ✓")
    if mlt and mgt:
        lo_v, hi_v = _q(mgt[2]), _q(mlt[2])
        between_words = rest[min(mlt.end(), mgt.end()):max(mlt.start(), mgt.start())]
        if lo_v < hi_v and not re.search(r"\bor\b", between_words):
            za, zb = (lo_v - mu) / sigma, (hi_v - mu) / sigma
            p = phi(float(zb)) - phi(float(za))
            return _sol("statistics", ctx, "P(a < X < b) = Φ((b − μ)/σ) − Φ((a − μ)/σ)  (normal distribution)",
                        known + [f"a = {_show(lo_v)}", f"b = {_show(hi_v)}"],
                        [f"z_a = {_val(za, pr)}, z_b = {_val(zb, pr)}", f"Φ({pr.dec(float(zb))}) − Φ({pr.dec(float(za))})"],
                        scale(p, _prob(p, pr, pct=True)))
        if hi_v < lo_v:
            zl, zh = (hi_v - mu) / sigma, (lo_v - mu) / sigma
            p = phi(float(zl)) + 1 - phi(float(zh))
            return _sol("statistics", ctx, "P(X < a) + P(X > b) = Φ(z_a) + 1 − Φ(z_b)  (normal distribution, two tails)",
                        known + [f"a = {_show(hi_v)}", f"b = {_show(lo_v)}"], [f"z_a = {_val(zl, pr)}, z_b = {_val(zh, pr)}"],
                        scale(p, _prob(p, pr, pct=True)))
        return None
    if mlt or mgt:
        mq = mlt or mgt
        x = _q(mq[2])
        z = (x - mu) / sigma
        zf = float(z)
        below = mq is mlt
        p = phi(zf) if below else 1 - phi(zf)
        rel = "<" if below else ">"
        sanity = (f"z {'>' if zf > 0 else '<' if zf < 0 else '='} 0, so the probability is "
                  f"{'above' if (zf > 0) == below and zf != 0 else 'below' if zf != 0 else 'exactly'} one half ✓")
        return _sol("statistics", ctx, f"z = (x − μ) / σ, P(X {rel} x) = {'Φ(z)' if below else '1 − Φ(z)'}  (normal distribution)",
                    known + [f"x = {_show(x)}"],
                    [f"z = ({_show(x)} − {ms_}) / {ss_} = {_val(z, pr)}",
                     f"Φ({pr.dec(zf)}) = {phi(zf):.4f}" + ("" if below else f", 1 − {phi(zf):.4f} = {1 - phi(zf):.4f}")],
                    scale(p, _prob(p, pr, pct=True)), sanity)
    return None


# ---------------------------------------------------------------- binomial trials in words

def trials(ctx: _Ctx) -> Solution | None:
    """"A player makes 70% of free throws; probability she makes exactly 7 of 10", "10% of parts are defective; in a
    sample of 5, P(at least 1 defective)", "expected number of defective items in 50 if 4% are defective"."""
    t = ctx.c
    if re.search(r"\bcoins?\b|\bdice\b|\bdie\b|\bcards?\b|\bdeck\b|\bpositive\b|\bnormal|\bmean\s+(?:of\s+)?\d|\bsd\b|"
                 r"\bstandard deviation\b|\$", ctx.m):
        return None
    ps = [m for m in re.finditer(rf"(?<![\w.])({NUM})\s*(?:%|percent\b)", t)]
    ps += [m for m in re.finditer(r"\b(?:probability|chance)\s+(?:of\s+(?:\w+\s+){0,4}?)?(?:is|=|of)\s+(0?\.\d+|\d+/\d+)\b", t)]
    if len(ps) != 1:
        return None
    p = _q(ps[0][1]) / (100 if "%" in ps[0][0] or "percent" in ps[0][0] else 1)
    if not 0 < p < 1:
        return None
    rest = _blank(t, [ps[0].span()])
    mk = (re.search(rf"\b({CMPW}|all|none|no)\s+(?:of\s+(?:the|them|her|his|their|these)\s+)?(\d+)?\s*(?:of|out of)\s+(?:the\s+|her\s+|his\s+|"
                    rf"their\s+|my\s+|next\s+)*(\d+)\b", rest)
          or re.search(rf"\b(?:in|of|out of|from)\s+(?:a\s+(?:random\s+)?sample\s+of\s+|the\s+next\s+|next\s+)?(\d+)\b.*?\b({CMPW})\s+(\d+)\b", rest)
          or re.search(rf"\b({CMPW})\s+(\d+)\b.*?\b(?:in|of|out of|from)\s+(?:a\s+(?:random\s+)?sample\s+of\s+|the\s+next\s+|next\s+)?(\d+)\b", rest))
    want_mean = re.search(r"\bexpected (?:number|count|value)\b|\bhow many\b.*\bexpect|\bmean number\b|\baverage number\b|\bvariance\b", rest)
    if not mk:
        if want_mean:
            mn = re.search(r"\b(?:sample of|batch of|group of|of|in|out of|from)\s+(\d+)\b|\b(\d+)\s+(?:trials|items|people|customers|"
                           r"parts|patients|shots|attempts|days|games|students)\b", rest)
            if mn:
                n = int(mn[1] or mn[2])
                return _binom_moments(ctx, "probability", n, p, [f"n = {n}", f"p = {_show(p)}"], "number of successes")
        return None
    g = mk.groups()
    if mk.re.pattern.startswith(r"\b(?:in|of"):
        n, cmpw, k = int(g[0]), g[1], int(g[2])
    elif mk.re.pattern.startswith(rf"\b({CMPW})\s+(\d+)\b.*?"):
        cmpw, k, n = g[0], int(g[1]), int(g[2])
    else:
        cmpw, n = g[0], int(g[2])
        k = int(g[1]) if g[1] else (n if cmpw == "all" else 0 if cmpw in ("none", "no") else None)
        if k is None:
            return None
        cmpw = "exactly" if cmpw in ("all", "none", "no") else cmpw
    if not 1 <= n <= MAX_N:
        return None
    rng = _event_range(cmpw, k, n)
    if not rng:
        return None
    return _binomial(ctx, "probability", n, p, rng[0], rng[1], [f"n = {n} trials", f"p = {_show(p)}"], "number of successes")


# ---------------------------------------------------------------- entry point

_TOPIC = re.compile(r"\b(?:mean|average|avg|median|modes?|range|variances?|var|standard deviations?|std|stdev|sd|s\.d|probabilit\w*|"
                    r"chances?|odds|likel\w*|percentiles?|z[- ]?scores?|zscores?|z[- ]?values?|normal\w*|gaussian|bell|binomial|"
                    r"bin|binom|dice|die|d\d+|\d+d\d+|coins?|heads?|tails?|flip\w*|toss\w*|cards?|deck|aces?|kings?|hands?|"
                    r"choose|combinations?|permutations?|arrang\w*|ways|committees?|ncr|npr|expected|expect\w*|raffles?|lottery|"
                    r"tickets?|bayes|positive|weighted|weights?|worth|frequenc\w*|anagrams?|handshakes?|podium|letters|word|"
                    r"presidents?|captains?|ev|fair|how many|number of|geometric|harmonic|scored|appears)\b|[σμ~]|\bp\s*\(|"
                    r"\b\d+[cp]\d+\b|\b[cpbn]\s*\(\s*\d")
_DEFINITION = re.compile(r"^\s*(?:(?:hey|hi|ok|okay|so|kepler|pls|please|quick one|quick q|um|hmm)[\s,:!]+)*(?:what(?:'s| is| are| does| do)|"
                         r"whats|define|explain|describe|meaning of|definition of|tell me about|how (?:do|does|can|should) (?:i|you|we|one)\b|"
                         r"why (?:is|do|does|are|would)|when (?:do|should|is|to|would)|(?:what's |what is )?the difference between|"
                         r"is there a difference|can you explain|give me an example)\b")


def solve(text: str) -> Solution | None:
    """A statistics or probability problem in plain English, solved exactly with steps; None when it isn't one."""
    if not text or len(text) > 600:
        return None
    ctx = _Ctx(text)
    t = ctx.c
    if not _TOPIC.search(t):
        return None
    if _DEFINITION.match(t) and not re.search(r"\d", t) and not re.search(
            r"\bprobabilit|\bchances?\b|\bodds\b|\bhow many\b|\bnumber of ways\b|\bexpected\b|\blikel|\barrange", t):
        return None
    for fn in (bayes, normal, binomial, expected_value, cards, dice, coin_moments, coins, trials, counting, weighted,
               missing_value, describe):
        try:
            sol = fn(ctx)
        except (ValueError, ZeroDivisionError, OverflowError, TypeError, AttributeError, KeyError, IndexError,
                RecursionError, StopIteration):
            sol = None
        if sol is not None:
            return sol
    return None
