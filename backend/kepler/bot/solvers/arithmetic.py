"""Everyday arithmetic, fractions, percentages, ratios, unit conversions, rates, uptime budgets, roots and powers,
rounding and scientific notation, in plain English with worked steps.

Exact arithmetic with Fraction (and sympy for surds), deterministic, no network. Chatter around the problem ("quick
one:", "pls", "show me the steps", "4 sig figs", "as a fraction") is ignored. Returns None for anything that is not one
of these problems: Kepler commands ("set sensitivity to 80%"), definitions ("what is a derivative") and small talk.
"""
import ast
import math
import re
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction as F

import sympy as sp

from ..fields import fmt
from ..reasoning import Solution

TRANS = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", "−": "-", "\u00a0": " ",
                       "×": "*", "÷": " div ", "⋅": "*", "·": "*"})
NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+"
N = rf"(?:{NUM})"
CUR = r"[$€£₹¥]"

CHATTER = re.compile(
    r"\bshow (?:me )?(?:the |all |your |all the )?(?:steps?|working|work(?:ings?)?|method|calculations?)\b|"
    r"\bstep[- ]by[- ]step\b|\bwith (?:the )?(?:steps|working)\b|"
    r"\bfor (?:my|a|our) (?:homework|class|assignment|exam|test|quiz|course|worksheet|[a-z]+ class)\b|"
    r"\b(?:pls|plz|please|thanks?(?: you)?|thx|ty)\b|\bquick (?:one|q|question)\b|\breal quick\b|"
    r"\b(?:can|could|would) (?:you|u)(?: please)?(?: help(?: me)?(?: with)?| tell me| work out| figure out| calculate|"
    r" compute| solve| find| do)?\b|\bhelp me(?: with)?\b|\bhey\b|\bkepler\b|\bum+\b|"
    r"\b(?:give (?:it|me|the answer) )?(?:as an? |in )?(?:exact(?: form| value| answer)?(?: if (?:you|u) can)?|"
    r"(?:simplified |simplest )?fraction(?: form)?|simplest form)\b|\band (?:reduce|simplify)(?: it)?\b")
SIGFIG = re.compile(r"\b(?:to|in|with|at)?\s*(\d+)\s*(?:sig(?:nificant)?\.?\s*(?:fig(?:ure)?s?|digits?)|s\.?f\.?)(?![a-z])")
DECPL = re.compile(r"\b(?:to|in|rounded to|round to)?\s*(\d+)\s*(?:decimal places?|dp|d\.p\.)(?![a-z])")
# trailing remarks after the question: "? i keep mixing up the product rule"
REMARK = re.compile(r"[?!.]\s+(?:i|i'm|im|my|we|this|it's|its|that's|idk|lol|ugh|no rush|thanks?)\b.*$")


def _n(s: str) -> F:
    return F(s.replace(",", ""))


def _ok(x: F) -> str:
    """Exact Fraction as text: integer, or p/q (mixed number) ≈ decimal."""
    if x.denominator == 1:
        return f"{x.numerator:,}"
    d = x.denominator
    while d % 2 == 0:
        d //= 2
    while d % 5 == 0:
        d //= 5
    if d == 1 and len(str(x.denominator)) <= 8:  # terminating decimal
        return _dec(x)
    s = f"{x.numerator}/{x.denominator}"
    if abs(x) > 1:
        w = int(abs(x.numerator) // x.denominator)
        r = abs(x) - w
        s += f" = {'-' if x < 0 else ''}{w} {r.numerator}/{r.denominator}"
    return s + f" ≈ {fmt(float(x))}"


def _dec(x: F) -> str:
    s = format(Decimal(x.numerator) / Decimal(x.denominator), "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    ip, _, fp = s.partition(".")
    neg = ip.startswith("-")
    ip = f"{int(ip.lstrip('-') or 0):,}"
    return ("-" if neg else "") + ip + ("." + fp if fp else "")


def _sig(x: float, n: int) -> str:
    if x == 0:
        return "0"
    d = Decimal(repr(x))
    q = Decimal(1).scaleb(d.adjusted() - n + 1)
    r = d.quantize(q, rounding=ROUND_HALF_UP)
    return f"{r:,f}" if r.adjusted() < 15 else f"{r:.{n - 1}E}"


def _sol(kind, problem, steps, answer, check="") -> Solution:
    return Solution(kind, problem, answer, steps + [f"result: {answer}"], check=check, confidence=0.96)


class Msg:
    def __init__(self, text: str):
        self.raw = text.strip()
        t = text.translate(TRANS).lower().strip()
        t = REMARK.sub("", t)
        self.sig = None
        self.dp = None
        m = SIGFIG.search(t)
        if m:
            self.sig = int(m.group(1))
            t = t[:m.start()] + t[m.end():]
        m = DECPL.search(t)
        if m and not re.search(r"\bround", t):
            self.dp = int(m.group(1))
            t = t[:m.start()] + t[m.end():]
        t = CHATTER.sub(" ", t)
        t = re.sub(r"\bper cent\b", "percent", t)
        t = re.sub(r"(?<=\d)\s*percent\b", "%", t)
        t = re.sub(r"^[\s,:;.!-]+|[\s,;:!-]+$", "", t)
        t = re.sub(r"\s+", " ", t).strip(" ,")
        self.t = t
        self.money = bool(re.search(CUR, t))

    def finish(self, x: float) -> str:
        if self.sig:
            return _sig(x, self.sig)
        if self.dp is not None:
            return f"{Decimal(repr(x)).quantize(Decimal(1).scaleb(-self.dp), rounding=ROUND_HALF_UP):,f}"
        return fmt(x)


def _cur(t: str) -> str:
    m = re.search(CUR, t)
    return m.group(0) if m else ""


def _m(c: str, x) -> str:
    return f"{'-' if x < 0 else ''}{c}{abs(float(x)):,.2f}"


# ---------------------------------------------------------------- uptime / SLO budgets

PERIODS = {"day": 1, "week": 7, "month": 30, "quarter": 90, "year": 365}


def uptime(m: Msg) -> Solution | None:
    t = m.t
    if not re.search(r"\b(uptime|availability|slo|sla|downtime|nines|error budget)\b", t):
        return None
    p = re.search(rf"({N})\s*%", t)
    if not p:
        return None
    pct = _n(p.group(1))
    if not 0 < pct < 100:
        return None
    q = re.search(rf"\b({N})[- ]?(day|week|month|quarter|year)s?\b", t)
    if q:
        days = _n(q.group(1)) * PERIODS[q.group(2)]
        label = f"{q.group(1)} {q.group(2)}s" if q.group(1) != "1" else f"1 {q.group(2)}"
    else:
        w = re.search(r"\b(?:a|per|each|every|over|in|for|monthly|yearly|weekly|daily|annual)\s*(day|week|month|"
                      r"quarter|year)?", t)
        word = re.search(r"\b(day|week|month|quarter|year)\b|\b(monthly|yearly|annual|weekly|daily)\b", t)
        if not word:
            days, label = F(30), "30 days (a month)"
        else:
            k = word.group(1) or {"monthly": "month", "yearly": "year", "annual": "year", "weekly": "week",
                                  "daily": "day"}[word.group(2)]
            days, label = F(PERIODS[k]), f"1 {k} ({PERIODS[k]} days)"
        del w
    minutes = (1 - pct / 100) * days * 1440
    secs = float(minutes * 60)
    h, rem = divmod(round(secs), 3600)
    mi, s = divmod(rem, 60)
    hms = (f"{h} h " if h else "") + f"{mi} min" + (f" {s} s" if s else "")
    ans = f"{fmt(float(minutes))} minutes of downtime allowed (≈ {hms})"
    steps = ["formula: allowed downtime = (1 − availability) × period",
             f"known: availability = {p.group(1)}%, period = {label} = {fmt(float(days * 1440))} minutes",
             f"substitute: (1 − {float(pct / 100)}) × {fmt(float(days * 1440))} min = {fmt(float(minutes))} min"]
    chk = f"check: {fmt(float(days * 1440 - minutes))} min up / {fmt(float(days * 1440))} min = {p.group(1)}%"
    return _sol("uptime budget", m.raw, steps, ans, chk)


# ---------------------------------------------------------------- rates

TUNIT = {"second": 1, "sec": 1, "s": 1, "minute": 60, "min": 60, "hour": 3600, "hr": 3600, "h": 3600, "day": 86400}
_TU = r"(second|sec|s|minute|min|hour|hr|h|day)s?"


def _tw(u: str) -> str:
    return {"sec": "second", "s": "second", "min": "minute", "hr": "hour", "h": "hour"}.get(u, u)


def _dur(secs: float) -> str:
    secs = round(secs)
    d, r = divmod(secs, 86400)
    h, r = divmod(r, 3600)
    mi, s = divmod(r, 60)
    parts = [f"{d} d" if d else "", f"{h} h" if h else "", f"{mi} min" if mi else "", f"{s} s" if s else ""]
    return " ".join(p for p in parts if p) or "0 s"


def rates(m: Msg) -> Solution | None:
    t = m.t
    rate = re.search(rf"({N})\s*(?:[a-z]+\s+)?(?:a|an|per|each|every|/)\s*{_TU}\b", t)
    if not rate:
        return None
    r, ru = _n(rate.group(1)), _tw(rate.group(2))
    # draining a backlog: how long
    if re.search(r"\b(backlog|queue|drain|clear|process|left|remaining|pending|how long)\b", t):
        others = [x for x in re.finditer(N, t) if x.start() != rate.start()]
        if not others or r == 0:
            return None
        total = _n(others[0].group(0))
        if re.search(r"\b(backlog|queue|messages|jobs|items|tasks|events|tickets|emails|records)\b", t) is None and \
                not re.search(r"\bhow long\b", t):
            return None
        tt = total / r
        secs = float(tt * TUNIT[ru])
        ans = f"{fmt(float(tt))} {ru}s (≈ {_dur(secs)})"
        steps = ["formula: time = amount ÷ rate", f"known: amount = {fmt(float(total))}, rate = {fmt(float(r))} per {ru}",
                 f"substitute: {fmt(float(total))} ÷ {fmt(float(r))} = {fmt(float(tt))} {ru}s"]
        return _sol("rate", m.raw, steps, ans, f"check: {fmt(float(tt))} × {fmt(float(r))} = {fmt(float(tt * r))}")
    d = re.search(rf"\b(?:over|for|in|during|across)\s+(?:a|an|one|({N}))\s*{_TU}\b", t[rate.end():])
    if not d:
        return None
    dv = _n(d.group(1)) if d.group(1) else F(1)
    du = _tw(d.group(2))
    secs = dv * TUNIT[du]
    total = r * secs / TUNIT[ru]
    ans = fmt(float(total)) if total.denominator != 1 else f"{total.numerator:,}"
    what = re.search(rf"{re.escape(rate.group(1))}\s*([a-z]+)\s+(?:a|an|per|each|every)", t)
    noun = what.group(1) if what else ""
    if noun:
        ans += f" {noun}"
    steps = ["formula: total = rate × time",
             f"known: rate = {fmt(float(r))} per {ru}, time = {fmt(float(dv))} {du}s = {fmt(float(secs / TUNIT[ru]))} {ru}s",
             f"substitute: {fmt(float(r))} × {fmt(float(secs / TUNIT[ru]))} = {fmt(float(total))}"]
    return _sol("rate", m.raw, steps, ans, f"check: {fmt(float(total))} ÷ {fmt(float(secs / TUNIT[ru]))} = {fmt(float(r))}")


# ---------------------------------------------------------------- unit conversion

U = {}


def _add(dim, factor, *names):
    for n in names:
        U[n] = (dim, F(factor))


_add("len", 1, "m", "meter", "meters", "metre", "metres")
_add("len", 1000, "km", "kilometer", "kilometers", "kilometre", "kilometres")
_add("len", F(1, 100), "cm", "centimeter", "centimeters", "centimetre", "centimetres")
_add("len", F(1, 1000), "mm", "millimeter", "millimeters", "millimetre", "millimetres")
_add("len", F("1609.344"), "mi", "mile", "miles")
_add("len", F("0.9144"), "yd", "yard", "yards")
_add("len", F("0.3048"), "ft", "foot", "feet")
_add("len", F("0.0254"), "in", "inch", "inches")
_add("mass", 1, "kg", "kilogram", "kilograms", "kilo", "kilos")
_add("mass", F(1, 1000), "g", "gram", "grams")
_add("mass", F(1, 10 ** 6), "mg", "milligram", "milligrams")
_add("mass", 1000, "t", "tonne", "tonnes")
_add("mass", F("0.45359237"), "lb", "lbs", "pound", "pounds")
_add("mass", F("0.45359237") / 16, "oz", "ounce", "ounces")
_add("mass", F("6.35029318"), "st", "stone", "stones")
_add("vol", 1, "l", "liter", "liters", "litre", "litres")
_add("vol", F(1, 1000), "ml", "milliliter", "milliliters", "millilitre", "millilitres")
_add("vol", F("3.785411784"), "gal", "gallon", "gallons")
_add("vol", F("0.946352946"), "quart", "quarts", "qt")
_add("vol", F("0.473176473"), "pint", "pints", "pt")
_add("vol", F("0.2365882365"), "cup", "cups")
_add("vol", F("0.0295735295625"), "fl oz", "fluid ounce", "fluid ounces")
_add("time", 1, "s", "sec", "secs", "second", "seconds")
_add("time", F(1, 1000), "ms", "millisecond", "milliseconds")
_add("time", 60, "min", "mins", "minute", "minutes")
_add("time", 3600, "h", "hr", "hrs", "hour", "hours")
_add("time", 86400, "day", "days")
_add("time", 604800, "week", "weeks", "wk", "wks")
_add("time", 31536000, "year", "years", "yr", "yrs")
_add("data", 1, "b", "byte", "bytes")
_add("data", F(1, 8), "bit", "bits")
for _i, _p in enumerate(["k", "m", "g", "t", "p"], 1):
    _full = ["kilo", "mega", "giga", "tera", "peta"][_i - 1]
    _bin = ["kibi", "mebi", "gibi", "tebi", "pebi"][_i - 1]
    _add("data", 1000 ** _i, f"{_p}b", f"{_full}byte", f"{_full}bytes")
    _add("data", 1024 ** _i, f"{_p}ib", f"{_bin}byte", f"{_bin}bytes")
    _add("data", F(1000 ** _i, 8), f"{_p}bit", f"{_full}bit", f"{_full}bits")
TEMP = {"c": "C", "°c": "C", "celsius": "C", "centigrade": "C", "degrees c": "C", "deg c": "C", "degrees celsius": "C",
        "f": "F", "°f": "F", "fahrenheit": "F", "degrees f": "F", "deg f": "F", "degrees fahrenheit": "F",
        "k": "K", "kelvin": "K", "kelvins": "K"}
SYMBOL = {"len": "m", "mass": "kg", "vol": "L", "time": "s", "data": "B"}
_UNAMES = sorted(list(U) + list(TEMP), key=len, reverse=True)
UR = "(" + "|".join(re.escape(u) for u in _UNAMES) + r")(?![a-z])"


def _unit(u: str):
    u = u.strip()
    if u in TEMP:
        return ("temp", TEMP[u])
    return U.get(u)


def _show(u: str) -> str:
    if u in TEMP:
        return {"C": "°C", "F": "°F", "K": "K"}[TEMP[u]]
    if re.fullmatch(r"[kmgtp]i?b(?:it)?", u):
        return u[0].upper() + u[1:-1] + ("B" if u.endswith("b") and not u.endswith("bit") else u[-1])
    return u


def _to_c(x: F, s: str) -> F:
    return x if s == "C" else (x - 32) * F(5, 9) if s == "F" else x - F("273.15")


def _from_c(x: F, s: str) -> F:
    return x if s == "C" else x * F(9, 5) + 32 if s == "F" else x + F("273.15")


TFORM = {("C", "F"): "°F = °C × 9/5 + 32", ("F", "C"): "°C = (°F − 32) × 5/9", ("C", "K"): "K = °C + 273.15",
         ("K", "C"): "°C = K − 273.15", ("F", "K"): "K = (°F − 32) × 5/9 + 273.15",
         ("K", "F"): "°F = (K − 273.15) × 9/5 + 32"}


def convert(m: Msg) -> Solution | None:
    t = re.sub(r"\bdegrees? ", "degrees ", m.t)
    t = re.sub(r"°\s+", "°", t)
    given = None
    g = re.search(rf"(?:use|using|assume|assuming|with|where|if|given)?\s*(?:that\s+)?1\s*{UR}\s*(?:=|is|equals)\s*({N})\s*{UR}", t)
    if g:
        given = (g.group(1), _n(g.group(2)), g.group(3))
        t = (t[:g.start()] + t[g.end():]).strip(" ,;()")
    pats = [rf"(?:convert\s+)?(-?{N})\s*{UR}\s+(?:to|in|into|in to|as|=|->|is how many|equals how many)\s+{UR}",
            rf"how many\s+{UR}\s+(?:are |is )?(?:there )?(?:in|is|are|make|=)\s+(-?{N})\s*{UR}"]
    mm = re.search(pats[0], t)
    if mm:
        val, fu, tu = _n(mm.group(1)), mm.group(2), mm.group(3)
    else:
        mm = re.search(pats[1], t)
        if not mm:
            return None
        tu, val, fu = mm.group(1), _n(mm.group(2)), mm.group(3)
    a, b = _unit(fu), _unit(tu)
    if a is None or b is None:
        return None
    vs = mm.group(1) if mm.re.pattern == pats[0] else mm.group(2)
    if given and given[0] == fu and given[2] == tu:
        res = val * given[1]
        steps = [f"formula: {_show(tu)} = {_show(fu)} × {fmt(float(given[1]))} (your factor: 1 {fu} = {given[1]} {tu})",
                 f"known: {vs} {fu}", f"substitute: {vs} × {fmt(float(given[1]))} = {fmt(float(res))}"]
        return _sol("unit conversion", m.raw, steps, f"{m.finish(float(res))} {_show(tu)}",
                    f"check: {fmt(float(res))} ÷ {fmt(float(given[1]))} = {fmt(float(val))} {fu}")
    if given and given[0] == tu and given[2] == fu:
        res = val / given[1]
        steps = [f"formula: {tu} = {fu} ÷ {fmt(float(given[1]))} (your factor: 1 {tu} = {given[1]} {fu})",
                 f"known: {vs} {fu}", f"substitute: {vs} ÷ {fmt(float(given[1]))} = {fmt(float(res))}"]
        return _sol("unit conversion", m.raw, steps, f"{m.finish(float(res))} {_show(tu)}",
                    f"check: {fmt(float(res))} × {fmt(float(given[1]))} = {fmt(float(val))} {fu}")
    if a[0] != b[0]:
        return None
    if a[0] == "temp":
        if a[1] == b[1]:
            return None
        res = _from_c(_to_c(val, a[1]), b[1])
        back = _from_c(_to_c(res, b[1]), a[1])
        steps = [f"formula: {TFORM[(a[1], b[1])]}", f"known: {vs} {_show(fu)}",
                 f"substitute: {fmt(float(res))}"]
        return _sol("unit conversion", m.raw, steps, f"{m.finish(float(res))} {_show(tu)}",
                    f"check: converting back gives {fmt(float(back))} {_show(fu)}")
    factor = a[1] / b[1]
    res = val * factor
    base = SYMBOL[a[0]]
    steps = [f"formula: value in {tu} = value in {fu} × ({fu} in {base}) ÷ ({tu} in {base})",
             f"known: 1 {fu} = {fmt(float(a[1]))} {base}, 1 {tu} = {fmt(float(b[1]))} {base}",
             f"substitute: {vs} × {_ok(factor).split(' ≈ ')[0] if factor.denominator != 1 else factor.numerator} "
             f"= {fmt(float(res))}"]
    ans = f"{m.finish(float(res))} {_show(tu)}" if res.denominator != 1 or m.sig else f"{res.numerator:,} {_show(tu)}"
    return _sol("unit conversion", m.raw, steps, ans,
                f"check: {fmt(float(res))} {tu} × {fmt(float(b[1]))} ÷ {fmt(float(a[1]))} = {fmt(float(val))} {fu}")


# ---------------------------------------------------------------- percentages

def _pct(x: F) -> str:
    return _ok(x) if x.denominator == 1 else fmt(float(x))


def percentages(m: Msg) -> Solution | None:
    t = re.sub(r"(?<=\d)\s+%", "%", m.t)
    c = _cur(t)
    tn = re.sub(CUR, "", t)
    P = r"(?:percent(?:age)?|%|pct)"
    # A is what % of B / what % is A of B / what % of B is A / A out of B as a percentage
    for pat, order in [(rf"\b({N}) is what {P} of ({N})", (1, 2)),
                       (rf"\bwhat {P} of ({N}) is ({N})", (2, 1)),
                       (rf"\bwhat {P} is ({N}) (?:of )?({N})\b", (1, 2)),
                       (rf"\b({N}) (?:out of|of|/) ({N})\s*(?:as|in|to|into|=|is)?\s*(?:a |an )?{P}", (1, 2)),
                       (rf"\b(?:express|write|convert)\s+({N})\s*/\s*({N}) (?:as|in|to)\s*(?:a )?{P}", (1, 2))]:
        mm = re.search(pat, tn)
        if mm:
            a, b = _n(mm.group(order[0])), _n(mm.group(order[1]))
            if b == 0:
                return None
            r = a / b * 100
            steps = ["formula: percent = part ÷ whole × 100", f"known: part = {_dec(a)}, whole = {_dec(b)}",
                     f"substitute: {_dec(a)} ÷ {_dec(b)} × 100 = {fmt(float(r))}"]
            return _sol("percentage", m.raw, steps, f"{m.finish(float(r)) if r.denominator != 1 else _dec(r)}%",
                        f"check: {fmt(float(r))}% of {_dec(b)} = {fmt(float(r * b / 100))}")
    # original price before a discount
    mm = re.search(rf"({N})% (?:off|discount|markdown|sale|reduction)", tn)
    if mm and re.search(r"\b(original|before|full price|regular|list price|was it|pre-?discount|used to cost)\b", tn):
        rest = tn[:mm.start()] + " " + tn[mm.end():]
        nums = [x for x in re.findall(rf"(?<![\d.]){N}(?![\d.,]|\s*%)", rest)]
        if nums:
            d, paid = _n(mm.group(1)), _n(nums[0])
            orig = paid / (1 - d / 100)
            steps = ["formula: original = sale price ÷ (1 − discount)",
                     f"known: sale price = {_m(c, paid)}, discount = {_dec(d)}%",
                     f"substitute: {_m(c, paid)} ÷ {fmt(float(1 - d / 100))} = {_m(c, orig)}"]
            return _sol("percentage", m.raw, steps, _m(c, orig),
                        f"check: {_m(c, orig)} − {_dec(d)}% = {_m(c, orig * (1 - d / 100))}")
    # successive discounts
    ds = re.findall(rf"({N})%\s*(?:off|discount)?", tn)
    if len(ds) >= 2 and re.search(r"\b(then|another|further|followed by|additional|extra|on top|successive|after that)\b",
                                  tn) and re.search(r"\b(off|discount|sale|reduc|markdown|coupon)", tn):
        fac = F(1)
        for d in ds:
            fac *= 1 - _n(d) / 100
        tot = (1 - fac) * 100
        price = re.search(rf"(?<![\d.])({N})(?![\d.,]|\s*%)", tn)
        steps = ["rule: successive discounts multiply: remaining = (1 − d₁)(1 − d₂)…",
                 "known: " + ", ".join(f"{d}%" for d in ds),
                 "substitute: " + " × ".join(fmt(float(1 - _n(d) / 100)) for d in ds) + f" = {fmt(float(fac))}"]
        ans = f"{fmt(float(tot))}% total discount (not {fmt(float(sum(_n(d) for d in ds)))}%)"
        if price:
            p = _n(price.group(1))
            ans = f"{_m(c, p * fac)} final price; " + ans
            steps.append(f"price: {_m(c, p)} × {fmt(float(fac))} = {_m(c, p * fac)}")
        return _sol("percentage", m.raw, steps, ans, f"check: 1 − {fmt(float(fac))} = {fmt(float(1 - fac))}")
    # percent change / percent off from old and new
    mm = (re.search(rf"\bfrom ({N}) to ({N})", tn)
          or re.search(rf"\b(?:was|old price(?: (?:is|was|of))?|originally|used to be|before)\s*:?\s*({N}).*?"
                       rf"\b(?:now|new price(?: (?:is|of))?|is now|sale price(?: (?:is|of))?|after|today)\s*:?\s*({N})", tn))
    if mm and re.search(rf"{P}|\b(?:percent|discount|off|change|increase|decrease|growth|drop)\b", tn) and \
            re.search(r"\b(change|increase|decrease|grow|growth|rise|rose|drop|fall|fell|off|discount|went|go|"
                      r"cheaper|up|down|differ)", tn):
        a, b = _n(mm.group(1)), _n(mm.group(2))
        if a == 0:
            return None
        r = (b - a) / a * 100
        word = "increase" if r > 0 else "decrease"
        if re.search(r"\b(off|discount|cheaper|sale)\b", tn) and r < 0:
            word = "off"
        steps = ["formula: percent change = (new − old) ÷ old × 100", f"known: old = {_dec(a)}, new = {_dec(b)}",
                 f"substitute: ({_dec(b)} − {_dec(a)}) ÷ {_dec(a)} × 100 = {fmt(float(r))}"]
        return _sol("percentage", m.raw, steps, f"{m.finish(abs(float(r)))}% {word}",
                    f"check: {_dec(a)} × (1 {'+' if r > 0 else '−'} {fmt(abs(float(r)) / 100)}) = {fmt(float(b))}")
    # increase / decrease Y by X%
    mm = re.search(rf"\b(increase|raise|decrease|reduce|lower|cut)\s+({N}) by ({N})%", tn) or \
        re.search(rf"\b({N}) (plus|minus|\+|-) ({N})%", tn)
    if mm:
        if mm.group(1)[0].isdigit():
            y, op, x = _n(mm.group(1)), mm.group(2), _n(mm.group(3))
            up = op in ("plus", "+")
        else:
            op, y, x = mm.group(1), _n(mm.group(2)), _n(mm.group(3))
            up = op in ("increase", "raise")
        r = y * (1 + (x if up else -x) / 100)
        steps = [f"formula: new = old × (1 {'+' if up else '−'} p/100)", f"known: old = {_dec(y)}, p = {_dec(x)}%",
                 f"substitute: {_dec(y)} × {fmt(float(1 + (x if up else -x) / 100))} = {_dec(r) if r.denominator < 10**8 else fmt(float(r))}"]
        ans = _m(c, r) if c else (_ok(r) if r.denominator == 1 else m.finish(float(r)))
        return _sol("percentage", m.raw, steps, ans)
    # X% of Y
    mm = re.search(rf"(?<![\d.])({N})% of ({N})(?![\d.,]|\s*%)", tn)
    if mm and not re.search(r"\b(why|spike|incident|alert|error|latency|signup|sensitivity|set)\b", tn):
        x, y = _n(mm.group(1)), _n(mm.group(2))
        r = x / 100 * y
        steps = ["formula: p% of y = p ÷ 100 × y", f"known: p = {_dec(x)}, y = {_dec(y)}",
                 f"substitute: {_dec(x)} ÷ 100 × {_dec(y)} = {fmt(float(r))}"]
        ans = _m(c, r) if c else (_dec(r) if r.denominator < 10 ** 8 and _ok(r).find("/") < 0 else m.finish(float(r)))
        return _sol("percentage", m.raw, steps, ans, f"check: {fmt(float(r))} ÷ {_dec(y)} × 100 = {_dec(x)}%")
    return None


# ---------------------------------------------------------------- ratios

def ratios(m: Msg) -> Solution | None:
    t = m.t
    c = _cur(t)
    tn = re.sub(CUR, "", t)
    tn = re.sub(rf"\bratio (?:of )?({N}) to ({N})\b", r"ratio \1:\2", tn)
    rr = re.search(rf"({N}(?:\s*:\s*{N})+)", tn)
    if not rr:
        return None
    parts = [_n(p) for p in re.split(r"\s*:\s*", rr.group(1))]
    if any(p <= 0 for p in parts) or re.search(r"\b(am|pm)\b|\d:\d\d\s*(?:am|pm)?\s*$", tn) and "ratio" not in tn:
        return None
    sp_ = re.search(rf"\b(split|divide|share|shared|allocate|distribute|partition)\b.*?({N})(?!\s*:)", tn[:rr.start()])
    if sp_:
        total = _n(sp_.group(2))
        s = sum(parts)
        shares = [total * p / s for p in parts]
        steps = ["rule: each share = total × part ÷ sum of parts",
                 f"known: total = {_m(c, total) if c else _dec(total)}, ratio = {rr.group(1)}, sum of parts = {_dec(s)}",
                 "substitute: " + ", ".join(f"{_dec(total)} × {_dec(p)}/{_dec(s)} = {fmt(float(x))}"
                                            for p, x in zip(parts, shares))]
        ans = " and ".join(_m(c, x) if c else _ok(x) for x in shares)
        return _sol("ratio", m.raw, steps, ans,
                    f"check: {' + '.join(fmt(float(x)) for x in shares)} = {fmt(float(sum(shares)))}")
    if re.search(r"\b(reduce|simplif|simplest|lowest terms)", tn):
        den = math.lcm(*[p.denominator for p in parts])
        ints = [int(p * den) for p in parts]
        g = math.gcd(*ints)
        red = [i // g for i in ints]
        steps = ["rule: divide every term by their greatest common divisor",
                 f"known: ratio {rr.group(1)}" + (f", scaled by {den} to whole numbers" if den > 1 else ""),
                 f"substitute: gcd = {g}, so " + " : ".join(f"{i}/{g}" for i in ints)]
        ans = ":".join(str(r) for r in red)
        return _sol("ratio", m.raw, steps, ans, f"check: gcd of {', '.join(map(str, red))} is 1")
    return None


# ---------------------------------------------------------------- roots, powers

ORD = {"square": 2, "cube": 3, "fourth": 4, "fifth": 5, "4th": 4, "5th": 5, "6th": 6, "sixth": 6}


def roots(m: Msg) -> Solution | None:
    t = re.sub(r"^(?:what(?:'s| is)|whats|find|calc(?:ulate)?|compute|evaluate|work out)\s+(?:the\s+)?", "", m.t)
    t = t.rstrip(" ?=.")
    mm = re.fullmatch(rf"(square|cube|fourth|fifth|sixth|4th|5th|6th)\s+root\s+(?:of\s+)?(-?{N})|"
                      rf"(sqrt|cbrt|√|∛)\s*\(?\s*(-?{N})\s*\)?", t)
    if mm:
        n = ORD[mm.group(1)] if mm.group(1) else (2 if mm.group(3) in ("sqrt", "√") else 3)
        xs = mm.group(2) or mm.group(4)
        x = _n(xs)
        if x < 0 and n % 2 == 0:
            return None
        e = sp.Rational(x.numerator, x.denominator)
        r = sp.real_root(e, n) if x < 0 else sp.root(e, n)
        r = sp.nsimplify(sp.radsimp(r))
        val = float(r)
        exact = re.sub(r"sqrt\((\d+)\)", r"√\1", str(r)).replace("*√", "√").replace("**(1/3)", "^(1/3)")
        name = {2: "square", 3: "cube"}.get(n, f"{n}th")
        if r.is_Rational:
            ans = _ok(F(int(r.p), int(r.q)))
        else:
            ans = f"{exact} ≈ {m.finish(val)}" if m.sig or m.dp is not None else f"{exact} ≈ {_sig(val, 6)}"
        steps = [f"rule: the {name} root of x is the number r with r^{n} = x",
                 f"known: x = {xs}", f"substitute: {name} root of {xs} = {exact}"]
        return _sol("roots and powers", m.raw, steps, ans, f"check: ({fmt(val)})^{n} ≈ {fmt(val ** n)}")
    mm = re.fullmatch(rf"(-?{N})\s*(?:to the power of|to the|raised to(?: the power of)?|\^|\*\*)\s*(-?{N})"
                      rf"(?:st|nd|rd|th)?(?: power)?|(-?{N})\s+(squared|cubed)", t)
    if mm:
        bs = mm.group(1) or mm.group(3)
        b = _n(bs)
        e = _n(mm.group(2)) if mm.group(2) else F(2 if mm.group(4) == "squared" else 3)
        if e.denominator != 1 or abs(e) > 400:
            return None
        r = b ** int(e)
        steps = ["rule: b^n means multiplying b by itself n times" + (" (negative n: reciprocal)" if e < 0 else ""),
                 f"known: b = {bs}, n = {e}", f"substitute: {bs}^{e} = {_ok(r)}"]
        ans = _ok(r)
        if abs(r) >= 10 ** 9 and r.denominator == 1:
            ans += f" ≈ {float(r):.4e}".replace("e+", " × 10^")
        return _sol("roots and powers", m.raw, steps, ans)
    return None


# ---------------------------------------------------------------- rounding, scientific notation

PLACE = {"ten": -1, "tens": -1, "hundred": -2, "hundreds": -2, "thousand": -3, "thousands": -3, "million": -6,
         "tenth": 1, "tenths": 1, "hundredth": 2, "hundredths": 2, "thousandth": 3, "thousandths": 3,
         "whole number": 0, "integer": 0, "one": 0, "ones": 0, "unit": 0, "units": 0, "cent": 2}


def rounding(m: Msg) -> Solution | None:
    t = m.t
    raw = m.raw.translate(TRANS).lower()
    mm = re.search(rf"\b(?:round|rounded|write|express|give)\s+(-?{N})\s*(?:to|in)?\s*(?:the nearest\s+(\w+(?: number)?))?",
                   t)
    if not mm:
        mm2 = re.fullmatch(rf"(-?{N})(?: rounded)?", t.rstrip(" ?."))
        if not (mm2 and (m.sig or m.dp is not None)):
            return None
        xs, place = mm2.group(1), None
    else:
        xs, place = mm.group(1), mm.group(2)
    x = Decimal(xs.replace(",", ""))
    if place:
        if place not in PLACE:
            return None
        q = Decimal(1).scaleb(-PLACE[place])
        r = (x / q).quantize(Decimal(1), rounding=ROUND_HALF_UP) * q
        r = r.quantize(Decimal(1)) if PLACE[place] <= 0 else r
        rule = f"round to the nearest {place}: look at the next digit, 5 or more rounds up"
    elif m.dp is not None or re.search(r"decimal place|\bdp\b", raw):
        dp = m.dp if m.dp is not None else int(re.search(r"(\d+)\s*(?:decimal places?|dp)", raw).group(1))
        r = x.quantize(Decimal(1).scaleb(-dp), rounding=ROUND_HALF_UP)
        rule = f"keep {dp} decimal places: look at the next digit, 5 or more rounds up"
    elif m.sig:
        r = Decimal(_sig(float(x), m.sig).replace(",", ""))
        rule = f"keep {m.sig} significant figures, counted from the first non-zero digit; 5 or more rounds up"
    else:
        return None
    out = f"{r:,f}"
    steps = [f"rule: {rule}", f"known: {xs}", f"substitute: {xs} → {out}"]
    return _sol("rounding", m.raw, steps, out, f"check: |{xs} − {out}| = {abs(x - r)}")


def scientific(m: Msg) -> Solution | None:
    t = m.t
    to_sci = re.search(rf"(-?{N}(?:e-?\d+)?)\s*(?:in|to|into|as)\s+(?:scientific|standard index|exponential|e)\s*"
                       r"(?:notation|form)", t)
    if to_sci:
        xs = to_sci.group(1)
        x = Decimal(xs.replace(",", ""))
        if x == 0:
            return None
        e = x.adjusted()
        mant = (x.scaleb(-e)).normalize()
        if m.sig:
            mant = mant.quantize(Decimal(1).scaleb(-(m.sig - 1)), rounding=ROUND_HALF_UP)
        ans = f"{mant:f} × 10^{e}"
        steps = ["rule: write a × 10^n with 1 ≤ |a| < 10",
                 f"known: {xs}", f"substitute: move the decimal point {abs(e)} place{'s' if abs(e) != 1 else ''} "
                 f"{'left' if e > 0 else 'right'}, so n = {e}"]
        return _sol("scientific notation", m.raw, steps, ans, f"check: {mant:f} × 10^{e} = {mant.scaleb(e):f}")
    fr = re.search(rf"(-?{N})\s*(?:\*|x|times)\s*10\s*(?:\^|\*\*)\s*(-?\d+)\s*(?:in|to|into|as)\s+(?:standard|decimal|"
                   r"ordinary|normal)\s*(?:form|notation|number)?", t) or \
        re.search(rf"(-?{N})e(-?\d+)\s*(?:in|to|into|as)\s+(?:standard|decimal|ordinary|normal)", t)
    if fr:
        a, e = Decimal(fr.group(1).replace(",", "")), int(fr.group(2))
        r = a.scaleb(e)
        out = f"{r:,f}"
        steps = ["rule: a × 10^n: move the decimal point n places (right if n > 0, left if n < 0)",
                 f"known: a = {fr.group(1)}, n = {e}", f"substitute: {out}"]
        return _sol("scientific notation", m.raw, steps, out)
    return None


# ---------------------------------------------------------------- arithmetic and fractions

PREFIX = re.compile(r"^(?:(?:so|ok|okay|and|now|also|hey|hi)\s+)*(?:what(?:'s| is| are)|whats|calc(?:ulate)?|compute|evaluate|"
                    r"work out|figure out|solve|simplify|find|tell me|do|how much is|what does|what do)\s+(?:the\s+)?"
                    r"(?:value of\s+|answer to\s+|result of\s+)?")
FRACW = rf"(?:\d+\s+\d+/\d+|{N}/{N}|-?{N})"


def _words_ops(t: str) -> str:
    A = rf"({FRACW})"
    rules = [(rf"\badd\s+{A}\s+(?:and|to|with)\s+{A}", r"(\1) + (\2)"),
             (rf"\bsum of\s+{A}\s+and\s+{A}", r"(\1) + (\2)"),
             (rf"\bsubtract\s+{A}\s+from\s+{A}", r"(\2) - (\1)"),
             (rf"\btake\s+{A}\s+(?:away\s+)?from\s+{A}", r"(\2) - (\1)"),
             (rf"\bdifference between\s+{A}\s+and\s+{A}", r"(\1) - (\2)"),
             (rf"\bmultiply\s+{A}\s+(?:by|and|with|times)\s+{A}", r"(\1) * (\2)"),
             (rf"\bproduct of\s+{A}\s+and\s+{A}", r"(\1) * (\2)"),
             (rf"\bdivide\s+{A}\s+(?:by|into)\s+{A}", r"(\1) / (\2)"),
             (rf"\bquotient of\s+{A}\s+and\s+{A}", r"(\1) / (\2)"),
             (rf"\b{A}\s+of\s+{A}\b", r"(\1) * (\2)")]
    for p, r in rules:
        t = re.sub(p, r, t)
    t = re.sub(r"\bdivided by\b|\binto\b(?=\s*\d)", " div ", t)
    t = re.sub(r"\bover\b", "/", t)
    t = re.sub(r"\bmultiplied by\b|\btimes\b|(?<=[\d)\s])x(?=[\s\d(])", "*", t)
    t = re.sub(r"\bplus\b|\band\b", "+", t)
    t = re.sub(r"\bminus\b|\bless\b", "-", t)
    t = re.sub(r"\bto the power of\b|\braised to\b", "^", t)
    t = re.sub(r"\bsquared\b", "^2", t)
    t = re.sub(r"\bcubed\b", "^3", t)
    return t


class _Ev:
    def __init__(self, nums):
        self.nums, self.steps = nums, []

    def ev(self, node):
        if isinstance(node, ast.Expression):
            return self.ev(node.body)
        if isinstance(node, ast.Name) and node.id in self.nums:
            return self.nums[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            v = self.ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.BinOp):
            a, b = self.ev(node.left), self.ev(node.right)
            op = node.op
            if isinstance(op, ast.Add):
                r, s = a + b, "+"
            elif isinstance(op, ast.Sub):
                r, s = a - b, "−"
            elif isinstance(op, ast.Mult):
                r, s = a * b, "×"
            elif isinstance(op, ast.Div):
                r, s = a / b, "÷"
            elif isinstance(op, ast.Pow):
                if b.denominator != 1 or abs(b) > 400 or abs(a.numerator) > 10 ** 50:
                    raise ValueError("power too large")
                r, s = a ** int(b), "^"
            else:
                raise ValueError("operator")
            if s == "÷" and isinstance(node.left, ast.Name) and isinstance(node.right, ast.Name) and \
                    r.denominator != 1 and a.denominator == b.denominator == 1:
                return r  # a written fraction such as 3/4: nothing to show
            line = f"{_fr(a)} {s} {_fr(b)}"
            if s in "+−" and (a.denominator != 1 or b.denominator != 1) and a.denominator != b.denominator:
                d = math.lcm(a.denominator, b.denominator)
                line += f" = {a.numerator * d // a.denominator}/{d} {s} {b.numerator * d // b.denominator}/{d}"
            if s == "÷" and b.denominator != 1:
                line += f" = {_fr(a)} × {b.denominator}/{b.numerator}"
            self.steps.append(f"{line} = {_fr(r)}")
            return r
        raise ValueError("not arithmetic")


def _fr(x: F) -> str:
    if x.denominator == 1:
        return f"{x.numerator:,}"
    s = _ok(x).split(" = ")[0].split(" ≈ ")[0]
    return s if "/" in s else f"{x.numerator}/{x.denominator}"


def arithmetic(m: Msg) -> Solution | None:
    t = PREFIX.sub("", m.t)
    t = re.sub(r"\s*(?:=\s*\??|\?+)\s*$", "", t).strip()
    t = re.sub(r"\b(?:as a mixed number|as a decimal|in decimal|exactly|exact|reduced|simplified|pls|then reduce)\b",
               "", t).strip(" ,.")
    t = _words_ops(t)
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)
    t = re.sub(r"(?<![\d./])(\d+)\s+(\d+)/(\d+)(?![\d.])", r"(\1+\2/\3)", t)  # mixed numbers
    t = re.sub(r"(?<![\d.)])(\d+)/(\d+)(?![\d.(])", r"(\1/\2)", t)
    t = re.sub(r"\s*\bdiv\b\s*", " / ", t)
    t = t.replace("^", "**").replace("[", "(").replace("]", ")")
    if not re.fullmatch(r"[\d\s.+\-*/()]+", t) or not re.search(r"\d\s*(?:[-+*/]|\*\*)\s*[-(\d.]", t):
        return None
    nums = {}

    def sub(mo):
        k = f"n{len(nums)}"
        nums[k] = F(mo.group(0))
        return k

    expr = re.sub(r"\d+(?:\.\d+)?|\.\d+", sub, t)
    ev = _Ev(nums)
    r = ev.ev(ast.parse(expr, mode="eval"))
    shown = re.sub(r"n(\d+)", lambda mo: _dec(nums[f"n{mo.group(1)}"]), expr).replace("**", "^").replace("*", "×")
    shown = shown.replace("/", "÷") if not re.search(r"\d/\d", t) or " / " in t else shown
    ans = _ok(r)
    if r.denominator != 1 and "/" not in ans and re.search(r"\d/\d", t):  # fractions in, fraction out
        w = abs(r.numerator) // r.denominator
        mixed = f" = {'-' if r < 0 else ''}{w} {abs(r) - w}" if w else ""
        ans = f"{r.numerator}/{r.denominator}{mixed} = {_dec(r)}"
    if m.sig or m.dp is not None:
        ans = (ans.split(" ≈ ")[0] + " ≈ " if r.denominator != 1 and "≈" in ans else "") + m.finish(float(r))
        if r.denominator == 1 and not m.sig:
            ans = _ok(r)
    if abs(r) >= 10 ** 12:
        ans += f" ≈ {float(r):.4e}".replace("e+", " × 10^")
    steps = [f"expression: {shown}", "rule: brackets, powers, then × and ÷, then + and − (left to right)"]
    steps += [f"step: {s}" for s in ev.steps]
    chk = ""
    tree = ast.parse(expr, mode="eval").body
    if isinstance(tree, ast.BinOp) and isinstance(tree.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        b = _Ev(nums).ev(tree.right)
        if isinstance(tree.op, ast.Add):
            chk = f"check: {_fr(r)} − {_fr(b)} = {_fr(r - b)}"
        elif isinstance(tree.op, ast.Sub):
            chk = f"check: {_fr(r)} + {_fr(b)} = {_fr(r + b)}"
        elif isinstance(tree.op, ast.Mult) and b != 0:
            chk = f"check: {_fr(r)} ÷ {_fr(b)} = {_fr(r / b)}"
        elif isinstance(tree.op, ast.Div):
            chk = f"check: {_fr(r)} × {_fr(b)} = {_fr(r * b)}"
    return _sol("arithmetic", m.raw, steps, ans, chk)


# ---------------------------------------------------------------- entry

NOT_MATH = re.compile(r"\b(incidents?|alerts?|sensitivity|signups?|checkout|latency|errors?|metrics?|dashboard|chart|"
                      r"connect|datadog|switch|mark|false alarm|break down|explain|spike[sd]?|anomal\w*|deploy)\b|#\d")
HANDLERS = [uptime, scientific, rounding, convert, rates, percentages, ratios, roots, arithmetic]


def solve(text: str) -> Solution | None:
    """An everyday arithmetic / percent / units problem solved with steps, or None when the message isn't one."""
    if not text or len(text) > 600 or not re.search(r"\d", text):
        return None
    m = Msg(text)
    if NOT_MATH.search(m.t) and not re.search(r"\b(uptime|slo|sla|availability|backlog|queue)\b", m.t):
        return None
    if re.match(r"(?:what(?:'s| is)|whats|define|explain)\s+(?:a|an|the)\s+[a-z]", m.t) and not re.search(r"\d", m.t[:30]) \
            and not re.search(rf"{N}\s*%|\b(uptime|availability|slo|sla|downtime)\b.*\d", m.t):
        return None
    for h in HANDLERS:
        try:
            sol = h(m)
        except (ValueError, ZeroDivisionError, ArithmeticError, SyntaxError, KeyError, TypeError, IndexError,
                RecursionError):
            sol = None
        if sol is not None:
            return sol
    return None
