"""Classic word problems and logic puzzles, solved exactly (sympy rationals) with worked steps and a check.

  ages            two conditions ("dad is 4 times my age, in 12 years twice"), "in how many years …", sums and
                  differences of ages
  mixtures        add water to dilute, evaporate, add the pure stuff, mix two strengths to hit a target, the strength
                  of a mix, blends priced per pound
  work rates      workers or pipes together, one filling while one drains, "together 4 h, A alone 6 h: B alone?"
  pairs           handshakes (also couples who skip their partner), diagonals of an n-gon, round-robin games, lines
                  and triangles through n points
  coins           pennies, nickels, dimes, quarters (and N-cent coins, bills): counts from the total and the value
  two-digit       numbers whose digits are reversed / swapped, digit sums and relations
  doubling        lily pads cover the lake on day 48: half on which day (also tripling, quarters, clock times)
  trains          meeting head-on, chasing, moving apart (departure offsets, clock times), "an hour before they meet",
                  trains passing poles, platforms and each other
  averages        weighted course grades (and the score needed on the final), combined group averages
  clock hands     angle at 3:15, when the hands overlap / are opposite / at right angles, how many times a day
  digit counts    how often a digit is written from 1 to 1000, how many numbers contain it, digits to number pages
  tickets         adult / child ticket counts from the total sold and the takings
  consecutive     integers (even, odd, multiples) with a given sum, product or sum of squares
  boats           river current up- and downstream (and planes with wind)

`solve(text)` reads the raw chat message (chatter like "quick one:", "pls", "4 sig figs" is fine) and returns None
for anything that isn't one of these, so Kepler commands and definition questions fall through to other readers.
"""
import contextvars
import math
import re
from decimal import Decimal

import sympy as sp

from ..fields import fmt as dec
from ..reasoning import Solution
from ..reasoning import fmt as efmt

KIND = "word_problem"
R = sp.Rational
N = r"(\d+(?:\.\d+)?)"
NUMRE = re.compile(r"\d+(?:\.\d+)?")

_SIG = contextvars.ContextVar("puzzles_sig", default=4)
_FRAC = contextvars.ContextVar("puzzles_frac", default=False)


# ---------------------------------------------------------------- numbers and formatting

def q(s) -> sp.Rational:
    return sp.Rational(str(s).replace(",", ""))


def sig(v: float) -> str:
    n = _SIG.get()
    if n == 4:
        return dec(v)
    if v == 0:
        return "0"
    digits = max(0, n - int(math.floor(math.log10(abs(v)))) - 1)
    return f"{v:,.{digits}f}"


def ex(x) -> str:
    """Short exact form: 12, 2.5, 16/3."""
    x = sp.nsimplify(x)
    if x.is_Integer:
        return f"{int(x):,}" if abs(x) >= 10000 else str(int(x))
    if x.is_Rational:
        if set(sp.factorint(x.q)) <= {2, 5} and x.q <= 10 ** 6:
            return format((Decimal(int(x.p)) / Decimal(int(x.q))).normalize(), "f")
        return f"{x.p}/{x.q}"
    return efmt(x)


def nice(x) -> str:
    """Exact when it's short (12, 2.5), else exact plus a decimal (16/3 ≈ 5.333, √2 ≈ 1.414)."""
    x = sp.nsimplify(x)
    if x.is_Integer:
        return ex(x)
    if x.is_Rational:
        if set(sp.factorint(x.q)) <= {2, 5} and x.q <= 10 ** 6:
            return f"{x.p}/{x.q} = {ex(x)}" if _FRAC.get() else ex(x)
        return f"{x.p}/{x.q} ≈ {sig(float(x))}"
    if x.is_number and x.is_real:
        return f"{efmt(x)} ≈ {sig(float(x))}"
    return efmt(x)


def cash(x, cur: str = "$") -> str:
    return f"{cur}{float(x):,.2f}"


def pl(word: str, x) -> str:
    """'1 hour', '2 hours'."""
    one = sp.nsimplify(x) == 1
    if one:
        return word[:-1] if word.endswith("s") and not word.endswith("ss") else word
    return word if word.endswith("s") else word + "s"


def duration(x, unit: str) -> str:
    """'2.4 hours = 2 h 24 min'."""
    x = sp.nsimplify(x)
    base = f"{nice(x)} {pl(unit, x)}"
    if x.is_Integer or x <= 0:
        return base
    if unit.startswith("hour"):
        h = int(sp.floor(x))
        m = (x - h) * 60
        head = f"{h} h " if h else ""
        if m.is_Integer:
            return f"{base} = {head}{int(m)} min"
        return f"{base} ≈ {head}{round(float(m))} min" if round(float(m)) < 60 else base
    if unit.startswith("minute"):
        mm = int(sp.floor(x))
        s = (x - mm) * 60
        if s.is_Integer:
            return f"{base} = {mm} min {int(s)} s"
        return f"{base} ≈ {mm} min {round(float(s))} s" if round(float(s)) < 60 else base
    return base


def _sol(problem: str, answer: str, steps: list[str], check: str = "") -> Solution:
    return Solution(KIND, problem.strip(), answer, steps, check=check, confidence=0.96)


def _unique(eqs, syms):
    try:
        sols = sp.solve(eqs, syms, dict=True)
    except (NotImplementedError, ValueError, TypeError):
        return None
    if len(sols) != 1 or any(s not in sols[0] for s in syms):
        return None
    if any(not sols[0][s].is_number for s in syms):
        return None
    return sols[0]


# ---------------------------------------------------------------- reading the message

ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
        "seventeen eighteen nineteen").split()
TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()
_VAL = {w: i for i, w in enumerate(ONES)} | {w: 20 + 10 * i for i, w in enumerate(TENS)}
_U = "|".join(sorted(ONES, key=len, reverse=True))
_D = "|".join(ONES[1:10])
_T = "|".join(TENS)
_B = rf"(?:(?:{_T})(?:[- ](?:{_D}))?|{_U})"
_H = rf"(?:(?:{_B}|a) hundred(?:(?: and)? {_B})?|{_B})"
_TH = rf"(?:{_H} thousand(?:,?(?: and)? {_H})?|{_H})"
NUMWORD = re.compile(rf"\b{_TH}\b")
ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9,
       "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15, "sixteenth": 16,
       "seventeenth": 17, "eighteenth": 18, "nineteenth": 19, "twentieth": 20, "thirtieth": 30, "fortieth": 40,
       "fiftieth": 50, "sixtieth": 60, "seventieth": 70, "eightieth": 80, "ninetieth": 90, "hundredth": 100}
_ORD_RE = re.compile(rf"\b(?:({_T})[- ])?({'|'.join(sorted(ORD, key=len, reverse=True))})\s+(?=(?:day|hour|minute|week|month|year)\b)")


def _wordval(s: str) -> int:
    total = cur = 0
    for w in s.replace("-", " ").replace(",", " ").split():
        if w == "and":
            continue
        if w == "a":
            cur = 1
        elif w == "hundred":
            cur = (cur or 1) * 100
        elif w == "thousand":
            total += (cur or 1) * 1000
            cur = 0
        else:
            cur += _VAL[w]
    return total + cur


def _numwords(t: str) -> str:
    def sub(m):
        run = m.group(0)
        if run == "one":
            before, after = m.string[max(0, m.start() - 8):m.start()], m.string[m.end():m.end() + 12]
            if re.match(r"\s+(?:another|of\b|by one)", after) or re.search(r"\b(?:no|the|which|this|that|each|any|every|some)\s+$", before):
                return run
        return str(_wordval(run))
    t = _ORD_RE.sub(lambda m: f"{(_VAL[m.group(1)] if m.group(1) else 0) + ORD[m.group(2)]}th ", t)
    return NUMWORD.sub(sub, t)


def prep(text: str) -> str:
    """Lower case, number words as digits, chatter that carries numbers ('4 sig figs', 'q3:') removed."""
    t = text.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = t.replace("−", "-").replace("–", "-").replace("—", " - ").replace("×", " x ").replace("½", " 1/2")
    t = re.sub(r"^\s*(?:q(?:uestion)?|problem|ex(?:ercise)?|no\.?|#)\s*\d+\s*[.:)]\s*", "", t)
    t = re.sub(r"[(\[]\s*\d+\s*(?:marks?|pts?|points)\s*[)\]]", " ", t)
    t = re.sub(r"\b(?:to |in |with |at |using )?\d+\s*(?:sig(?:nificant)?\.?\s*(?:figs?|figures?|digits?)|s\.?f\.?(?=\W|$)|d\.?p\.?(?=\W|$)|decimal places?|decimals?\b|dp\b)", " ", t)
    t = re.sub(r"\b(?:grade|year|class|level|unit|chapter|section|lesson|week|module|std|standard)\s+\d+\s+(?=(?:math|maths|homework|hw|test|exam|quiz|question|problem|assignment|worksheet)s?\b)", "", t)
    t = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", t)
    t = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", t)
    t = re.sub(r"\bhalf a dozen\b", "6", t)
    t = re.sub(r"\b(?:a|one) dozen\b", "12", t)
    t = _numwords(t)
    t = re.sub(r"\btwice\b", "2 times", t)
    t = re.sub(r"\bthrice\b", "3 times", t)
    t = re.sub(r"\bhalf as (many|much|old|long|big|fast|large)\b", r"0.5 times as \1", t)
    t = re.sub(r"\bhalf an hour\b|\ba half hour\b", "30 minutes", t)
    t = re.sub(r"\ba quarter of an hour\b|\bquarter of an hour\b", "15 minutes", t)
    t = re.sub(r"\b(?:an|1) hour and a half\b", "90 minutes", t)
    t = re.sub(r"\b(\d+) and a half (hours?|days?|minutes?|years?|weeks?)\b", r"\1.5 \2", t)
    t = re.sub(r"\b(?:an|a single) hour\b", "1 hour", t)
    t = re.sub(r"\b(\d+)\s*(?:hours?|hrs?|h)\s*(?:and\s*)?(\d+)\s*(?:minutes?|mins?|m)\b",
               lambda m: f"{int(m.group(1)) * 60 + int(m.group(2))} minutes", t)
    return re.sub(r"\s+", " ", t).strip()


# ---------------------------------------------------------------- clock hands

def _clock_time(t: str):
    m = re.search(r"\b(\d{1,2})[:.](\d{2})(?![\d.])", t)
    if m and int(m.group(1)) <= 24 and int(m.group(2)) < 60:
        return int(m.group(1)), int(m.group(2))
    pats = [(r"\bquarter (?:past|after) (\d{1,2})\b", lambda g: (int(g[0]), 15)),
            (r"\bhalf (?:past|after) (\d{1,2})\b", lambda g: (int(g[0]), 30)),
            (r"\bquarter (?:to|till|before|of) (\d{1,2})\b", lambda g: ((int(g[0]) - 1) or 12, 45)),
            (r"\b(\d{1,2}) (?:minutes? )?(?:past|after) (\d{1,2})\b", lambda g: (int(g[1]), int(g[0]))),
            (r"\b(\d{1,2}) (?:minutes? )?(?:to|till|before) (\d{1,2})\b", lambda g: ((int(g[1]) - 1) or 12, 60 - int(g[0]))),
            (r"\b(\d{1,2})\s*(?:o'?\s?clock|a\.?m\.?|p\.?m\.?)(?!\w)", lambda g: (int(g[0]), 0)),
            (r"\b(noon|midnight)\b", lambda g: (12, 0)),
            (r"\bat (\d{1,2})\b(?![:.]?\d|\s*(?:degrees|°|times|minutes?|hours?|%))", lambda g: (int(g[0]), 0))]
    for pat, mk in pats:
        m = re.search(pat, t)
        if m:
            h, mi = mk(m.groups())
            if 0 <= h <= 24 and 0 <= mi < 60:
                return h, mi
    return None


def _clock_str(h: int, m) -> str:
    m = sp.nsimplify(m)
    whole = int(sp.floor(m))
    secs = (m - whole) * 60
    s = round(float(secs))
    if s == 60:
        whole, s = whole + 1, 0
    hh = h % 12 or 12
    exact = f"{hh}:{whole:02d}" + (f":{s:02d}" if s else "")
    return exact if secs.is_Integer and not s else f"≈ {exact}"


def _mixed(x) -> str:
    x = sp.nsimplify(x)
    if x.is_Integer:
        return str(int(x))
    w = int(sp.floor(x))
    f = x - w
    return f"{w} {f.p}/{f.q}" if w else f"{f.p}/{f.q}"


def clock(t: str, text: str) -> Solution | None:
    if not re.search(r"\bclock\b|\bhands?\b", t):
        return None
    angle_q = re.search(r"\bangles?\b|\bdegrees?\b|°", t)
    rel = None
    if re.search(r"overlap|coincid|on top of each other|same (?:place|position|direction|spot)|\bmeet\b|line up|aligned|\btogether\b", t):
        rel = "overlap"
    elif re.search(r"opposite|straight line|form a line|180", t):
        rel = "opposite"
    elif re.search(r"right angles?|perpendicular|\b90 ?(?:degrees|°)|at 90\b", t):
        rel = "right"
    if rel:
        name = {"overlap": "overlap", "opposite": "point in opposite directions", "right": "are at right angles"}[rel]
        if re.search(r"how many times", t):
            hours = 24 if re.search(r"\bday\b|24 hours|24h|a full day", t) else 12
            per12 = 22 if rel == "right" else 11
            n = per12 * hours // 12
            return _sol(text, f"{n} times", [
                "rule: the minute hand turns 6° a minute, the hour hand 0.5°, so the minute hand gains 330° an hour",
                "known: in 12 hours it gains 330° × 12 = 3,960° = 11 full laps on the hour hand",
                f"substitute: each lap gives {'2 right angles (90° and 270°)' if rel == 'right' else '1 ' + ('overlap' if rel == 'overlap' else 'opposite position')}"
                f" → {per12} in 12 hours" + (f", × 2 for 24 hours" if hours == 24 else ""),
                f"result: {n} times"],
                "the 11 laps in 12 hours are why the hands meet at 12:00 but not between 11 and 12" if rel == "overlap" else "")
        m = re.search(r"between (\d{1,2})(?::00)?\s*(?:o'?clock|am|pm|a\.m\.|p\.m\.)? and (\d{1,2})\b", t)
        if m:
            h = int(m.group(1)) % 12
            deltas = {"overlap": [0], "opposite": [180], "right": [90, 270]}[rel]
            times = sorted({R(2, 11) * (30 * h + d + 360 * k) for d in deltas for k in (-1, 0, 1)
                            if 0 <= R(2, 11) * (30 * h + d + 360 * k) < 60})
            hh = h or 12
            steps = ["rule: hour hand at 30°·h + 0.5°·m, minute hand at 6°·m; the minute hand gains 5.5° a minute",
                     f"known: at {hh}:00 the hour hand is {30 * h}° ahead; the hands {name} when the gap is "
                     + " or ".join(f"{d}°" for d in deltas) + " (mod 360°)"]
            if not times:
                return _sol(text, f"never strictly between {hh} and {(hh % 12) + 1} (it happens at 12:00)", steps)
            for x in times:
                steps.append(f"substitute: 5.5·m = {ex(5.5 * x)} → m = {_mixed(x)} minutes")
            ans = " and ".join(f"{_mixed(x)} minutes past {hh} ({_clock_str(h, x)})" for x in times)
            x0 = times[0]
            ha, ma = 30 * h + x0 / 2, 6 * x0
            steps.append(f"result: {ans}")
            return _sol(text, ans, steps, f"at m = {_mixed(x0)}: hour hand {nice(ha % 360)}°, minute hand {nice(ma % 360)}° ✓")
    if not angle_q:
        return None
    tm = _clock_time(t)
    if not tm:
        return None
    h, m = tm
    hh = h % 12
    ha, ma = 30 * hh + R(m, 2), 6 * m
    diff = abs(ha - ma)
    small = min(diff, 360 - diff)
    want_big = re.search(r"reflex|larger|bigger|greater|outer|other angle|obtuse side", t)
    ans = 360 - small if want_big else small
    shown = f"{h}:{m:02d}"
    steps = ["formula: hour hand = 30° × h + 0.5° × m, minute hand = 6° × m  (from 12, clockwise)",
             f"known: h = {hh or 12}" + (f" ({h}:00 on a 24-hour clock)" if h > 12 else "") + f", m = {m}",
             f"substitute: hour hand = 30 × {hh} + 0.5 × {m} = {nice(ha)}°, minute hand = 6 × {m} = {ma}°",
             f"result: |{nice(ha)} − {ma}| = {nice(diff)}°" + (f", and 360 − {nice(diff)} = {nice(360 - diff)}°" if diff > 180 else "")
             + f" → the smaller angle is {nice(small)}° (the reflex angle {nice(360 - small)}°)"]
    return _sol(text, f"{nice(ans)}°", steps,
                f"|30h − 5.5m| = |{30 * hh} − {ex(R(11, 2) * m)}| = {nice(diff)}° ✓  (at {shown})")


# ---------------------------------------------------------------- handshakes, diagonals, games, points

POLY = {"triangle": 3, "quadrilateral": 4, "square": 4, "rectangle": 4, "rhombus": 4, "pentagon": 5, "hexagon": 6,
        "heptagon": 7, "septagon": 7, "octagon": 8, "nonagon": 9, "enneagon": 9, "decagon": 10, "hendecagon": 11,
        "undecagon": 11, "dodecagon": 12, "tridecagon": 13, "tetradecagon": 14, "pentadecagon": 15,
        "hexadecagon": 16, "icosagon": 20}
POLY_RE = re.compile(r"\b(" + "|".join(sorted(POLY, key=len, reverse=True)) + r")s?\b")
PEOPLE = (r"(?:people|persons|guests|friends|students|players|delegates|members|men|women|boys|girls|kids|children|"
          r"attendees|participants|guys|employees|colleagues|executives|scientists|diplomats|athletes|individuals|"
          r"politicians|dancers|workers|co-?workers|strangers|relatives|classmates|teammates|teachers|doctors|"
          r"leaders|ministers|senators|engineers|businessmen|businesswomen|mathematicians|couples|teams|of us|of them)")
PEOPLE_Q = r"how many (?:people|persons|guests|friends|students|players|delegates|members|attendees|participants|guys|employees|were there|are there|people were|people are)"


def _c2(n):
    return sp.binomial(n, 2)


def _inverse_pairs(total, offset: int):
    """Smallest n with n(n − offset)/2 = total (offset 1: handshakes, 3: diagonals)."""
    disc = offset * offset + 8 * total
    r = sp.sqrt(disc)
    n = (offset + r) / 2
    return n, disc


def pairs(t: str, text: str) -> Solution | None:
    if re.search(r"hand ?shakes?|shak\w* hands?|shook hands|hand-shak", t):
        return _handshakes(t, text)
    if re.search(r"\bdiagonals?\b", t):
        return _diagonals(t, text)
    if re.search(r"\b(?:games?|matches|fixtures|bouts)\b", t) and re.search(
            r"round[- ]robin|each other|every other|everyone else|every one else|all the others|one another|each of the other|"
            r"every (?:other )?(?:team|player|club|side|school)|each (?:other )?(?:team|player|club|side|school)|all other (?:teams|players)", t):
        return _games(t, text)
    pts = re.search(r"\b(\d+) (?:distinct |different |separate )?points\b", t)
    if pts and re.search(r"how many", t) and re.search(r"\b(?:lines?|line segments?|chords?|triangles?)\b", t):
        n = int(pts.group(1))
        if n < 2 or n > 10 ** 6:
            return None
        if re.search(r"\btriangles?\b", t):
            v = sp.binomial(n, 3)
            return _sol(text, f"{ex(v)} triangles", [
                "rule: any 3 of the points (no three on a line) make one triangle: C(n, 3) = n(n − 1)(n − 2)/6",
                f"known: n = {n}", f"substitute: {n} × {n - 1} × {n - 2} / 6", f"result: {ex(v)} triangles"])
        v = _c2(n)
        return _sol(text, f"{ex(v)} lines", [
            "rule: every pair of points (no three on a line) gives one line: C(n, 2) = n(n − 1)/2",
            f"known: n = {n}", f"substitute: {n} × {n - 1} / 2", f"result: {ex(v)} lines"],
            f"each point joins the other {n - 1}: {n} × {n - 1} ends, each line counted twice ✓")
    return None


def _handshakes(t: str, text: str) -> Solution | None:
    couples = re.search(r"\b(\d+) (?:married )?couples\b", t)
    if couples and re.search(r"spouse|partner|husband|wife|their own|other half|significant other", t):
        c = int(couples.group(1))
        n = 2 * c
        v = _c2(n) - c
        return _sol(text, f"{ex(v)} handshakes", [
            "rule: everyone shakes hands with everyone except their own partner: C(2c, 2) − c",
            f"known: c = {c} couples, so {n} people",
            f"substitute: {n} × {n - 1} / 2 − {c} = {ex(_c2(n))} − {c}", f"result: {ex(v)} handshakes"],
            f"each person shakes {n - 2} hands: {n} × {n - 2} / 2 = {ex(R(n * (n - 2), 2))} ✓")
    known = re.search(r"\b(\d+) (?:hand ?shakes|handshakes)\b|\bhandshakes (?:is|was|were|are|totals?|=) (\d+)\b", t)
    ppl = (re.search(rf"\b(\d+) (?:other )?{PEOPLE}\b", t)
           or re.search(r"\b(?:party|meeting|room|group|class|gathering|conference|team|reunion|event|dinner|club|committee|panel|board|crowd|wedding)\s+(?:of|with)\s+(\d+)\b", t)
           or re.search(r"\b(\d+) (?:of us|of them|of you)\b", t))
    if known and not ppl and re.search(rf"{PEOPLE_Q}|how many (?:were|are) (?:at|in|there)|number of (?:people|guests)", t):
        h = int(next(g for g in known.groups() if g))
        n, disc = _inverse_pairs(h, 1)
        steps = ["rule: n people make n(n − 1)/2 handshakes", f"known: n(n − 1)/2 = {h} → n² − n − {2 * h} = 0",
                 f"substitute: n = (1 + √(1 + 8 × {h}))/2 = (1 + √{disc})/2"]
        if not n.is_Integer:
            return _sol(text, f"no whole number of people gives exactly {h} handshakes", steps + [f"result: n = {nice(n)} isn't whole"])
        steps.append(f"result: n = {ex(n)} people")
        return _sol(text, f"{ex(n)} people", steps, f"{ex(n)} × {ex(n - 1)} / 2 = {h} ✓")
    if not ppl:
        return None
    n = int(ppl.group(1))
    if re.search(rf"\b{n} other\b", t):
        n += 1
    if n < 2 or n > 10 ** 7:
        return None
    v = _c2(n)
    return _sol(text, f"{ex(v)} handshakes", [
        "rule: each of the n people shakes hands with the other n − 1, and every handshake involves two people: "
        "H = n(n − 1)/2 = C(n, 2)", f"known: n = {n}", f"substitute: H = {n} × {n - 1} / 2", f"result: {ex(v)} handshakes"],
        f"add them up: {n - 1} + {n - 2} + … + 1 = {ex(v)} ✓")


def _diagonals(t: str, text: str) -> Solution | None:
    known = re.search(r"\b(\d+) diagonals\b|\bdiagonals (?:is|are|=) (\d+)\b", t)
    m = (re.search(r"\b(\d+)[- ]?(?:sided|sides|gon)\b", t)
         or re.search(r"\b(?:polygon|shape|figure|n-gon)\s+(?:with|that has|having|of|has)\s+(\d+)\s+(?:sides|vertices|corners|edges|angles)\b", t)
         or re.search(r"\b(\d+) (?:sides|vertices|corners|edges)\b", t))
    named = POLY_RE.search(t)
    if known and not m and re.search(r"how many (?:sides|vertices|corners|edges|angles)|what (?:kind of |type of |sort of )?polygon|which polygon|name (?:of )?the polygon|what shape", t):
        d = int(next(g for g in known.groups() if g))
        n, disc = _inverse_pairs(d, 3)
        steps = ["rule: an n-gon has n(n − 3)/2 diagonals", f"known: n(n − 3)/2 = {d} → n² − 3n − {2 * d} = 0",
                 f"substitute: n = (3 + √(9 + 8 × {d}))/2 = (3 + √{disc})/2"]
        if not n.is_Integer:
            return _sol(text, f"no polygon has exactly {d} diagonals", steps + [f"result: n = {nice(n)} isn't whole"])
        name = next((k for k, v in POLY.items() if v == n and k not in ("square", "rectangle", "rhombus")), f"{ex(n)}-gon")
        steps.append(f"result: n = {ex(n)} sides")
        return _sol(text, f"{ex(n)} sides ({name})", steps, f"{ex(n)} × {ex(n - 3)} / 2 = {d} ✓")
    if m:
        n = int(m.group(1))
    elif named:
        n = POLY[named.group(1)]
    else:
        return None
    if n < 3 or n > 10 ** 7:
        return None
    v = R(n * (n - 3), 2)
    return _sol(text, f"{ex(v)} diagonals", [
        "rule: each vertex joins the n − 3 vertices that aren't itself or its two neighbours, and each diagonal has two "
        "ends: D = n(n − 3)/2", f"known: n = {n}", f"substitute: D = {n} × {n - 3} / 2", f"result: {ex(v)} diagonals"],
        f"C({n}, 2) − {n} sides = {ex(_c2(n))} − {n} = {ex(v)} ✓")


def _games(t: str, text: str) -> Solution | None:
    k = 1
    km = re.search(r"\bplays? (?:each other |every other \w+ |each other \w+ |against each other )?(\d+) times\b|\b(\d+) times (?:each|against each other|against every)", t)
    if km:
        k = int(next(g for g in km.groups() if g))
    elif re.search(r"home and away|home-and-away|\b2 times\b|\bdouble round", t):
        k = 2
    m = (re.search(r"\b(\d+) (?:teams|players|clubs|schools|people|participants|competitors|contestants|sides|chess players|"
                   r"tennis players|nations|countries|colleges|members|friends|kids|students|boys|girls|squads|universities)\b", t)
         or re.search(r"\b(?:league|tournament|competition|division|group) (?:of|with) (\d+)\b", t))
    known = re.search(r"\b(\d+) (?:games|matches)\b", t)
    if known and not m and re.search(r"how many (?:teams|players|clubs|schools|participants|competitors|contestants|sides|nations|countries)", t):
        g = int(known.group(1))
        if g % k:
            return None
        n, disc = _inverse_pairs(g // k, 1)
        steps = [f"rule: n teams playing each pair {k} time{'s' if k > 1 else ''} make {k if k > 1 else ''}{'·' if k > 1 else ''}n(n − 1)/2 games",
                 f"known: n(n − 1)/2 = {g // k}", f"substitute: n = (1 + √{disc})/2"]
        if not n.is_Integer:
            return _sol(text, f"no whole number of teams gives exactly {g} games", steps + [f"result: n = {nice(n)}"])
        steps.append(f"result: {ex(n)} teams")
        return _sol(text, f"{ex(n)} teams", steps, f"{ex(n)} × {ex(n - 1)} / 2 × {k} = {g} ✓")
    if not m:
        return None
    n = int(m.group(1))
    if n < 2 or n > 10 ** 7:
        return None
    v = _c2(n) * k
    return _sol(text, f"{ex(v)} games", [
        "rule: one game for every pair of teams: C(n, 2) = n(n − 1)/2" + (f", times {k} because each pair meets {k} times" if k > 1 else ""),
        f"known: n = {n}" + (f", each pair plays {k} times" if k > 1 else ""),
        f"substitute: {n} × {n - 1} / 2" + (f" × {k}" if k > 1 else ""), f"result: {ex(v)} games"],
        f"each team plays {(n - 1) * k} games: {n} × {(n - 1) * k} / 2 = {ex(v)} ✓")


# ---------------------------------------------------------------- how often a digit is written

def _place_counts(n: int, d: int) -> list[int]:
    """Occurrences of digit d at each place (units first) when writing 1..n."""
    out, p = [], 1
    while p <= n:
        high, cur, low = n // (p * 10), (n // p) % 10, n % p
        if d:
            c = high * p + (p if cur > d else low + 1 if cur == d else 0)
        else:
            c = ((high - 1) * p + (p if cur > 0 else low + 1)) if high else 0
        out.append(c)
        p *= 10
    return out


def _free(n: int, d: int) -> int:
    """How many of 1..n never use the digit d."""
    if n <= 0:
        return 0
    s = str(n)
    total = sum((8 if d else 9) * 9 ** (k - 1) for k in range(1, len(s)))
    for i, ch in enumerate(s):
        c = int(ch)
        total += sum(1 for x in range(1 if i == 0 else 0, c) if x != d) * 9 ** (len(s) - i - 1)
        if c == d:
            break
    else:
        total += 1
    return total


def _all_digits(n: int) -> int:
    total, k, lo = 0, 1, 1
    while lo <= n:
        hi = min(n, 10 ** k - 1)
        total += (hi - lo + 1) * k
        k, lo = k + 1, 10 ** k
    return total


def _range(t: str):
    m = re.search(r"\b(?:from|between) (\d+) (?:to|and|through|thru|till|until|up to|-) (\d+)\b", t)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"\b(?:first|1st) (\d+) (?:natural numbers|positive integers|whole numbers|counting numbers|numbers|integers|pages)\b", t)
    if m:
        return 1, int(m.group(1))
    m = re.search(r"\b(\d+)[- ]pages?\b|\b(?:book|document|report|magazine|manual|novel|diary|notebook) (?:with|of|has|that has|having|containing) (\d+) pages\b|\bpages? 1 (?:to|through|-) (\d+)\b|\b(\d+) pages\b", t)
    if m:
        return 1, int(next(g for g in m.groups() if g))
    m = re.search(r"\b(?:up to|upto|until|till|through|to)\s+(\d+)\b", t)
    if m:
        return 1, int(m.group(1))
    m = re.search(r"\b(?:below|under|less than)\s+(\d+)\b", t)
    if m:
        return 1, int(m.group(1)) - 1
    m = re.search(r"\b(\d+) ?- ?(\d+)\b", t)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def digit_count(t: str, text: str) -> Solution | None:
    if not re.search(r"\bdigits?\b|\bnumerals?\b|\b\d'?s\b|how many times|how often", t):
        return None
    contain = re.search(r"how many (?:numbers|integers|whole numbers|natural numbers|of (?:them|these|the numbers)|pages|page numbers|house numbers|values)\b.*?"
                        r"\b(?:contain|contains|containing|have|has|having|include|includes|including|with|use|uses|using|feature|show)\b"
                        r"(?: at least one| a| an| the| one or more)?(?: digit| numeral)?(?: of)? (\d)(?:'?s)?\b", t)
    d = None
    for pat in (r"\b(?:the )?(?:digit|numeral) (\d)\b(?!\d)",
                r"\bhow many (\d)'?s\b",
                r"\bnumber of (\d)'?s\b",
                r"\bhow (?:many times|often) (?:is|does|do|will|would|did|must|should|can) (?:the )?(?:number )?(\d)\b(?! ?(?:to|-|through|and)\b ?\d)",
                r"\bhow (?:many times|often) (?:do|does|will|would|did|must|should|can) (?:you|i|we|one|someone|he|she|they|a \w+) "
                r"(?:have to |need to )?(?:write|use|print|type|press|see|count|need|paint) (?:the )?(?:digit |numeral |number )?(\d)\b",
                r"\bcount (?:the |all the )?(\d)'?s\b"):
        m = re.search(pat, t)
        if m:
            d = int(m.group(1))
            break
    rng = _range(t)
    if not rng:
        return None
    a, b = rng
    if b < a or b > 10 ** 15 or a < 0:
        return None
    a = max(a, 1)
    if contain:
        dd = int(contain.group(1))
        free = _free(b, dd) - _free(a - 1, dd)
        total = b - a + 1
        v = total - free
        return _sol(text, f"{ex(v)} numbers", [
            f"rule: count the numbers with no {dd} at all, then take them away from all {ex(total)} numbers",
            f"known: {a} to {b} inclusive",
            f"substitute: numbers without a {dd}: {ex(free)}; {ex(total)} − {ex(free)}",
            f"result: {ex(v)} numbers contain at least one {dd}"],
            "this counts numbers, not digits: 77 counts once here" if dd and b >= 11 * dd else "")
    if d is None:
        if re.search(r"how many digits|total (?:number of )?digits|digits (?:are|would be|will be|were) (?:needed|used|required|printed|written)", t):
            v = _all_digits(b) - _all_digits(a - 1)
            parts, k, lo = [], 1, 1
            while lo <= b:
                hi, l2 = min(b, 10 ** k - 1), max(lo, a)
                if l2 <= hi:
                    parts.append(f"{l2}–{hi}: {hi - l2 + 1} × {k} = {ex((hi - l2 + 1) * k)}")
                k, lo = k + 1, 10 ** k
            return _sol(text, f"{ex(v)} digits", [
                "rule: group the numbers by how many digits they have", f"known: {a} to {b}",
                "substitute: " + "; ".join(parts), f"result: {ex(v)} digits"])
        return None
    hi, lo = _place_counts(b, d), _place_counts(a - 1, d)
    lo += [0] * (len(hi) - len(lo))
    per = [x - y for x, y in zip(hi, lo)]
    v = sum(per)
    names = ["units", "tens", "hundreds", "thousands", "ten-thousands", "hundred-thousands", "millions"]
    shown = [f"{names[i] if i < len(names) else f'10^{i}'} place: {ex(c)}" for i, c in enumerate(per) if c]
    return _sol(text, f"{ex(v)} times", [
        f"rule: count the {d}s place by place (units, tens, …) and add",
        f"known: digit {d}, numbers {a} to {b} inclusive",
        "substitute: " + ("; ".join(shown) or "none"), f"result: {ex(v)} times"],
        (f"numbers containing a {d}: {ex((b - a + 1) - (_free(b, d) - _free(a - 1, d)))} (fewer, because a number like "
         f"{d}{d} has two)") if d and b >= 11 * d else "")


# ---------------------------------------------------------------- doubling growth

FRACTIONS = [(r"\b(?:half|1/2|halfway|50 ?%)", R(1, 2)), (r"\b(?:quarter|1/4|one[- ]fourth|fourth|25 ?%)", R(1, 4)),
             (r"\b(?:eighth|1/8|12\.5 ?%)", R(1, 8)), (r"\b(?:sixteenth|1/16)", R(1, 16)), (r"\b(?:ninth|1/9)", R(1, 9)),
             (r"\b(?:third|1/3)", R(1, 3))]


def doubling(t: str, text: str) -> Solution | None:
    if re.search(r"\bdoubl\w*|\b2 times (?:as (?:big|large|much|many) |its size |the size |in size |bigger |larger |more )?(?:every|each|per)|\btwice its size", t):
        g, verb = 2, "doubles"
    elif re.search(r"\btripl\w*|\b3 times (?:as (?:big|large|much|many) |its size |in size |bigger |larger |more )?(?:every|each|per)", t):
        g, verb = 3, "triples"
    elif re.search(r"\bquadrupl\w*", t):
        g, verb = 4, "quadruples"
    else:
        return None
    if not re.search(r"\b(?:cover\w*|fill\w*|full|entire|whole|complete\w*|all of|takes over|occup\w*|reach\w*)\b", t):
        return None
    frac = None
    m = re.search(r"\b(\d+)/(\d+)\b", t)
    if m and int(m.group(2)) > 0 and int(m.group(1)) < int(m.group(2)):
        frac = R(int(m.group(1)), int(m.group(2)))
    if frac is None:
        for pat, f in FRACTIONS:
            if re.search(pat, t):
                frac = f
                break
    if frac is None:
        return None
    unit_m = re.search(r"\b(?:every|each|per|a|an) (day|hour|minute|second|week|month|year)\b|\b(daily|hourly|weekly|yearly|annually)\b", t)
    unit = None
    if unit_m:
        unit = unit_m.group(1) or {"daily": "day", "hourly": "hour", "weekly": "week", "yearly": "year", "annually": "year"}[unit_m.group(2)]
    full = (re.search(r"\b(?:day|hour|minute|week|month|year) (\d+)\b", t)
            or re.search(r"\b(\d+)(?:st|nd|rd|th)? (days?|hours?|minutes?|mins?|weeks?|months?|years?|seconds?|secs?)\b", t)
            or re.search(r"\b(\d+)(?:st|nd|rd|th) (day|hour|minute|week|month|year)\b", t))
    clockm = re.search(r"\b(?:full|covered|filled|covers|fills|cover|fill|complete)\b[^.?]*?\b(?:at|by) (noon|midnight|\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)|\d{1,2}:\d{2})", t)
    k = sp.log(1 / frac, g)
    k = sp.nsimplify(k) if sp.nsimplify(k).is_Integer else k
    if clockm and unit in ("minute", "hour", "second"):
        tm = _clock_time(clockm.group(1))
        if not tm:
            return None
        h, mi = tm
        if re.search(r"\bpm\b|p\.m\.", clockm.group(1)) and h < 12:
            h += 12
        if not k.is_Integer:
            return None
        total = h * 60 + mi - (int(k) if unit == "minute" else int(k) * 60 if unit == "hour" else 0)
        if unit == "second":
            return None
        hh, mm = divmod(total % (24 * 60), 60)
        when = f"{hh % 12 or 12}:{mm:02d} {'am' if hh < 12 else 'pm'}"
        return _sol(text, when, [
            f"rule: it {verb} every {unit}, so going back one {unit} divides it by {g}",
            f"known: full at {clockm.group(1)}, asked when it is {ex(frac)} full",
            f"substitute: {ex(frac)} = (1/{g})^{ex(k)} → {ex(k)} {pl(unit, k)} earlier", f"result: {when}"],
            f"from {when}, {ex(k)} more {verb[:-1]}{'ing' if not verb.endswith('es') else ''}s → full ✓".replace("doublings", "doublings").replace("ings", "ings"))
    if not full:
        return None
    n = int(full.group(1))
    if unit is None:
        unit = re.sub(r"s$", "", full.group(2) if full.lastindex and full.lastindex >= 2 and full.group(2) else "day")
        unit = {"min": "minute", "sec": "second"}.get(unit, unit)
    ans_n = n - k
    if ans_n.is_number and ans_n < 0:
        return None
    which = re.search(r"\b(?:which|what) (?:day|hour|minute|week|month|year)\b|\bon (?:which|what)\b", t)
    if ans_n.is_Integer:
        ans = f"{unit} {ex(ans_n)}" if which else f"{ex(ans_n)} {pl(unit + 's', ans_n)}"
    else:
        ans = f"{nice(ans_n)} {unit + 's'}"
    steps = [f"rule: it {verb} every {unit}, so one {unit} before it is full it covers 1/{g}; work backwards",
             f"known: full after {n} {pl(unit + 's', n)}, asked when it covers {ex(frac)}",
             f"substitute: {ex(frac)} = (1/{g})^k → k = {nice(k)} {pl(unit + 's', k) if k.is_Integer else unit + 's'} earlier: {n} − {nice(k)}",
             f"result: {ans}"]
    trap = ""
    if frac == R(1, 2) and g == 2:
        trap = f" — not {ex(R(n, 2))}: halving the area isn't halving the time"
    chain = ""
    if k.is_Integer and 0 < k <= 4:
        seq = [f"{unit} {ex(ans_n + i)}: {ex(frac * g ** i)}" for i in range(int(k) + 1)]
        chain = " → ".join(seq).replace(": 1 ", ": full ").rstrip()
        chain = chain[:-2] + "full" if chain.endswith(": 1") else chain
    return _sol(text, ans, steps, (chain + " ✓" if chain else "") + trap)


# ---------------------------------------------------------------- consecutive integers

def consecutive(t: str, text: str) -> Solution | None:
    t = re.sub(r"\b(?:negative|minus) (\d)", r"-\1", t)
    m = re.search(r"\b(\d+) consecutive (?:positive |negative |whole |natural |counting )?(even |odd )?(?:positive |negative )?"
                  r"(?:integers?|numbers?|whole numbers?|natural numbers?|ints?|counting numbers?|page numbers?|pages|multiples of (\d+))?\b", t)
    if not m:
        m2 = re.search(r"\b(?:a pair of|pair of) consecutive (even |odd )?", t)
        if not m2:
            return None
        cnt, par, mult = 2, (m2.group(1) or "").strip(), None
        span = m2.span()
    else:
        cnt, par, mult = int(m.group(1)), (m.group(2) or "").strip(), m.group(3)
        span = m.span()
    if cnt < 2 or cnt > 50:
        return None
    rest = t[:span[0]] + " " + t[span[1]:]
    if re.search(r"\bproduct\b|multipl(?:y|ied)(?: together)?(?: to| gives?| makes?| is)\b|multipl(?:y|ied) together", rest):
        op = "product"
    elif re.search(r"\bsquares\b", rest):
        op = "squares"
    elif re.search(r"\bsum\b|\badd(?:s|ed)?\b|\btotal\w*\b|\bcombined\b|\baltogether\b|\btogether\b|\bplus\b", rest):
        op = "sum"
    else:
        return None
    nums = [mm for mm in re.finditer(r"-?\d+(?:\.\d+)?", rest) if not (mult and mm.group(0) == mult)]
    if len(nums) != 1:
        cue = re.search(r"(?:is|are|equals?|=|of|to|gives?|makes?|be|was|totals?|totaling|totalling|yields?)\s+(-?\d+(?:\.\d+)?)", rest)
        if not cue:
            return None
        target = q(cue.group(1))
    else:
        target = q(nums[0].group(0))
    step = int(mult) if mult else (2 if par else 1)
    x = sp.Symbol("n")
    terms = [x + step * i for i in range(cnt)]
    expr = {"sum": sum(terms), "product": sp.Mul(*terms), "squares": sum(e ** 2 for e in terms)}[op]
    sols = [s for s in sp.solve(sp.Eq(expr, target), x) if s.is_real]

    def ok(s):
        if not s.is_integer:
            return False
        if par == "even" and s % 2:
            return False
        if par == "odd" and s % 2 == 0:
            return False
        if mult and s % int(mult):
            return False
        if re.search(r"\bpositive\b|\bnatural\b|\bcounting\b|\bpages?\b|\bwhole\b", t) and s <= 0:
            return False
        return True
    good = sorted((s for s in sols if ok(s)), reverse=True)
    word = f"{par} " if par else (f"multiples of {mult} " if mult else "")
    let = ", ".join(efmt(e) for e in terms)
    shown_expr = {"sum": efmt(sp.expand(expr)), "product": " · ".join(f"({efmt(e)})" for e in terms),
                  "squares": " + ".join(f"({efmt(e)})²" for e in terms)}[op]
    steps = [f"rule: consecutive {word or 'integers '}go up by {step}: let them be {let}",
             f"known: {'sum' if op == 'sum' else 'product' if op == 'product' else 'sum of squares'} = {ex(target)}",
             f"substitute: {shown_expr} = {ex(target)}" + (f" → n = {nice(sols[0])}" if op == "sum" and sols else "")]
    if not good:
        bad = ", ".join(nice(s) for s in sols) or "no real value"
        return _sol(text, f"no {cnt} consecutive {word}integers have that {op if op != 'squares' else 'sum of squares'}",
                    steps + [f"result: n = {bad}, which isn't a valid {par or 'whole'} number"])
    sets = [[e.subs(x, s) for e in terms] for s in good]
    main = sets[0]
    pick = None
    if re.search(r"\b(?:largest|greatest|biggest|larger|greater|bigger|highest|last)\b", t):
        pick = max(main)
    elif re.search(r"\b(?:smallest|least|smaller|lesser|lowest|first)\b", t):
        pick = min(main)
    elif re.search(r"\bmiddle\b", t) and cnt % 2:
        pick = main[cnt // 2]
    listing = ", ".join(ex(v) for v in main)
    ans = ex(pick) if pick is not None else listing
    if len(sets) > 1 and pick is None:
        ans += " (or " + "; ".join(", ".join(ex(v) for v in s_) for s_ in sets[1:]) + ")"
    steps.append(f"result: n = {ex(good[0])}, so the numbers are {listing}" + (f"; asked for {ex(pick)}" if pick is not None else ""))
    joiner = " + " if op == "sum" else " × " if op == "product" else "² + "
    val = sum(main) if op == "sum" else sp.Mul(*main) if op == "product" else sum(v ** 2 for v in main)
    chk = joiner.join(ex(v) for v in main) + ("²" if op == "squares" else "") + f" = {ex(val)} ✓"
    return _sol(text, ans, steps, chk)


# ---------------------------------------------------------------- two-digit numbers, digits reversed

def two_digit(t: str, text: str) -> Solution | None:
    if not re.search(r"\bdigits?\b", t):
        return None
    if not re.search(r"\b(?:2|two)[- ]digits?\b|\btens(?:'s)? digit|\bunits?(?:'s)? digit|\bones(?:'s)? digit|revers|interchang|swap|switch|flip|transpos|backwards", t):
        return None
    if re.search(r"how many (?:times|numbers|integers)|\bfrom \d+ to \d+\b|\bpages?\b", t):
        return None
    a, b = sp.symbols("a b", integer=True)
    num, rev, s_ = 10 * a + b, 10 * b + a, a + b
    conds = []  # (text, sympy relation or predicate)
    tt = re.sub(r"\bhalf (?:of )?(?:the )?", "0.5 times the ", t)
    tt = re.sub(r"\bunit'?s?\b|\bones\b|\bone'?s\b", "units", tt)
    tt = re.sub(r"\bten'?s\b", "tens", tt)
    tt = re.sub(r"\b(?:the |its |their |of |both )+(?=digits)", "", tt)
    tt = re.sub(r"\b(sum|product) digits", r"\1 of digits", tt)
    tt = re.sub(r"\b(sum|product) of digits of (?:a |the |this |that )?(?:(?:2|two)[- ]digit )?number", r"\1 of digits", tt)
    tt = re.sub(r"\b(?:you |we |i )?(?:get|gets|getting|gives?|giving|makes?|making|forms?|becomes?) (?:a|the) (?:new )?number (?=\d+ (?:more|greater|larger|bigger|less|smaller|fewer)\b)", "new number is ", tt)
    which = {"tens": a, "units": b}
    reversal = re.search(r"revers|interchang|swap|switch|flip|transpos|backwards|order of (?:the |its )?digits", tt)
    for m in re.finditer(r"sum of (?:the |its |their )?(?:2 )?digits (?:is|=|equals|of|gives|will be|adds up to|was)? ?(\d+)|digits (?:add up to|sum to|total|add to) (\d+)", tt):
        v = int(next(g for g in m.groups() if g))
        conds.append((f"a + b = {v}", sp.Eq(s_, v)))
    for m in re.finditer(r"product of (?:the |its )?digits (?:is|=|equals) (\d+)", tt):
        conds.append((f"a·b = {m.group(1)}", sp.Eq(a * b, int(m.group(1)))))
    for m in re.finditer(r"difference (?:between|of) (?:the |its )?(?:2 )?digits (?:is|=|equals) (\d+)|digits differ by (\d+)", tt):
        v = int(next(g for g in m.groups() if g))
        conds.append((f"|a − b| = {v}", lambda A, B, v=v: abs(A - B) == v))
    for m in re.finditer(r"(tens|units) digit is (\d+(?:\.\d+)?) times (?:the |its )?(tens|units) digit", tt):
        if m.group(1) != m.group(3):
            x, y = which[m.group(1)], which[m.group(3)]
            conds.append((f"{x} = {m.group(2)}·{y}", sp.Eq(x, q(m.group(2)) * y)))
    for m in re.finditer(r"(tens|units) digit is (\d+) (more|greater|bigger|larger|less|smaller|fewer) than (?:the |its )?(tens|units) digit", tt):
        if m.group(1) != m.group(4):
            x, y, v = which[m.group(1)], which[m.group(4)], int(m.group(2))
            sign = 1 if m.group(3) in ("more", "greater", "bigger", "larger") else -1
            conds.append((f"{x} = {y} {'+' if sign > 0 else '−'} {v}", sp.Eq(x, y + sign * v)))
    for m in re.finditer(r"(tens|units) digit exceeds (?:the |its )?(tens|units) digit by (\d+)", tt):
        if m.group(1) != m.group(2):
            x, y = which[m.group(1)], which[m.group(2)]
            conds.append((f"{x} = {y} + {m.group(3)}", sp.Eq(x, y + int(m.group(3)))))
    for m in re.finditer(r"(tens|units) digit is (?:equal to |the same as )?(?:the |its )?(tens|units) digit\b", tt):
        if m.group(1) != m.group(2):
            conds.append(("a = b", sp.Eq(a, b)))
    for m in re.finditer(r"(tens|units) digit is (\d)\b(?! times| more| less| greater| smaller| bigger| larger| fewer)", tt):
        conds.append((f"{which[m.group(1)]} = {m.group(2)}", sp.Eq(which[m.group(1)], int(m.group(2)))))
    for m in re.finditer(r"number is (\d+(?:\.\d+)?) times (?:the )?sum of (?:its )?digits", tt):
        conds.append((f"10a + b = {m.group(1)}(a + b)", sp.Eq(num, q(m.group(1)) * s_)))
    for m in re.finditer(r"number is (\d+) (more|less|greater|smaller) than (\d+(?:\.\d+)?) times (?:the )?sum of (?:its )?digits", tt):
        sign = 1 if m.group(2) in ("more", "greater") else -1
        conds.append((f"10a + b = {m.group(3)}(a + b) {'+' if sign > 0 else '−'} {m.group(1)}", sp.Eq(num, q(m.group(3)) * s_ + sign * int(m.group(1)))))
    for m in re.finditer(r"number is (\d+) (more|less|greater|smaller) than (?:the )?sum of (?:its )?digits", tt):
        sign = 1 if m.group(2) in ("more", "greater") else -1
        conds.append((f"10a + b = a + b {'+' if sign > 0 else '−'} {m.group(1)}", sp.Eq(num, s_ + sign * int(m.group(1)))))
    if reversal:
        for m in re.finditer(r"sum of (?:the )?(?:original )?number and (?:its reverse|the (?:new|reversed|resulting) number|the number (?:formed|obtained|made)[^.,;]*?) (?:is|=|equals) (\d+)", tt):
            conds.append((f"(10a + b) + (10b + a) = {m.group(1)}", sp.Eq(num + rev, int(m.group(1)))))
        for m in re.finditer(r"difference (?:between|of) (?:the )?(?:original )?number and (?:its reverse|the (?:new|reversed|resulting) number|the number (?:formed|obtained|made)[^.,;]*?) (?:is|=|equals) (\d+)", tt):
            v = int(m.group(1))
            conds.append((f"|(10a + b) − (10b + a)| = {v}", lambda A, B, v=v: abs(9 * (A - B)) == v))
        for m in re.finditer(r"(?:new|resulting|reversed|obtained|resultant) number (?:is|exceeds|will be|becomes|would be)? ?(?:by )?(\d+) ?(more|greater|larger|bigger|less|smaller|fewer)? ?(?:than )?(?:the )?(?:original|old|given|first|initial|former)?", tt):
            if not m.group(2):
                ex_m = re.search(r"exceeds (?:the )?(?:original|old|given|first|initial)? ?(?:number )?by (\d+)", m.group(0))
                if not ex_m:
                    continue
                v, sign = int(ex_m.group(1)), 1
            else:
                v, sign = int(m.group(1)), (1 if m.group(2) in ("more", "greater", "larger", "bigger") else -1)
            conds.append((f"(10b + a) − (10a + b) = {sign * v}", sp.Eq(rev - num, sign * v)))
        for m in re.finditer(r"new number exceeds (?:the )?(?:original|old|given)? ?(?:number )?by (\d+)", tt):
            conds.append((f"(10b + a) − (10a + b) = {m.group(1)}", sp.Eq(rev - num, int(m.group(1)))))
        for m in re.finditer(r"original (?:number )?exceeds (?:the )?(?:new|reversed|resulting) (?:number )?by (\d+)", tt):
            conds.append((f"(10a + b) − (10b + a) = {m.group(1)}", sp.Eq(num - rev, int(m.group(1)))))
        for m in re.finditer(r"\b(?:number |it |value )?(?:is |gets |will be |would be )?(increased|increases|goes up|rises|grows|decreased|decreases|goes down|drops|falls|is reduced|reduces|shrinks|reduced)(?: the (?:original )?number| it| its value)? by (\d+)", tt):
            sign = 1 if m.group(1) in ("increased", "increases", "goes up", "rises", "grows") else -1
            conds.append((f"(10b + a) − (10a + b) = {sign * int(m.group(2))}", sp.Eq(rev - num, sign * int(m.group(2)))))
        for m in re.finditer(r"(?:original |given )?number is (\d+) (more|greater|larger|bigger|less|smaller) than (?:the )?(?:number (?:formed|obtained|made) by (?:reversing|interchanging|swapping)|its reverse|the reversed number|the new number|reversed|new)", tt):
            sign = 1 if m.group(2) in ("more", "greater", "larger", "bigger") else -1
            conds.append((f"(10a + b) − (10b + a) = {sign * int(m.group(1))}", sp.Eq(num - rev, sign * int(m.group(1)))))
    # de-duplicate by text, keep order
    seen, uniq = set(), []
    for c in conds:
        if c[0] not in seen:
            seen.add(c[0])
            uniq.append(c)
    conds = uniq
    if len(conds) < 2 and not (len(conds) == 1 and reversal):
        return None

    def holds(c, A, B):
        rel = c[1]
        if callable(rel):
            return rel(A, B)
        return bool(rel.subs({a: A, b: B}))
    sols = [(A, B) for A in range(1, 10) for B in range(10) if all(holds(c, A, B) for c in conds)]
    steps = ["rule: let the tens digit be a and the units digit b: the number is 10a + b, reversed it is 10b + a"]
    for txt, rel in conds:
        line = f"known: {txt}"
        if "(10b + a) − (10a + b)" in txt:
            v = int(txt.split("=")[-1])
            line += f" → 9(b − a) = {v}" + (f" → b − a = {ex(R(v, 9))}" if v % 9 == 0 else " (not a multiple of 9: impossible)")
        elif "(10a + b) − (10b + a)" in txt:
            v = int(txt.split("=")[-1])
            line += f" → 9(a − b) = {v}" + (f" → a − b = {ex(R(v, 9))}" if v % 9 == 0 else " (not a multiple of 9: impossible)")
        elif "(10a + b) + (10b + a)" in txt:
            v = int(txt.split("=")[-1])
            line += f" → 11(a + b) = {v}" + (f" → a + b = {ex(R(v, 11))}" if v % 11 == 0 else "")
        steps.append(line)
    if not sols:
        return _sol(text, "no two-digit number fits all of that", steps + ["result: no digits a = 1–9, b = 0–9 satisfy every condition"])
    if len(sols) > 8:
        return None
    nums = [10 * A + B for A, B in sols]
    steps.append("substitute: " + "; ".join(f"a = {A}, b = {B}" for A, B in sols) + " (digits a = 1–9, b = 0–9)")
    steps.append(f"result: {', '.join(map(str, nums))}")
    A, B = sols[0]
    chk = f"{10 * A + B} reversed is {10 * B + A}"
    if any("a + b =" in c[0] for c in conds):
        chk += f", digit sum {A + B}"
    if "(10b + a) − (10a + b)" in " ".join(c[0] for c in conds) or "(10a + b) − (10b + a)" in " ".join(c[0] for c in conds):
        chk += f", difference {abs(9 * (B - A))}"
    ans = " or ".join(map(str, nums)) if len(nums) > 1 else str(nums[0])
    return _sol(text, ans, steps, chk + " ✓")


# ---------------------------------------------------------------- coins and bills

COIN_TYPES = [
    (r"pennies|penny|1[- ]?(?:cent|c|¢) coins?", 1, "penny", "pennies"),
    (r"nickels?|nickles?|5[- ]?(?:cent|c|¢) coins?", 5, "nickel", "nickels"),
    (r"dimes?|10[- ]?(?:cent|c|¢) coins?", 10, "dime", "dimes"),
    (r"quarters?|25[- ]?(?:cent|c|¢) coins?", 25, "quarter", "quarters"),
    (r"half[- ]dollars?(?: coins?)?|50[- ]?(?:cent|c|¢) coins?", 50, "half-dollar", "half-dollars"),
    (r"dollar coins?|\$1 coins?|1[- ]dollar coins?|loonies|loonie", 100, "dollar coin", "dollar coins"),
]
_GENERIC_COIN = r"(\d+)[- ]?(?:cents?|c|¢|p|pence|paise)[- ]?(?:coins?|pieces?)|[$£€₹](\d+)[- ]?(?:coins?|notes?|bills?)|(\d+)[- ](?:dollars?|pounds?|euros?|rupees?)[- ]?(?:coins?|notes?|bills?)"
BILL_WORDS = {"ones": 100, "fives": 500, "tens": 1000, "twenties": 2000, "fifties": 5000, "hundreds": 10000}


def _coin_mentions(t: str):
    """[(start, end, cents, singular, plural)] for every coin or bill named, in order."""
    found = []
    for m in re.finditer(_GENERIC_COIN, t):
        if m.group(1):
            c = int(m.group(1))
            sym = "p" if re.search(r"\d[- ]?(?:p|pence)\b", m.group(0)) else "¢"
            nm = f"{c}{sym} coin"
        else:
            c = int(m.group(2) or m.group(3)) * 100
            kind = "bill" if re.search(r"bills?|notes?", m.group(0)) else "coin"
            nm = f"${c // 100} {kind}"
        found.append((m.start(), m.end(), c, nm, nm + "s"))
    for pat, c, s1, s2 in COIN_TYPES:
        for m in re.finditer(rf"\b(?:{pat})(?!\w)", t):
            if not any(s <= m.start() < e for s, e, *_ in found):
                found.append((m.start(), m.end(), c, s1, s2))
    if re.search(r"\b(?:bills|notes)\b", t):
        for w, c in BILL_WORDS.items():
            for m in re.finditer(rf"\b{w}\b", t):
                if not any(s <= m.start() < e for s, e, *_ in found):
                    found.append((m.start(), m.end(), c, f"${c // 100} bill", f"${c // 100} bills"))
    return sorted(found)


def _money_cents(t: str, exclude: list[tuple[int, int]]):
    out = []
    pats = [(r"[$£€₹]\s?(\d+(?:\.\d{1,2})?)(?!\d|\.\d|[- ]?(?:coins?|bills?|notes?))", 100),
            (r"\b(\d+(?:\.\d+)?)\s*(?:dollars?|bucks|pounds?|euros?|rupees?)\b(?![- ]?(?:coins?|bills?|notes?))", 100),
            (r"\b(\d+)\s*(?:cents?|¢|c|p|pence)(?![\w-]| coins?| pieces?)", 1)]
    for pat, f in pats:
        for m in re.finditer(pat, t):
            if any(s <= m.start() < e for s, e in exclude) or any(s <= m.start() < e for s, e, _ in out):
                continue
            out.append((m.start(), m.end(), q(m.group(1)) * f))
    return out


def _relations(t: str, alt: str, key, syms: dict):
    """'2 times as many dimes as nickels', '3 more quarters than dimes', 'same number of X and Y'."""
    eqs = []
    A = rf"({alt})"
    for m in re.finditer(rf"(\d+(?:\.\d+)?|half) times as many {A}(?: \w+)? as (?:there are )?(?:the )?{A}", t):
        k = R(1, 2) if m.group(1) == "half" else q(m.group(1))
        x, y = key(m.group(2)), key(m.group(3))
        if x in syms and y in syms and x != y:
            eqs.append((sp.Eq(syms[x], k * syms[y]), f"{ex(k)} times as many {x} as {y}"))
    for m in re.finditer(rf"(\d+) (more|fewer|less) {A}(?: \w+)? than (?:the )?{A}", t):
        x, y = key(m.group(3)), key(m.group(4))
        n = int(m.group(1)) * (1 if m.group(2) == "more" else -1)
        if x in syms and y in syms and x != y:
            eqs.append((sp.Eq(syms[x], syms[y] + n), f"{m.group(1)} {m.group(2)} {x} than {y}"))
    for m in re.finditer(rf"number of {A} is (\d+(?:\.\d+)?) times (?:the number of )?(?:the )?{A}", t):
        x, y = key(m.group(1)), key(m.group(3))
        if x in syms and y in syms and x != y:
            eqs.append((sp.Eq(syms[x], q(m.group(2)) * syms[y]), f"{m.group(2)} times as many {x} as {y}"))
    for m in re.finditer(rf"number of {A} is (\d+) (more|less|fewer|greater) than (?:the number of )?(?:the )?{A}", t):
        x, y = key(m.group(1)), key(m.group(4))
        n = int(m.group(2)) * (1 if m.group(3) in ("more", "greater") else -1)
        if x in syms and y in syms and x != y:
            eqs.append((sp.Eq(syms[x], syms[y] + n), f"{m.group(2)} {m.group(3)} {x} than {y}"))
    for m in re.finditer(rf"(?:same number of|(?<!times )as many) {A}(?: \w+)? (?:as|and) (?:the )?{A}", t):
        x, y = key(m.group(1)), key(m.group(2))
        if x in syms and y in syms and x != y:
            eqs.append((sp.Eq(syms[x], syms[y]), f"as many {x} as {y}"))
    return eqs


def coins(t: str, text: str) -> Solution | None:
    if not re.search(r"\bcoins?\b|nickels?|nickles?|\bdimes?\b|pennies|penny|\bbills\b|\bnotes\b|half[- ]dollars?", t):
        return None
    ment = _coin_mentions(t)
    kinds = []
    for s, e, c, s1, s2 in ment:
        if c not in [k[0] for k in kinds]:
            kinds.append((c, s1, s2))
    if len(kinds) < 2 or len(kinds) > 5:
        return None
    if not re.search(r"\bcoins?\b|nickels?|\bdimes?\b|pennies|\bbills\b|\bnotes\b", t):
        return None
    name_of = {c: s2 for c, s1, s2 in kinds}
    alias = {}
    for s, e, c, s1, s2 in ment:
        alias[t[s:e]] = name_of[c]
    alt = "|".join(re.escape(a) for a in sorted(alias, key=len, reverse=True))
    syms = {name_of[c]: sp.Symbol(name_of[c].replace(" ", "_").replace("$", "d").replace("¢", "c").replace("-", "_")) for c, _, _ in kinds}
    cents = {name_of[c]: c for c, _, _ in kinds}
    spans = [(s, e) for s, e, *_ in ment]
    explicit = {}
    combined = []
    for s, e, c, s1, s2 in ment:
        nm = name_of[c]
        before = re.search(r"(\d+) (?:\w+ )?$", t[max(0, s - 12):s])
        after = re.match(rf",? (?:and|or|&) (?:{alt})\b", t[e:])
        if before and not re.search(r"(?:times|more|fewer|less|than) $", t[max(0, s - 12):s]):
            n = int(before.group(1))
            if after and not re.match(r",? (?:and|or|&) \d", t[e:]):
                combined.append(n)
            elif nm not in explicit:
                explicit[nm] = n
    total_n = None
    m = re.search(r"\b(\d+) (?:coins|pieces|bills|notes)\b|\b(?:total|altogether|in all) (?:of )?(\d+)(?! cents| dollars)\b|\b(\d+) (?:of them|in total|in all|altogether)\b", t)
    if m:
        total_n = int(next(g for g in m.groups() if g))
        if any(s <= m.start() < e for s, e in spans):
            total_n = None
    if total_n is None and combined:
        total_n = combined[0]
        explicit = {k: v for k, v in explicit.items() if v != total_n}
    values = _money_cents(t, spans)
    value = values[-1][2] if values else None
    unknown = [nm for nm in syms if nm not in explicit]
    cur = "£" if "£" in t or re.search(r"\bpence\b|\d+p\b", t) else "€" if "€" in t else "₹" if "₹" in t else "$"

    def money(v):
        return f"{cur}{float(v) / 100:,.2f}"
    if not unknown and re.search(r"how much|total value|worth|value|how many (?:cents|dollars)|in total|altogether", t):
        tot = sum(cents[nm] * n for nm, n in explicit.items())
        parts = [f"{n} × {cents[nm]}¢" for nm, n in explicit.items()]
        return _sol(text, money(tot), ["rule: value = Σ count × coin value",
                                       "known: " + ", ".join(f"{n} {nm}" for nm, n in explicit.items()),
                                       "substitute: " + " + ".join(parts), f"result: {ex(tot)}¢ = {money(tot)}"])
    eqs, lines = [], []
    for nm, n in explicit.items():
        eqs.append(sp.Eq(syms[nm], n))
    if total_n is not None:
        eqs.append(sp.Eq(sum(syms.values()), total_n))
        lines.append(f"count: {' + '.join(str(s) for s in syms.values())} = {total_n}")
    if value is not None:
        eqs.append(sp.Eq(sum(cents[nm] * s for nm, s in syms.items()), value))
        lines.append(f"value in cents: {' + '.join(f'{cents[nm]}·{s}' for nm, s in syms.items())} = {ex(value)}")
    for eq, desc in _relations(t, alt, lambda w: alias.get(w, w), syms):
        eqs.append(eq)
        lines.append(f"{desc}: {efmt(eq.lhs)} = {efmt(eq.rhs)}")
    if value is None or len(eqs) < len(syms):
        return None
    sol = _unique(eqs, list(syms.values()))
    if not sol:
        return None
    vals = {nm: sol[s] for nm, s in syms.items()}
    if any(not v.is_Integer or v < 0 for v in vals.values()):
        return _sol(text, "no whole-number answer: the counts and total don't fit together",
                    ["rule: one unknown per kind of coin, one equation per fact", *[f"known: {x}" for x in lines],
                     "result: " + ", ".join(f"{nm} = {nice(v)}" for nm, v in vals.items())])
    ans = " and ".join(f"{ex(v)} {nm if v != 1 else next(s1 for c, s1, s2 in kinds if s2 == nm)}" for nm, v in vals.items())
    asked = re.search(rf"how many ({alt})", t)
    if asked and len(vals) > 1:
        first = alias.get(asked.group(1))
        if first in vals:
            ans = f"{ex(vals[first])} {first}" + " (and " + ", ".join(f"{ex(v)} {nm}" for nm, v in vals.items() if nm != first) + ")"
    steps = ["rule: one unknown per kind of coin; the count and the value each give an equation",
             *[f"known: {x}" for x in lines],
             "substitute: solve together → " + ", ".join(f"{s} = {ex(sol[s])}" for s in syms.values()),
             "result: " + " and ".join(f"{ex(v)} {nm}" for nm, v in vals.items())]
    chk = []
    if total_n is not None:
        chk.append(" + ".join(ex(v) for v in vals.values()) + f" = {total_n} coins ✓")
    chk.append(" + ".join(f"{ex(v)}×{cents[nm]}¢" for nm, v in vals.items()) + f" = {money(value)} ✓")
    return _sol(text, ans, steps, "; ".join(chk))


# ---------------------------------------------------------------- adult / child tickets

TICKET_CATS = (r"adults?|child(?:ren)?|kids?|students?|seniors?|members?|non-?members?|general(?: admission)?|vip|regular|"
               r"premium|reserved|balcony|orchestra|floor|lawn|youths?|teens?|teenagers?|infants?|early[- ]bird|advance|"
               r"door|standard|economy|grown-?ups?|boys?|girls?|men|women|veterans?|faculty|staff")


def _cat(w: str) -> str:
    w = w.replace("-", " ")
    table = {"children": "child", "kids": "child", "kid": "child", "adults": "adult", "grown ups": "adult", "grown up": "adult",
             "grownups": "adult", "grownup": "adult", "students": "student", "seniors": "senior", "members": "member",
             "non members": "non-member", "non member": "non-member", "nonmembers": "non-member", "nonmember": "non-member",
             "general admission": "general", "youths": "youth", "teens": "teen", "teenagers": "teen", "teenager": "teen",
             "infants": "infant", "early bird": "early-bird", "boys": "boy", "girls": "girl", "men": "man", "women": "woman",
             "veterans": "veteran"}
    return table.get(w, w)


def tickets(t: str, text: str) -> Solution | None:
    t = re.sub(r"\b(?:tix|tkts?)\b", "tickets", t)
    if not re.search(r"\btickets?\b|\badmissions?\b|\bentry fees?\b|\bentrance fees?\b", t):
        return None
    C = rf"({TICKET_CATS})"
    prices = {}
    pats = [rf"\b{C}(?:'s)?(?: tickets?| admissions?| fares?| seats?| passes?)?(?: (?:cost|costs|are|were|is|was|sell for|sold for|sell at|sold at|at|priced at|go for|went for|for|pay|paid|cost them|each cost|are priced at))?(?: just| only)?\s*(?:of\s*)?[$£€₹]\s?(\d+(?:\.\d+)?)",
            rf"[$£€₹]\s?(\d+(?:\.\d+)?)(?: each)? (?:per|for an?|for each|for|a|an|to) {C}\b",
            rf"\b{C}(?:'s)?(?: tickets?)? (?:cost|costs|are|were|sell for|sold for|priced at|at) (\d+(?:\.\d+)?)(?: dollars| each| apiece)"]
    for i, pat in enumerate(pats):
        for m in re.finditer(pat, t):
            cat, price = (m.group(2), m.group(1)) if i == 1 else (m.group(1), m.group(2))
            cat = _cat(cat)
            if cat not in prices:
                prices[cat] = (q(price), m.span())
    if len(prices) != 2:
        return None
    cats = list(prices)
    syms = {c: sp.Symbol(c.replace("-", "_")) for c in cats}
    price_spans = [v[1] for v in prices.values()]
    total = re.search(r"\b(\d+) (?:tickets|people|persons|visitors|guests|customers|attendees|spectators|fans|patrons|seats|admissions|students|children and adults|adults and children)\b(?! (?:cost|at))", t) \
        or re.search(r"\btotal of (\d+)(?! dollars)\b(?=[^$]*tickets)|\battendance (?:was|of) (\d+)\b|\bsold (\d+)\b(?! dollars)|\btickets (?:were|was|sold|totall?ed|numbered|came to)(?: were| was)? (\d+)\b(?! dollars)(?= total| in total| altogether| tickets|[,.;]|$)|\b(\d+) total tickets\b", t)
    total_n = None
    if total:
        total_n = int(next(g for g in total.groups() if g))
        if any(s <= total.start() < e for s, e in price_spans):
            total_n = None
    revenue = None
    for m in re.finditer(r"[$£€₹]\s?(\d+(?:\.\d+)?)|\b(\d+(?:\.\d+)?) dollars\b", t):
        if any(s <= m.start() < e for s, e in price_spans):
            continue
        v = q(m.group(1) or m.group(2))
        if v not in [p for p, _ in prices.values()] or revenue is None:
            revenue = v
    if revenue is None:
        m = re.search(r"\b(?:total|collected|revenue|took in|takings|raised|receipts|sales|brought in|earned|made|came to|totaling|totalling|income) (?:of |was |were |is |are |amounted to )?(\d+(?:\.\d+)?)\b", t)
        revenue = q(m.group(1)) if m else None
    alt = TICKET_CATS
    rels = _relations(re.sub(r"\b(" + TICKET_CATS + r") tickets\b", r"\1", t), alt, _cat, syms)
    eqs, lines = [], []
    if total_n is not None:
        eqs.append(sp.Eq(sum(syms.values()), total_n))
        lines.append(f"tickets: {' + '.join(map(str, syms.values()))} = {total_n}")
    if revenue is not None:
        eqs.append(sp.Eq(sum(prices[c][0] * syms[c] for c in cats), revenue))
        lines.append(f"takings: {' + '.join(f'{ex(prices[c][0])}·{syms[c]}' for c in cats)} = {ex(revenue)}")
    for eq, desc in rels:
        eqs.append(eq)
        lines.append(f"{desc}: {efmt(eq.lhs)} = {efmt(eq.rhs)}")
    if len(eqs) < 2 or revenue is None and total_n is None:
        return None
    sol = _unique(eqs[:3], list(syms.values()))
    if not sol:
        return None
    vals = {c: sol[syms[c]] for c in cats}
    steps = ["rule: one unknown per kind of ticket; the number sold and the money taken each give an equation",
             "known: " + ", ".join(f"{c} {cash(prices[c][0])}" for c in cats), *[f"known: {x}" for x in lines]]
    if any(not v.is_Integer or v < 0 for v in vals.values()):
        return _sol(text, "no whole-number answer: those totals can't come from those prices",
                    steps + ["result: " + ", ".join(f"{c} = {nice(v)}" for c, v in vals.items())])
    a, b = cats
    if total_n is not None and revenue is not None:
        steps.append(f"substitute: {a} = {total_n} − {b} → {ex(prices[a][0])}({total_n} − {b}) + {ex(prices[b][0])}·{b} = {ex(revenue)}"
                     f" → {ex(prices[b][0] - prices[a][0])}·{b} = {ex(revenue - prices[a][0] * total_n)}")
    order = cats
    asked = re.search(rf"how many ({TICKET_CATS})", t)
    if asked and _cat(asked.group(1)) in vals:
        first = _cat(asked.group(1))
        order = [first] + [c for c in cats if c != first]
    ans = " and ".join(f"{ex(vals[c])} {c}" for c in order) + " tickets"
    steps.append(f"result: {ans}")
    chk = []
    if total_n is not None:
        chk.append(f"{ex(vals[a])} + {ex(vals[b])} = {total_n} ✓")
    chk.append(f"{ex(vals[a])} × {cash(prices[a][0])} + {ex(vals[b])} × {cash(prices[b][0])} = "
               f"{cash(sum(prices[c][0] * vals[c] for c in cats))}" + (" ✓" if revenue is not None else ""))
    return _sol(text, ans, steps, "; ".join(chk))


# ---------------------------------------------------------------- mixtures

VOLU = (r"litres?|liters?|l|ml|millilit(?:re|er)s?|gallons?|gal|quarts?|qts?|pints?|fl ?oz|ounces?|oz|cups?|kgs?|kilograms?|"
        r"kilos?|g|grams?|pounds?|lbs?|tons?|tonnes?|cc|cl|units?|parts?|cans?|jugs?|bottles?|buckets?|barrels?|drums?|m3|"
        r"cubic (?:feet|meters?|metres?|centimet(?:er|re)s?)")
AMT = rf"(\d+(?:\.\d+)?)\s*-?\s*({VOLU})\b"
PCT = r"(\d+(?:\.\d+)?)\s*(?:%|percent\b|per cent\b)"
TARGET_CUE = (r"\b(?:make|makes|making|get|getting|produce|obtain|create|form|yield|end up with|to have|give|giving|bring|"
              r"brings|reduce|reduces|raise|raises|increase|lower|dilute|strengthen|weaken|achieve|reach|result|resulting|"
              r"becomes?|so (?:that )?(?:it|the \w+) (?:is|becomes|will be|has)|until (?:it|the \w+) (?:is|becomes)|need|needs|"
              r"want|wants|require|requires|desired|target|final|turn it into|into)\b")


def _unit_name(u: str) -> str:
    u = u.lower().strip()
    if re.fullmatch(r"litres?|liters?|l", u):
        return "L"
    if re.fullmatch(r"ml|millilit(?:re|er)s?|cc", u):
        return "mL"
    if re.fullmatch(r"pounds?|lbs?", u):
        return "lb"
    if re.fullmatch(r"ounces?|oz", u):
        return "oz"
    if re.fullmatch(r"kgs?|kilograms?|kilos?", u):
        return "kg"
    if re.fullmatch(r"g|grams?", u):
        return "g"
    if re.fullmatch(r"gal|gallons?", u):
        return "gallons"
    return u if u.endswith("s") else u + "s"


def mixture(t: str, text: str) -> Solution | None:
    price_mode = False
    PR = r"[$£€₹]\s?(\d+(?:\.\d+)?)\s*(?:per|a|an|/|each|for (?:a|one|each))\s*(pound|lb|kg|kilo(?:gram)?|ounce|oz|liter|litre|gallon|gram|g|bag|cup)\b"
    pcts = list(re.finditer(PCT, t))
    if len(pcts) < 1 or not re.search(r"solution|mixture|mix|mixed|mixing|blend|dilut|concentrat|alcohol|acid|antifreeze|saline|"
                                      r"brine|bleach|juice|salt|sugar|water|evaporat|alloy|milk|fat|vinegar|chemical|chemist|drink|syrup|"
                                      r"peroxide|ethanol|glycol|fertili[sz]er|pesticide|paint|gold|silver|copper|nickel|cream|sauce|"
                                      r"coffee|tea|nuts|candy|seed|feed|disinfectant|cleaner|solvent|mash|wine|spirit|vodka|rum", t):
        prs = list(re.finditer(PR, t))
        if len(prs) >= 2 and re.search(r"\bmix|\bblend|\bcombin", t):
            pcts, price_mode = prs, True
        else:
            return None
    if not re.search(r"how (?:much|many)|what (?:amount|volume|quantity|weight|mass|is the (?:concentration|percent|percentage|strength))|"
                     r"what (?:percent|percentage|concentration|strength)|find|calculate|determine|work out|\?", t):
        return None
    cur = next((c for c in "$£€₹" if c in t), "$")
    water_add = re.search(r"how (?:much|many \w+(?: of)?) (?:pure |distilled |plain |fresh |tap )?water|(?:add|adding|added|pour|pouring|mix(?:ed)? in|dilute\w* (?:it )?with|put in|top(?:ped)? up with)\s+(?:(\d+(?:\.\d+)?)\s*-?\s*(" + VOLU + r")\b (?:of )?)?(?:some |more |pure |distilled |plain |fresh |tap )*water|water (?:must|should|needs to|has to|will|would|is to|to) be (?:added|mixed)", t)
    evap = re.search(r"evaporat|boil(?:ed|ing)? (?:off|away)|remov\w* (?:some |of )?(?:the )?water|water (?:must|should|needs to|has to|will|would) be (?:removed|evaporated|boiled)|dehydrat", t)
    pure = re.search(r"\b(?:how (?:much|many \w+(?: of)?) |add (?:some )?|adding )?pure (?!water)([a-z]+)", t)
    replace = re.search(r"drain\w* (?:off )?(?:and|then) (?:replac|refill)|replac\w* (?:it |them |some )?with|remov\w* and replac", t)
    substance = None
    sm = re.search(r"%\s*(?:of\s+)?([a-z]+)(?: solution| mixture| by volume| by mass)?", t) or re.search(r"\b([a-z]+) solution\b", t)
    if sm and sm.group(1) not in ("solution", "mixture", "a", "an", "the", "and", "of", "to", "is", "with", "concentration", "pure", "water"):
        substance = sm.group(1)
    substance = substance or (pure.group(1) if pure else "solute")
    pieces = []
    prev = 0
    for p in pcts:
        before = t[prev:p.start()]
        am = list(re.finditer(AMT, before))
        amt = None
        unit = None
        if am:
            last = am[-1]
            gap = before[last.end():]
            if len(gap.split()) <= 7 and not re.search(r"\b(?:with|and|to|into|added|add|mix|mixed)\b", gap):
                amt, unit = q(last.group(1)), _unit_name(last.group(2))
        cue = re.search(TARGET_CUE, before)
        pieces.append({"c": q(p.group(1)) / (1 if price_mode else 100), "amt": amt, "unit": unit, "cue": bool(cue),
                       "raw": p.group(1), "pos": p.start()})
        prev = p.end()
    qpos = re.search(r"how (?:much|many)|what (?:amount|volume|quantity)", t)
    if qpos:  # "how many liters of the 70% ..." re-mentions a component already given
        pieces = [p for i, p in enumerate(pieces)
                  if not (p["pos"] > qpos.start() and p["amt"] is None and any(o["c"] == p["c"] for o in pieces[:i]))]
    units = [p["unit"] for p in pieces if p["unit"]]
    am_all = list(re.finditer(AMT, t))
    unit = units[0] if units else (_unit_name(am_all[0].group(2)) if am_all else None)
    if not unit:
        um = re.search(rf"how (?:much|many) ({VOLU})\b", t)
        unit = _unit_name(um.group(1)) if um else "units"
    target = None
    cued = [p for p in pieces if p["cue"]]
    ask_conc = re.search(r"what (?:is the )?(?:percent|percentage|concentration|strength)|(?:concentration|percentage|strength|percent) of (?:the |this |that )?(?:new |resulting |final )?(?:mixture|solution|mix|blend|result)|what % |how strong|new concentration|resulting concentration|final concentration|price per|cost per|worth per|what (?:should|will|would|must) (?:the )?(?:mixture|blend|mix) (?:sell|cost)", t)
    if cued:
        target = cued[-1]
    elif not ask_conc and len(pieces) >= 2:
        target = pieces[-1]
    comps = [p for p in pieces if p is not target]
    fmt_c = (lambda c: cash(c, cur) + f"/{unit if unit not in ('units',) else 'unit'}") if price_mode else (lambda c: f"{ex(c * 100)}%")
    extra = None
    if not price_mode and water_add and not evap:
        wa = water_add.group(1)
        extra = {"c": R(0), "amt": q(wa) if wa else None, "name": "water", "sign": 1}
    elif not price_mode and evap:
        extra = {"c": R(0), "amt": None, "name": "water removed", "sign": -1}
    elif not price_mode and pure and not replace:
        extra = {"c": R(1), "amt": None, "name": f"pure {pure.group(1)}", "sign": 1}
    if replace and not price_mode and target and len(comps) == 1 and comps[0]["amt"] is not None:
        V, c1, c2 = comps[0]["amt"], comps[0]["c"], target["c"]
        cr = R(0) if re.search(r"with (?:pure |plain |fresh )?water", t) else R(1)
        if cr == c1:
            return None
        x = V * (c2 - c1) / (cr - c1)
        if x < 0 or x > V:
            return _sol(text, "not possible by draining and replacing", [f"known: {ex(V)} {unit} at {fmt_c(c1)}, target {fmt_c(c2)}"])
        nm = "water" if cr == 0 else f"pure {substance}"
        return _sol(text, f"{nice(x)} {unit}", [
            f"rule: draining x {unit} removes x × {fmt_c(c1)} of the {substance}; refilling with {nm} adds x × {fmt_c(cr)}",
            f"known: {ex(V)} {unit} at {fmt_c(c1)}, target {fmt_c(c2)}",
            f"substitute: {ex(V)}·{ex(c1)} − {ex(c1)}·x + {ex(cr)}·x = {ex(V)}·{ex(c2)} → x = {ex(V)}·({ex(c2)} − {ex(c1)}) / ({ex(cr)} − {ex(c1)})",
            f"result: drain and replace {nice(x)} {unit}"],
            f"{ex(V)}·{ex(c1)} + {nice(x)}·({ex(cr)} − {ex(c1)}) = {nice(V * c2)} {unit} of {substance} in {ex(V)} {unit} = {fmt_c(c2)} ✓")
    if target is None:
        if not ask_conc:
            return None
        parts = [p for p in comps if p["amt"] is not None]
        if extra and extra["amt"] is not None:
            parts.append({"c": extra["c"], "amt": extra["amt"] * extra["sign"], "name": extra["name"]})
        if len(parts) < 2 or any(p["amt"] is None for p in comps):
            return None
        tot = sum(p["amt"] for p in parts)
        solute = sum(p["amt"] * p["c"] for p in parts)
        if tot <= 0:
            return None
        c = solute / tot
        shown = cash(c, cur) + f" per {unit.rstrip('s')}" if price_mode else f"{nice(c * 100)}%"
        return _sol(text, shown, [
            "formula: concentration = total " + ("value" if price_mode else substance) + " ÷ total amount",
            "known: " + ", ".join(f"{ex(p['amt'])} {unit} at {fmt_c(p['c'])}" for p in parts),
            "substitute: (" + " + ".join(f"{ex(p['amt'])} × {ex(p['c'])}" for p in parts) + f") ÷ {ex(tot)} = {nice(solute)} ÷ {ex(tot)}",
            f"result: {shown}"],
            f"{nice(tot)} {unit} × {ex(c) if price_mode else nice(c)} = {nice(solute)} ✓")
    T = target["amt"]
    Ts = sp.Symbol("T")
    syms = []
    terms = []  # (sign, amount expr, conc, label)
    for i, p in enumerate(comps):
        if p["amt"] is None:
            s_ = sp.Symbol("x" if not syms else "y")
            syms.append(s_)
            terms.append((1, s_, p["c"], fmt_c(p["c"])))
        else:
            terms.append((1, p["amt"], p["c"], fmt_c(p["c"])))
    if extra:
        if extra["amt"] is None:
            s_ = sp.Symbol("x" if not syms else "y")
            syms.append(s_)
            terms.append((extra["sign"], s_, extra["c"], extra["name"]))
        else:
            terms.append((extra["sign"], extra["amt"], extra["c"], extra["name"]))
    if not terms or not syms:
        return None
    tot_expr = Ts if T is None else T
    unknowns = syms + ([Ts] if T is None else [])
    if len(unknowns) > 2:
        return None
    eq_amt = sp.Eq(sum(sg * a for sg, a, c, _ in terms), tot_expr)
    eq_sol = sp.Eq(sum(sg * a * c for sg, a, c, _ in terms), tot_expr * target["c"])
    sol = _unique([eq_amt, eq_sol], unknowns)
    if not sol:
        return None
    if any(sol[s] < 0 for s in unknowns):
        return _sol(text, "not possible: the target can't be reached by adding that", [
            f"known: target {fmt_c(target['c'])}", "result: the amount would have to be negative"])
    labelled = []
    for sg, a, c, lab in terms:
        if isinstance(a, sp.Symbol):
            labelled.append((a, lab, sol[a]))
    if len(labelled) == 1:
        a, lab, v = labelled[0]
        if lab in ("water", "water removed") or lab.startswith("pure "):
            ans = f"{nice(v)} {unit} of {lab.replace(' removed', '')}" + (" evaporated" if lab == "water removed" else "")
        else:
            ans = f"{nice(v)} {unit} of the {lab}" + (" " + ("solution" if not price_mode else "kind") if not price_mode else "")
    else:
        ans = " and ".join(f"{nice(v)} {unit} of the {lab}" for a, lab, v in labelled)
    ans = ans.replace("of the $", "at $").replace(" kind", "")
    total_v = sol.get(Ts, T)
    known = [f"{ex(a)} {unit} at {lab}" if not isinstance(a, sp.Symbol) else f"{a} {unit} of {lab}" + ("" if lab.endswith("%") or lab.startswith(cur) else f" ({fmt_c(c)})")
             for sg, a, c, lab in terms]
    known.append(f"target {fmt_c(target['c'])}" + (f", {ex(T)} {unit} in all" if T is not None else ""))
    show_amt = " ".join(("+ " if sg > 0 else "− ") + (ex(a) if not isinstance(a, sp.Symbol) else str(a)) for sg, a, c, _ in terms).lstrip("+ ")
    show_sol = " ".join(("+ " if sg > 0 else "− ") + f"{ex(c)}·" + (ex(a) if not isinstance(a, sp.Symbol) else str(a)) for sg, a, c, _ in terms).lstrip("+ ")
    what = "value" if price_mode else substance
    steps = [f"rule: the amount of {what} is conserved: Σ amount × " + ("price" if price_mode else "concentration") + " before = after",
             "known: " + "; ".join(known),
             f"substitute: amounts {show_amt} = {ex(tot_expr) if T is not None else 'T'}; {what} {show_sol} = {ex(target['c'])}·{ex(tot_expr) if T is not None else 'T'}",
             "result: " + ", ".join(f"{s} = {nice(sol[s])}" for s in unknowns) + f" → {ans}"]
    tot_amt = sum(sg * (sol[a] if isinstance(a, sp.Symbol) else a) for sg, a, c, _ in terms)
    tot_sol = sum(sg * (sol[a] if isinstance(a, sp.Symbol) else a) * c for sg, a, c, _ in terms)
    chk = (f"{nice(tot_sol)} {unit} of {substance} in {nice(tot_amt)} {unit} = {nice(tot_sol / tot_amt * 100)}% ✓" if not price_mode
           else f"total value {cash(tot_sol, cur)} for {nice(tot_amt)} {unit} = {cash(tot_sol / tot_amt, cur)} each ✓")
    del total_v
    return _sol(text, ans, steps, chk)


# ---------------------------------------------------------------- weighted averages

CATW = (r"home ?works?|hw|quiz(?:zes)?|tests?|exams?|mid-?terms?(?: exams?)?|final(?: exams?)?|finals|labs?(?: reports?| work)?|"
        r"projects?|participation|attendance|assignments?|essays?|papers?|presentations?|class ?work|course ?work|"
        r"portfolios?|reports?|practicals?|discussions?|problem sets?|psets?|readings?|orals?|tutorials?|seminars?|"
        r"labwork|test_\d|exam_\d|quiz_\d|assignment_\d|project_\d|paper_\d|essay_\d|lab_\d|unit_\d")


def _catw(w: str) -> str:
    w = w.replace("-", "").replace(" ", "")
    for pre, out in (("homework", "homework"), ("hw", "homework"), ("quiz_", None), ("quiz", "quizzes"), ("midterm", "midterm"),
                     ("finals", "final"), ("final", "final"), ("lab_", None), ("lab", "labs"), ("test_", None),
                     ("test", "tests"), ("exam_", None), ("exam", "exams"), ("project_", None), ("project", "projects"),
                     ("assignment_", None), ("assignment", "assignments"), ("essay_", None), ("essay", "essays"),
                     ("paper_", None), ("paper", "papers"), ("participation", "participation"), ("attendance", "attendance"),
                     ("presentation", "presentations"), ("classwork", "classwork"), ("coursework", "coursework")):
        if w.startswith(pre):
            return out or w.replace("_", " ")
    return w.rstrip("s") if not w.endswith("ss") else w


def weighted(t: str, text: str) -> Solution | None:
    if re.search(r"\baverag|\bmean\b", t):
        sol = _group_average(t, text)
        if sol:
            return sol
    if not re.search(r"%|percent|weight|worth|counts?\b", t):
        return None
    tt = re.sub(r"\b(first|second|third|fourth|1st|2nd|3rd|4th) (test|exam|quiz|assignment|project|paper|essay|lab)\b",
                lambda m: f"{m.group(2)}_{ {'first': 1, 'second': 2, 'third': 3, 'fourth': 4, '1st': 1, '2nd': 2, '3rd': 3, '4th': 4}[m.group(1)]}", t)
    tt = re.sub(r"\b(test|exam|quiz|assignment|project|paper|essay|lab|unit) ?#?([1-9])\b(?!\s*(?:%|\.\d|\d|percent))", r"\1_\2", tt)
    tt = re.sub(r"\(\s*(\d+(?:\.\d+)?)\s*%\s*\)", r" weight \1% ", tt)
    target = None
    tm = re.search(r"\b(?:get|end up with|finish with|achieve|have|earn|reach|pull|keep|hit|be|for|with|at least|of|an|a)\s+(?:an?\s+|at least\s+)?(\d+(?:\.\d+)?)\s*%?\s*"
                   r"(?:overall|in the (?:class|course|module|subject)|(?:as )?(?:my |a |the |an )?(?:final|overall|course|class|total|semester|term) (?:grade|mark|average|score|percentage)|average|for the (?:class|course|semester|term|year)|or (?:higher|better|above|more))", tt) \
        or re.search(r"\b(?:overall|final|course|class|total|semester) (?:grade|mark|average|score) (?:of|is|to be|=) (?:at least )?(\d+(?:\.\d+)?)", tt)
    if tm and re.search(r"\bneed|\bmust|have to|has to|\brequired?\b|minimum|at least|what (?:score|grade|mark)|how (?:much|well|high)", tt):
        target = (q(tm.group(1)), tm.span(1))
    cats = [(m.start(), m.end(), _catw(m.group(0))) for m in re.finditer(rf"\b(?:{CATW})\b", tt)]
    if len(cats) < 2:
        return None
    order = []
    for s, e, c in cats:
        if c not in order:
            order.append(c)
    if len(order) < 2 or len(order) > 8:
        return None
    nums = []
    for m in re.finditer(r"(?<![\w.])(\d+(?:\.\d+)?)(?:\s*(%|percent|points|pts|marks|/\s?100))?", tt):
        if target and m.start(1) == target[1][0]:
            continue
        if any(s <= m.start() < e for s, e, _ in cats):
            continue
        pct = m.group(2) in ("%", "percent")
        nums.append({"v": q(m.group(1)), "pct": pct, "s": m.start(), "e": m.end()})
    if not nums:
        return None
    info = {c: {"w": None, "s": None, "amb": []} for c in order}
    # "homework, quizzes and the final are worth 20%, 30% and 50%" / "… scored 90, 80 and 70 respectively"
    resp_done = set()
    for lm in re.finditer(r"(?:\d+(?:\.\d+)?\s*%?(?:,\s*|,?\s+and\s+)){1,7}\d+(?:\.\d+)?\s*%?", tt):
        vals = [x for x in nums if lm.start() <= x["s"] < lm.end()]
        if len(vals) == len(order) and len(vals) >= 2:
            seg = tt[max(0, lm.start() - 60):lm.start()]
            is_w = all(v["pct"] for v in vals) and (re.search(r"worth|count|weigh|make up|account|of (?:the|my|your) grade", seg + tt[lm.end():lm.end() + 30]) or True)
            if sum(v["v"] for v in vals) == 100 and is_w:
                for c, v in zip(order, vals):
                    info[c]["w"] = v["v"]
            else:
                for c, v in zip(order, vals):
                    info[c]["s"] = v["v"]
            resp_done.update(id(v) for v in vals)
    clauses = re.split(r"[.;\n]|,(?!\s*\d)|\band\b(?!\s*\d)|\bwhile\b|\bbut\b|\bwhereas\b", tt)
    pos = 0
    spans = []
    for cl in clauses:
        i = tt.find(cl, pos)
        spans.append((i, i + len(cl)))
        pos = i + len(cl)
    last_cat = None
    for cs, ce in spans:
        here = [c for s, e, c in cats if cs <= s < ce]
        mine = [x for x in nums if cs <= x["s"] < ce and id(x) not in resp_done]
        if len(here) > 1:
            # "85 on homework, 72 on the midterm" in one clause: give each number to the category right after "on/in"
            for x in mine:
                after = re.match(rf"\s*(?:%|percent|points)?\s*(?:(?:on|in|for|from)\s+)?(?:the |my |our |a |an )?({CATW})\b", tt[x["e"]:])
                prior = [c for s, e, c in cats if s < x["s"] and s >= cs]
                c = _catw(after.group(1)) if after else (prior[-1] if prior else None)
                if c:
                    info[c]["amb"].append((x, tt[cs:x["s"]], tt[x["e"]:ce]))
            last_cat = here[-1]
            continue
        c = here[0] if here else last_cat
        if c is None:
            continue
        for x in mine:
            direct = re.match(rf"\s*(?:%|percent|points)?\s*(?:(?:on|in|for|from)\s+)?(?:the |my |our |a |an )?({CATW})\b", tt[x["e"]:])
            info[_catw(direct.group(1)) if direct and _catw(direct.group(1)) in info else c]["amb"].append((x, tt[cs:x["s"]], tt[x["e"]:ce]))
        last_cat = c
    W_CUE = r"worth|counts?|count for|weigh\w*|weight|makes? up|accounts? for|is valued|valued at|contributes?|percent of|% of"
    S_CUE = r"got|get|scored?|have|had|earned|received|made|averag\w*|grade (?:of|is)|mark (?:of|is)|\bon\b|result|a mark|a score|:"
    for c in order:
        for x, before, after in info[c]["amb"]:
            if re.search(rf"(?:{W_CUE})\s*(?:of\s*|at\s*|for\s*|is\s*|=\s*)?$", before) or re.match(r"\s*%?\s*(?:of (?:the|my|your|our|their|a) (?:final |overall |total |course |class )?(?:grade|mark|score|course|class|total))", after) or before.rstrip().endswith("weight"):
                if info[c]["w"] is None:
                    info[c]["w"] = x["v"]
                    continue
            if re.search(rf"(?:{S_CUE})\s*(?:a |an |the )?$", before) or re.match(r"\s*%?\s*(?:on|in|for)\b", after) or not x["pct"]:
                if info[c]["s"] is None:
                    info[c]["s"] = x["v"]
                    continue
            if x["pct"] and info[c]["w"] is None:
                info[c]["w"] = x["v"]
            elif info[c]["s"] is None:
                info[c]["s"] = x["v"]
    weights = {c: info[c]["w"] for c in order}
    scores = {c: info[c]["s"] for c in order}
    if any(w is None for w in weights.values()):
        return None
    missing = [c for c in order if scores[c] is None]
    total_w = sum(weights.values())
    if total_w <= 0:
        return None
    norm = "" if total_w == 100 else f" (weights add up to {ex(total_w)}%, so divide by {ex(total_w)})"
    if not missing:
        g = sum(weights[c] * scores[c] for c in order) / total_w
        terms = " + ".join(f"{ex(weights[c] / 100)} × {ex(scores[c])}" for c in order)
        return _sol(text, f"{nice(g)}", [
            "formula: weighted average = Σ weight × score ÷ Σ weights",
            "known: " + ", ".join(f"{c} {ex(scores[c])} (weight {ex(weights[c])}%)" for c in order),
            f"substitute: {terms}" + ("" if total_w == 100 else f" ÷ {ex(total_w / 100)}") + norm,
            f"result: {nice(g)}"],
            " + ".join(ex(weights[c] * scores[c] / 100) for c in order) + f" = {nice(g * total_w / 100)}" + ("" if total_w == 100 else f" ÷ {ex(total_w / 100)}") + " ✓")
    if len(missing) != 1 or target is None:
        return None
    c0 = missing[0]
    tv = target[0]
    have = sum(weights[c] * scores[c] for c in order if c != c0)
    need = (tv * total_w - have) / weights[c0]
    steps = ["formula: weighted average = Σ weight × score ÷ Σ weights; solve for the missing score",
             "known: " + ", ".join(f"{c} {ex(scores[c])} (weight {ex(weights[c])}%)" for c in order if c != c0)
             + f", {c0} weight {ex(weights[c0])}%, target {ex(tv)}" + norm,
             f"substitute: {' + '.join(f'{ex(weights[c] / 100)} × {ex(scores[c])}' for c in order if c != c0)} + {ex(weights[c0] / 100)}·x = {ex(tv * total_w / 100)}"
             f" → {ex(have / 100)} + {ex(weights[c0] / 100)}·x = {ex(tv * total_w / 100)}",
             f"result: x = {nice(need)}"]
    ans = f"{nice(need)} on the {c0}"
    if need > 100:
        ans += " (more than 100, so not reachable)"
    elif need <= 0:
        ans = f"anything: you already have {ex(tv)} without the {c0}"
    chk = f"{' + '.join(ex(weights[c] * scores[c] / 100) for c in order if c != c0)} + {ex(weights[c0] / 100)} × {nice(need)} = {ex(tv * total_w / 100)} ✓"
    return _sol(text, ans, steps, chk)


GROUP = (r"students|people|boys|girls|men|women|workers|employees|players|kids|children|members|items|numbers|values|"
         r"apples|pupils|candidates|runners|teachers|staff|athletes|cars|houses|families|days|months|weeks|tests|exams|"
         r"quizzes|games|matches|classes|scores|readings|observations|batsmen|innings|participants|adults|seniors|juniors|"
         r"customers|patients|animals|dogs|cats|bags|boxes|books|trees|plants|teams")


def _group_average(t: str, text: str) -> Solution | None:
    if not re.search(r"combined|overall|whole|entire|all \d+|all of|both|together|altogether|in total|all the|everyone|class average|new average|total average|mean of all|average of all|average age of|for all", t):
        return None
    groups = []
    G = rf"(?:{GROUP})"
    for m in re.finditer(rf"\b(\d+) ((?:\w+ )?{G})\b(?:[^.;,\d]{{0,40}}?)\b(?:average|mean|avg|averag(?:e|ed|ing))(?: \w+){{0,2}}? (?:of |is |was |=|: |score of |mark of |weight of |age of |height of |salary of |of about )?[$£€₹]?\s?(\d+(?:\.\d+)?)", t):
        groups.append((int(m.group(1)), q(m.group(3)), m.group(2), m.span()))
    for m in re.finditer(rf"\b(?:average|mean)(?: \w+){{0,2}}? of (?:the |a group of |another |a class of |a second group of |the other )?(\d+) ((?:\w+ )?{G})\b(?: \w+){{0,3}}? (?:is|was|=|are|were) [$£€₹]?\s?(\d+(?:\.\d+)?)", t):
        if not any(s <= m.start() < e for *_, (s, e) in groups):
            groups.append((int(m.group(1)), q(m.group(3)), m.group(2), m.span()))
    for m in re.finditer(rf"\b(\d+) ((?:\w+ )?{G}) (?:who |that |which )?(?:averag(?:e|ed|es|ing)|have an average of|has an average of|had an average of) [$£€₹]?\s?(\d+(?:\.\d+)?)", t):
        if not any(s <= m.start() < e for *_, (s, e) in groups):
            groups.append((int(m.group(1)), q(m.group(3)), m.group(2), m.span()))
    groups.sort(key=lambda g: g[3][0])
    if len(groups) < 2:
        return None
    total_n = sum(g[0] for g in groups)
    total = sum(g[0] * g[1] for g in groups)
    avg = total / total_n
    return _sol(text, nice(avg), [
        "formula: combined average = total of everything ÷ how many (each group's total is count × its average)",
        "known: " + ", ".join(f"{g[0]} {g[2]} averaging {ex(g[1])}" for g in groups),
        f"substitute: ({' + '.join(f'{g[0]} × {ex(g[1])}' for g in groups)}) ÷ ({' + '.join(str(g[0]) for g in groups)}) = {ex(total)} ÷ {total_n}",
        f"result: {nice(avg)}"],
        f"not the plain average of the averages ({nice(sum(g[1] for g in groups) / len(groups))}): the bigger group counts for more"
        if len({g[0] for g in groups}) > 1 else f"{total_n} × {nice(avg)} = {ex(total)} ✓")


# ---------------------------------------------------------------- speeds, distances, times (shared by trains and boats)

SPEED_U = (r"km/h|km/hr|kmph|kph|kmh|km per hour|kms? an hour|kilomet(?:er|re)s? (?:per|an|a) hour|kilomet(?:er|re)s?/h|"
           r"mph|mi/h|miles? (?:per|an|a) hour|m/s|meters? per second|metres? per second|m per s|knots?|ft/s|feet per second|"
           r"m/min|meters? per minute|metres? per minute|km/min|yards? per second")
DIST_U = r"km|kms|kilomet(?:er|re)s?|miles?|mi|m|met(?:er|re)s?|ft|feet|foot|yards?|yd|nautical miles?"
DIST_F = {"km": 1000, "mile": R(1609344, 1000), "m": 1, "ft": R(3048, 10000), "yard": R(9144, 10000), "nmi": 1852}
TIME_F = {"hour": 3600, "minute": 60, "second": 1}


def _dist_key(u: str) -> str:
    u = u.lower()
    if u.startswith("naut"):
        return "nmi"
    if u in ("km", "kms") or u.startswith("kilom"):
        return "km"
    if u.startswith("mi"):
        return "mile"
    if u in ("ft", "feet", "foot"):
        return "ft"
    if u.startswith("y"):
        return "yard"
    return "m"


def _speed_key(u: str):
    u = u.lower()
    if u.startswith("knot"):
        return "nmi", "hour"
    if re.match(r"km/min", u):
        return "km", "minute"
    if re.match(r"m/min|met\w* per minute", u):
        return "m", "minute"
    if re.match(r"km|kilom", u):
        return "km", "hour"
    if re.match(r"mph|mi/h|mile", u):
        return "mile", "hour"
    if re.match(r"ft/s|feet", u):
        return "ft", "second"
    if re.match(r"yard", u):
        return "yard", "second"
    return "m", "second"


def _time_key(u: str) -> str:
    u = u.lower()
    if u.startswith("h"):
        return "hour"
    if u.startswith("m"):
        return "minute"
    return "second"


SPEED_SHOW = {("km", "hour"): "km/h", ("mile", "hour"): "mph", ("m", "second"): "m/s", ("nmi", "hour"): "knots",
              ("ft", "second"): "ft/s", ("m", "minute"): "m/min", ("km", "minute"): "km/min", ("yard", "second"): "yd/s"}
DIST_SHOW = {"km": "km", "mile": "miles", "m": "m", "ft": "ft", "yard": "yards", "nmi": "nautical miles"}


def _speeds(t: str):
    out = []
    for m in re.finditer(rf"(\d+(?:\.\d+)?)\s*({SPEED_U})(?![a-z])", t):
        du, tu = _speed_key(m.group(2))
        out.append((q(m.group(1)) * DIST_F[du] / TIME_F[tu], (du, tu), m.span(), q(m.group(1))))
    return out


def _clock_times(t: str):
    """Clock times in minutes after midnight, in order: '9 am', '10:30 pm', '14:15', 'noon'."""
    out = []
    for m in re.finditer(r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)(?![a-z])|\b(\d{1,2}):(\d{2})\b|\b(noon|midday|midnight)\b", t):
        if m.group(6):
            mins = 12 * 60 if m.group(6) != "midnight" else 0
        elif m.group(3):
            h, mi = int(m.group(1)), int(m.group(2) or 0)
            if h > 12 or mi > 59:
                continue
            pm = m.group(3).startswith("p")
            h = (h % 12) + (12 if pm else 0)
            mins = h * 60 + mi
        else:
            h, mi = int(m.group(4)), int(m.group(5))
            if h > 23 or mi > 59:
                continue
            mins = h * 60 + mi
        out.append((mins, m.span()))
    return out


def _show_clock(mins) -> str:
    mins = sp.nsimplify(mins)
    whole = int(round(float(mins)))
    approx = "" if mins.is_Integer else "≈ "
    day, rem = divmod(whole, 24 * 60)
    h, mi = divmod(rem, 60)
    s = f"{approx}{h % 12 or 12}:{mi:02d} {'am' if h < 12 else 'pm'}"
    return s + (" the next day" if day else "")


# ---------------------------------------------------------------- boats and currents

def boats(t: str, text: str) -> Solution | None:
    if not re.search(r"upstream|downstream|still water|still air|\bcurrent\b|\bstream\b|tail ?wind|head ?wind|with the wind|against the wind|air ?speed|wind speed|speed of the wind", t):
        return None
    if not re.search(r"upstream|downstream|still|against|with the|tail ?wind|head ?wind|air ?speed|\bin \d", t):
        return None
    air = bool(re.search(r"\bwind\b|plane|air ?speed|still air|jet|aircraft|flight|flies|fly|flew", t))
    flow = "wind" if air else "current"
    still_name = "still air" if air else "still water"
    DOWN = r"downstream|with the (?:current|wind|stream|tide)|with a tail ?wind|with the tail ?wind|tail ?wind|with the river"
    UP = r"upstream|against the (?:current|wind|stream|tide)|into a head ?wind|against a head ?wind|into the wind|head ?wind|against the river"
    sp_list = _speeds(t)
    still = cur_v = down_v = up_v = None
    units = sp_list[0][1] if sp_list else None
    for v, u, (s, e), raw in sp_list:
        before, after = t[max(0, s - 45):s], t[e:e + 30]
        if re.search(r"\b(?:current|stream|river|wind|tide)\W*(?:speed|rate)?\W*(?:is|of|=|at)?\W*$", before) and not re.match(r"\s*(?:in still|in calm)", after):
            cur_v = v
        elif re.search(r"still (?:water|air)|air ?speed|in calm (?:water|air)", before + " " + after[:25]):
            still = v
        elif re.search(rf"(?:{DOWN})\W*(?:speed|rate)?\W*(?:is|of|=|at)?\W*$", before) or re.match(rf"\s*(?:{DOWN})", after):
            down_v = v
        elif re.search(rf"(?:{UP})\W*(?:speed|rate)?\W*(?:is|of|=|at)?\W*$", before) or re.match(rf"\s*(?:{UP})", after):
            up_v = v
        elif re.search(r"current|stream|river|wind|flow|tide|water (?:flows|moves|runs)", before[-35:] + " " + after[:20]):
            cur_v = v
        elif re.search(r"boat|ship|plane|swimmer|canoe|kayak|steamer|motorboat|rower|man|woman|jet|aircraft|launch|ferry|yacht|raft", before):
            still = v
    trips = []  # (direction, distance SI, time SI)
    TU = r"hours?|hrs?|h|minutes?|mins?|seconds?|secs?"
    for m in re.finditer(rf"(\d+(?:\.\d+)?)\s*({DIST_U})\b\s*({DOWN}|{UP})\b[^.;?]*?\bin (\d+(?:\.\d+)?)\s*({TU})\b", t):
        d = q(m.group(1)) * DIST_F[_dist_key(m.group(2))]
        trips.append(("down" if re.match(DOWN, m.group(3)) else "up", d, q(m.group(4)) * TIME_F[_time_key(m.group(5))], m.span(), _dist_key(m.group(2)), _time_key(m.group(5))))
    for m in re.finditer(rf"({DOWN}|{UP})\b[^.;?\d]*?(\d+(?:\.\d+)?)\s*({DIST_U})\b[^.;?\d]*?\bin (\d+(?:\.\d+)?)\s*({TU})\b", t):
        if any(s <= m.start() < e for *_, (s, e), _a, _b in trips):
            continue
        d = q(m.group(2)) * DIST_F[_dist_key(m.group(3))]
        trips.append(("down" if re.match(DOWN, m.group(1)) else "up", d, q(m.group(4)) * TIME_F[_time_key(m.group(5))], m.span(), _dist_key(m.group(3)), _time_key(m.group(5))))
    for m in re.finditer(rf"takes? (\d+(?:\.\d+)?)\s*({TU}) to (?:go|travel|row|swim|sail|paddle|fly|cover|cruise|motor) (\d+(?:\.\d+)?)\s*({DIST_U})\b\s*({DOWN}|{UP})", t):
        d = q(m.group(3)) * DIST_F[_dist_key(m.group(4))]
        trips.append(("down" if re.match(DOWN, m.group(5)) else "up", d, q(m.group(1)) * TIME_F[_time_key(m.group(2))], m.span(), _dist_key(m.group(4)), _time_key(m.group(2))))
    trips.sort(key=lambda x: x[3][0])
    if len(trips) == 1:
        back = re.search(rf"(?:return(?:s|ed|ing)?|comes? back|came back|back|same distance|the same trip)\b[^.;?\d]*?\bin (\d+(?:\.\d+)?)\s*({TU})\b", t[trips[0][3][1]:])
        if back:
            d0 = trips[0]
            trips.append(("up" if d0[0] == "down" else "down", d0[1], q(back.group(1)) * TIME_F[_time_key(back.group(2))], (0, 0), d0[4], _time_key(back.group(2))))
    du, tu = units if units else ((trips[0][4], "hour") if trips else ("km", "hour"))
    if trips and not units:
        du = trips[0][4]
        tu = "hour" if trips[0][5] in ("hour", "minute") else "second"
    vf = DIST_F[du] / TIME_F[tu]
    vs = SPEED_SHOW.get((du, tu), f"{DIST_SHOW[du]}/{tu}")

    def V(x):
        return f"{nice(x / vf)} {vs}"
    steps = [f"rule: {'downstream' if not air else 'with the wind'} speed = {'boat' if not air else 'plane'} + {flow}, "
             f"{'upstream' if not air else 'against the wind'} speed = {'boat' if not air else 'plane'} − {flow}"]
    for d, dist, tim, *_ in trips:
        v = dist / tim
        steps.append(f"known: {'downstream' if d == 'down' and not air else 'upstream' if not air else 'with the wind' if d == 'down' else 'against the wind'}"
                     f" {nice(dist / DIST_F[du])} {DIST_SHOW[du]} in {nice(tim / TIME_F[tu])} {pl(tu + 's', tim / TIME_F[tu])} → {V(v)}")
        if d == "down":
            down_v = v
        else:
            up_v = v
    ask_still = re.search(rf"(?:speed|rate|velocity)[^.?]*?(?:in still (?:water|air)|of the (?:boat|plane|swimmer|ship|canoe|man|rower)|in calm)|still[- ](?:water|air) speed|air ?speed|how fast (?:can|does|is|would) (?:the |a |he |she )?(?:boat|plane|swimmer|man|he|she)", t)
    ask_cur = re.search(r"(?:speed|rate|velocity) of (?:the )?(?:current|stream|river|wind|water|tide|flow)|current'?s? speed|wind speed|how fast (?:is|does) (?:the )?(?:current|stream|river|wind)", t)
    if down_v is not None and up_v is not None and (still is None or cur_v is None):
        b, c = (down_v + up_v) / 2, (down_v - up_v) / 2
        steps += [f"substitute: {'boat' if not air else 'plane'} = ({V(down_v)} + {V(up_v)}) / 2, {flow} = ({V(down_v)} − {V(up_v)}) / 2",
                  f"result: {still_name} {V(b)}, {flow} {V(c)}"]
        if ask_cur and not ask_still:
            ans = f"{flow} {V(c)} ({still_name} {V(b)})"
        else:
            ans = f"{still_name} {V(b)}, {flow} {V(c)}"
        return _sol(text, ans, steps, f"{V(b)} + {V(c)} = {V(down_v)} and {V(b)} − {V(c)} = {V(up_v)} ✓")
    if still is not None and cur_v is None and (down_v is not None or up_v is not None):
        c = (down_v - still) if down_v is not None else (still - up_v)
        steps += [f"substitute: {flow} = " + (f"{V(down_v)} − {V(still)}" if down_v is not None else f"{V(still)} − {V(up_v)}"), f"result: {flow} {V(c)}"]
        return _sol(text, f"{flow} {V(c)}", steps)
    if cur_v is not None and still is None and (down_v is not None or up_v is not None) and not re.search(r"and back|round trip|return", t):
        b = (down_v - cur_v) if down_v is not None else (up_v + cur_v)
        steps += [f"substitute: {'boat' if not air else 'plane'} = " + (f"{V(down_v)} − {V(cur_v)}" if down_v is not None else f"{V(up_v)} + {V(cur_v)}"), f"result: {still_name} {V(b)}"]
        return _sol(text, f"{still_name} {V(b)}", steps)
    rt = re.search(rf"(\d+(?:\.\d+)?)\s*({DIST_U})\b[^.?;]*?(?:and back|round trip|there and back|and return|and returns|and comes back|return trip|both ways|back again|returning)[^.?;]*?(?:in|takes?|took|total of|altogether|of) (\d+(?:\.\d+)?)\s*({TU})\b", t) \
        or re.search(rf"(?:and back|round trip|there and back|return trip|both ways)[^.?;]*?(\d+(?:\.\d+)?)\s*({DIST_U})\b[^.?;\d]*?(?:in|takes?|took) (\d+(?:\.\d+)?)\s*({TU})\b", t)
    if rt:
        D = q(rt.group(1)) * DIST_F[_dist_key(rt.group(2))]
        T = q(rt.group(3)) * TIME_F[_time_key(rt.group(4))]
        if not units:
            du, tu = _dist_key(rt.group(2)), "hour" if _time_key(rt.group(4)) != "second" else "second"
            vf = DIST_F[du] / TIME_F[tu]
            vs = SPEED_SHOW.get((du, tu), f"{DIST_SHOW[du]}/{tu}")
        Dd, Tt = D / DIST_F[du], T / TIME_F[tu]
        x = sp.Symbol("v", positive=True)
        if cur_v is not None and still is None:
            c = cur_v / vf
            roots = [r for r in sp.solve(sp.Eq(Dd / (x - c) + Dd / (x + c), Tt), x) if r.is_real and r > c]
            if len(roots) != 1:
                return None
            b = roots[0]
            steps += [f"known: {nice(Dd)} {DIST_SHOW[du]} each way in {nice(Tt)} {tu}s in all, {flow} {nice(c)} {vs}",
                      f"substitute: {nice(Dd)}/(v − {nice(c)}) + {nice(Dd)}/(v + {nice(c)}) = {nice(Tt)} → {ex(Tt)}v² − {ex(2 * Dd)}v − {ex(Tt * c * c)} = 0",
                      f"result: v = {nice(b)} {vs} (the other root is negative)"]
            return _sol(text, f"{still_name} {nice(b)} {vs}", steps,
                        f"{nice(Dd)}/{nice(b - c)} + {nice(Dd)}/{nice(b + c)} = {nice(Dd / (b - c))} + {nice(Dd / (b + c))} = {nice(Tt)} {tu}s ✓")
        if still is not None and cur_v is None:
            b = still / vf
            roots = [r for r in sp.solve(sp.Eq(Dd / (b - x) + Dd / (b + x), Tt), x) if r.is_real and 0 < r < b]
            if len(roots) != 1:
                return None
            c = roots[0]
            steps += [f"known: {nice(Dd)} {DIST_SHOW[du]} each way in {nice(Tt)} {tu}s, {still_name} {nice(b)} {vs}",
                      f"substitute: {nice(Dd)}/({nice(b)} − c) + {nice(Dd)}/({nice(b)} + c) = {nice(Tt)}",
                      f"result: c = {nice(c)} {vs}"]
            return _sol(text, f"{flow} {nice(c)} {vs}", steps,
                        f"{nice(Dd / (b - c))} + {nice(Dd / (b + c))} = {nice(Tt)} {tu}s ✓")
        if still is not None and cur_v is not None:
            pass
    if still is not None and cur_v is not None:
        b, c = still, cur_v
        if c >= b and re.search(rf"{UP}", t):
            return _sol(text, f"it can't go {'upstream' if not air else 'against the wind'}: the {flow} is at least as fast", steps)
        dm = list(re.finditer(rf"(\d+(?:\.\d+)?)\s*({DIST_U})\b(?!\s*(?:per|/|an hour|a hour))", t))
        tm_ = re.search(rf"\bin (\d+(?:\.\d+)?)\s*({TU})\b", t)
        steps.append(f"known: {still_name} {V(b)}, {flow} {V(c)} → downstream {V(b + c)}, upstream {V(b - c)}".replace(
            "downstream", "with the wind" if air else "downstream").replace("upstream", "against the wind" if air else "upstream"))
        if dm and re.search(r"how long|how much time|how many (?:hours|minutes)|time (?:taken|needed|will it take|to)|take\?", t):
            D = q(dm[0].group(1)) * DIST_F[_dist_key(dm[0].group(2))]
            Dd = D / DIST_F[du]
            both = re.search(r"and back|round trip|there and back|return|both ways", t)
            tdown, tup = D / (b + c) / TIME_F[tu], D / (b - c) / TIME_F[tu] if b > c else None
            if both:
                tot = tdown + tup
                steps += [f"substitute: {nice(Dd)}/{nice((b + c) / vf)} + {nice(Dd)}/{nice((b - c) / vf)} = {nice(tdown)} + {nice(tup)}",
                          f"result: {duration(tot, tu)}"]
                return _sol(text, duration(tot, tu), steps)
            seg = t[max(0, dm[0].start() - 30):dm[0].end() + 30]
            upward = bool(re.search(UP, seg)) or (re.search(UP, t) and not re.search(DOWN, t))
            tt_ = tup if upward else tdown
            spd = (b - c) if upward else (b + c)
            steps += [f"substitute: time = {nice(Dd)} ÷ {V(spd)}", f"result: {duration(tt_, tu)}"]
            return _sol(text, duration(tt_, tu), steps, f"{V(spd)} × {nice(tt_)} {tu}s = {nice(Dd)} {DIST_SHOW[du]} ✓")
        if tm_ and re.search(r"how far", t):
            T = q(tm_.group(1)) * TIME_F[_time_key(tm_.group(2))]
            upward = bool(re.search(UP, t)) and not re.search(DOWN, t)
            spd = (b - c) if upward else (b + c)
            dist = spd * T / DIST_F[du]
            steps += [f"substitute: distance = {V(spd)} × {nice(T / TIME_F[tu])} {tu}s", f"result: {nice(dist)} {DIST_SHOW[du]}"]
            return _sol(text, f"{nice(dist)} {DIST_SHOW[du]}", steps)
        if re.search(r"(?:downstream|upstream) speed|speed (?:downstream|upstream)|how fast", t):
            return _sol(text, f"downstream {V(b + c)}, upstream {V(b - c)}", steps + [f"result: {V(b + c)} and {V(b - c)}"])
    return None


# ---------------------------------------------------------------- trains

MOVER = r"trains?|cars?|bus(?:es)?|cyclists?|bikes?|bicycles?|runners?|walkers?|joggers?|planes?|trucks?|motorcycles?|boats?|ships?|people|persons|friends|men|women|boys|girls|brothers|sisters|drivers|vehicles|riders|hikers"


def _places(text: str) -> list[str]:
    out = []
    skip = {"A", "The", "Train", "How", "When", "What", "If", "At", "It", "They", "Two", "One", "Another", "Find", "Car", "Bus"}
    for m in re.finditer(r"\b(?:from|leaves|leaving|departs|departing|left|starts? from|sets? (?:out|off) from|station|city|town) ([A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)?)", text):
        w = m.group(1)
        if w.split()[0] not in skip and w not in out:
            out.append(w)
    return out


def train_pass(t: str, text: str) -> Solution | None:
    if not re.search(r"\b(?:pass(?:es)?|cross(?:es)?|clears?|go(?:es)? (?:past|through|over)|get past|overtakes?)\b", t):
        return None
    LEN = rf"(\d+(?:\.\d+)?)\s*({DIST_U})\b[- ]?(?:long\b|in length\b)|\blength (?:of )?(\d+(?:\.\d+)?)\s*({DIST_U})\b|\b(\d+(?:\.\d+)?)\s*({DIST_U})[- ](?:long )?(?:train|platform|bridge|tunnel|station|goods train)"
    lens = []
    for m in re.finditer(LEN, t):
        g = [x for x in m.groups() if x]
        lens.append((q(g[0]) * DIST_F[_dist_key(g[1])], m.span(), _dist_key(g[1])))
    if not lens:
        return None
    sps = _speeds(t)
    tm = re.search(r"\bin (\d+(?:\.\d+)?)\s*(seconds?|secs?|s|minutes?|mins?)\b", t)
    obj_point = re.search(r"\b(?:pole|post|signal|tree|man|person|lamp ?post|pillar|telegraph|milestone|standing|boy|girl|woman|platform man|sign|flag)\b", t)
    obj_len = re.search(r"\b(?:platform|bridge|tunnel|station|another train|other train|second train|goods train|each other)\b", t)
    two_trains = len(sps) >= 2 and re.search(r"\b(?:another train|other train|second train|goods train|each other|two trains|both trains)\b", t)
    if two_trains:
        if len(lens) < 2:
            return None
        v1, v2 = sps[0][0], sps[1][0]
        opposite = bool(re.search(r"opposite|toward|towards|each other", t)) and not re.search(r"same direction|overtak", t)
        rel = v1 + v2 if opposite else abs(v1 - v2)
        if rel == 0:
            return None
        L = lens[0][0] + lens[1][0]
        tt_ = L / rel
        return _sol(text, duration(tt_, "seconds"), [
            f"rule: to clear each other the trains cover both lengths at their relative speed ({'sum' if opposite else 'difference'} of speeds)",
            f"known: lengths {nice(lens[0][0])} m + {nice(lens[1][0])} m; speeds {nice(sps[0][3])} and {nice(sps[1][3])} {SPEED_SHOW[sps[0][1]]} = "
            f"{nice(v1)} and {nice(v2)} m/s",
            f"substitute: t = {nice(L)} ÷ {nice(rel)} m/s", f"result: {duration(tt_, 'seconds')}"],
            f"{nice(rel)} m/s × {nice(tt_)} s = {nice(L)} m ✓")
    L1 = lens[0][0]
    L2 = lens[1][0] if len(lens) > 1 and obj_len else 0
    if obj_len and not obj_point and len(lens) < 2:
        if not (sps and tm and re.search(r"length of (?:the )?(?:platform|bridge|tunnel)|how long is the (?:platform|bridge|tunnel)", t)):
            return None
    if sps and not tm:
        v = sps[0][0]
        if len(sps) > 1 and obj_point:
            other = sps[1][0]
            v = v + other if re.search(r"opposite|toward|towards", t) else v - other
        dist = L1 + L2
        tt_ = dist / v
        steps = ["rule: the train has to cover its own length" + (" plus the " + obj_len.group(0) + "'s" if L2 else "") + " to pass it",
                 f"known: train {nice(L1)} m" + (f", {obj_len.group(0)} {nice(L2)} m" if L2 else "") + f", speed {nice(sps[0][3])} {SPEED_SHOW[sps[0][1]]} = {nice(sps[0][0])} m/s"
                 + (f", relative speed {nice(v)} m/s" if len(sps) > 1 and obj_point else ""),
                 f"substitute: t = {nice(dist)} m ÷ {nice(v)} m/s", f"result: {duration(tt_, 'seconds')}"]
        return _sol(text, duration(tt_, "seconds"), steps, f"{nice(v)} m/s × {nice(tt_)} s = {nice(dist)} m ✓")
    if tm and sps:
        T = q(tm.group(1)) * TIME_F[_time_key(tm.group(2))]
        v = sps[0][0]
        covered = v * T
        if obj_len and len(lens) == 1:
            other = covered - L1
            return _sol(text, f"{nice(other)} m", [
                "rule: distance covered = train length + platform length", f"known: train {nice(L1)} m, speed {nice(v)} m/s, time {nice(T)} s",
                f"substitute: {nice(v)} × {nice(T)} − {nice(L1)}", f"result: {nice(other)} m"])
    return None


def trains(t: str, text: str) -> Solution | None:
    sps = _speeds(t)
    if len(sps) != 2:
        return None
    if not re.search(r"\b(?:meet|meets|met|pass|passes|catch(?:es)? up|catch|overtake|overtakes|overtaken|apart|cross|toward|towards|each other|"
                     r"same direction|opposite directions?|head start|later|leaves?|left|departs?|set off|sets off|start|starts|collide)\b", t):
        return None
    (vA, uA, spanA, rawA), (vB, uB, spanB, rawB) = sps
    du, tu = uA
    if du == "m" and tu == "second" and re.search(r"\bhours?\b|\bkm\b|\bmiles?\b", t):
        du, tu = "km", "hour"
    vf = DIST_F[du] / TIME_F[tu]
    vs = SPEED_SHOW.get((du, tu), f"{DIST_SHOW[du]}/{tu}")
    speed_spans = [spanA, spanB]
    D = None
    for m in re.finditer(rf"(\d+(?:\.\d+)?)\s*({DIST_U})\b(?!\s*(?:per|/|an hour|a hour|long))", t):
        if any(s <= m.start() < e for s, e in speed_spans):
            continue
        D = q(m.group(1)) * DIST_F[_dist_key(m.group(2))]
        break
    times = [x for x in _clock_times(t) if not any(s <= x[1][0] < e for s, e in speed_spans)]
    off_m = re.search(r"\b(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)\s*(?:later|after (?:the first|it|that|him|her|train a|the other|the first one))|\b(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)\s*head start|head start of (\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)", t)
    tA = tB = R(0)
    clock0 = None
    if len(times) >= 2:
        tA, tB = R(times[0][0] * 60), R(times[1][0] * 60)
        clock0 = 0
    elif off_m:
        g = [x for x in off_m.groups() if x]
        off = q(g[0]) * TIME_F[_time_key(g[1])]
        if off_m.group(3) or off_m.group(5):
            tA, tB = R(0), off  # head start for the first one
        else:
            tA, tB = R(0), off
        if times:
            clock0 = times[0][0]
            tA, tB = tA + clock0 * 60, tB + clock0 * 60
            clock0 = 0
    elif times:
        tA = tB = R(times[0][0] * 60)
        clock0 = 0
    toward = re.search(r"toward|towards|approach|head[- ]on|each other|collide|opposite (?:ends|stations|cities|towns|points|sides)|from the other end", t)
    chase = re.search(r"same direction|catch(?:es)? up|overtake|overtakes|overtaken|catch (?:up with )?(?:it|him|her|the first|them)|follows?|chas|same (?:station|place|point|track|road|town|city|spot|start)", t)
    apart_q = re.search(r"\bapart\b", t) and re.search(r"opposite directions?", t) and not toward
    places = _places(text)
    start_name = f"{places[0]}" if places else "the first one's start"
    steps = []

    def T(x):
        return x / TIME_F[tu]

    def Dd(x):
        return x / DIST_F[du]

    def clock(sec):
        return _show_clock(sec / 60) if clock0 is not None else None
    before_meet = re.search(r"\b(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?) before (?:they|the trains|the two \w+|the \w+) (?:meet|collide|cross|pass)", t)
    if before_meet and (toward or not chase):
        tau = q(before_meet.group(1)) * TIME_F[_time_key(before_meet.group(2))]
        d = (vA + vB) * tau
        return _sol(text, f"{nice(Dd(d))} {DIST_SHOW[du]}", [
            "rule: in the last stretch before they meet they close the gap at the sum of their speeds",
            f"known: {nice(rawA)} + {nice(rawB)} = {nice((vA + vB) / vf)} {vs}, time {nice(T(tau))} {tu}s",
            f"substitute: {nice((vA + vB) / vf)} × {nice(T(tau))}", f"result: {nice(Dd(d))} {DIST_SHOW[du]} apart"],
            "the starting distance doesn't matter" if D else "")
    if toward and not chase:
        if D is None:
            return None
        first, second = (tA, tB) if tA <= tB else (tB, tA)
        v_first = vA if tA <= tB else vB
        head = v_first * (second - first)
        if head >= D:
            return None
        rem = D - head
        tm_after = rem / (vA + vB)
        meet = second + tm_after
        xA = vA * (meet - tA)
        steps.append("rule: moving toward each other they close the gap at the sum of their speeds")
        steps.append(f"known: {nice(Dd(D))} {DIST_SHOW[du]} apart, speeds {nice(rawA)} and {nice(rawB)} {vs}"
                     + (f"; the {'first' if tA <= tB else 'second'} sets off {duration(T(second - first), tu)} earlier" if second != first else ""))
        if head:
            steps.append(f"substitute: head start {nice(v_first / vf)} × {nice(T(second - first))} = {nice(Dd(head))} {DIST_SHOW[du]}, "
                         f"leaving {nice(Dd(rem))}; {nice(Dd(rem))} ÷ ({nice(rawA)} + {nice(rawB)}) = {nice(T(tm_after))} {tu}s")
        else:
            steps.append(f"substitute: t = {nice(Dd(D))} ÷ ({nice(rawA)} + {nice(rawB)}) = {nice(T(tm_after))} {tu}s")
        when = clock(meet)
        ans = f"they meet {duration(T(tm_after), tu)} after the {'second one sets off' if head else 'start'}"
        if when:
            ans = f"they meet at {when}, " + ans.replace("they meet ", "")
        ans += f", {nice(Dd(xA))} {DIST_SHOW[du]} from {start_name}"
        steps.append(f"result: {ans}")
        xB = vB * (meet - tB)
        return _sol(text, ans, steps, f"{nice(Dd(xA))} + {nice(Dd(xB))} = {nice(Dd(D))} {DIST_SHOW[du]} ✓")
    if chase:
        lead_d = re.search(rf"(\d+(?:\.\d+)?)\s*({DIST_U})\b\s*(?:ahead|head start|in front|behind)", t)
        head_d = q(lead_d.group(1)) * DIST_F[_dist_key(lead_d.group(2))] if lead_d else R(0)
        if tA <= tB:
            (v1, t1, r1), (v2, t2, r2) = (vA, tA, rawA), (vB, tB, rawB)
        else:
            (v1, t1, r1), (v2, t2, r2) = (vB, tB, rawB), (vA, tA, rawA)
        if tA == tB and head_d:
            (v1, r1), (v2, r2) = ((vA, rawA), (vB, rawB)) if vA < vB else ((vB, rawB), (vA, rawA))
        if v2 <= v1:
            return _sol(text, "it never catches up: the one behind isn't faster", [f"known: {nice(r1)} and {nice(r2)} {vs}"])
        lead = v1 * (t2 - t1) + head_d
        if lead <= 0:
            return None
        tc = lead / (v2 - v1)
        catch = t2 + tc
        where = v2 * tc
        steps += ["rule: the gap closes at the difference of the speeds",
                  f"known: the first moves at {nice(r1)} {vs}" + (f" and has {duration(T(t2 - t1), tu)} start" if t2 > t1 else "")
                  + (f" and is {nice(Dd(head_d))} {DIST_SHOW[du]} ahead" if head_d else "") + f"; the second at {nice(r2)} {vs}",
                  f"substitute: lead = {nice(Dd(lead))} {DIST_SHOW[du]}; time = {nice(Dd(lead))} ÷ ({nice(r2)} − {nice(r1)}) = {nice(T(tc))} {tu}s"]
        when = clock(catch)
        ans = f"{duration(T(tc), tu)} after the second one sets off"
        if when:
            ans = f"at {when} ({ans})"
        ans += f", {nice(Dd(where))} {DIST_SHOW[du]} from the start"
        steps.append(f"result: {ans}")
        return _sol(text, ans, steps, f"first: {nice(r1)} × {nice(T(catch - t1))} = {nice(Dd(v1 * (catch - t1) + head_d))}; "
                                      f"second: {nice(r2)} × {nice(T(tc))} = {nice(Dd(where))} {DIST_SHOW[du]} ✓")
    if apart_q and D is not None:
        first, second = (tA, tB) if tA <= tB else (tB, tA)
        v_first = vA if tA <= tB else vB
        head = v_first * (second - first)
        rem = D - head
        if rem <= 0:
            return None
        tm_after = rem / (vA + vB)
        when = clock(second + tm_after)
        ans = f"{duration(T(tm_after), tu)}" + (" after the second one sets off" if head else "") + (f" (at {when})" if when else "")
        return _sol(text, ans, [
            "rule: moving in opposite directions the gap grows at the sum of the speeds",
            f"known: {nice(rawA)} and {nice(rawB)} {vs}, target gap {nice(Dd(D))} {DIST_SHOW[du]}",
            f"substitute: t = {nice(Dd(rem))} ÷ {nice((vA + vB) / vf)}", f"result: {ans}"],
            f"{nice((vA + vB) / vf)} × {nice(T(tm_after))} = {nice(Dd(rem))} {DIST_SHOW[du]} ✓")
    return None


# ---------------------------------------------------------------- work rates

DUR = r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|days?|weeks?|seconds?|secs?)\b"
FILLV = r"\b(?:fill|fills|filled|filling|fills up)\b"
DRAINV = r"\b(?:drain|drains|drained|draining|leak|leaks|leaked|leaking|empties|emptied|emptying|siphons?|pumps? out|lets? out|takes? out)\b|(?<!\ban )(?<!\bthe )(?<!\ba )(?<!\bis )(?<!\bwas )(?<!\bwhen )\bempty\b(?! tank| pool| bath| tub| cistern| bucket| container| reservoir| one)"
TOGETHER = r"\b(?:together|both|combined|jointly|at the same time|simultaneously|as a team|between them|working together|all 3|all three)\b"
UNIT_KEY = {"h": "hour", "hr": "hour", "hrs": "hour", "hour": "hour", "hours": "hour", "min": "minute", "mins": "minute",
            "minute": "minute", "minutes": "minute", "day": "day", "days": "day", "week": "week", "weeks": "week",
            "second": "second", "seconds": "second", "sec": "second", "secs": "second"}
UNIT_SEC = {"second": 1, "minute": 60, "hour": 3600, "day": 86400, "week": 604800}


def _agent_names(text: str, t: str, n: int) -> list[str]:
    tagged = re.findall(r"\b(pipe|tap|hose|machine|printer|pump|worker|inlet|outlet|faucet|crew|team|robot|drain) ([a-c]|[1-3]|x|y)\b", t)
    if len({f"{a} {b}" for a, b in tagged}) >= n:
        out = []
        for a, b in tagged:
            nm = f"{a} {b.upper()}"
            if nm not in out:
                out.append(nm)
        return out[:n]
    skip = {"It", "If", "How", "What", "When", "The", "A", "An", "Working", "Together", "Both", "One", "Another", "Pipe",
            "Tap", "Then", "They", "He", "She", "I", "Find", "In", "At", "Alone", "Each", "And", "With", "Quick", "Pls",
            "Please", "Hey", "Hi", "Kepler", "Show", "Can", "Could", "Would", "Also", "Help", "There", "This", "That", "So",
            "Ok", "Okay", "Two", "Three", "Mr", "Mrs", "Ms", "Dr", "Suppose", "Given", "Assume", "Machine", "Printer", "If",
            "Working", "Running", "Hose", "Drain", "Leak", "Homework", "For", "Answer", "Steps", "My", "Our", "His", "Her",
            "Using", "Let", "Pump", "Painting", "Worker", "Workers", "Man", "Woman", "Boy", "Girl", "Help", "Quickly", "Yo"}
    names = []
    for w in re.findall(r"\b[A-Z][a-z]+\b", text):
        if w not in skip and w not in names:
            names.append(w)
    if len(names) >= n:
        return names[:n]
    return [chr(ord("A") + i) for i in range(n)]


def work(t: str, text: str) -> Solution | None:
    if not re.search(r"\b(?:job|work|works|task|fill|fills|filled|tank|pool|tap|pipe|pipes|hose|faucet|paint|paints|painting|mow|mows|"
                     r"build|builds|dig|digs|clean|cleans|finish|finishes|complete|completes|do it|does it|drain|drains|empty|empties|"
                     r"bath|tub|cistern|fence|house|room|lawn|wall|together|alone|both|working|leak|leaks|reservoir|bucket|print|"
                     r"prints|type|types|harvest|plough|plow|wash|washes|assemble|cook|bake|pack|packs|load|unload|repair|machine)\b", t):
        return None
    durs = list(re.finditer(DUR, t))
    if len(durs) < 2 or len(durs) > 4:
        return None
    if not re.search(rf"{TOGETHER}|\balone\b|by (?:himself|herself|itself|themselves)|on (?:his|her|its|their) own|single-?handed|\bopen\b|\bopened\b|\bturned on\b|\bwith both\b", t):
        return None
    if not re.search(r"how (?:long|many (?:hours?|minutes?|days?|weeks?|seconds?))|what time|time (?:taken|needed|required|will it take|would it take|to)|when will|how much time|find the time|\btake\b|\?", t):
        return None
    if re.search(r"\b(?:km|miles?|mph|km/h|speed|upstream|downstream|apart|train|meet)\b", t):
        return None
    units = [UNIT_KEY.get(d.group(2), "hour") for d in durs]
    base = min(units, key=lambda u: UNIT_SEC[u]) if len(set(units)) > 1 else units[0]
    agents = []
    prev = 0
    for d, u in zip(durs, units):
        seg = t[prev:d.start()]
        seg_last = re.split(r"[.?!]", seg)[-1]
        val = q(d.group(1)) * UNIT_SEC[u] / UNIT_SEC[base]
        fills = [m.end() for m in re.finditer(FILLV, seg_last)]
        drains = [m.end() for m in re.finditer(DRAINV, seg_last)]
        sign = -1 if drains and (not fills or max(drains) > max(fills)) else 1
        comb = bool(re.search(TOGETHER, seg_last))
        agents.append({"d": val, "sign": sign, "comb": comb, "raw": d.group(0)})
        prev = d.end()
    combined = [a for a in agents if a["comb"]]
    singles = [a for a in agents if not a["comb"]]
    names = _agent_names(text, t, len(singles) + 1)
    unit_s = base + "s"
    if len(combined) > 1:
        return None
    if combined:
        if len(singles) != 1:
            return None
        Tc, a = combined[0]["d"], singles[0]
        r = 1 / Tc - a["sign"] / a["d"]
        if r <= 0:
            return _sol(text, "not possible: together they'd be no faster than one alone", [f"known: together {ex(Tc)} {unit_s}, alone {ex(a['d'])} {unit_s}"])
        other = 1 / r
        n1, n2 = names[0], names[1]
        return _sol(text, duration(other, base), [
            "rule: rates add: 1/together = 1/A + 1/B, where each rate is jobs per " + base,
            f"known: together {ex(Tc)} {unit_s}, {n1} alone {ex(a['d'])} {unit_s}",
            f"substitute: 1/x = 1/{ex(Tc)} − 1/{ex(a['d'])} = {ex(r)}", f"result: x = {duration(other, base)} for {n2} alone"],
            f"1/{ex(a['d'])} + 1/{nice(other)} = {ex(1 / a['d'] + r)} = 1/{ex(Tc)} ✓")
    if len(singles) < 2:
        return None
    rate = sum(a["sign"] / a["d"] for a in singles)
    terms = " ".join(("+ " if a["sign"] > 0 else "− ") + f"1/{ex(a['d'])}" for a in singles).lstrip("+ ")
    knowns = ", ".join(f"{nm} {'empties' if a['sign'] < 0 else 'does'} it in {ex(a['d'])} {unit_s}" for nm, a in zip(names, singles))
    steps = [f"rule: work rates add (a drain counts negative): combined rate = Σ 1/time, time = 1 ÷ rate",
             f"known: {knowns}" + (f" (all in {unit_s})" if len(set(units)) > 1 else ""),
             f"substitute: {terms} = {ex(rate)} of the job per {base}"]
    if rate <= 0:
        return _sol(text, "never: it drains at least as fast as it fills", steps + ["result: the net rate isn't positive"])
    tot = 1 / rate
    steps.append(f"result: 1 ÷ {ex(rate)} = {duration(tot, base)}")
    chk = " ".join(("+ " if a["sign"] > 0 else "− ") + nice(tot / a["d"]) for a in singles).lstrip("+ ")
    return _sol(text, duration(tot, base), steps, f"in {nice(tot)} {unit_s}: {chk} = 1 job ✓")


# ---------------------------------------------------------------- ages

RELWORDS = ("son daughter father mother dad mom mum mommy mummy daddy papa mama brother sister uncle aunt grandfather "
            "grandmother grandpa grandma granddad grandad granny nana grandson granddaughter nephew niece cousin wife husband "
            "friend child kid boss teacher baby sibling twin boyfriend girlfriend neighbor neighbour stepdad stepmom stepfather "
            "stepmother parent man woman boy girl lady gentleman student").split()
_RELALT = "|".join(sorted(RELWORDS, key=len, reverse=True))
AGE_STOP = set(("it they them who what how which the a an and is will was in ago years year there this that one now then currently "
                "today also so if when age ages old times as than older younger be would sum total their both each after before "
                "from hence later next last time his its our your of to by for with at on together combined but while whereas "
                "where find present current difference number same twice half double triple thrice many much more less born we "
                "us are were am has had have been being does do did can could should shall may might must not only just exactly "
                "about around nearly almost 's s d ll").split())
PARENTS = {"dad", "father", "mother", "mom", "mum", "mommy", "mummy", "daddy", "papa", "mama", "grandfather", "grandmother",
           "grandpa", "grandma", "granddad", "grandad", "granny", "nana", "uncle", "aunt", "teacher", "boss", "parent",
           "stepdad", "stepmom", "stepfather", "stepmother"}
TP = (r"in (\d+(?:\.\d+)?) years?(?: time)?|(\d+(?:\.\d+)?) years? (?:from now|hence|later|on|in the future|time)|after (\d+(?:\.\d+)?) years?|"
      r"(\d+(?:\.\d+)?) years? (?:ago|back|before|earlier|previously)|(next year)|(last year)|(a year ago)|(in a year)")


def _tp_value(m) -> sp.Rational:
    g = m.groups()
    if g[0] or g[1] or g[2]:
        return q(g[0] or g[1] or g[2])
    if g[3]:
        return -q(g[3])
    if g[4] or g[7]:
        return R(1)
    return R(-1)


def _age_norm(t: str) -> str:
    s = " " + t + " "
    s = re.sub(r"\by/?o\b|\by\.o\.", "years old", s)
    s = re.sub(r"\byrs?\b", lambda m: "years" if m.group(0) == "yrs" else "year", s)
    s = re.sub(r"\b(?:i'm|im|i am)\b", "me is", s)
    s = re.sub(r"\bam i\b", "is me", s)
    s = re.sub(r"\bi'll\b", "me will", s)
    s = re.sub(r"\bi'd\b", "me would", s)
    s = re.sub(r"\bi\b", "me", s)
    s = re.sub(r"\b(he|she|it|who|what|that|there)'s\b", r"\1 is", s)
    s = re.sub(r"\bthey're\b", "they are", s)
    s = re.sub(r"\bwe're\b", "we are", s)
    s = re.sub(r"\b(?:my age|mine|myself)\b", "me", s)
    s = re.sub(rf"\b(?:his|her|their|our|your|my|the|a|an)\s+(?=(?:{_RELALT})s?\b)", "", s)
    s = re.sub(r"\bhis age\b", "he", s)
    s = re.sub(r"\bher age\b", "she", s)
    s = re.sub(r"\bthe age of (?:the |his |her |my |your )?([a-z]+)\b", r"\1", s)
    s = re.sub(r"\b([a-z]+)'s? age\b", r"\1", s)
    s = re.sub(r"\b([a-z]+)'s\b", r"\1", s)
    s = re.sub(r"\bmy\b|\byour\b", "", s)
    s = re.sub(r"\bhalf (?:of )?", "0.5 times ", s)
    s = re.sub(r"\b(?:a|one) third (?:of )?", "1/3 times ", s)
    s = re.sub(r"\b(?:a|one) quarter (?:of )?", "0.25 times ", s)
    s = re.sub(r"\bdouble (?:of )?", "2 times ", s)
    s = re.sub(r"\btriple (?:of )?", "3 times ", s)
    s = re.sub(r"\bquadruple (?:of )?", "4 times ", s)
    s = re.sub(r"\btimes older than\b", "times as old as", s)
    s = re.sub(r"\btimes as old as\b", "times as old as", s)
    s = re.sub(r"\byears senior to\b", "years older than", s)
    s = re.sub(r"\byears junior to\b", "years younger than", s)
    s = re.sub(r"\b(?:right now|currently|presently|at present|today|this year|at the moment)\b", "", s)
    s = re.sub(r"(?<!from )\bnow\b", "", s)
    s = re.sub(r"\b(?:rn|atm)\b", "", s)
    s = re.sub(r"\b(?:exactly|precisely|just) (?=\d|twice|thrice|double|triple|half)", "", s)
    s = re.sub(r"\b(he|she|they|me|[a-z]+) (?:will be|would be|was|is) then\b", r"\1", s)
    s = re.sub(r"\b(?:the|a|an)\b", "", s)
    s = re.sub(rf"\b([a-z]+),? ({TP}),? (will|would|was|is)\b", r"\2 \1 \14", s) if False else s
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r" ,", ",", s)
    return s


def ages(t: str, text: str) -> Solution | None:
    if not re.search(r"\b(?:old|older|younger|age|ages|aged|years? ago|in \d+ years?|years? from now|birthday)\b", t):
        return None
    s = _age_norm(t)
    P = r"([a-z]+)"
    V = r"(?:is|was|will be|would be|will become|becomes|became|be|are|were|has been|had been|shall be)"
    NUMF = r"(\d+(?:\.\d+)?(?:/\d+)?)(?![\d/]|\.\d)"
    pats = [
        ("times", rf"{P} {V} {NUMF} times(?: as old as| as old| older than| of| the age of| that of)?(?: {P})?"),
        ("older", rf"{P} {V} {NUMF} years? (older|younger) than {P}"),
        ("older2", rf"{P} {V} (older|younger) than {P} by {NUMF} years?"),
        ("older3", rf"{P} {V} {NUMF} years? (older|younger)\b(?! than)"),
        ("sum", rf"(?:sum|total) of (?:their |our |both |two |all )?(?:present |current )?ages(?: of {P} and {P})?(?: {V}| equals?| =| adds? up to| comes? to)? ?{NUMF}"),
        ("sum", rf"(?:their|our|both|combined|total) (?:present |current )?(?:combined |total )?ages? (?:add up to|adds up to|sum to|sums to|total|totals|come to|comes to|make|equal|equals|is|are|=|will be|was|were) {NUMF}"),
        ("sum", rf"{P} and {P}(?: together)? {V} {NUMF}(?: years old)? (?:together|combined|in total|altogether|between them)"),
        ("sum", rf"(?:together|combined|between them),? (?:they|{P} and {P}) {V} {NUMF}"),
        ("sum", rf"{P} and {P} (?:combined |total )?ages? (?:add up to|sum to|total|is|are|=|come to|make|equals?) {NUMF}"),
        ("sum", rf"ages of {P} and {P} (?:add up to|sum to|total|is|are|=|come to|make|equals?) {NUMF}"),
        ("sum", rf"(?:sum|total) of {P} and {P}(?:'s?)? (?:present |current )?ages? (?:is|are|=|equals?|adds? up to|comes? to) {NUMF}"),
        ("sum", rf"combined age (?:of {P} and {P} )?{V} {NUMF}"),
        ("diff", rf"difference (?:between|of|in) (?:their |our |two |both )?ages(?: of {P} and {P})?(?: {V}| =| equals?)? ?{NUMF}"),
        ("diff", rf"(?:their|our) ages differ by {NUMF}"),
        ("diff", rf"{P} and {P} differ (?:in age )?by {NUMF}"),
        ("diff", rf"(?<!ages )difference (?:between them )?(?:is|was|=) {NUMF}"),
        ("age", rf"{P} (?:{V}|turns|turned|will turn|is aged|was aged) {NUMF}(?: years?(?: old)?)?(?! times| years? (?:older|younger)| ?%)"),
    ]
    found = []
    for kind, pat in pats:
        for m in re.finditer(pat, s):
            found.append((m.start(), -(m.end() - m.start()), kind, m))
    found.sort(key=lambda f: (f[0], f[1]))
    chosen, used = [], []
    for st, neg, kind, m in found:
        if any(st < e and m.end() > b for b, e in used):
            continue
        used.append(m.span())
        chosen.append((kind, m))
    chosen.sort(key=lambda c: c[1].start())
    if not chosen:
        return None
    unknown_time = re.search(r"\bin how many years\b|\bhow many years (?:from now|will it (?:take|be)|until|before|later|hence|ago)\b|\bhow long (?:until|before|will it be)\b|\bwhen will\b|\bhow many years ago\b", s)
    X = sp.Symbol("x")
    tsign = -1 if unknown_time and re.search(r"how many years ago", s) else 1
    persons: list[str] = []
    syms: dict[str, sp.Symbol] = {}
    state = {"subj": None}

    def person(name, subject=False, other=None):
        if name is None:
            return None
        if name in ("he", "she", "him", "her", "his"):
            cand = state["subj"] if state["subj"] and state["subj"] != other else next((p for p in reversed(persons) if p not in (other, "me")), None)
            return cand
        if name in AGE_STOP or not re.fullmatch(r"[a-z]+", name):
            return None
        if name not in syms:
            syms[name] = sp.Symbol("you" if name == "me" else name)
            persons.append(name)
        if subject and name != "me":
            state["subj"] = name
        return name

    eqs, lines = [], []
    consumed = []
    prev_end = 0
    diff_facts = []
    for kind, m in chosen:
        region = s[prev_end:m.end()]
        shift = R(0)
        tps = [x for x in re.finditer(TP, region) if not any(b <= prev_end + x.start() < e for b, e in consumed)]
        trail = re.match(rf"\s*,?\s*({TP})(?=\s*(?:[.,;?!]|$|and\b|but\b))", s[m.end():])
        has_shift = False
        if tps:
            shift = _tp_value(tps[-1])
            has_shift = True
            consumed.append((prev_end + tps[-1].start(), prev_end + tps[-1].end()))
        elif trail:
            tm2 = re.search(TP, trail.group(0))
            shift = _tp_value(tm2)
            has_shift = True
            consumed.append((m.end() + trail.start(1), m.end() + trail.end(1)))
        sh = shift
        if not has_shift and unknown_time and m.start() > unknown_time.start() - 5 and kind in ("times", "older", "sum"):
            sh = tsign * X
        elif not has_shift and unknown_time and re.search(r"\bwill be\b", m.group(0)) and kind in ("times", "sum"):
            sh = tsign * X
        g = m.groups()
        prev_end = m.end()
        try:
            if kind == "times":
                a = person(g[0], True)
                b = person(g[2], other=a) if g[2] else None
                if a is None:
                    continue
                if b is None:
                    others = [p for p in persons if p != a]
                    if len(others) != 1:
                        continue
                    b = others[0]
                k = q(g[1])
                eq = sp.Eq(syms[a] + sh, k * (syms[b] + sh))
            elif kind in ("older", "older2", "older3"):
                if kind == "older":
                    a, n, rel, b = person(g[0], True), q(g[1]), g[2], g[3]
                elif kind == "older2":
                    a, rel, b, n = person(g[0], True), g[1], g[2], q(g[3])
                else:
                    a, n, rel, b = person(g[0], True), q(g[1]), g[2], None
                if a is None:
                    continue
                b = person(b, other=a) if b else None
                if b is None:
                    others = [p for p in persons if p != a]
                    if len(others) != 1:
                        continue
                    b = others[0]
                eq = sp.Eq(syms[a], syms[b] + (n if rel == "older" else -n))
            elif kind == "sum":
                names = [x for x in g[:-1] if x]
                ps = [person(x) for x in names] if names else list(persons)
                ps = [p for p in ps if p]
                if len(ps) < 2:
                    continue
                eq = sp.Eq(sum(syms[p] + sh for p in ps), q(g[-1]))
            elif kind == "diff":
                names = [x for x in g[:-1] if x]
                ps = [person(x) for x in names] if names else list(persons)
                ps = [p for p in ps if p]
                diff_facts.append((ps, q(g[-1]), m.group(0)))
                continue
            else:  # age
                a = person(g[0], True)
                if a is None:
                    continue
                eq = sp.Eq(syms[a] + sh, q(g[1]))
        except (KeyError, ValueError, TypeError):
            continue
        if eq is sp.true or eq is sp.false:
            continue
        eqs.append(eq)
        lines.append(f"'{m.group(0).strip()}'" + (f" ({'in' if sh > 0 else ''} {ex(abs(sh))} year{'s' if abs(sh) != 1 else ''}{' ago' if sh < 0 else ''})" if sh.is_number and sh != 0 else "")
                     + f" → {efmt(eq.lhs)} = {efmt(eq.rhs)}")
    for ps, d, raw in diff_facts:
        if len(ps) < 2:
            ps = list(persons)
        if len(ps) != 2:
            continue
        older = None
        om = re.search(r"\b([a-z]+) is (?:the )?older\b(?! than)", s)
        if om and om.group(1) in ps:
            older = om.group(1)
        elif any(p in PARENTS for p in ps) and not all(p in PARENTS for p in ps):
            older = next(p for p in ps if p in PARENTS)
        assumed = older is None
        older = older or ps[0]
        younger = ps[1] if older == ps[0] else ps[0]
        eq = sp.Eq(syms[older] - syms[younger], d)
        eqs.append(eq)
        lines.append(f"'{raw.strip()}' → {efmt(eq.lhs)} = {efmt(eq.rhs)}" + (f" (taking {_who(older)} as the older)" if assumed else ""))
    unknowns = [syms[p] for p in persons] + ([X] if any(e.has(X) for e in eqs) else [])
    if not persons or not eqs:
        return None
    if len(persons) == 1 and not any(e.has(X) for e in eqs):
        return None
    if len(eqs) < len(unknowns):
        return None
    sol = _unique(eqs, unknowns)
    steps = ["rule: one unknown per person (their age now); each statement becomes an equation, shifting every age by the same number of years for 'in N years' / 'N years ago'"]
    steps += [f"known: {x}" for x in lines]
    if not sol:
        return _sol(text, "those statements contradict each other (or don't pin the ages down)", steps)
    vals = {p: sol[syms[p]] for p in persons}
    steps.append("substitute: solve together → " + ", ".join(f"{_who(p)} = {nice(v)}" for p, v in vals.items())
                 + (f", x = {nice(sol[X])}" if X in sol else ""))
    if any(v < 0 for v in vals.values()) or (X in sol and sol[X] < 0):
        return _sol(text, "no valid ages: the solution would be negative", steps)
    chk = []
    for e in eqs:
        lv, rv = e.lhs.subs(sol), e.rhs.subs(sol)
        chk.append(f"{nice(lv)} = {nice(rv)} {'✓' if sp.simplify(lv - rv) == 0 else '✗'}")
    if X in sol:
        yrs = sol[X]
        ans = f"{nice(yrs)} years" + (" ago" if tsign < 0 else "")
        steps.append(f"result: {ans}")
        return _sol(text, ans, steps, "; ".join(chk))
    qm = re.search(r"how old (?:is|was|will|are|am|would|were|'s) ([a-z]+)(?: be)?(?: (?:in (\d+(?:\.\d+)?) years?|(\d+(?:\.\d+)?) years? (?:from now|hence|later)|(\d+(?:\.\d+)?) years? ago))?", s) \
        or re.search(r"what (?:is|was|will be) ([a-z]+)(?: age)?\b(?: (?:in (\d+(?:\.\d+)?) years?|(\d+(?:\.\d+)?) years? (?:from now|hence)|(\d+(?:\.\d+)?) years? ago))?", s) \
        or re.search(r"(?:find|what are|calculate|work out|determine) ([a-z]+)\b(?: age)?(?: (?:in (\d+(?:\.\d+)?) years?|(\d+(?:\.\d+)?) years? (?:from now|hence)|(\d+(?:\.\d+)?) years? ago))?", s)
    who = None
    off = R(0)
    if qm:
        nm = qm.group(1)
        if nm in ("he", "she"):
            others = [p for p in persons if p != "me"]
            nm = state["subj"] or (others[0] if len(others) == 1 else None)
        if nm in vals:
            who = nm
            off = q(qm.group(2) or qm.group(3)) if (qm.group(2) or qm.group(3)) else (-q(qm.group(4)) if qm.group(4) else R(0))
    if who:
        v = vals[who] + off
        when = "" if off == 0 else (f" in {ex(off)} years" if off > 0 else f" {ex(-off)} years ago")
        ans = f"{nice(v)} years old"
        rest = [f"{_who(p)} {nice(x)}" for p, x in vals.items() if p != who]
        if rest:
            ans += f" ({_who(who)}{when}; " + ", ".join(rest) + " now)" if when else f" ({', '.join(rest)})"
        steps.append(f"result: {_who(who)} {'is' if not when else 'will be' if off > 0 else 'was'} {nice(v)}{when}")
    else:
        ans = ", ".join(f"{_who(p)} {nice(v)}" for p, v in vals.items())
        steps.append(f"result: {ans}")
    return _sol(text, ans, steps, "; ".join(chk))


def _who(p: str) -> str:
    return "you" if p == "me" else p


# ---------------------------------------------------------------- entry point

def anon_ages(t: str, text: str) -> Solution | None:
    """Two unnamed people: the sum and the difference of their ages."""
    if not re.search(r"\bages?\b|\bold(?:er)?\b", t):
        return None
    sm = re.search(r"(?:sum|total) of (?:the |their |two |2 |both )*(?:people'?s? )?ages (?:is|are|=|equals|adds? up to|comes? to) (\d+(?:\.\d+)?)", t)
    dm = re.search(r"difference (?:between (?:them|their ages|the ages) |of (?:their |the )?ages |in (?:their |the )?ages )?(?:is|=|equals) (\d+(?:\.\d+)?)", t)
    if not sm or not dm:
        return None
    S, D = q(sm.group(1)), q(dm.group(1))
    if D > S:
        return None
    old, young = (S + D) / 2, (S - D) / 2
    steps = ["rule: older = (sum + difference) / 2, younger = (sum − difference) / 2",
             f"known: sum = {ex(S)}, difference = {ex(D)}",
             f"substitute: older = ({ex(S)} + {ex(D)}) / 2, younger = ({ex(S)} − {ex(D)}) / 2",
             f"result: {nice(old)} and {nice(young)}"]
    if re.search(r"\byounger\b", t) and not re.search(r"\bolder\b", t):
        ans = f"{nice(young)} years old (the older is {nice(old)})"
    elif re.search(r"\bolder\b", t) and not re.search(r"\byounger\b", t):
        ans = f"{nice(old)} years old (the younger is {nice(young)})"
    else:
        ans = f"{nice(old)} and {nice(young)} years old"
    return _sol(text, ans, steps, f"{nice(old)} + {nice(young)} = {ex(S)}, {nice(old)} − {nice(young)} = {ex(D)} ✓")


HANDLERS = (clock, pairs, digit_count, doubling, consecutive, two_digit, coins, tickets, mixture, weighted, boats,
            train_pass, trains, work, ages, anon_ages)
DEFINITION = re.compile(r"^\s*(?:what|who|whats|what's|define|explain|meaning of)\b(?:\s+(?:is|are|was|were|does|do)\b)?[^\d]*$")


def solve(text: str) -> Solution | None:
    """A classic word problem or puzzle, solved with steps; None when the message isn't one."""
    if not text or len(text) > 600:
        return None
    t = prep(text)
    if not re.search(r"\d", t) and not POLY_RE.search(t):
        return None
    if DEFINITION.match(t) and not re.search(r"\d", t) and not re.search(r"\bdiagonals?\b", t):
        return None
    low = text.lower()
    sm = re.search(r"(\d+)\s*(?:sig(?:nificant)?\.?\s*(?:figs?|figures?|digits?)|s\.?f\.?(?=\W|$))", low)
    tok_sig = _SIG.set(min(max(int(sm.group(1)), 1), 12) if sm else 4)
    tok_frac = _FRAC.set(bool(re.search(r"\bfractions?\b|\bexact\b", low)))
    try:
        for handler in HANDLERS:
            sol = handler(t, text)
            if sol is not None:
                return sol
    finally:
        _SIG.reset(tok_sig)
        _FRAC.reset(tok_frac)
    return None
