"""Electrical calculations in plain English, solved exactly with worked steps.

"how many amps does a 2300 W kettle draw on 230 V?" → reads every quantity with its unit and SI prefix (mA, µA,
kΩ, kilohm, MΩ, mV, kV, kWh, mAh …), what is asked, and the setting (series / parallel / '100 Ω || 200 Ω' networks,
a voltage divider, a battery, hours a day for so many days, a price per kWh), then works it out in exact rationals
(sympy) with the formula, the knowns, the substitution, the result and a check. Handles Ohm's law, power
(P = VI = I²R = V²/R), equivalent resistance, energy E = P·t, electricity cost, battery capacity and runtime,
charge Q = I·t and voltage dividers. Anything else (Kepler commands, definitions, small talk) gives None.
"""
import math
import re
from decimal import ROUND_HALF_UP, Decimal, localcontext

import sympy as sp

from ..reasoning import Solution

R = sp.Rational
E_CHARGE = R("1.602176634e-19")
NUM = r"\d+(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+"

# ---------------------------------------------------------------- units

# dimensions: V voltage, I current, R resistance, P power, E energy (J), Q charge (C), CAP capacity (C), T time (s)
UNITS: dict[str, tuple[str, sp.Rational, bool]] = {}  # normalised spelling → (dim, factor to SI, 'M' may mean mega)
_SYM_PREFIX = {"": R(1), "p": R(1, 10**12), "n": R(1, 10**9), "µ": R(1, 10**6), "μ": R(1, 10**6), "u": R(1, 10**6),
               "m": R(1, 1000), "k": R(1000), "g": R(10**9)}
_SYM_BASE = {"v": ("V", 1), "a": ("I", 1), "ω": ("R", 1), "ohm": ("R", 1), "ohms": ("R", 1), "w": ("P", 1),
             "wh": ("E", 3600), "ah": ("CAP", 3600), "j": ("E", 1), "c": ("Q", 1)}
for _p, _pf in _SYM_PREFIX.items():
    for _b, (_d, _f) in _SYM_BASE.items():
        if (_p in "pg" and _p and _b in ("a", "ah", "c")) or (_p == "g" and _b in ("ω", "ohm", "ohms")):
            continue
        UNITS[_p + _b] = (_d, _pf * _f, _p == "m")
_WORD_PREFIX = {"": R(1), "milli": R(1, 1000), "micro": R(1, 10**6), "nano": R(1, 10**9), "kilo": R(1000),
                "mega": R(10**6)}
_WORD_BASE = {"volt": ("V", 1), "amp": ("I", 1), "ampere": ("I", 1), "ohm": ("R", 1), "watt": ("P", 1),
              "joule": ("E", 1), "coulomb": ("Q", 1), "watt hour": ("E", 3600), "amp hour": ("CAP", 3600),
              "ampere hour": ("CAP", 3600)}
for _p, _pf in _WORD_PREFIX.items():
    for _b, (_d, _f) in _WORD_BASE.items():
        for _s in ("", "s"):
            UNITS[_p + _b + _s] = (_d, _pf * _f, False)
            if _p:
                UNITS[_p + " " + _b + _s] = (_d, _pf * _f, False)
for _s in ("kilohm", "kilohms", "k ohm", "k ohms", "k ω"):
    UNITS[_s] = ("R", R(1000), False)
for _s in ("megohm", "megohms", "meg ohm", "meg ohms", "meg"):
    UNITS[_s] = ("R", R(10**6), False)
UNITS["k"] = ("R", R(1000), False)  # "4.7k resistor", only in a resistor context
UNITS["kilowatt hour"] = UNITS["kilowatt hours"] = ("E", R(3_600_000), False)
_TIME = {("s", "sec", "secs", "second", "seconds"): 1, ("ms", "millisecond", "milliseconds"): R(1, 1000),
         ("min", "mins", "minute", "minutes"): 60, ("h", "hr", "hrs", "hour", "hours"): 3600,
         ("day", "days"): 86400, ("week", "weeks"): 7 * 86400, ("month", "months"): 30 * 86400,
         ("year", "years"): 365 * 86400}
for _ks, _f in _TIME.items():
    for _k in _ks:
        UNITS[_k] = ("T", R(_f), False)


def _norm(s: str) -> str:
    return re.sub(r"[\s\-]+", " ", s.lower()).strip()


_ALTS = "|".join(re.escape(k).replace(r"\ ", r"[\s\-]?") for k in sorted(UNITS, key=len, reverse=True))
QTY = re.compile(rf"(?<![\w.])({NUM})\s*-?\s*({_ALTS})(?![a-zA-ZµμωωΩ])", re.I)
SIGFIG = re.compile(r"\b(?:to\s+|in\s+|at\s+)?(\d+)\s*(sig(?:nificant)?\.?\s*fig(?:ure)?s?|s\.\s?f\.?|sf\b|"
                    r"d\.p\.?|dp\b|decimal places?)", re.I)
WORDNUM = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
           "a pair of": 2}


class Qty:
    def __init__(self, dim: str, val, start: int, end: int, raw: str):
        self.dim, self.val, self.start, self.end, self.raw = dim, val, start, end, raw


def _r(s: str):
    return R(s.replace(",", ""))


def _parse(text: str):
    """(cleaned text, quantities, sig figs, decimal places)."""
    sf, dp = 4, None
    m = SIGFIG.search(text)
    if m:
        n = int(m.group(1))
        if "d" in m.group(2).lower()[:2] and "sig" not in m.group(2).lower():
            dp = min(n, 10)
        else:
            sf = max(1, min(n, 12))
        text = text[:m.start()] + " " * (m.end() - m.start()) + text[m.end():]
    clean = text.replace("Ω", "Ω").replace("μ", "µ")
    resist_ctx = bool(re.search(r"resist|ohm|Ω|divider|\|\||parallel|series", clean, re.I))
    qs: list[Qty] = []
    for m in QTY.finditer(clean):
        raw = m.group(2)
        low = _norm(raw)
        if low not in UNITS:
            continue
        dim, fac, msym = UNITS[low]
        after = clean[m.end():]
        if low == "a" and raw != "A" and not re.match(r"\s*(?:$|[,.;:!?)])", after):
            continue
        if low == "c" and raw != "C":
            continue
        if low == "k" and not resist_ctx:
            continue
        if low in ("h", "s") and re.match(r"\s*'", after):
            continue
        if msym and raw[0] == "M" and low not in ("ma", "mah"):
            fac = fac * 10**9  # MΩ, MW, MV: mega, not milli
        qs.append(Qty(dim, _r(m.group(1)) * fac, m.start(), m.end(), m.group(0)))
    # labelled resistors without a unit: "R1 = 10, R2 = 20"
    taken = {q.start for q in qs}
    for m in re.finditer(rf"\bR_?\d*\s*(?:=|is|:)\s*({NUM})\s*([kKM])?(?![\w.])", clean):
        if m.start(1) in taken:
            continue
        fac = {"k": 1000, "K": 1000, "M": 10**6, None: 1}[m.group(2)]
        qs.append(Qty("R", _r(m.group(1)) * fac, m.start(1), m.end(), m.group(0)))
    # "2, 3 and 6 ohms", "100 || 200 Ω": the unit carries back over the list
    extra = []
    for q in qs:
        if q.dim != "R":
            continue
        fac = q.val / _r(re.match(NUM, q.raw).group(0)) if re.match(NUM, q.raw) else R(1)
        before = clean[:q.start]
        while True:
            m = re.search(rf"(?<![\w.])({NUM})\s*([kK]?)\s*(?:,\s*(?:and\s+)?|\s+and\s+|\s*&\s*|\s*\|\|\s*|\s*//\s*|"
                          rf"\s*\+\s*)$", before)
            if not m or any(x.start == m.start(1) for x in qs + extra):
                break
            f = R(1000) if m.group(2) else fac
            extra.append(Qty("R", _r(m.group(1)) * f, m.start(1), m.end(1), m.group(0)))
            before = before[:m.start()]
    qs += extra
    # counts: "three 6 Ω resistors", "4 x 100 ohm", "five 60 W bulbs"
    out = []
    for q in sorted(qs, key=lambda q: q.start):
        n = 1
        if q.dim in ("R", "P"):
            before = clean[:q.start]
            m = re.search(r"\b(two|three|four|five|six|seven|eight|nine|ten|a pair of|\d+)\s*(x|×|\*)?\s*"
                          r"(?:identical\s+|equal\s+|similar\s+)?$", before, re.I)
            if m and (m.group(2) or re.match(r"\s*(?:resistors?|resistances|bulbs|lamps|lights|led|leds)\b",
                                             clean[q.end:], re.I) or "identical" in m.group(0).lower()):
                w = m.group(1).lower()
                if w in WORDNUM or (m.group(2) and w.isdigit()):
                    n = WORDNUM.get(w) or int(w)
                    if not 1 < n <= 50:
                        n = 1
        if q.dim == "P":
            if n > 1:
                q.raw = f"{n} × {q.raw}"
            q.val = q.val * n
            out.append(q)
        else:
            out += [q] * n
    return clean, out, sf, dp


# ---------------------------------------------------------------- display

PREFIXABLE = {"V", "A", "Ω", "W", "J", "C"}
_DOWN = [(R(1), ""), (R(1, 1000), "m"), (R(1, 10**6), "µ"), (R(1, 10**9), "n"), (R(1, 10**12), "p")]
_UP = [(R(10**9), "G"), (R(10**6), "M"), (R(1000), "k")]


def _dec(x: float, sf: int, dp: int | None) -> str:
    if x == 0:
        return "0"
    if dp is not None:
        s = f"{x:,.{dp}f}"
        return s
    if abs(x) >= 1e15:
        return f"{x:.{sf}g}"
    mag = math.floor(math.log10(abs(x)))
    digits = max(0, sf - 1 - mag)
    y = round(x, digits)
    if y != 0 and math.floor(math.log10(abs(y))) > mag:  # 9.9996 → 10.00
        digits = max(0, digits - 1)
    s = f"{y:,.{digits}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def _pretty(x) -> str:
    s = sp.sstr(x).replace("**", "^").replace("*", "·")
    s = re.sub(r"sqrt\((\d+)\)", r"√\1", s).replace("sqrt", "√")
    return s.replace("·√", "√")


def show(val, unit: str, sf: int = 4, dp: int | None = None, prefix: bool = True) -> str:
    val = sp.nsimplify(val) if not isinstance(val, sp.Basic) else val
    fv = float(val)
    scale, p = R(1), ""
    if prefix and unit in PREFIXABLE and fv != 0:
        a = abs(fv)
        up_at = 1000 if unit in ("Ω", "J") else 10_000
        if a >= up_at:
            for s, ps in _UP:
                if a >= s:
                    scale, p = s, ps
                    break
        elif a < 1:
            for s, ps in _DOWN:
                if a >= float(s) * 0.9999999:
                    scale, p = s, ps
                    break
            else:
                scale, p = _DOWN[-1]
    d = _dec(fv / float(scale), sf, dp)
    approx_txt = f"{d} {p}{unit}".strip()
    try:
        exact = _r(d) * scale == val
    except (ValueError, TypeError, sp.SympifyError):
        exact = False
    if exact:
        return approx_txt
    if val.is_Rational and val.q <= 10000 and abs(val.p) < 10**9:
        return f"{val.p}/{val.q} {unit} ≈ {approx_txt}".replace("  ", " ")
    if val.is_number and not val.is_Rational and len(_pretty(val)) <= 14:
        return f"{_pretty(val)} {unit} ≈ {approx_txt}"
    return f"≈ {approx_txt}"


def short(val, unit: str = "", sf: int = 6) -> str:
    """The decimal value only, for knowns and substitutions."""
    return show(val, unit, sf=sf).split("≈ ")[-1]


def hours_text(sec, sf=4, dp=None) -> str:
    h = sec / 3600
    if h >= 1:
        txt = show(h, "h", sf, dp, prefix=False)
        whole = int(math.floor(float(h)))
        mins = (h - whole) * 60
        if mins != 0:
            mtxt = _dec(float(mins), 3, None)
            txt += f" ({whole} h {mtxt} min)"
        return txt
    if sec >= 60:
        return show(sec / 60, "min", sf, dp, prefix=False)
    return show(sec, "s", sf, dp, prefix=False)


def _money(x, sym: str) -> str:
    with localcontext() as ctx:
        ctx.prec = 40
        d = (Decimal(int(x.p)) / Decimal(int(x.q))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{sym}{d:,.2f}"


def _sol(problem: str, formula: str, knowns: list[str], sub: str, answer: str, check: str = "",
         extra: list[str] | None = None) -> Solution:
    steps = [f"formula: {formula}", "known: " + ", ".join(knowns), f"substitute: {sub}"] + (extra or [])
    steps.append(f"result: {answer}")
    return Solution("electrical", problem, answer, steps, check=check, confidence=0.97)


# ---------------------------------------------------------------- what is asked

_TARGETS = {
    "I": r"\bcurrent\b|\bamps?\b|\bamperage\b|\bamperes?\b|\bdraws?\b|\bdrawn\b|\bmilliamps?\b|\bhow many ma\b",
    "V": r"\bvoltage\b|\bvolts?\b|potential difference|\bp\.?d\.?\b|\bemf\b|\bvoltage drop\b",
    "R": r"\bresistance\b|\bohms?\b|\bwhat resistor\b|\bwhich resistor\b|\bresistor value\b|\bsize of resistor\b|"
         r"\bresistor (?:do|should|would|is needed)|\bequivalent\b|\beffective\b|\bcombined\b|\bkilohms?\b",
    "P": r"\bpower\b|\bwatts?\b|\bwattage\b|\bdissipat\w*|\brating\b|\bkilowatts?\b",
}


def _wants(tq: str) -> list[str]:
    found = []
    for k, pat in _TARGETS.items():
        m = re.search(pat, tq)
        if m:
            found.append((m.start(), k))
    return [k for _, k in sorted(found)]


def _first(qs, dim):
    for q in qs:
        if q.dim == dim:
            return q.val
    return None


def _all(qs, dim):
    return [q.val for q in qs if q.dim == dim]


SYM = {"V": "V", "I": "A", "R": "Ω", "P": "W"}
NAME = {"V": "V", "I": "I", "R": "R", "P": "P"}

# target → (knowns) → (formula, function)
OHM = {
    "I": {("R", "V"): ("I = V / R", lambda k: k["V"] / k["R"], "{V} / {R}"),
          ("P", "V"): ("I = P / V", lambda k: k["P"] / k["V"], "{P} / {V}"),
          ("P", "R"): ("I = √(P / R)", lambda k: sp.sqrt(k["P"] / k["R"]), "√({P} / {R})")},
    "V": {("I", "R"): ("V = I · R", lambda k: k["I"] * k["R"], "{I} × {R}"),
          ("I", "P"): ("V = P / I", lambda k: k["P"] / k["I"], "{P} / {I}"),
          ("P", "R"): ("V = √(P · R)", lambda k: sp.sqrt(k["P"] * k["R"]), "√({P} × {R})")},
    "R": {("I", "V"): ("R = V / I", lambda k: k["V"] / k["I"], "{V} / {I}"),
          ("P", "V"): ("R = V² / P", lambda k: k["V"] ** 2 / k["P"], "{V}² / {P}"),
          ("I", "P"): ("R = P / I²", lambda k: k["P"] / k["I"] ** 2, "{P} / {I}²")},
    "P": {("I", "V"): ("P = V · I", lambda k: k["V"] * k["I"], "{V} × {I}"),
          ("I", "R"): ("P = I² · R", lambda k: k["I"] ** 2 * k["R"], "{I}² × {R}"),
          ("R", "V"): ("P = V² / R", lambda k: k["V"] ** 2 / k["R"], "{V}² / {R}")},
}


def _ohm_value(target: str, known: dict):
    """(formula, value, substitution) for one of V, I, R, P from two others."""
    for keys, (formula, fn, sub) in OHM[target].items():
        if all(known.get(k) is not None for k in keys):
            return formula, sp.nsimplify(fn(known)), sub.format(**{k: short(known[k]) for k in keys})
    return None


def _check(known: dict, sf) -> str:
    v, i, r, p = (known.get(k) for k in "VIRP")
    if v is not None and i is not None and r is not None:
        ok = sp.simplify(v - i * r) == 0
        return f"V = I·R = {short(i)} × {short(r)} = {short(i * r)} V {'✓' if ok else '✗'}"
    if v is not None and i is not None and p is not None:
        ok = sp.simplify(p - v * i) == 0
        return f"P = V·I = {short(v)} × {short(i)} = {short(v * i)} W {'✓' if ok else '✗'}"
    return ""


# ---------------------------------------------------------------- networks

def _parallel(vals):
    return 1 / sum(1 / v for v in vals)


def _expr_network(clean: str, rqs: list[Qty]):
    """'100 Ω || 200 Ω + 50 Ω' with || binding tighter than +, and brackets."""
    toks = []
    for q in rqs:
        toks.append((q.start, q.end, ("R", q.val)))
    lo, hi = min(q.start for q in rqs), max(q.end for q in rqs)
    lo = clean.rfind("(", 0, lo) if clean.rfind("(", 0, lo) != -1 and "(" in clean[:lo] else lo
    for m in re.finditer(r"\|\||//|\+|\(|\)|\bseries with\b|\bparallel with\b", clean):
        if m.start() < lo or m.start() > hi + 3:
            continue
        if any(s <= m.start() < e for s, e, _ in toks):
            continue
        op = {"//": "||", "series with": "+", "parallel with": "||"}.get(m.group(0), m.group(0))
        toks.append((m.start(), m.end(), op))
    toks = [t[2] for t in sorted(toks, key=lambda t: t[0])]
    pos = 0

    def atom():
        nonlocal pos
        if pos < len(toks) and toks[pos] == "(":
            pos += 1
            v = series()
            if pos < len(toks) and toks[pos] == ")":
                pos += 1
            return v
        t = toks[pos]
        if not isinstance(t, tuple):
            raise ValueError("bad network")
        pos += 1
        return t[1]

    def par():
        nonlocal pos
        vals = [atom()]
        while pos < len(toks) and toks[pos] == "||":
            pos += 1
            vals.append(atom())
        return _parallel(vals) if len(vals) > 1 else vals[0]

    def series():
        nonlocal pos
        total = par()
        while pos < len(toks) and toks[pos] == "+":
            pos += 1
            total += par()
        return total

    val = series()
    if pos != len(toks):
        raise ValueError("bad network")
    return sp.nsimplify(val)


def _network(clean: str, t: str, rqs: list[Qty]):
    """(equivalent resistance, description, mode) for two or more resistors, or None."""
    vals = [q.val for q in rqs]
    if "||" in clean or "//" in clean:
        req = _expr_network(clean, rqs)
        return req, "R_eq from the network (‖ first, then series sums)", "expr"
    ps = [m.start() for m in re.finditer(r"\bparallel\b", t)]
    ss = [m.start() for m in re.finditer(r"\bseries\b", t)]
    if ps and not ss:
        return _parallel(vals), "1/R_eq = " + " + ".join(f"1/{short(v)}" for v in vals), "parallel"
    if ss and not ps:
        return sum(vals), "R_eq = " + " + ".join(short(v) for v in vals), "series"
    if not ps and not ss:
        return None
    k1, p1, k2, p2 = ("parallel", ps[0], "series", ss[0]) if ps[0] < ss[0] else ("series", ss[0], "parallel", ps[0])
    before = [q.val for q in rqs if q.start < p1]
    after = [q.val for q in rqs if q.start >= p1]

    def comb(mode, xs):
        return _parallel(xs) if mode == "parallel" else sum(xs)

    sym = {"parallel": " ‖ ", "series": " + "}
    if len(before) >= 2 and after:  # "A and B in parallel, in series with C"
        g = comb(k1, before)
        req = comb(k2, [g] + after)
        desc = f"({sym[k1].join(short(v) for v in before)}){sym[k2]}{sym[k2].join(short(v) for v in after)}"
    elif len(before) == 1 and len(after) >= 2:  # "A in series with a parallel pair B and C"
        g = comb(k2, after)
        req = comb(k1, before + [g])
        desc = f"{short(before[0])}{sym[k1]}({sym[k2].join(short(v) for v in after)})"
    else:
        return None
    return sp.nsimplify(req), f"R_eq = {desc}", "mixed"


# ---------------------------------------------------------------- solvers

def _price(t: str):
    m = re.search(rf"([$£€])?\s*({NUM})\s*(cents?|¢|c|p|pence)?\s*(?:per|/|a|an|for each|each|for every|for 1)\s*"
                  r"(?:kwh|kilowatt[\s\-]?hours?|unit)\b", t)
    if not m:
        m2 = re.search(rf"(?:kwh|unit)\s*(?:costs?|is|at|price is|priced at|=)\s*([$£€])?\s*({NUM})\s*(cents?|¢|c|p|pence)?",
                       t)
        if not m2:
            return None
        m = m2
    val = _r(m.group(2))
    unit = m.group(3)
    sym = m.group(1) or ""
    if unit:
        val = val / 100
        sym = sym or ("£" if unit in ("p", "pence") else "$")
    return val, sym, m.group(0).strip()


def _daily(clean: str, t: str, qs: list[Qty]):
    """Total time for 'N hours a day for D days', else the first time; with a description."""
    tq = [q for q in qs if q.dim == "T"]
    daily = None
    for q in tq:
        if re.match(r"\s*(?:a|per|each|every|/)\s*day\b|\s*daily\b", clean[q.end:], re.I):
            daily = q
            break
    if daily is None:
        if not tq:
            m = re.search(r"\b(?:for|in|over|of)\s+(an?|one|half an?)\s+(hour|minute|second|day)\b", t)
            if not m:
                return None
            f = {"hour": 3600, "minute": 60, "second": 1, "day": 86400}[m.group(2)]
            return R(f, 2 if "half" in m.group(1) else 1), m.group(0).split(" ", 1)[1]
        return tq[0].val, tq[0].raw
    days = None
    for q in tq:
        if q is not daily and q.val >= 86400:
            days = q.val / 86400
            break
    if days is None:
        m = re.search(r"\b(?:a|per|one|1|in a|for a|each|every|over a)\s+(week|month|year)\b", t)
        if m:
            days = {"week": 7, "month": 30, "year": 365}[m.group(1)]
    if days is None:
        return daily.val, daily.raw + " (one day)"
    return daily.val * days, f"{daily.raw} a day × {days} days"


def _power_from(known: dict):
    if known.get("P") is not None:
        return known["P"], None
    r = _ohm_value("P", known)
    if r:
        return r[1], f"P = {r[0].split('= ')[1]} = {r[2]} = {short(r[1], 'W')}"
    return None, None


def _energy(text, clean, t, tq, qs, known, sf, dp):
    price = _price(t)
    wants_e = re.search(r"\benergy\b|\bkwh\b|\bkilowatt.?hours?\b|\bjoules?\b|\bwh\b|\bwatt.?hours?\b|electricity|"
                        r"\bunits\b|\bconsum\w*|\buses?\b|\bused\b|\bcost\w*\b|\bbill\b|\bpay\b|\bspend\b|\bprice\b", tq)
    e_given = _first(qs, "E")
    if price and e_given is not None and not known.get("P") and re.search(r"\bcost|\bbill|\bpay|\bspend|\bprice", tq):
        kwh = e_given / 3_600_000
        cost = kwh * price[0]
        ans = _money(cost, price[1])
        return _sol(text, "cost = E (kWh) × price", [f"E = {short(kwh, 'kWh')}", f"price = {price[2]}"],
                    f"cost = {short(kwh)} × {short(price[0])}", ans, f"{ans} ÷ {short(price[0])} = {short(kwh)} kWh ✓")
    if not wants_e and not price:
        return None
    p, pstep = _power_from(known)
    tt = _daily(clean, t, qs)
    if e_given is not None and p is not None and tt is None and re.search(r"\bhow long\b|\bhow many (?:hours|minutes)", tq):
        sec = e_given / p
        ans = hours_text(sec, sf, dp)
        return _sol(text, "t = E / P", [f"E = {short(e_given, 'J')}", f"P = {short(p, 'W')}"],
                    f"t = {short(e_given)} J / {short(p)} W = {short(sec)} s", ans, f"P·t = {short(p * sec, 'J')} ✓")
    if p is None or tt is None:
        return None
    sec, tdesc = tt
    e = p * sec
    kwh = e / 3_600_000
    knowns = [f"P = {short(p, 'W')}", f"t = {tdesc} = {hours_text(sec)}"]
    extra = [pstep] if pstep else []
    sub = f"E = {short(p)} W × {short(sec / 3600)} h = {short(e / 3600)} Wh = {short(kwh)} kWh = {short(e)} J"
    if price and re.search(r"\bcost|\bbill|\bpay|\bspend|\bprice|how much", tq):
        cost = kwh * price[0]
        ans = _money(cost, price[1])
        extra.append(f"cost = {short(kwh)} kWh × {short(price[0])} per kWh = {_money(cost, price[1])}")
        return _sol(text, "E = P · t, cost = E (kWh) × price", knowns + [f"price = {price[2]}"], sub, ans,
                    f"{ans} ÷ {short(price[0])} per kWh = {short(cost / price[0])} kWh ✓", extra)
    if not wants_e:
        return None
    if re.search(r"\bjoules?\b|\bin j\b|\bmj\b|\bkj\b", tq):
        ans = show(e, "J", sf, dp)
    elif re.search(r"\bkwh\b|\bkilowatt|\bunits\b", tq):
        ans = show(kwh, "kWh", sf, dp, prefix=False)
    elif re.search(r"\bwh\b|\bwatt.?hours?\b", tq):
        ans = show(e / 3600, "Wh", sf, dp, prefix=False)
    elif sec < 3600 and p < 1000:
        ans = show(e, "J", sf, dp)
    else:
        ans = show(kwh, "kWh", sf, dp, prefix=False)
    return _sol(text, "E = P · t", knowns, sub, ans, f"E / t = {short(e / sec, 'W')} = P ✓", extra)


def _battery(text, clean, t, tq, qs, known, sf, dp):
    cap = _first(qs, "CAP")
    batt = re.search(r"batter|\bcell\b|power ?bank|\bcapacity\b|\bmah\b|\bups\b", t)
    if not batt:
        return None
    v, i = known.get("V"), known.get("I")
    e_cap = _first(qs, "E")
    asks_time = re.search(r"\bhow long\b|\bruntime\b|\brun time\b|\blast\b|\bhow many (?:hours|minutes)\b|\bduration\b|"
                          r"\bfully (?:dis)?charge\b|\btime\b", tq)
    if cap is not None and asks_time:
        if i is None:
            p, _ = _power_from(known)
            if p is not None and v is not None:
                i = p / v
            else:
                return None
        sec = cap / i
        ans = hours_text(sec, sf, dp)
        return _sol(text, "t = capacity / I", [f"capacity = {short(cap / 3600, 'Ah')}", f"I = {short(i, 'A')}"],
                    f"t = {short(cap / 3600)} Ah / {short(i)} A = {short(sec / 3600)} h", ans,
                    f"I·t = {short(i)} A × {short(sec / 3600)} h = {short(i * sec / 3600, 'Ah')} ✓")
    if e_cap is not None and asks_time and cap is None:
        p, _ = _power_from(known)
        if p is None:
            return None
        sec = e_cap / p
        ans = hours_text(sec, sf, dp)
        return _sol(text, "t = E / P", [f"E = {short(e_cap / 3600, 'Wh')}", f"P = {short(p, 'W')}"],
                    f"t = {short(e_cap / 3600)} Wh / {short(p)} W = {short(sec / 3600)} h", ans,
                    f"P·t = {short(p * sec / 3600, 'Wh')} ✓")
    if cap is not None and v is not None and re.search(r"\bwh\b|\bwatt.?hours?\b|\benergy\b|\bjoules?\b", tq):
        e = cap * v
        ans = show(e, "J", sf, dp) if re.search(r"\bjoules?\b", tq) else show(e / 3600, "Wh", sf, dp, prefix=False)
        return _sol(text, "E = capacity × V", [f"capacity = {short(cap / 3600, 'Ah')}", f"V = {short(v, 'V')}"],
                    f"E = {short(cap / 3600)} Ah × {short(v)} V = {short(e / 3600)} Wh = {short(e)} J", ans,
                    f"E / V = {short(e / v / 3600, 'Ah')} ✓")
    if cap is None and re.search(r"\bcapacity\b|\bmah\b|\bah\b|\bamp.?hours?\b", tq):
        tt = _daily(clean, t, qs)
        if i is None or tt is None:
            return None
        c = i * tt[0]
        unit_mah = re.search(r"\bmah\b|milliamp", tq) or c < 3600
        ans = show(c / R(3.6), "mAh", sf, dp, prefix=False) if unit_mah else show(c / 3600, "Ah", sf, dp, prefix=False)
        return _sol(text, "capacity = I · t", [f"I = {short(i, 'A')}", f"t = {hours_text(tt[0])}"],
                    f"capacity = {short(i)} A × {short(tt[0] / 3600)} h = {short(c / 3600)} Ah", ans,
                    f"capacity / I = {short(c / i / 3600)} h ✓")
    return None


def _charge(text, clean, t, tq, qs, known, sf, dp):
    q = _first(qs, "Q")
    i = known.get("I")
    electrons = re.search(r"\belectrons?\b", tq)
    asks_q = re.search(r"\bcharge\b|\bcoulombs?\b", tq) and not _price(t)
    tt = _daily(clean, t, qs)
    if q is None and (asks_q or electrons) and i is not None and tt is not None:
        sec = tt[0]
        qv = i * sec
        if electrons:
            n = qv / E_CHARGE
            return _sol(text, "Q = I · t, n = Q / e", [f"I = {short(i, 'A')}", f"t = {short(sec, 's')}",
                                                         "e = 1.602176634×10⁻¹⁹ C"],
                        f"Q = {short(i)} × {short(sec)} = {short(qv)} C, n = {short(qv)} / 1.602176634e-19",
                        f"≈ {float(n):.{sf}g} electrons".replace("e+", "×10^"), f"n·e = {short(n * E_CHARGE, 'C')} ✓")
        ans = show(qv, "C", sf, dp)
        return _sol(text, "Q = I · t", [f"I = {short(i, 'A')}", f"t = {short(sec, 's')}"],
                    f"Q = {short(i)} × {short(sec)}", ans, f"Q / t = {short(qv / sec, 'A')} ✓")
    if q is not None and i is None and tt is not None and re.search(_TARGETS["I"], tq):
        iv = q / tt[0]
        ans = show(iv, "A", sf, dp)
        return _sol(text, "I = Q / t", [f"Q = {short(q, 'C')}", f"t = {short(tt[0], 's')}"],
                    f"I = {short(q)} / {short(tt[0])}", ans, f"I·t = {short(iv * tt[0], 'C')} ✓")
    if q is not None and i is not None and tt is None and re.search(r"\bhow long\b|\btime\b|\bseconds\b", tq):
        sec = q / i
        ans = show(sec, "s", sf, dp, prefix=False)
        return _sol(text, "t = Q / I", [f"Q = {short(q, 'C')}", f"I = {short(i, 'A')}"],
                    f"t = {short(q)} / {short(i)}", ans, f"I·t = {short(i * sec, 'C')} ✓")
    if q is not None and electrons and i is None:
        n = q / E_CHARGE
        return _sol(text, "n = Q / e", [f"Q = {short(q, 'C')}", "e = 1.602176634×10⁻¹⁹ C"],
                    f"n = {short(q)} / 1.602176634e-19", f"≈ {float(n):.{sf}g} electrons".replace("e+", "×10^"),
                    f"n·e = {short(n * E_CHARGE, 'C')} ✓")
    return None


def _across(clean: str, rqs: list[Qty]):
    m = re.search(r"\bacross\s+(?:the\s+|resistor\s+)?(R_?\d|top|upper|first|bottom|lower|second|\S)", clean, re.I)
    if not m:
        return None
    tag = m.group(1).lower().replace("_", "")
    if tag in ("r1", "top", "upper", "first"):
        return 0
    if tag in ("r2", "bottom", "lower", "second"):
        return 1
    if re.fullmatch(r"r\d", tag):
        return int(tag[1]) - 1
    for k, q in enumerate(rqs):
        if 0 <= q.start - m.end(1) + 1 <= 2 or (m.start(1) <= q.start <= m.start(1) + 2):
            return k
    return None


def _divider(text, clean, t, tq, qs, known, sf, dp):
    rqs = [q for q in qs if q.dim == "R"]
    vs = _all(qs, "V")
    if "divider" not in t or len(rqs) < 1 or not vs:
        return None
    if len(vs) >= 2 and len(rqs) == 1:  # design: find R2
        vin, vout = max(vs), min(vs)
        r1 = rqs[0].val
        r2 = sp.nsimplify(r1 * vout / (vin - vout))
        ans = show(r2, "Ω", sf, dp)
        return _sol(text, "R2 = R1 · Vout / (Vin − Vout)", [f"Vin = {short(vin, 'V')}", f"Vout = {short(vout, 'V')}",
                                                             f"R1 = {short(r1, 'Ω')}"],
                    f"R2 = {short(r1)} × {short(vout)} / ({short(vin)} − {short(vout)})", ans,
                    f"Vout = Vin·R2/(R1+R2) = {short(vin * r2 / (r1 + r2), 'V')} ✓")
    if len(rqs) < 2:
        return None
    vin = vs[0]
    r1, r2 = rqs[0].val, rqs[1].val
    k = _across(clean, rqs[:2])
    k = 1 if k is None or k > 1 else k
    rx = (r1, r2)[k]
    vout = sp.nsimplify(vin * rx / (r1 + r2))
    ans = show(vout, "V", sf, dp)
    lab = "R1" if k == 0 else "R2"
    return _sol(text, f"Vout = Vin · {lab} / (R1 + R2)", [f"Vin = {short(vin, 'V')}", f"R1 = {short(r1, 'Ω')}",
                                                           f"R2 = {short(r2, 'Ω')}"],
                f"Vout = {short(vin)} × {short(rx)} / ({short(r1)} + {short(r2)})", ans,
                f"the other resistor drops {short(vin - vout, 'V')}; {short(vout)} + {short(vin - vout)} = "
                f"{short(vin)} V ✓")


def _net_solve(text, clean, t, tq, qs, known, sf, dp):
    rqs = [q for q in qs if q.dim == "R"]
    rqs = [q for k, q in enumerate(rqs) if not (re.search(r"\b(?:across|through|in|of)\s+(?:the\s+|each\s+)?$",
                                                          clean[:q.start], re.I)
                                                and any(x.val == q.val for x in rqs[:k]))]
    if len(rqs) < 2:
        return None
    net = _network(clean, t, rqs)
    if net is None:
        return None
    req, desc, mode = net
    vals = [q.val for q in rqs]
    wants = _wants(tq)
    v = known.get("V")
    i = known.get("I")
    knowns = [", ".join(short(x, "Ω") for x in vals)]
    if mode == "parallel":
        chk = f"R_eq = {short(req, 'Ω')} is below the smallest resistor ({short(min(vals), 'Ω')}) ✓"
    elif mode == "series":
        chk = f"R_eq = {short(req, 'Ω')} is above the largest resistor ({short(max(vals), 'Ω')}) ✓"
    else:
        chk = ""
    lines = [desc, f"R_eq = {show(req, 'Ω', sf, dp)}"]
    if v is not None and ("I" in wants or not wants or "V" in wants or "P" in wants):
        cur = sp.nsimplify(v / req)
        lines.append(f"I = V / R_eq = {short(v)} / {short(req)} = {short(cur, 'A')}")
        if "V" in wants and mode == "series":
            k = _across(clean, rqs)
            drops = [cur * x for x in vals]
            if k is not None and k < len(vals):
                ans = show(drops[k], "V", sf, dp)
                lines.append(f"V = I · R = {short(cur)} × {short(vals[k])}")
            else:
                ans = ", ".join(show(d, "V", sf, dp) for d in drops)
                lines.append("V_k = I · R_k for each resistor")
            return _sol(text, "R_eq = R1 + R2 + …, I = V / R_eq, V_k = I · R_k", knowns + [f"V = {short(v, 'V')}"],
                        "; ".join(lines[:-1]), ans, f"the drops add to {short(sum(drops), 'V')} = supply ✓")
        if "P" in wants:
            pw = sp.nsimplify(v ** 2 / req)
            ans = show(pw, "W", sf, dp)
            return _sol(text, "P = V² / R_eq", knowns + [f"V = {short(v, 'V')}"], "; ".join(lines), ans,
                        f"P = V·I = {short(v * cur, 'W')} ✓")
        ans = show(cur, "A", sf, dp)
        extra = []
        if mode == "parallel" and re.search(r"\beach\b|\bbranch", tq):
            extra.append("branch currents: " + ", ".join(f"{short(v)} / {short(x)} = {short(v / x, 'A')}"
                                                         for x in vals))
            ans += " total (" + ", ".join(show(v / x, "A", sf, dp) for x in vals) + " in the branches)"
        return _sol(text, "I = V / R_eq", knowns + [f"V = {short(v, 'V')}"], "; ".join(lines), ans,
                    f"V = I·R_eq = {short(cur * req, 'V')} ✓", extra)
    if i is not None and "V" in wants:
        vv = sp.nsimplify(i * req)
        ans = show(vv, "V", sf, dp)
        return _sol(text, "V = I · R_eq", knowns + [f"I = {short(i, 'A')}"], "; ".join(lines), ans,
                    f"V / R_eq = {short(vv / req, 'A')} ✓")
    if wants and "R" not in wants:
        return None
    return _sol(text, "series: R_eq = R1 + R2 + …; parallel: 1/R_eq = 1/R1 + 1/R2 + …", knowns, desc,
                show(req, "Ω", sf, dp), chk)


def _ohm(text, clean, t, tq, qs, known, sf, dp):
    wants = [w for w in _wants(tq) if known.get(w) is None]
    if not wants:
        return None
    have = {k: v for k, v in known.items() if v is not None}
    if len(have) < 2:
        return None
    results, steps_f, subs = [], [], []
    k2 = dict(have)
    for w in wants:
        r = _ohm_value(w, have)
        if r is None:
            r = _ohm_value(w, k2)
        if r is None:
            continue
        formula, val, sub = r
        k2[w] = val
        steps_f.append(formula)
        subs.append(f"{formula.split(' =')[0]} = {sub} = {short(val, SYM[w])}")
        results.append(show(val, SYM[w], sf, dp))
    if not results:
        return None
    ans = results[0] if len(results) == 1 else ", ".join(f"{w} = {r}" for w, r in zip(wants, results))
    knowns = [f"{k} = {short(v, SYM[k])}" for k, v in have.items()]
    return _sol(text, ", ".join(steps_f) + ("  (Ohm's law)" if any("R" in f for f in steps_f) else ""), knowns,
                "; ".join(subs), ans, _check(k2, sf))


DEFINITION = re.compile(r"^\s*(?:what(?:'s| is| are)|define|explain|meaning of)\b(?!.*\d)", re.I)


def solve(text: str) -> Solution | None:
    if not text or len(text) > 600 or DEFINITION.search(text):
        return None
    clean, qs, sf, dp = _parse(text)
    elec = [q for q in qs if q.dim in ("V", "I", "R", "P", "E", "Q", "CAP")]
    t = clean.lower()
    if not elec:
        return None
    tq = t
    for q in sorted(qs, key=lambda q: q.start, reverse=True):
        if q.end > q.start:
            tq = tq[:q.start] + " # " + tq[q.end:]
    known = {k: _first(qs, k) for k in "VIRP"}
    rcount = len([q for q in qs if q.dim == "R" and not re.search(r"\b(?:across|through)\s+(?:the\s+)?$",
                                                                   clean[:q.start], re.I)])
    if rcount >= 2:
        known["R"] = None
    for fn in (_divider, _battery, _charge, _energy, _net_solve):
        sol = fn(text, clean, t, tq, qs, known, sf, dp)
        if sol is not None:
            return sol
    if rcount >= 2:
        return None
    return _ohm(text, clean, t, tq, qs, known, sf, dp)
