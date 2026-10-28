"""Geometry and trigonometry word problems in plain English, answered exactly (π and √ kept) with worked steps.

"area of a rectangle 8 by 5", "triangle with sides 5, 6 and 7, area?", "a tank 3 ft across and 4 ft deep holds how
much", "hypotenuse is 17 and one short side is 8", "volume of a ball of radius 3 in", "sin 60°", "a 10 m ladder leans
at 60° to the ground, how high does it reach", "each interior angle of a regular hexagon", "convert 2π/3 to degrees".

What it reads
  plane      squares, rectangles, triangles (base/height, three sides by Heron, equilateral), circles (from radius,
             diameter, circumference or area), trapezoids, parallelograms, rhombi, sectors and arcs, annuli, diagonals
  solids     cubes, cuboids (boxes, tanks, rooms), cylinders, cones, spheres, hemispheres, square/rectangular pyramids:
             volume (also "holds", litres), surface area, curved area
  triangles  Pythagoras (hypotenuse or a missing leg), similar-triangle scaling, ladders, angles of elevation and
             depression, shadows
  angles     sin / cos / tan exact values, degrees <-> radians, polygon angle sums, regular-polygon angles, wheels

Each reader fires only when the message names its shape or setting and gives the numbers it needs, so Kepler commands
("is signups ok", "switch payments to area") and definition questions ("what is a derivative") return None.
"""
import re

import sympy as sp

from ..fields import money
from ..reasoning import Solution

N = r"(?:\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)"
_UNIT_NAMES = {"mm": "mm", "millimetre": "mm", "millimeter": "mm", "cm": "cm", "centimetre": "cm", "centimeter": "cm",
               "km": "km", "kilometre": "km", "kilometer": "km", "m": "m", "metre": "m", "meter": "m", "in": "in",
               "inch": "in", "inches": "in", "ft": "ft", "feet": "ft", "foot": "ft", "yd": "yd", "yard": "yd",
               "mi": "mi", "mile": "mi", "unit": "units", "units": "units"}
_TO_M = {"mm": sp.Rational(1, 1000), "cm": sp.Rational(1, 100), "m": 1, "km": 1000, "in": sp.Rational(254, 10000),
         "ft": sp.Rational(3048, 10000), "yd": sp.Rational(9144, 10000), "mi": sp.Rational(1609344, 1000)}
U = (r"(?:millimet(?:er|re)s?|centimet(?:er|re)s?|kilomet(?:er|re)s?|met(?:er|re)s?|inch(?:es)?|feet|foot|ft|yards?|yd|"
     r"miles?|units?|mm|cm|km|m(?![a-z])|mi(?![a-z])|in(?=\s*(?:$|[.,;:?!)^]|and\b|by\b|x\b|tall|high|long|wide|deep|"
     r"across|radius|diameter|side|base|height|edge|squared|cubed|sq|cubic|ladder|pole|shadow|-)))")
_PI = r"(?:pi|π)"

KEYWORDS = re.compile(
    r"\b(?:area|perimeter|circumference|radius|radii|diameter|volume|surface|square|rectangle|rectangular|oblong|triangle|"
    r"triangular|circle|circular|trapezoid|trapezium|parallelogram|rhombus|sector|arc|annulus|ring|washer|diagonal|"
    r"hypotenuse|pythag\w*|legs?|cube|cuboid|box|prism|cylinder|cylindrical|can|pipe|tank|cone|sphere|ball|globe|"
    r"hemisphere|dome|bowl|pyramid|sin|cos|tan|sine|cosine|tangent|sec|csc|cot|radians?|degrees?|ladder|elevation|"
    r"depression|shadow|polygon|\w+gon|interior|exterior|wheel|tyre|tire|similar|equilateral|isosceles|scalene|"
    r"angle|holds?|capacity|fence|fencing|slant|room|pool|aquarium|brick|garden|field|lawn|plot|pizza|kite|"
    r"right[- ]angled?)\b|°")
_BAD = re.compile(r"\b(?:incidents?|signups?|alerts?|sensitivity|latency|errors?|checkout\w*|payments?|#\d+|"
                  r"false alarm|connect|datadog|chart|break down|mute|threshold|metric|dashboard)\b")


class _Ctx:
    def __init__(self, text: str, t: str):
        self.text, self.t = text, t
        self.sf: int | None = None
        self.dp: int | None = None
        self.frac = False
        self.price: sp.Rational | None = None
        self.cur = "$"
        self.price_dim = ""
        self.unit = ""


def R(s: str) -> sp.Rational:
    return sp.Rational(s.replace(",", ""))


# ---------------------------------------------------------------- formatting

def ex(e) -> str:
    """Exact form: 36π, 6√2, 25√3/2, π/3."""
    s = sp.sstr(e)
    s = s.replace("pi", "π")
    s = re.sub(r"sqrt\((\d+|π)\)", r"√\1", s)
    s = re.sub(r"sqrt\(", "√(", s)
    s = re.sub(r"\*\*", "^", s)
    s = re.sub(r"(?<=[\dπ)])\*(?=[π√(])", "", s)
    s = re.sub(r"(?<=[√\d])\*(?=π)", "", s)
    return s.replace("*", "·")


def dec(c: _Ctx, x, default_dp: int = 2) -> str:
    x = float(x)
    if c.sf:
        s = f"{x:.{c.sf}g}"
        if "e" not in s and abs(x) >= 1000:
            s = f"{x:,.{max(0, c.sf - len(str(int(abs(x)))))}f}"
        return s
    dp = c.dp if c.dp is not None else default_dp
    if x != 0 and abs(x) < 10 ** -dp * 5:
        return f"{x:.4g}"
    return f"{x:,.{dp}f}"


def _terminates(q: sp.Rational) -> bool:
    d = int(q.q)
    for p in (2, 5):
        while d % p == 0:
            d //= p
    return d == 1


def _places(q: sp.Rational) -> int:
    """Decimal places a terminating fraction needs exactly: 225/4 → 2, 1/8 → 3."""
    d, k2, k5 = int(q.q), 0, 0
    while d % 2 == 0:
        d, k2 = d // 2, k2 + 1
    while d % 5 == 0:
        d, k5 = d // 5, k5 + 1
    return max(k2, k5)


def show(c: _Ctx, e, unit: str = "", default_dp: int = 2) -> str:
    """The value with its unit: exact where it differs from the decimal, then ≈ decimal."""
    e = sp.nsimplify(sp.simplify(e)) if not isinstance(e, (int, sp.Integer)) else sp.Integer(e)
    u = f" {unit}" if unit else ""
    trig = e.has(sp.sin, sp.cos, sp.tan, sp.asin, sp.acos, sp.atan)
    if e.is_Rational:
        if e.is_Integer:
            return f"{int(e):,}{u}"
        if _terminates(e) and not c.frac and c.sf is None and c.dp is None:
            return f"{float(e):,.{_places(e)}f}".rstrip("0").rstrip(".") + u
        if c.frac:
            return f"{e}{u} ≈ {dec(c, e, default_dp)}{u}"
        if _terminates(e):
            return f"{dec(c, e, default_dp)}{u}"
        return f"{e}{u} ≈ {dec(c, e, default_dp)}{u}"
    neg_pi = any(p.base.has(sp.pi) and p.exp.is_negative for p in e.atoms(sp.Pow)) or e.has(sp.sqrt(sp.pi))
    if trig or neg_pi or len(ex(e)) > 28:
        return f"≈ {dec(c, e, default_dp)}{u}".removeprefix("≈ ")
    return f"{ex(e)}{u} ≈ {dec(c, e, default_dp)}{u}"


def deg_show(c: _Ctx, e) -> str:
    e = sp.nsimplify(sp.simplify(e))
    if e.is_Rational:
        return show(c, e) + "°"
    return f"{dec(c, e)}°"


def _sol(c: _Ctx, kind: str, formula: str, knowns: list[str], sub: str, answer: str, check: str = "",
         value=None, dim: str = "") -> Solution:
    steps = [f"formula: {formula}", "known: " + ", ".join(knowns), f"substitute: {sub}", f"result: {answer}"]
    if c.price is not None and value is not None:
        total = sp.N(value * c.price, 30)
        steps.append(f"cost: {dec(c, value)} {dim} × {c.cur}{money(float(c.price))} = {c.cur}{money(float(total))}")
        answer = f"{c.cur}{money(float(total))}"
    return Solution(kind, c.text, answer, steps, check=check, confidence=0.97)


# ---------------------------------------------------------------- reading

def _strip(text: str) -> _Ctx:
    t = " " + text.lower() + " "
    for a, b in (("’", "'"), ("×", " x "), ("−", "-"), ("–", "-"), ("—", " - "), ("²", "^2"), ("³", "^3"),
                 ("º", "°"), ("√", "sqrt"), (" ", " ")):
        t = t.replace(a, b)
    c = _Ctx(text, t)
    m = re.search(r"\b(\d+)\s*(?:sig(?:nificant)?\.?\s*(?:figs?|figures|digits)|s\.?f\.?(?![a-z]))", t)
    if m:
        c.sf = max(1, min(12, int(m.group(1))))
        t = t.replace(m.group(0), " ")
    m = re.search(r"\b(?:to\s+)?(\d+)\s*(?:d\.?p\.?(?![a-z])|decimal(?:\s+places?|s)?|places)", t)
    if m:
        c.dp = min(10, int(m.group(1)))
        t = t.replace(m.group(0), " ")
    m = re.search(r"\b(?:to\s+the\s+)?nearest\s+(whole|tenth|hundredth|thousandth)", t)
    if m:
        c.dp = {"whole": 0, "tenth": 1, "hundredth": 2, "thousandth": 3}[m.group(1)]
        t = t.replace(m.group(0), " ")
    if re.search(r"\bfraction\b", t):
        c.frac = True
    m = re.search(rf"([$£€₹]|\brs\.?)\s*({N})\s*(?:per|/|a|an|for each|each)\s*(square|sq\.?|cubic)?\s*({U})?", t) or \
        re.search(rf"\b({N})\s*(dollars?|pounds?|euros?|rupees?)\s*(?:per|/|a|an|for each)\s*(square|sq\.?|cubic)?\s*({U})?", t)
    if m:
        cur = m.group(1)
        c.cur = {"rs": "₹", "rs.": "₹"}.get(cur, cur) if not cur[0].isdigit() else "$"
        if cur[0].isdigit():
            c.price, c.cur = R(cur), {"d": "$", "p": "£", "e": "€", "r": "₹"}[m.group(2)[0]]
        else:
            c.price = R(m.group(2))
        c.price_dim = m.group(3) or ""
        t = t.replace(m.group(0), " per-unit ")
    c.t = re.sub(r"\s+", " ", t)
    um = re.search(rf"\b(?:sq\.?|square|cubic)\s+({U})", c.t) or re.search(rf"{N}\s*(?:{_PI}\s*)?({U})", c.t) or re.search(rf"\b(?:in|of)\s+({U})\b", c.t)
    if um:
        key = um.group(1).rstrip("s") if um.group(1) not in _UNIT_NAMES else um.group(1)
        c.unit = _UNIT_NAMES.get(key, _UNIT_NAMES.get(um.group(1), ""))
        if c.unit == "units":
            c.unit = ""
    return c


_DIMWORDS = (r"radius|radii|diameter|height|high|tall|deep|depth|length|long|width|wide|breadth|side|sides|edge|base|"
             r"bases|slant|hypotenuse|leg|circumference|area|perimeter|diagonal|volume|arc|angle|inner|outer|apothem|"
             r"distance|away|far|shadow|ladder|by|and")


def _pi_mult(t: str, end: int):
    """π when the number ending at `end` is written as a multiple of π ("81π", "16 pi"), else 1."""
    return sp.pi if re.match(rf"\s*\*?\s*{_PI}\b(?!\s*/)", t[end:]) else 1


def lab(c: _Ctx, names: str, t: str | None = None, back_first: bool = False):
    """A number tied to one of `names`: "radius 5", "radius of the base is 5 cm", "5 cm radius", "r = 5", "area 81π"."""
    t = c.t if t is None else t
    if back_first:
        m = re.search(rf"({N})\s*(?:{U})?\s*(?:{names})\b", t)
        if m:
            return R(m.group(1))
    m = re.search(rf"\b(?:{names})\b((?:(?!\b(?:{_DIMWORDS})\b)[^\d.,;?!])" r"{0,30}?)" rf"({N})(?!\.?\d)(?!\s*(?:°|deg|rad))", t)
    if m and not re.search(rf"\b(?:{_DIMWORDS})\b", m.group(1)):
        return R(m.group(2)) * _pi_mult(t, m.end(2))
    m = re.search(rf"({N})\s*(?:{U})?\s*(?:\^?[23]\s*)?(?:{names})\b", t)
    if m:
        return R(m.group(1))
    return None


def letter(c: _Ctx, ch: str):
    m = re.search(rf"\b{ch}\s*(?:=|:|is)\s*({N})", c.t)
    return R(m.group(1)) if m else None


def numbers(t: str) -> list[sp.Rational]:
    t = re.sub(rf"{N}\s*(?:°|deg(?:rees?)?\b)", " ", t)
    return [R(x) for x in re.findall(N, t)]


def asks(c: _Ctx, pat: str) -> bool:
    return re.search(rf"\b(?:{pat})", c.t) is not None


def angle_deg(t: str):
    """The angle in the message, in degrees (exact): 60°, 45 degrees, π/3, 2pi/3 rad, 1.2 radians."""
    m = re.search(rf"({N})\s*(?:°|deg(?:rees?|s)?\b)", t)
    if m:
        return R(m.group(1)), "deg", m
    m = re.search(rf"(?:\b({N})\s*\*?\s*)?{_PI}(?:\s*/\s*({N}))?(?:\s*(?:rad(?:ians?|s)?|c)\b)?", t)
    if m and (m.group(1) or m.group(2) or re.search(r"\brad", t)):
        r = (R(m.group(1)) if m.group(1) else 1) * sp.pi / (R(m.group(2)) if m.group(2) else 1)
        return sp.simplify(r * 180 / sp.pi), "rad", m
    m = re.search(rf"({N})\s*(?:rad(?:ians?|s)?)\b", t)
    if m:
        return R(m.group(1)) * 180 / sp.pi, "rad", m
    return None


def _u(c: _Ctx, p: int = 1) -> str:
    if not c.unit:
        return {1: "units", 2: "square units", 3: "cubic units"}[p]
    return c.unit + {1: "", 2: "²", 3: "³"}[p]


# ---------------------------------------------------------------- angles

def convert(c: _Ctx) -> Solution | None:
    t = c.t
    if not re.search(r"\bradians?\b|\brad\b", t) or not re.search(r"\bdeg|°|\bconvert|\bin\b|\bto\b", t):
        return None
    if re.search(r"\b(?:sin|cos|tan|sine|cosine|tangent|arc|sector|wheel)\b", t):
        return None
    m = re.search(rf"({N})\s*(?:°|deg(?:rees?|s)?\b)", t)
    if m and re.search(r"(?:to|in|into|as)\s+rad", t):
        d = R(m.group(1))
        r = d * sp.pi / 180
        return _sol(c, "trigonometry", "radians = degrees × π / 180", [f"{show(c, d)}°"], f"{show(c, d)} × π / 180",
                    f"{show(c, r, 'rad', 4)}", f"{ex(r)} × 180 / π = {show(c, d)}° ✓")
    a = angle_deg(t)
    if a and a[1] == "rad":
        d = a[0]
        r = d * sp.pi / 180
        return _sol(c, "trigonometry", "degrees = radians × 180 / π", [f"{ex(sp.nsimplify(r))} rad"],
                    f"{ex(sp.nsimplify(r))} × 180 / π", deg_show(c, d), f"{deg_show(c, d)} × π / 180 = {ex(sp.nsimplify(r))} ✓")
    return None


_POLY = {"triangle": 3, "quadrilateral": 4, "pentagon": 5, "hexagon": 6, "heptagon": 7, "septagon": 7, "octagon": 8,
         "nonagon": 9, "enneagon": 9, "decagon": 10, "hendecagon": 11, "undecagon": 11, "dodecagon": 12, "icosagon": 20}


def polygon(c: _Ctx) -> Solution | None:
    t = c.t
    if not re.search(r"\bangles?\b|\bsides?\b", t) or not re.search(r"interior|exterior|inside|sum|each|regular|total|"
                                                                    r"add up|how many sides", t):
        return None
    if re.search(r"\b(?:sin|cos|tan|ladder|elevation)\b|°.*\b(?:side|opposite|adjacent)\b.*\d", t) and "polygon" not in t:
        if not re.search(r"how many sides", t):
            return None
    n = None
    m = re.search(rf"\b({N})[- ]?(?:sided|gon)\b", t) or re.search(rf"\bpolygon (?:with|that has|having) ({N}) sides", t) \
        or re.search(rf"\b({N}) sides\b", t)
    if m:
        n = int(R(m.group(1)))
    else:
        for w, k in _POLY.items():
            if re.search(rf"\b{w}s?\b", t):
                n = k
                break
    if re.search(r"how many sides", t):
        m = re.search(rf"({N})\s*(?:°|deg)", t)
        if not m:
            return None
        a = R(m.group(1))
        if re.search(r"exterior", t):
            k = sp.Rational(360) / a
            return _sol(c, "geometry", "n = 360° / exterior angle", [f"exterior angle = {show(c, a)}°"],
                        f"n = 360 / {show(c, a)}", f"{show(c, k)} sides" if k.is_Integer else "no regular polygon has that angle",
                        f"360 / {show(c, k)} = {show(c, a)}° ✓" if k.is_Integer else "")
        if a >= 180:
            return None
        k = sp.Rational(360) / (180 - a)
        return _sol(c, "geometry", "each exterior angle = 180° − interior; n = 360° / exterior",
                    [f"interior angle = {show(c, a)}°"], f"n = 360 / (180 − {show(c, a)}) = 360 / {show(c, 180 - a)}",
                    f"{show(c, k)} sides" if k.is_Integer else "no regular polygon has that angle",
                    f"({show(c, k)} − 2) × 180 / {show(c, k)} = {show(c, (k - 2) * 180 / k)}° ✓" if k.is_Integer else "")
    if n is None or n < 3 or n > 10 ** 6:
        return None
    total = (n - 2) * 180
    if re.search(r"exterior", t):
        if re.search(r"sum|total|add up", t):
            return _sol(c, "geometry", "exterior angles of any convex polygon sum to 360°", [f"n = {n}"], "360°", "360°")
        e = sp.Rational(360, n)
        return _sol(c, "geometry", "each exterior angle = 360° / n", [f"n = {n}"], f"360 / {n}", deg_show(c, e),
                    f"interior + exterior = {deg_show(c, sp.Rational(total, n))} + {deg_show(c, e)} = 180° ✓")
    if re.search(r"\beach\b|\bone\b|\bevery\b|\bsingle\b|regular", t) and not re.search(r"\bsum\b|\btotal\b|add up", t):
        e = sp.Rational(total, n)
        return _sol(c, "geometry", "each interior angle = (n − 2) × 180° / n", [f"n = {n} (regular)"],
                    f"({n} − 2) × 180 / {n} = {total} / {n}", deg_show(c, e),
                    f"{n} × {deg_show(c, e)} = {total}° ✓")
    return _sol(c, "geometry", "sum of interior angles = (n − 2) × 180°", [f"n = {n}"], f"({n} − 2) × 180",
                f"{total:,}°", f"split into {n - 2} triangles of 180° each ✓")


_FN = {"sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "sine": sp.sin, "cosine": sp.cos, "tangent": sp.tan,
       "sec": sp.sec, "csc": sp.csc, "cosec": sp.csc, "cot": sp.cot, "secant": sp.sec, "cosecant": sp.csc,
       "cotangent": sp.cot}


def trig_value(c: _Ctx) -> Solution | None:
    t = c.t
    m = re.search(r"\b(sine|cosine|tangent|secant|cosecant|cotangent|sin|cos|tan|sec|cosec|csc|cot)\b\s*(?:of\s*)?\(?\s*"
                  rf"(-?\s*(?:{N}\s*\*?\s*)?{_PI}(?:\s*/\s*{N})?|-?\s*{N}(?:\s*/\s*{N})?)\s*"
                  r"(°|deg(?:rees?|s)?\b|rad(?:ians?|s)?\b)?\s*\)?", t)
    if not m or re.search(r"\b(?:ladder|shadow|elevation|depression|triangle|opposite|adjacent|hypotenuse)\b", t):
        return None
    if re.search(r"\^\s*-\s*1|\b(?:inverse|arc(?:sin|cos|tan)|asin|acos|atan)\b|=", t):
        return None
    if re.match(r"\s*(?:[-+*/^]|plus|minus|times)\s*\S", t[m.end():]) or re.search(r"[-+*/]\s*$", t[:m.start()]):
        return None
    name, raw, u = m.group(1), m.group(2).replace(" ", ""), m.group(3) or ""
    neg = raw.startswith("-")
    raw = raw.lstrip("-")
    if re.search(_PI, raw) or u.startswith("rad"):
        if re.search(_PI, raw):
            pm = re.match(rf"({N})?\*?{_PI}(?:/({N}))?", raw)
            r = (R(pm.group(1)) if pm.group(1) else 1) * sp.pi / (R(pm.group(2)) if pm.group(2) else 1)
        else:
            r = sp.Rational(raw) if "/" not in raw else R(raw.split("/")[0]) / R(raw.split("/")[1])
        if neg:
            r = -r
        label = f"{ex(r)} rad"
    else:
        d = R(raw) if "/" not in raw else R(raw.split("/")[0]) / R(raw.split("/")[1])
        if neg:
            d = -d
        r = d * sp.pi / 180
        label = f"{show(c, d)}°"
    fn = _FN[name]
    short = {"sine": "sin", "cosine": "cos", "tangent": "tan", "secant": "sec", "cosecant": "csc", "cosec": "csc",
             "cotangent": "cot"}.get(name, name)
    val = sp.simplify(fn(r))
    if val.has(sp.zoo) or val is sp.zoo or val is sp.nan:
        return _sol(c, "trigonometry", f"{short}(θ)", [f"θ = {label}"], f"{short}({label})", "undefined",
                    f"{short} has an asymptote at {label}")
    rule = {"sin": "opposite / hypotenuse", "cos": "adjacent / hypotenuse", "tan": "opposite / adjacent = sin/cos"}.get(
        short, f"reciprocal of {'cos' if short == 'sec' else 'sin' if short == 'csc' else 'tan'}")
    sub = f"{short}({label})" + ("" if label.endswith("rad") else f" = {short}({ex(r)} rad)")
    ans = show(c, val, "", 4)
    chk = ""
    if short in ("sin", "cos"):
        other = sp.simplify((sp.cos if short == "sin" else sp.sin)(r))
        chk = f"sin² + cos² = {ex(sp.nsimplify(sp.simplify(sp.sin(r) ** 2)))} + {ex(sp.nsimplify(sp.simplify(sp.cos(r) ** 2)))} = 1 ✓" \
            if not val.has(sp.sin, sp.cos) and not other.has(sp.sin, sp.cos) else ""
    return _sol(c, "trigonometry", f"{short}(θ) = {rule}", [f"θ = {label}"], sub, ans, chk)


# ---------------------------------------------------------------- right triangles in words

def right_words(c: _Ctx) -> Solution | None:
    t = c.t
    if not re.search(r"\b(?:ladder|elevation|depression|shadow|kite|guy wire|wire|cable|ramp|string)\b", t):
        return None
    a = angle_deg(t)
    u = c.unit
    uu = u or "units"
    askang = re.search(r"\b(?:what|find|calculate|whats|what's)\b[^.?]*\bangle\b|\bangle\b[^.?]*\?|\bangle of (?:elevation|depression)\b(?![^.?,]*\d)", t) and not a
    if "ladder" in t or re.search(r"\b(?:kite|wire|cable|ramp|string)\b", t):
        L = lab(c, r"ladder|string|wire|cable|ramp|long")
        if L is None:
            nums = numbers(t)
            L = nums[0] if nums else None
        if L is None:
            return None
        if a:
            th = a[0] * sp.pi / 180
            wall = re.search(r"(?:with|from|to|and) the wall", t) and not re.search(r"(?:with|to|and) the (?:ground|floor|horizontal)", t)
            want_base = re.search(r"how far|distance|foot|bottom|base|away from", t) and not re.search(r"how (?:high|far up|tall)|height|reach", t)
            if want_base:
                val = L * (sp.sin(th) if wall else sp.cos(th))
                f = "base = L · sin(θ), θ with the wall" if wall else "base = L · cos(θ), θ with the ground"
            else:
                val = L * (sp.cos(th) if wall else sp.sin(th))
                f = "height = L · cos(θ), θ with the wall" if wall else "height = L · sin(θ), θ with the ground"
            return _sol(c, "trigonometry", f, [f"L = {show(c, L, uu)}", f"θ = {deg_show(c, a[0])}"],
                        f"{show(c, L)} × {'cos' if ('cos' in f) else 'sin'}({deg_show(c, a[0])})", show(c, val, uu),
                        f"base² + height² = L²: {dec(c, (L * sp.cos(th)) ** 2)} + {dec(c, (L * sp.sin(th)) ** 2)} = {dec(c, L ** 2)} ✓")
        foot = lab(c, r"from the wall|from the base|away|foot|bottom|distance")
        hgt = lab(c, r"height|high|up the wall|reaches|reach|tall")
        rest = [x for x in numbers(t) if x != L]
        if askang and rest:
            o = hgt if hgt is not None else None
            if o is not None:
                ang = sp.asin(o / L) * 180 / sp.pi
                return _sol(c, "trigonometry", "θ = sin⁻¹(height / L)", [f"L = {show(c, L, uu)}", f"height = {show(c, o, uu)}"],
                            f"sin⁻¹({show(c, o)} / {show(c, L)})", deg_show(c, ang) + " with the ground")
            d = foot if foot is not None else rest[0]
            ang = sp.acos(d / L) * 180 / sp.pi
            return _sol(c, "trigonometry", "θ = cos⁻¹(base / L)", [f"L = {show(c, L, uu)}", f"base = {show(c, d, uu)}"],
                        f"cos⁻¹({show(c, d)} / {show(c, L)})", deg_show(c, ang) + " with the ground")
        if rest and (foot is not None or hgt is not None or len(rest) == 1):
            known = foot if foot is not None else hgt if hgt is not None else rest[0]
            if known >= L:
                return None
            other = sp.sqrt(L ** 2 - known ** 2)
            return _sol(c, "geometry", "other side = √(L² − known²)  (Pythagoras)", [f"L = {show(c, L, uu)}", f"known side = {show(c, known, uu)}"],
                        f"√({show(c, L)}² − {show(c, known)}²) = √{show(c, L ** 2 - known ** 2)}", show(c, other, uu),
                        f"{show(c, known)}² + {dec(c, other)}² = {show(c, L)}² ✓")
        return None
    # elevation / depression / shadow
    h = lab(c, r"tall|high|height|feet tall|metres tall|meters tall|pole|tower|tree|building|cliff|person|man|woman|flagpole|lighthouse|post", back_first=True)
    s = lab(c, r"shadow", back_first=True)
    d = lab(c, r"away|from the (?:base|foot|bottom)|from it|distance|horizontal|from the (?:tree|tower|building|pole|cliff)")
    if d is None and s is not None:
        d = s
    if a:
        th = a[0] * sp.pi / 180
        want_h = re.search(r"how (?:tall|high)|height|find the (?:tree|tower|building|pole)", t)
        want_d = re.search(r"how (?:long|far)|length|distance|shadow", t) and not want_h
        nums = numbers(t)
        if want_d and h is None and len(nums) == 1:
            h = nums[0]
        if want_h and d is None and len(nums) == 1:
            d = nums[0]
        if want_h and d is not None and (h is None or h == d):
            val = d * sp.tan(th)
            return _sol(c, "trigonometry", "height = distance · tan(θ)", [f"distance = {show(c, d, uu)}", f"θ = {deg_show(c, a[0])}"],
                        f"{show(c, d)} × tan({deg_show(c, a[0])})", show(c, val, uu),
                        f"tan⁻¹({dec(c, val)} / {show(c, d)}) = {deg_show(c, a[0])} ✓")
        if want_d and h is not None:
            val = h / sp.tan(th)
            name = "shadow" if "shadow" in t else "distance"
            return _sol(c, "trigonometry", f"{name} = height / tan(θ)", [f"height = {show(c, h, uu)}", f"θ = {deg_show(c, a[0])}"],
                        f"{show(c, h)} / tan({deg_show(c, a[0])})", show(c, val, uu),
                        f"tan⁻¹({show(c, h)} / {dec(c, val)}) = {deg_show(c, a[0])} ✓")
        return None
    nums = numbers(t)
    if "shadow" in t and len(nums) >= 3 and not re.search(r"\bangle\b", t):
        # similar triangles: h1 / s1 = h2 / s2
        h1, s1, x = nums[0], nums[1], nums[2]
        want_h = re.search(r"how (?:tall|high)|height", t.split(",")[-1] if "," in t else t)
        if re.search(r"how (?:long|far)|length of (?:its|the) shadow|shadow\s*\?", t[t.rfind(re.findall(N, t)[-1]):]) and not want_h:
            val = x * s1 / h1
            return _sol(c, "geometry", "similar triangles: shadow₂ = height₂ × shadow₁ / height₁",
                        [f"height₁ = {show(c, h1, uu)}", f"shadow₁ = {show(c, s1, uu)}", f"height₂ = {show(c, x, uu)}"],
                        f"{show(c, x)} × {show(c, s1)} / {show(c, h1)}", show(c, val, uu),
                        f"{show(c, h1)}/{show(c, s1)} = {dec(c, x)}/{dec(c, val)} ✓")
        val = x * h1 / s1
        return _sol(c, "geometry", "similar triangles: height₂ = shadow₂ × height₁ / shadow₁",
                    [f"height₁ = {show(c, h1, uu)}", f"shadow₁ = {show(c, s1, uu)}", f"shadow₂ = {show(c, x, uu)}"],
                    f"{show(c, x)} × {show(c, h1)} / {show(c, s1)}", show(c, val, uu),
                    f"{show(c, h1)}/{show(c, s1)} = {dec(c, val)}/{show(c, x)} ✓")
    if askang or re.search(r"\bangle\b", t):
        if len(nums) >= 2:
            hh = h if h is not None else nums[0]
            dd = d if d is not None and d != hh else next((x for x in nums if x != hh), None)
            if dd is None:
                return None
            ang = sp.atan(hh / dd) * 180 / sp.pi
            name = "depression" if "depression" in t else "elevation"
            return _sol(c, "trigonometry", f"angle of {name} θ = tan⁻¹(height / horizontal distance)",
                        [f"height = {show(c, hh, uu)}", f"horizontal = {show(c, dd, uu)}"],
                        f"tan⁻¹({show(c, hh)} / {show(c, dd)})", deg_show(c, ang),
                        f"{show(c, dd)} × tan({deg_show(c, ang)}) = {dec(c, dd * sp.tan(ang * sp.pi / 180))} ✓")
    return None


# ---------------------------------------------------------------- triangles

def pythagoras(c: _Ctx) -> Solution | None:
    t = c.t
    if not re.search(r"hypotenuse|pythag|right[- ]?(?:angled?|triangle)|\blegs?\b|short sides?|\bright\b.*\btriangle", t):
        return None
    if re.search(r"\barea\b|\bperimeter\b", t) and not re.search(r"hypotenuse|missing|third|other side|longest", t):
        return None
    if re.search(r"\b(?:sin|cos|tan)\b|°", t) and not re.search(r"90\s*°", t):
        return None
    uu = c.unit or "units"
    tt = re.sub(r"\b90\s*(?:°|deg(?:rees?)?)", " ", t)
    c_ = lab(c, r"hypotenuse|hyp|longest side|long side|diagonal side", tt)
    nums = numbers(tt)
    if c_ is not None:
        legs = [x for x in nums if x != c_]
        if not legs:
            return None
        a = legs[0]
        if a >= c_:
            return None
        b = sp.sqrt(c_ ** 2 - a ** 2)
        return _sol(c, "geometry", "b = √(c² − a²)  (Pythagoras, c the hypotenuse)", [f"c = {show(c, c_, uu)}", f"a = {show(c, a, uu)}"],
                    f"b = √({show(c, c_)}² − {show(c, a)}²) = √{show(c, c_ ** 2 - a ** 2)}", show(c, b, uu),
                    f"{show(c, a)}² + {ex(b) if not b.is_Rational else show(c, b)}² = {show(c, a ** 2 + b ** 2)} = {show(c, c_)}² ✓")
    if len(nums) < 2:
        return None
    a, b = nums[0], nums[1]
    if re.search(r"missing|third|other|leg\b|shorter", t) and not re.search(r"hypotenuse|longest", t) and len(nums) >= 2:
        big, small = max(a, b), min(a, b)
        leg = sp.sqrt(big ** 2 - small ** 2)
        if re.search(r"\blegs?\b[^.?]*\b(?:are|of|is)\b", t):  # legs given → hypotenuse
            pass
        else:
            return _sol(c, "geometry", "b = √(c² − a²)  (Pythagoras, c the longest side)", [f"c = {show(c, big, uu)}", f"a = {show(c, small, uu)}"],
                        f"b = √({show(c, big)}² − {show(c, small)}²) = √{show(c, big ** 2 - small ** 2)}", show(c, leg, uu),
                        f"{show(c, small)}² + {ex(leg) if not leg.is_Rational else show(c, leg)}² = {show(c, big)}² ✓")
    h = sp.sqrt(a ** 2 + b ** 2)
    return _sol(c, "geometry", "c = √(a² + b²)  (Pythagoras)", [f"a = {show(c, a, uu)}", f"b = {show(c, b, uu)}"],
                f"c = √({show(c, a)}² + {show(c, b)}²) = √{show(c, a ** 2 + b ** 2)}", show(c, h, uu),
                f"{show(c, a)}² + {show(c, b)}² = {show(c, a ** 2 + b ** 2)} = ({ex(h) if not h.is_Rational else show(c, h)})² ✓")


def similar(c: _Ctx) -> Solution | None:
    t = c.t
    if not re.search(r"\bsimilar\b|\bscale(?:d| factor)\b|\benlarge", t):
        return None
    if not re.search(r"triangle|shape|figure|polygon|rectangle|square|pentagon|hexagon", t):
        return None
    uu = c.unit or "units"
    k = None
    m = re.search(rf"scale factor (?:of |is |=\s*)?({N})(?:\s*/\s*({N}))?", t) or re.search(rf"scaled (?:up |down )?by (?:a factor of )?({N})(?:\s*/\s*({N}))?", t)
    used: list[sp.Rational] = []
    if m:
        k = R(m.group(1)) / (R(m.group(2)) if m.group(2) else 1)
        used = [R(m.group(1))] + ([R(m.group(2))] if m.group(2) else [])
        src = f"scale factor k = {show(c, k)}"
    else:
        m = re.search(rf"({N})\s*(?:{U})?\s*(?::|to)\s*({N})", t) and re.search(rf"ratio[^\d]*({N})\s*(?::|to)\s*({N})", t)
        m = m or re.search(rf"({N})\s*(?:{U})?\s*(?:corresponds|matches|is matched) (?:to|with) (?:a |the )?(?:side (?:of )?)?({N})", t) \
            or re.search(rf"(?:corresponding )?sides? (?:of |are |measuring |is )?({N})\s*(?:{U})?\s*and\s*({N})", t) \
            or re.search(rf"side (?:of |is )?({N})\s*(?:{U})?[^\d]{{3,60}}?(?:corresponding|matching) side (?:of |is )?({N})", t)
        if not m:
            return None
        p, q = R(m.group(1)), R(m.group(2))
        k = q / p
        used = [p, q]
        src = f"k = {show(c, q)} / {show(c, p)} = {show(c, k)}"
    nums = numbers(t)
    for x in used:
        if x in nums:
            nums.remove(x)
    if asks(c, "area") and nums:
        a = lab(c, "area") or nums[0]
        if re.search(r"(?:larger|bigger)[^.?]*area[^.?]*\d[^?]*smaller|area of the smaller", t) and k > 1:
            val = a / k ** 2
            return _sol(c, "geometry", "areas scale by k²", [src, f"larger area = {show(c, a, _u(c, 2))}"],
                        f"{show(c, a)} / {show(c, k)}²", show(c, val, _u(c, 2)), f"{dec(c, val)} × {show(c, k ** 2)} = {show(c, a)} ✓")
        val = a * k ** 2
        return _sol(c, "geometry", "areas scale by k² (lengths by k)", [src, f"area = {show(c, a, _u(c, 2))}"],
                    f"{show(c, a)} × {show(c, k)}² = {show(c, a)} × {show(c, k ** 2)}", show(c, val, _u(c, 2)),
                    f"{dec(c, val)} / {show(c, a)} = {show(c, k ** 2)} = k² ✓")
    if asks(c, "volume") and nums:
        a = lab(c, "volume") or nums[0]
        val = a * k ** 3
        return _sol(c, "geometry", "volumes scale by k³", [src, f"volume = {show(c, a, _u(c, 3))}"],
                    f"{show(c, a)} × {show(c, k)}³", show(c, val, _u(c, 3)))
    if nums:
        x = lab(c, "perimeter") if asks(c, "perimeter") else None
        x = x if x is not None else nums[0]
        val = x * k
        return _sol(c, "geometry", "lengths scale by k", [src, f"length = {show(c, x, uu)}"], f"{show(c, x)} × {show(c, k)}",
                    show(c, val, uu), f"{dec(c, val)} / {show(c, x)} = {show(c, k)} ✓")
    return None


def triangle(c: _Ctx) -> Solution | None:
    t = c.t
    if not re.search(r"\btriang", t):
        return None
    u1, u2 = c.unit or "units", _u(c, 2)
    m = re.search(rf"sides?(?: lengths?)?(?: of| are| measuring| measure| with|:)?\s*({N})\s*(?:{U})?\s*,?\s*({N})\s*(?:{U})?\s*,?\s*(?:and\s*)?({N})", t) \
        or re.search(rf"({N})\s*(?:{U})?\s*,\s*({N})\s*(?:{U})?\s*,?\s*(?:and\s*)?({N})", t)
    if re.search(r"equilateral", t):
        s = lab(c, r"sides?|side length|edge") or (numbers(t) or [None])[0]
        if s is None:
            return None
        if asks(c, "perimeter"):
            return _sol(c, "geometry", "P = 3s", [f"s = {show(c, s, u1)}"], f"3 × {show(c, s)}", show(c, 3 * s, u1), value=3 * s, dim=u1)
        if asks(c, "height|altitude"):
            h = sp.sqrt(3) / 2 * s
            return _sol(c, "geometry", "h = (√3/2) · s", [f"s = {show(c, s, u1)}"], f"√3/2 × {show(c, s)}", show(c, h, u1),
                        f"({show(c, s / 2)})² + h² = {show(c, s)}² ✓")
        if asks(c, "area"):
            A = sp.sqrt(3) / 4 * s ** 2
            return _sol(c, "geometry", "A = (√3/4) · s²", [f"s = {show(c, s, u1)}"], f"√3/4 × {show(c, s)}² = √3/4 × {show(c, s ** 2)}",
                        show(c, A, u2), f"½ × base × height = ½ × {show(c, s)} × {ex(sp.sqrt(3) / 2 * s)} = {ex(A)} ✓", value=A, dim=u2)
        return None
    b = lab(c, r"base")
    h = lab(c, r"height|high|tall|altitude|perpendicular height")
    if asks(c, "area") and b is not None and h is not None:
        A = b * h / 2
        return _sol(c, "geometry", "A = ½ · base · height", [f"base = {show(c, b, u1)}", f"height = {show(c, h, u1)}"],
                    f"A = ½ × {show(c, b)} × {show(c, h)}", show(c, A, u2), f"2 × {show(c, A)} / {show(c, b)} = {show(c, h)} = height ✓", value=A, dim=u2)
    if m:
        a, b_, c3 = sorted([R(m.group(1)), R(m.group(2)), R(m.group(3))])
        if a + b_ <= c3:
            return Solution("geometry", c.text, "no such triangle", [f"{show(c, a)} + {show(c, b_)} ≤ {show(c, c3)}: the triangle inequality fails"],
                            confidence=0.95)
        if asks(c, "perimeter"):
            P = a + b_ + c3
            return _sol(c, "geometry", "P = a + b + c", [f"sides {show(c, a)}, {show(c, b_)}, {show(c, c3)}"],
                        f"{show(c, a)} + {show(c, b_)} + {show(c, c3)}", show(c, P, u1), value=P, dim=u1)
        if asks(c, "area"):
            s = (a + b_ + c3) / 2
            A = sp.sqrt(s * (s - a) * (s - b_) * (s - c3))
            chk = ""
            if a ** 2 + b_ ** 2 == c3 ** 2:
                chk = f"right triangle ({show(c, a)}² + {show(c, b_)}² = {show(c, c3)}²): ½ × {show(c, a)} × {show(c, b_)} = {show(c, a * b_ / 2)} ✓"
            return Solution("geometry", c.text, show(c, A, u2),
                            ["formula: Heron: A = √(s(s − a)(s − b)(s − c)), s = (a + b + c)/2",
                             f"known: a = {show(c, a)}, b = {show(c, b_)}, c = {show(c, c3)}",
                             f"s = ({show(c, a)} + {show(c, b_)} + {show(c, c3)}) / 2 = {show(c, s)}",
                             f"substitute: A = √({show(c, s)} × {show(c, s - a)} × {show(c, s - b_)} × {show(c, s - c3)}) = √{show(c, s * (s - a) * (s - b_) * (s - c3))}",
                             f"result: {show(c, A, u2)}"], check=chk, confidence=0.97)
    return None


# ---------------------------------------------------------------- circles and parts

def _radius(c: _Ctx):
    r = lab(c, r"radius|radii") or letter(c, "r")
    if r is not None:
        return r, f"r = {show(c, r, c.unit or 'units')}"
    d = lab(c, r"diameter|across|wide|width") or letter(c, "d")
    if d is not None:
        return d / 2, f"d = {show(c, d, c.unit or 'units')} → r = {show(c, d / 2)}"
    return None, ""


def sector(c: _Ctx) -> Solution | None:
    t = c.t
    if not re.search(r"\bsector\b|\barc\b|\bslice\b|\bwedge\b", t):
        return None
    a = angle_deg(t)
    r, rk = _radius(c)
    if r is None:
        nums = [x for x in numbers(t)]
        if a and a[1] == "rad" and not re.search(_PI, t):
            nums = [x for x in nums if x != R(a[2].group(1))]
        r = nums[0] if nums else None
        rk = f"r = {show(c, r, c.unit or 'units')}" if r is not None else ""
    if r is None or not a:
        return None
    th = a[0] * sp.pi / 180
    thk = f"θ = {deg_show(c, a[0])} = {ex(sp.nsimplify(th))} rad" if a[1] == "deg" else f"θ = {ex(sp.nsimplify(th))} rad"
    u1, u2 = c.unit or "units", _u(c, 2)
    if re.search(r"\barc\b", t) and not re.search(r"area of the sector|sector'?s? area|\barea\b", t) or asks(c, "arc length|length of the arc"):
        L = r * th
        return _sol(c, "geometry", "arc length s = r · θ (θ in radians)", [rk, thk], f"s = {show(c, r)} × {ex(sp.nsimplify(th))}",
                    show(c, L, u1), f"{deg_show(c, a[0])} / 360° × 2π × {show(c, r)} = {dec(c, L)} ✓")
    if asks(c, "perimeter"):
        P = 2 * r + r * th
        return _sol(c, "geometry", "P = 2r + r · θ", [rk, thk], f"2 × {show(c, r)} + {show(c, r)} × {ex(sp.nsimplify(th))}", show(c, P, u1))
    A = r ** 2 * th / 2
    return _sol(c, "geometry", "sector area A = ½ · r² · θ (θ in radians)", [rk, thk],
                f"A = ½ × {show(c, r)}² × {ex(sp.nsimplify(th))}", show(c, A, u2),
                f"{deg_show(c, a[0])} / 360° × π × {show(c, r)}² = {dec(c, A)} ✓", value=A, dim=u2)


def annulus(c: _Ctx) -> Solution | None:
    t = c.t
    if not re.search(r"annulus|\bring\b|washer|concentric|path around|between two circles", t):
        return None
    R_ = lab(c, r"outer radius|outer|bigger radius|larger radius|big radius")
    r_ = lab(c, r"inner radius|inner|smaller radius|small radius|hole")
    if R_ is None or r_ is None:
        m = re.search(rf"radi(?:i|uses)\s*(?:of|are|:)?\s*({N})\s*(?:{U})?\s*and\s*({N})", t)
        if not m:
            nums = numbers(t)
            if len(nums) < 2:
                return None
            R_, r_ = max(nums[:2]), min(nums[:2])
        else:
            R_, r_ = max(R(m.group(1)), R(m.group(2))), min(R(m.group(1)), R(m.group(2)))
        if re.search(r"diameter", t) and not re.search(r"radi", t):
            R_, r_ = R_ / 2, r_ / 2
    if r_ >= R_:
        return None
    A = sp.pi * (R_ ** 2 - r_ ** 2)
    return _sol(c, "geometry", "A = π(R² − r²)", [f"R = {show(c, R_, c.unit or 'units')}", f"r = {show(c, r_, c.unit or 'units')}"],
                f"π × ({show(c, R_)}² − {show(c, r_)}²) = π × {show(c, R_ ** 2 - r_ ** 2)}", show(c, A, _u(c, 2)),
                f"π{show(c, R_ ** 2)} − π{show(c, r_ ** 2)} = {ex(A)} ✓", value=A, dim=_u(c, 2))


def wheel(c: _Ctx) -> Solution | None:
    t = c.t
    if not re.search(r"\b(?:wheel|tyre|tire|bicycle|bike|roller|cylinder rolls|rolls)\b", t) or not re.search(
            r"turn|revolution|rotation|spin|roll|rev\b|revs\b|how far|distance", t):
        return None
    r, rk = _radius(c)
    if r is None:
        return None
    uu = c.unit or "units"
    circ = 2 * sp.pi * r
    m = re.search(rf"({N})\s*(?:full\s+|complete\s+)?(?:turns|revolutions|rotations|times|revs|spins)", t)
    if re.search(r"how many (?:turns|revolutions|rotations|times|revs)", t):
        m2 = re.search(rf"({N})\s*({U})", t[re.search(r'how many|cover|travel|go|roll', t).start():]) or \
            re.search(rf"(?:cover|travel|go|roll|distance of)\s*({N})\s*({U})", t)
        if not m2:
            return None
        du = _UNIT_NAMES.get(m2.group(2).rstrip("s"), _UNIT_NAMES.get(m2.group(2), ""))
        dist = R(m2.group(1))
        if du and c.unit and du != c.unit and du in _TO_M and c.unit in _TO_M:
            dist_c = dist * _TO_M[du] / _TO_M[c.unit]
        else:
            dist_c = dist
        n = dist_c / circ
        return _sol(c, "geometry", "turns = distance / circumference, circumference = 2πr", [rk, f"distance = {show(c, dist)} {m2.group(2)}"],
                    f"{show(c, dist_c, uu)} / (2π × {show(c, r)})", show(c, n, "turns"),
                    f"{dec(c, n)} × {dec(c, circ)} = {dec(c, dist_c)} ✓")
    n = R(m.group(1)) if m else 1
    D = n * circ
    return _sol(c, "geometry", "one turn rolls one circumference: distance = n · π · d", [rk, f"n = {show(c, n)} turn{'s' if n != 1 else ''}"],
                f"{show(c, n)} × π × {show(c, 2 * r)}", show(c, D, uu), f"{dec(c, D)} / {dec(c, circ)} = {show(c, n)} turns ✓")


def circle(c: _Ctx) -> Solution | None:
    t = c.t
    if not re.search(r"\bcircle|circular|\bpizza|\bdisc|\bdisk|\bround (?:table|pond|garden|rug|plate)|circumference", t):
        return None
    u1, u2 = c.unit or "units", _u(c, 2)
    r, rk = _radius(c)
    C = lab(c, r"circumference|perimeter")
    A = lab(c, r"area")
    if r is None and C is not None and not re.search(r"(?:find|what(?:'s| is)?|calculate|whats)\s+(?:is\s+)?(?:the\s+|its\s+)?circumference", t):
        r = C / (2 * sp.pi)
        rk = f"C = {show(c, C, u1)} → r = C / 2π = {ex(r)}"
        if asks(c, "radius") and not asks(c, "area"):
            return _sol(c, "geometry", "r = C / (2π)", [f"C = {show(c, C, u1)}"], f"{show(c, C)} / (2π)", show(c, r, u1),
                        f"2π × {dec(c, r)} = {show(c, C)} ✓")
        if asks(c, "diameter"):
            return _sol(c, "geometry", "d = C / π", [f"C = {show(c, C, u1)}"], f"{show(c, C)} / π", show(c, 2 * r, u1))
    if r is None and A is not None:
        r = sp.sqrt(A / sp.pi)
        if asks(c, "diameter"):
            return _sol(c, "geometry", "d = 2√(A / π)", [f"A = {show(c, A, u2)}"], f"2√({show(c, A)} / π)", show(c, 2 * r, u1))
        if asks(c, "circumference|perimeter"):
            return _sol(c, "geometry", "r = √(A/π), C = 2πr", [f"A = {show(c, A, u2)}"], f"2π × √({show(c, A)} / π)",
                        show(c, 2 * sp.pi * r, u1))
        return _sol(c, "geometry", "r = √(A / π)  (from A = πr²)", [f"A = {show(c, A, u2)}"], f"r = √({show(c, A)} / π)", show(c, r, u1),
                    f"π × {dec(c, r, 4)}² = {dec(c, sp.pi * r ** 2)} ✓")
    if r is None:
        nums = numbers(t)
        if len(nums) != 1:
            return None
        r = nums[0]
        rk = f"r = {show(c, r, u1)}"
    if asks(c, "area|space|cover|covers|size") and not asks(c, r"(?:find|what(?:'s| is)?|calculate|whats)\s+(?:is\s+)?(?:the\s+|its\s+)?(?:radius|diameter|circumference)"):
        Aa = sp.pi * r ** 2
        return _sol(c, "geometry", "A = πr²", [rk], f"A = π × {show(c, r)}² = π × {show(c, r ** 2)}", show(c, Aa, u2),
                    f"√({dec(c, Aa)} / π) = {show(c, r)} ✓", value=Aa, dim=u2)
    if asks(c, "circumference|perimeter|around|distance round|border|fence|fencing|edging|trim"):
        Cc = 2 * sp.pi * r
        return _sol(c, "geometry", "C = 2πr", [rk], f"C = 2 × π × {show(c, r)}", show(c, Cc, u1), f"π × d = π × {show(c, 2 * r)} = {ex(Cc)} ✓",
                    value=Cc, dim=u1)
    if asks(c, "diameter"):
        return _sol(c, "geometry", "d = 2r", [rk], f"2 × {show(c, r)}", show(c, 2 * r, u1))
    if asks(c, "radius"):
        return _sol(c, "geometry", "r = d / 2", [rk], f"{show(c, 2 * r)} / 2", show(c, r, u1))
    if asks(c, "area|space|cover|covers|size"):
        Aa = sp.pi * r ** 2
        return _sol(c, "geometry", "A = πr²", [rk], f"A = π × {show(c, r)}² = π × {show(c, r ** 2)}", show(c, Aa, u2),
                    f"√({dec(c, Aa)} / π) = {show(c, r)} ✓", value=Aa, dim=u2)
    return None


# ---------------------------------------------------------------- quadrilaterals

def _by(c: _Ctx):
    m = re.search(rf"({N})\s*(?:{U})?\s*(?:by|x|\*)\s*({N})(?:\s*(?:{U})?\s*(?:by|x|\*)\s*({N}))?", c.t)
    if not m:
        return None
    return [R(g) for g in m.groups() if g]


def diagonal(c: _Ctx) -> Solution | None:
    t = c.t
    if not re.search(r"\bdiagonal", t) or re.search(r"\b(?:cube|cuboid|box|prism|room|rhombus|kite|parallelogram)\b", t):
        return None
    uu = c.unit or "units"
    if re.search(r"\bsquare\b", t):
        s = lab(c, r"sides?|side length|edge") or (numbers(t) or [None])[0]
        if s is None:
            return None
        if lab(c, r"diagonal") is not None and asks(c, "side|area"):
            d = lab(c, "diagonal")
            if asks(c, "area"):
                return _sol(c, "geometry", "A = d² / 2", [f"d = {show(c, d, uu)}"], f"{show(c, d)}² / 2", show(c, d ** 2 / 2, _u(c, 2)))
            return _sol(c, "geometry", "s = d / √2", [f"d = {show(c, d, uu)}"], f"{show(c, d)} / √2", show(c, d / sp.sqrt(2), uu))
        d = s * sp.sqrt(2)
        return _sol(c, "geometry", "d = s√2", [f"s = {show(c, s, uu)}"], f"d = √({show(c, s)}² + {show(c, s)}²) = {show(c, s)}√2",
                    show(c, d, uu), f"{dec(c, d)}² ≈ {dec(c, d ** 2)} = 2 × {show(c, s)}² ✓")
    dims = _by(c)
    if not dims:
        l_ = lab(c, r"length|long")
        w = lab(c, r"width|wide|breadth")
        if l_ is None or w is None:
            nums = numbers(t)
            if len(nums) < 2:
                return None
            l_, w = nums[0], nums[1]
        dims = [l_, w]
    if len(dims) != 2:
        return None
    l_, w = dims
    d = sp.sqrt(l_ ** 2 + w ** 2)
    return _sol(c, "geometry", "d = √(l² + w²)", [f"l = {show(c, l_, uu)}", f"w = {show(c, w, uu)}"],
                f"√({show(c, l_)}² + {show(c, w)}²) = √{show(c, l_ ** 2 + w ** 2)}", show(c, d, uu),
                f"{show(c, l_)}² + {show(c, w)}² = {show(c, l_ ** 2 + w ** 2)} ✓")


def quad(c: _Ctx) -> Solution | None:
    t = c.t
    u1, u2 = c.unit or "units", _u(c, 2)
    if re.search(r"trapez", t):
        m = re.search(rf"(?:parallel sides|bases|sides)\s*(?:of|are|measuring|:)?\s*({N})\s*(?:{U})?\s*and\s*({N})", t)
        a, b = (R(m.group(1)), R(m.group(2))) if m else (lab(c, r"top|shorter base|short base"), lab(c, r"bottom|longer base|long base"))
        h = lab(c, r"height|high|tall|apart|distance between|perpendicular")
        if a is None or b is None or h is None:
            nums = numbers(t)
            if len(nums) != 3:
                return None
            a, b, h = nums
        if not asks(c, "area"):
            return None
        A = (a + b) / 2 * h
        return _sol(c, "geometry", "A = ½ (a + b) · h", [f"a = {show(c, a, u1)}", f"b = {show(c, b, u1)}", f"h = {show(c, h, u1)}"],
                    f"½ × ({show(c, a)} + {show(c, b)}) × {show(c, h)}", show(c, A, u2),
                    f"average base {show(c, (a + b) / 2)} × height {show(c, h)} = {show(c, A)} ✓", value=A, dim=u2)
    if re.search(r"rhombus|\bkite\b", t) and asks(c, "area") and re.search(r"diagonal", t):
        m = re.search(rf"diagonals?\s*(?:of|are|measuring|:)?\s*({N})\s*(?:{U})?\s*and\s*({N})", t)
        nums = [R(m.group(1)), R(m.group(2))] if m else numbers(t)
        if len(nums) < 2:
            return None
        A = nums[0] * nums[1] / 2
        return _sol(c, "geometry", "A = d₁ · d₂ / 2", [f"d₁ = {show(c, nums[0], u1)}", f"d₂ = {show(c, nums[1], u1)}"],
                    f"{show(c, nums[0])} × {show(c, nums[1])} / 2", show(c, A, u2), value=A, dim=u2)
    if re.search(r"parallelogram|rhombus", t):
        b = lab(c, r"base|side")
        h = lab(c, r"height|high|perpendicular")
        if b is None or h is None:
            nums = numbers(t)
            if len(nums) != 2:
                return None
            b, h = nums
        if asks(c, "area"):
            A = b * h
            return _sol(c, "geometry", "A = base × height", [f"base = {show(c, b, u1)}", f"height = {show(c, h, u1)}"],
                        f"{show(c, b)} × {show(c, h)}", show(c, A, u2), value=A, dim=u2)
        return None
    sq = re.search(r"\bsquare\b(?!\s*(?:units|metres|meters|feet|foot|cm|m\b|km|inch|in\b|yards?|miles?))|\bsquare (?:room|garden|field|plot|tile|lawn|patio)", t)
    rect = re.search(r"rectang|oblong|\b(?:room|garden|field|plot|lawn|patio|yard|floor|wall|sheet|board|carpet|rug|pool|court|park)\b|\bby\b|\d\s*x\s*\d", t)
    if not (sq or rect):
        return None
    want_area = asks(c, r"area|carpet|tiles?|tiling|cover|covers|paint|turf|space|how big|square (?:feet|metres|meters|units)")
    want_per = asks(c, r"perimeter|fence|fencing|border|around|edging|trim|skirting|distance round|go round")
    if sq and not rect:
        s = lab(c, r"sides?|side length|edge|each side|long|wide")
        A = lab(c, r"area")
        if s is None and A is not None and asks(c, "side|perimeter|length"):
            side = sp.sqrt(A)
            if want_per and not asks(c, "side length"):
                return _sol(c, "geometry", "s = √A, P = 4s", [f"A = {show(c, A, u2)}"], f"4 × √{show(c, A)}", show(c, 4 * side, u1))
            return _sol(c, "geometry", "s = √A", [f"A = {show(c, A, u2)}"], f"√{show(c, A)}", show(c, side, u1),
                        f"{dec(c, side)}² = {show(c, A)} ✓")
        P = lab(c, r"perimeter")
        if s is None and P is not None and asks(c, "area|side"):
            side = P / 4
            if want_area:
                return _sol(c, "geometry", "s = P / 4, A = s²", [f"P = {show(c, P, u1)}"], f"({show(c, P)} / 4)² = {show(c, side)}²",
                            show(c, side ** 2, u2))
            return _sol(c, "geometry", "s = P / 4", [f"P = {show(c, P, u1)}"], f"{show(c, P)} / 4", show(c, side, u1))
        if s is None:
            nums = numbers(t)
            if len(nums) != 1:
                return None
            s = nums[0]
        if want_area:
            return _sol(c, "geometry", "A = s²", [f"s = {show(c, s, u1)}"], f"{show(c, s)}²", show(c, s ** 2, u2),
                        f"√{show(c, s ** 2)} = {show(c, s)} ✓", value=s ** 2, dim=u2)
        if want_per:
            return _sol(c, "geometry", "P = 4s", [f"s = {show(c, s, u1)}"], f"4 × {show(c, s)}", show(c, 4 * s, u1),
                        value=4 * s, dim=u1)
        return None
    dims = _by(c)
    if dims and len(dims) == 3:
        return None
    if not dims:
        l_, w = lab(c, r"length|long"), lab(c, r"width|wide|breadth")
        A = lab(c, r"area")
        if A is not None and (l_ is None) != (w is None):
            known = l_ if l_ is not None else w
            other = A / known
            return _sol(c, "geometry", "A = l × w, so the other side = A / known side", [f"A = {show(c, A, u2)}", f"side = {show(c, known, u1)}"],
                        f"{show(c, A)} / {show(c, known)}", show(c, other, u1), f"{show(c, known)} × {show(c, other)} = {show(c, A)} ✓")
        if l_ is None or w is None:
            nums = numbers(t)
            if len(nums) != 2 or not rect:
                return None
            l_, w = nums
        dims = [l_, w]
    l_, w = dims
    if want_area:
        A = l_ * w
        return _sol(c, "geometry", "A = length × width", [f"length = {show(c, l_, u1)}", f"width = {show(c, w, u1)}"],
                    f"{show(c, l_)} × {show(c, w)}", show(c, A, u2), f"{show(c, A)} / {show(c, w)} = {show(c, l_)} ✓", value=A, dim=u2)
    if want_per:
        P = 2 * (l_ + w)
        return _sol(c, "geometry", "P = 2(length + width)", [f"length = {show(c, l_, u1)}", f"width = {show(c, w, u1)}"],
                    f"2 × ({show(c, l_)} + {show(c, w)})", show(c, P, u1),
                    f"{show(c, l_)} + {show(c, w)} + {show(c, l_)} + {show(c, w)} = {show(c, P)} ✓", value=P, dim=u1)
    return None


# ---------------------------------------------------------------- solids

def _vol_ask(c: _Ctx) -> bool:
    return asks(c, r"volume|holds?|hold|capacity|how much (?:water|liquid|air|sand|soil|concrete|space|can|will|does|fits?)|"
                   r"fill|litres|liters|contain|how much (?:it|does it)")


def _sa_ask(c: _Ctx) -> str:
    if asks(c, r"curved|lateral|side area|label"):
        return "curved"
    if asks(c, r"surface|total area|paint|wrap|cover|material|\bsa\b|area"):
        return "total"
    return ""


def _litres(c: _Ctx, V, f, knowns, sub, ans, chk) -> Solution:
    if asks(c, "litres|liters|\\bl\\b") and c.unit in ("cm", "m", "mm"):
        L = V * {"cm": sp.Rational(1, 1000), "m": 1000, "mm": sp.Rational(1, 10 ** 6)}[c.unit]
        conv = {"cm": "1 L = 1,000 cm³", "m": "1 m³ = 1,000 L", "mm": "1 L = 1,000,000 mm³"}[c.unit]
        s = _sol(c, "geometry", f, knowns, sub, show(c, L, "L"), chk)
        s.steps.insert(3, f"convert: {ans}, {conv}")
        return s
    return _sol(c, "geometry", f, knowns, sub, ans, chk, value=V, dim=_u(c, 3))


def solid(c: _Ctx) -> Solution | None:
    t = c.t
    u1, u2, u3 = c.unit or "units", _u(c, 2), _u(c, 3)
    vol, sa = _vol_ask(c), _sa_ask(c)
    if not (vol or sa or asks(c, "diagonal|slant")):
        return None
    if re.search(r"hemispher|\bdome\b|\bbowl\b", t):
        r, rk = _radius(c)
        if r is None:
            nums = numbers(t)
            if len(nums) != 1:
                return None
            r, rk = nums[0], f"r = {show(c, nums[0], u1)}"
        if vol:
            V = sp.Rational(2, 3) * sp.pi * r ** 3
            return _litres(c, V, "V = (2/3)πr³", [rk], f"2/3 × π × {show(c, r)}³", show(c, V, u3), f"half of (4/3)π × {show(c, r)}³ ✓")
        if sa == "curved":
            S = 2 * sp.pi * r ** 2
            return _sol(c, "geometry", "curved area = 2πr²", [rk], f"2 × π × {show(c, r)}²", show(c, S, u2), value=S, dim=u2)
        S = 3 * sp.pi * r ** 2
        return _sol(c, "geometry", "total surface = 2πr² (curved) + πr² (flat) = 3πr²", [rk], f"3 × π × {show(c, r)}²",
                    show(c, S, u2), value=S, dim=u2)
    if re.search(r"\bspher|\bball|\bglobe|\bmarble|\borb|\bbubble|\bballoon", t):
        r, rk = _radius(c)
        if r is None:
            nums = numbers(t)
            if len(nums) != 1:
                return None
            r, rk = nums[0], f"r = {show(c, nums[0], u1)}"
        if vol:
            V = sp.Rational(4, 3) * sp.pi * r ** 3
            return _litres(c, V, "V = (4/3)πr³", [rk], f"4/3 × π × {show(c, r)}³ = 4/3 × π × {show(c, r ** 3)}", show(c, V, u3),
                           f"{dec(c, V)} / (4/3 π) = {show(c, r ** 3)} = {show(c, r)}³ ✓")
        S = 4 * sp.pi * r ** 2
        return _sol(c, "geometry", "A = 4πr²", [rk], f"4 × π × {show(c, r)}²", show(c, S, u2), f"dV/dr of (4/3)πr³ = 4πr² ✓", value=S, dim=u2)
    if re.search(r"\bcones?\b|\bconical|\bfunnel|ice cream cone", t):
        r, rk = _radius(c)
        h = lab(c, r"height|high|tall|deep|depth|perpendicular height") or letter(c, "h")
        sl = lab(c, r"slant height|slant") or letter(c, "l")
        if sl is not None and h == sl:
            h = None
        if r is None:
            return None
        if h is None and sl is not None:
            if sl <= r:
                return None
            h = sp.sqrt(sl ** 2 - r ** 2)
        if h is None:
            return None
        if sl is None:
            sl = sp.sqrt(r ** 2 + h ** 2)
        if asks(c, "slant") and not vol and not sa:
            return _sol(c, "geometry", "l = √(r² + h²)", [rk, f"h = {show(c, h, u1)}"], f"√({show(c, r)}² + {show(c, h)}²)", show(c, sl, u1))
        if vol:
            V = sp.pi * r ** 2 * h / 3
            return _litres(c, V, "V = (1/3)πr²h", [rk, f"h = {show(c, h, u1)}"], f"1/3 × π × {show(c, r)}² × {show(c, h)}", show(c, V, u3),
                           f"a third of the cylinder π × {show(c, r)}² × {show(c, h)} = {ex(3 * V)} ✓")
        if sa == "curved":
            S = sp.pi * r * sl
            return _sol(c, "geometry", "curved area = πrl, l = √(r² + h²)", [rk, f"l = {show(c, sl, u1)}"], f"π × {show(c, r)} × {ex(sl)}",
                        show(c, S, u2), value=S, dim=u2)
        S = sp.pi * r * (r + sl)
        return _sol(c, "geometry", "A = πr² + πrl = πr(r + l), l = √(r² + h²)", [rk, f"h = {show(c, h, u1)}", f"l = {show(c, sl, u1)}"],
                    f"π × {show(c, r)} × ({show(c, r)} + {ex(sl)})", show(c, S, u2), value=S, dim=u2)
    if re.search(r"\bpyramid", t):
        a = lab(c, r"base (?:edge|side|length)|base|side|edge|sides")
        h = lab(c, r"height|high|tall|vertical height|perpendicular height") or letter(c, "h")
        sl = lab(c, r"slant height|slant")
        dims = _by(c)
        if dims and len(dims) >= 2:
            bl, bw = dims[0], dims[1]
            if len(dims) == 3 and h is None:
                h = dims[2]
        elif a is not None:
            bl = bw = a
        else:
            nums = numbers(t)
            if len(nums) != 2:
                return None
            bl = bw = nums[0]
            h = nums[1]
        if h is None and sl is not None and bl == bw:
            h = sp.sqrt(sl ** 2 - (bl / 2) ** 2)
        if h is None:
            return None
        if vol:
            V = bl * bw * h / 3
            return _litres(c, V, "V = (1/3) · base area · h", [f"base = {show(c, bl)} × {show(c, bw)} {u1}", f"h = {show(c, h, u1)}"],
                           f"1/3 × {show(c, bl * bw)} × {show(c, h)}", show(c, V, u3), f"3 × {show(c, V)} = {show(c, bl * bw * h)} = base × h ✓")
        if bl != bw:
            return None
        sl = sl if sl is not None else sp.sqrt(h ** 2 + (bl / 2) ** 2)
        S = bl ** 2 + 2 * bl * sl
        return _sol(c, "geometry", "A = a² + 2·a·l, slant l = √(h² + (a/2)²)", [f"a = {show(c, bl, u1)}", f"h = {show(c, h, u1)}", f"l = {show(c, sl, u1)}"],
                    f"{show(c, bl)}² + 2 × {show(c, bl)} × {ex(sl)}", show(c, S, u2), value=S, dim=u2)
    cyl = re.search(r"cylind|\bcan\b|\bpipe\b|\btin\b|\bdrum\b|\bsilo\b|\bcylinder", t)
    tank = re.search(r"\btank\b|\bwell\b|\bglass\b|\bcup\b|\bmug\b|\bpool\b", t)
    r, rk = _radius(c)
    if cyl or (tank and r is not None):
        h = lab(c, r"height|high|tall|deep|depth|long|length") or letter(c, "h")
        if r is None or h is None:
            return None
        if vol:
            V = sp.pi * r ** 2 * h
            return _litres(c, V, "V = πr²h", [rk, f"h = {show(c, h, u1)}"], f"π × {show(c, r)}² × {show(c, h)} = π × {show(c, r ** 2 * h)}",
                           show(c, V, u3), f"base area π × {show(c, r ** 2)} times height {show(c, h)} ✓")
        if sa == "curved":
            S = 2 * sp.pi * r * h
            return _sol(c, "geometry", "curved area = 2πrh", [rk, f"h = {show(c, h, u1)}"], f"2 × π × {show(c, r)} × {show(c, h)}",
                        show(c, S, u2), value=S, dim=u2)
        S = 2 * sp.pi * r * (r + h)
        return _sol(c, "geometry", "A = 2πr² + 2πrh = 2πr(r + h)", [rk, f"h = {show(c, h, u1)}"],
                    f"2 × π × {show(c, r)} × ({show(c, r)} + {show(c, h)})", show(c, S, u2),
                    f"two ends {ex(2 * sp.pi * r ** 2)} + side {ex(2 * sp.pi * r * h)} = {ex(S)} ✓", value=S, dim=u2)
    if re.search(r"\bcubes?\b|\bdice\b|\bdie\b", t) and not re.search(r"cuboid", t):
        s = lab(c, r"sides?|edges?|side length|edge length|long|wide")
        if s is None:
            nums = numbers(t)
            if len(nums) != 1:
                return None
            s = nums[0]
        if asks(c, "diagonal"):
            return _sol(c, "geometry", "space diagonal = s√3", [f"s = {show(c, s, u1)}"], f"{show(c, s)} × √3", show(c, s * sp.sqrt(3), u1))
        if vol:
            return _litres(c, s ** 3, "V = s³", [f"s = {show(c, s, u1)}"], f"{show(c, s)}³", show(c, s ** 3, u3), f"∛{show(c, s ** 3)} = {show(c, s)} ✓")
        return _sol(c, "geometry", "A = 6s²", [f"s = {show(c, s, u1)}"], f"6 × {show(c, s)}²", show(c, 6 * s ** 2, u2),
                    f"6 faces of {show(c, s ** 2)} ✓", value=6 * s ** 2, dim=u2)
    if re.search(r"cuboid|rectangular (?:prism|box|solid|tank|block)|\bbox\b|\bprism\b|\broom\b|\btank\b|\bbrick\b|\bblock\b|"
                 r"aquarium|\bpool\b|\bcontainer\b|\bcrate\b|\bfridge\b|\bcarton\b|\bchest\b", t):
        dims = _by(c)
        if not dims or len(dims) != 3:
            l_, w = lab(c, r"length|long"), lab(c, r"width|wide|breadth")
            h = lab(c, r"height|high|tall|deep|depth")
            if None in (l_, w, h):
                nums = numbers(t)
                if len(nums) != 3:
                    return None
                l_, w, h = nums
            dims = [l_, w, h]
        l_, w, h = dims
        if asks(c, "diagonal"):
            d = sp.sqrt(l_ ** 2 + w ** 2 + h ** 2)
            return _sol(c, "geometry", "d = √(l² + w² + h²)", [f"{show(c, l_)} × {show(c, w)} × {show(c, h)} {u1}"],
                        f"√{show(c, l_ ** 2 + w ** 2 + h ** 2)}", show(c, d, u1))
        if vol:
            V = l_ * w * h
            return _litres(c, V, "V = l × w × h", [f"l = {show(c, l_, u1)}", f"w = {show(c, w, u1)}", f"h = {show(c, h, u1)}"],
                           f"{show(c, l_)} × {show(c, w)} × {show(c, h)}", show(c, V, u3), f"{show(c, V)} / ({show(c, l_)} × {show(c, w)}) = {show(c, h)} ✓")
        S = 2 * (l_ * w + l_ * h + w * h)
        return _sol(c, "geometry", "A = 2(lw + lh + wh)", [f"l = {show(c, l_, u1)}", f"w = {show(c, w, u1)}", f"h = {show(c, h, u1)}"],
                    f"2 × ({show(c, l_ * w)} + {show(c, l_ * h)} + {show(c, w * h)})", show(c, S, u2), value=S, dim=u2)
    return None


# ---------------------------------------------------------------- entry point

_DEFN = re.compile(r"^\s*(?:what(?:'s| is| are)|define|explain|meaning of|who|why|how are)\b(?:\s+(?:a|an|the))?\s+[a-z ]+\??\s*$")


def solve(text: str) -> Solution | None:
    if not text or len(text) > 500:
        return None
    c = _strip(text)
    t = c.t
    poly = re.search(r"\bangles?\b", t) and re.search(r"|".join(_POLY) + r"|polygon", t)
    if not (re.search(r"\d", t) or poly) or not KEYWORDS.search(t) or _BAD.search(t):
        return None
    if _DEFN.match(t) and not re.search(r"\d", t):
        return None
    m = _PAIR.search(t)
    if m:
        both = _pair(text, c, m)
        if both is not None:
            return both
    return _one(c)


_MEASURE = r"perimeter|circumference|surface area|area|volume"
_PAIR = re.compile(rf"\b({_MEASURE})\s*(?:,|and|n|&|\+|plus)\s*(?:also\s+)?(?:the\s+|its\s+)?({_MEASURE})\b")


def _one(c: _Ctx) -> Solution | None:
    for fn in (convert, polygon, right_words, trig_value, wheel, similar, sector, annulus, solid, pythagoras,
               diagonal, triangle, circle, quad):
        sol = fn(c)
        if sol is not None:
            return sol
    return None


def _pair(text: str, c: _Ctx, m) -> Solution | None:
    """"perimeter and area", "volume and surface area": solve each measure on its own and report both."""
    a, b = m.group(1), m.group(2)
    if a == b or {a, b} == {"area", "surface area"}:
        return None
    parts = []
    for w in (a, b):
        sub = _strip(text)
        sub.t = sub.t[:m.start()] + w + sub.t[m.end():]
        s = _one(sub)
        if s is None:
            return None
        parts.append((w, s))
    (wa, sa), (wb, sb) = parts
    steps = [f"{wa}: {x}" for x in sa.steps] + [f"{wb}: {x}" for x in sb.steps]
    return Solution(sa.kind, text, f"{wa} {sa.answer}; {wb} {sb.answer}", steps, check="; ".join(x for x in (sa.check, sb.check) if x),
                    confidence=min(sa.confidence, sb.confidence))
