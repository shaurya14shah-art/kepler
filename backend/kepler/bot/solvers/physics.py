"""Mechanics and basic physics word problems in plain English, solved exactly with worked steps.

"A 1200 kg car at 20 m/s brakes with 6000 N, how far does it go?" → reads every quantity with its unit (km/h, g/cm³,
kWh, N/m, kg·m/s …), what is asked, any gravity given ("g = 10", "on the Moon"), and the setting (dropped, thrown up,
launched horizontally, stuck together, a spring, efficiency …), then works it out in exact rationals (sympy), so
9.81 × 3 stays 29.43 and √ results keep an exact form. Each answer has the formula, the knowns in SI units, the
substitution, the result and a check. Anything that is not this kind of problem (Kepler commands, definitions, small
talk) gives None so the other solvers can try.
"""
import re
from decimal import ROUND_HALF_UP, Decimal, localcontext

import sympy as sp

from ..reasoning import Solution

R = sp.Rational
G0 = R("9.81")
C_LIGHT = R(300_000_000)
V_SOUND = R(343)
P_ATM = R(101325)

PLANETS = {"moon": R("1.62"), "mars": R("3.71"), "jupiter": R("24.79"), "venus": R("8.87"), "mercury": R("3.7"),
           "saturn": R("10.44"), "uranus": R("8.69"), "neptune": R("11.15"), "pluto": R("0.62"), "sun": R(274),
           "earth": G0}
FLUIDS = [("sea ?water|salt ?water|the sea|the ocean|ocean|seawater", R(1025), "sea water"),
          ("mercury", R(13600), "mercury"), ("water|lake|pool|river|tank|dam", R(1000), "water")]
MATERIALS = {"water": R(1000), "ice": R(917), "aluminium": R(2700), "aluminum": R(2700), "iron": R(7870),
             "steel": R(7850), "copper": R(8960), "gold": R(19300), "silver": R(10490), "lead": R(11340),
             "mercury": R(13600), "sea water": R(1025), "seawater": R(1025)}

# ---------------------------------------------------------------- units

# dimension, factor to SI, display, spellings (lower case, single spaces)
_UNITS = [
    ("acc", 1, "m/s²", ["m/s^2", "m/s2", "m/s/s", "m/sec^2", "m/sec2", "ms^-2", "ms-2", "m s^-2", "m s-2", "m·s^-2",
                        "m/s squared", "m per s squared", "m per s^2", "meters per second squared",
                        "metres per second squared", "meter per second squared", "metre per second squared",
                        "meters per second per second", "metres per second per second", "m per second squared",
                        "m/s per second", "n/kg", "newtons per kilogram", "newton per kilogram", "newtons per kg",
                        "n per kg", "meters per sec squared", "metres per sec squared"]),
    ("acc", R("0.3048"), "ft/s²", ["ft/s^2", "ft/s2", "feet per second squared"]),
    ("acc", R(1, 100), "cm/s²", ["cm/s^2", "cm/s2"]),
    ("vel", 1, "m/s", ["m/s", "m/sec", "ms^-1", "ms-1", "m s^-1", "m s-1", "m·s^-1", "meters per second",
                       "metres per second", "meter per second", "metre per second", "m per s", "m per sec",
                       "m per second", "meters/second", "metres/second", "m/second", "meters per sec", "metres per sec"]),
    ("vel", R(5, 18), "km/h", ["km/h", "km/hr", "kmh", "km/hour", "kmph", "kph", "km per hour", "km an hour",
                               "km per hr", "kilometers per hour", "kilometres per hour", "kilometer per hour",
                               "kilometre per hour", "kilometers an hour", "kilometres an hour", "kms per hour",
                               "km/hrs", "kmhr"]),
    ("vel", R("0.44704"), "mph", ["mph", "miles per hour", "mile per hour", "miles an hour", "mi/h", "mi/hr"]),
    ("vel", R("0.3048"), "ft/s", ["ft/s", "feet per second", "foot per second", "ft/sec"]),
    ("vel", R(1, 100), "cm/s", ["cm/s", "centimetres per second", "centimeters per second", "cm per second"]),
    ("vel", R(1852, 3600), "knots", ["knots", "knot"]),
    ("density", 1, "kg/m³", ["kg/m^3", "kg/m3", "kg per cubic metre", "kg per cubic meter", "kg per m^3", "kg per m3",
                             "kilograms per cubic metre", "kilograms per cubic meter", "kilogram per cubic metre",
                             "kilogram per cubic meter", "kg m^-3", "kgm^-3"]),
    ("density", 1000, "g/cm³", ["g/cm^3", "g/cm3", "g/cc", "g per cm^3", "g per cm3", "g per cubic centimetre",
                                "g per cubic centimeter", "grams per cubic centimetre", "grams per cubic centimeter",
                                "gram per cubic centimetre", "gram per cubic centimeter", "grams per cm^3",
                                "grams per cm3", "g cm^-3", "g/cubic cm"]),
    ("density", 1000, "g/mL", ["g/ml", "g per ml", "grams per ml", "grams per millilitre", "grams per milliliter",
                               "g/millilitre", "g/milliliter"]),
    ("density", 1000, "kg/L", ["kg/l", "kg per litre", "kg per liter", "kg/litre", "kg/liter", "kilograms per litre",
                               "kilograms per liter"]),
    ("density", 1, "g/L", ["g/l", "g per litre", "g per liter", "grams per litre", "grams per liter", "g/litre"]),
    ("spring", 1, "N/m", ["n/m", "newtons per metre", "newtons per meter", "newton per metre", "newton per meter",
                          "n per m", "n per metre", "n per meter", "n m^-1", "nm^-1"]),
    ("spring", 100, "N/cm", ["n/cm", "newtons per cm", "newtons per centimetre", "newtons per centimeter", "n per cm"]),
    ("spring", 1000, "N/mm", ["n/mm", "newtons per mm"]),
    ("spring", 1000, "kN/m", ["kn/m"]),
    ("pressure", 1, "Pa", ["pa", "pascal", "pascals", "n/m^2", "n/m2", "n per square metre", "n per square meter",
                           "n per m^2", "n per m2", "newtons per square metre", "newtons per square meter"]),
    ("pressure", 1000, "kPa", ["kpa", "kilopascal", "kilopascals"]),
    ("pressure", 10**6, "MPa", ["mpa", "megapascal", "megapascals", "n/mm^2", "n/mm2"]),
    ("pressure", 100, "hPa", ["hpa", "hectopascal", "hectopascals", "mbar", "millibar", "millibars"]),
    ("pressure", 10**4, "N/cm²", ["n/cm^2", "n/cm2", "n per cm^2", "n per cm2", "n per square centimetre",
                                  "n per square centimeter", "newtons per square centimetre",
                                  "newtons per square centimeter"]),
    ("pressure", 101325, "atm", ["atm", "atmosphere", "atmospheres"]),
    ("pressure", 10**5, "bar", ["bar", "bars"]),
    ("pressure", R("133.322"), "mmHg", ["mmhg", "mm hg", "mm of mercury"]),
    ("pressure", R("6894.757"), "psi", ["psi"]),
    ("momentum", 1, "kg·m/s", ["kg m/s", "kg·m/s", "kgm/s", "kg.m/s", "kg*m/s", "kg m s^-1", "kg ms^-1", "kgms^-1",
                               "kg ms-1", "kg m s-1", "kgms-1", "kg-m/s", "kilogram metres per second",
                               "kilogram meters per second", "kg metres per second", "kg meters per second"]),
    ("momentum", 1, "N·s", ["n s", "ns", "n·s", "n.s", "n-s", "n*s", "newton second", "newton seconds",
                            "newton-second", "newton-seconds"]),
    ("energy", 1, "J", ["j", "joule", "joules"]),
    ("energy", 1000, "kJ", ["kj", "kilojoule", "kilojoules"]),
    ("energy", 10**6, "MJ", ["mj", "megajoule", "megajoules"]),
    ("energy", 10**9, "GJ", ["gj", "gigajoule", "gigajoules"]),
    ("energy", 3_600_000, "kWh", ["kwh", "kw h", "kw-h", "kw·h", "kwhr", "kw hr", "kilowatt hour", "kilowatt hours",
                                  "kilowatt-hour", "kilowatt-hours", "kilowatthour", "kilowatthours"]),
    ("energy", 3600, "Wh", ["wh", "watt hour", "watt hours", "watt-hour", "watt-hours"]),
    ("energy", 3_600_000_000, "MWh", ["mwh", "megawatt hour", "megawatt hours", "megawatt-hour", "megawatt-hours"]),
    ("energy", 4184, "kcal", ["kcal", "kilocalorie", "kilocalories", "kcals"]),
    ("energy", R("4.184"), "cal", ["cal", "calorie", "calories", "cals"]),
    ("energy", R("1.602176634e-19"), "eV", ["ev", "electronvolt", "electronvolts", "electron volt", "electron volts"]),
    ("power", 1, "W", ["w", "watt", "watts"]),
    ("power", 1000, "kW", ["kw", "kilowatt", "kilowatts"]),
    ("power", 10**6, "MW", ["mw", "megawatt", "megawatts"]),
    ("power", 10**9, "GW", ["gw", "gigawatt", "gigawatts"]),
    ("power", R("745.7"), "hp", ["hp", "horsepower", "horse power", "bhp"]),
    ("freq", 1, "Hz", ["hz", "hertz"]),
    ("freq", 1000, "kHz", ["khz", "kilohertz"]),
    ("freq", 10**6, "MHz", ["mhz", "megahertz"]),
    ("freq", 10**9, "GHz", ["ghz", "gigahertz"]),
    ("force", 1, "N", ["n", "newton", "newtons"]),
    ("force", 1000, "kN", ["kn", "kilonewton", "kilonewtons"]),
    ("force", 10**6, "MN", ["meganewton", "meganewtons"]),
    ("area", 1, "m²", ["m^2", "m2", "sq m", "sq. m", "sqm", "square metre", "square metres", "square meter",
                       "square meters", "metres squared", "meters squared", "square m"]),
    ("area", R(1, 10**4), "cm²", ["cm^2", "cm2", "sq cm", "sq. cm", "square centimetre", "square centimetres",
                                  "square centimeter", "square centimeters", "square cm", "centimetres squared",
                                  "centimeters squared"]),
    ("area", R(1, 10**6), "mm²", ["mm^2", "mm2", "sq mm", "square millimetre", "square millimetres",
                                  "square millimeter", "square millimeters", "square mm"]),
    ("area", 10**6, "km²", ["km^2", "km2", "sq km", "square kilometre", "square kilometres", "square kilometer",
                            "square kilometers"]),
    ("vol", 1, "m³", ["m^3", "m3", "cubic metre", "cubic metres", "cubic meter", "cubic meters", "cu m", "cubic m"]),
    ("vol", R(1, 10**6), "cm³", ["cm^3", "cm3", "cc", "ccs", "cubic centimetre", "cubic centimetres",
                                 "cubic centimeter", "cubic centimeters", "cubic cm"]),
    ("vol", R(1, 10**9), "mm³", ["mm^3", "mm3", "cubic millimetre", "cubic millimetres", "cubic millimeter",
                                 "cubic millimeters"]),
    ("vol", R(1, 1000), "L", ["l", "litre", "litres", "liter", "liters", "ltr", "ltrs", "dm^3", "dm3"]),
    ("vol", R(1, 10**6), "mL", ["ml", "millilitre", "millilitres", "milliliter", "milliliters", "mls"]),
    ("len", 1, "m", ["m", "metre", "metres", "meter", "meters", "mtr", "mtrs"]),
    ("len", 1000, "km", ["km", "kms", "kilometre", "kilometres", "kilometer", "kilometers"]),
    ("len", R(1, 100), "cm", ["cm", "cms", "centimetre", "centimetres", "centimeter", "centimeters"]),
    ("len", R(1, 1000), "mm", ["mm", "millimetre", "millimetres", "millimeter", "millimeters"]),
    ("len", R(1, 10**6), "µm", ["um", "micrometre", "micrometres", "micrometer", "micrometers", "micron", "microns"]),
    ("len", R(1, 10**9), "nm", ["nm", "nanometre", "nanometres", "nanometer", "nanometers"]),
    ("len", R("1609.344"), "miles", ["mile", "miles"]),
    ("len", R("0.3048"), "ft", ["ft", "foot", "feet"]),
    ("len", R("0.0254"), "in", ["inch", "inches"]),
    ("len", R("0.9144"), "yd", ["yard", "yards", "yd", "yds"]),
    ("time", 1, "s", ["s", "sec", "secs", "second", "seconds"]),
    ("time", R(1, 1000), "ms", ["ms", "millisecond", "milliseconds", "msec"]),
    ("time", 60, "min", ["min", "mins", "minute", "minutes"]),
    ("time", 3600, "h", ["h", "hr", "hrs", "hour", "hours"]),
    ("time", 86400, "days", ["day", "days"]),
    ("mass", 1, "kg", ["kg", "kgs", "kilogram", "kilograms", "kilo", "kilos", "kilogramme", "kilogrammes"]),
    ("mass", R(1, 1000), "g", ["g", "gram", "grams", "gramme", "grammes", "gm", "gms"]),
    ("mass", R(1, 10**6), "mg", ["mg", "milligram", "milligrams"]),
    ("mass", 1000, "t", ["tonne", "tonnes", "ton", "tons", "metric ton", "metric tons"]),
    ("mass", R("0.45359237"), "lb", ["lb", "lbs"]),
    ("angle", 1, "°", ["°", "deg", "degs", "degree", "degrees"]),
    ("angle", 180 / sp.pi, "rad", ["rad", "rads", "radian", "radians"]),
    ("pct", 1, "%", ["%", "percent", "per cent", "pct"]),
]
UNIT_INDEX: dict[str, tuple[str, sp.Expr, str]] = {}
FACTOR: dict[str, sp.Expr] = {}
for _dim, _f, _disp, _sp in _UNITS:
    for _s in _sp:
        UNIT_INDEX[_s] = (_dim, sp.sympify(_f), _disp)
    FACTOR.setdefault(_disp, sp.sympify(_f))
SI = {"acc": "m/s²", "vel": "m/s", "len": "m", "time": "s", "mass": "kg", "force": "N", "energy": "J", "power": "W",
      "freq": "Hz", "area": "m²", "vol": "m³", "density": "kg/m³", "pressure": "Pa", "spring": "N/m",
      "momentum": "kg·m/s", "angle": "°", "pct": "%"}
UNIT_ALT = "|".join(re.escape(s).replace("\\ ", " ") for s in sorted(UNIT_INDEX, key=len, reverse=True))
NUM = r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:e[+-]?\d+)?|-?\.\d+(?:e[+-]?\d+)?"
QTY = re.compile(rf"(?<![\w.^])({NUM})\s*-?\s*({UNIT_ALT})(?![a-z0-9])", re.I)
LABEL_DIM = {"u": "vel", "v": "vel", "v0": "vel", "vi": "vel", "vf": "vel", "v1": "vel", "v2": "vel", "u1": "vel",
             "u2": "vel", "a": "acc", "s": "len", "d": "len", "h": "len", "x": "len", "t": "time", "m": "mass",
             "m1": "mass", "m2": "mass", "F": "force", "k": "spring", "f": "freq", "T": "time", "λ": "len",
             "θ": "angle", "ρ": "density", "p": "momentum", "KE": "energy", "PE": "energy", "GPE": "energy",
             "E": "energy", "Ek": "energy", "Ep": "energy"}
SUPER = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")
SUP_OUT = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")

# ---------------------------------------------------------------- numbers out


def _dec(x) -> Decimal:
    x = sp.sympify(x)
    if x.is_Rational:
        with localcontext() as ctx:
            ctx.prec = 60
            return Decimal(int(x.p)) / Decimal(int(x.q))
    return Decimal(str(sp.N(x, 50)))


def _terminates(x) -> bool:
    return bool(x.is_Rational) and set(sp.factorint(int(x.q))) <= {2, 5}


def _short(x) -> bool:
    """An exact decimal that is short enough to show in full (441.45, 98,100, 0.0025)."""
    if not _terminates(x):
        return False
    d = _dec(x).normalize()
    return len(d.as_tuple().digits) <= 6 and -4 <= d.adjusted() < 9


def num(x, sig: int | None = None, dp: int | None = None) -> str:
    """Exact when short, else 4 significant figures (or the asked sig figs / decimal places), half up."""
    x = sp.sympify(x)
    d = _dec(x)
    if d == 0:
        return "0"
    sign = "-" if d < 0 else ""
    d = abs(d)
    if dp is not None:
        q = d.quantize(Decimal(1).scaleb(-dp), rounding=ROUND_HALF_UP)
        return sign + f"{q:,.{dp}f}"
    if sig is None and _short(x):
        q = d.normalize()
    else:
        q = d.quantize(Decimal(1).scaleb(d.adjusted() - (sig or 4) + 1), rounding=ROUND_HALF_UP)
        if sig is None:
            q = q.normalize()
    e = q.adjusted()
    if e >= 9 or e < -4:
        mant = q.scaleb(-e)
        m = f"{mant.normalize() if sig is None else mant:f}"
        return f"{sign}{m} × 10{str(e).translate(SUP_OUT)}"
    return sign + f"{q:,f}"


def _pretty(s: str) -> str:
    s = s.replace("**", "^").replace("sqrt(", "√(").replace("pi", "π")
    s = re.sub(r"√\((\d+)\)", r"√\1", s)
    s = re.sub(r"(\d)\*(?=[√π])", r"\1", s)
    return s.replace("*", "·")


def exact_form(x, force: bool = False) -> str | None:
    """A short exact form worth showing next to the decimal: 10/3, 250√3, 5√2/2; None when the decimal says it all."""
    x = sp.sympify(x)
    if x.is_Rational:
        if x.q == 1 or (_terminates(x) and not force):
            return None
        if force or (x.q <= 10000 and abs(x.p) <= 10**7):
            return f"{x.p}/{x.q}"
        return None
    if not x.is_number or x.has(sp.Float, sp.cos, sp.sin, sp.tan, sp.atan, sp.asin, sp.acos, sp.log):
        return None
    s = sp.sstr(x)
    if not force and any(int(r) > 1000 for r in re.findall(r"sqrt\((\d+)\)", s)):
        return None
    p = _pretty(s)
    return p if len(p) <= (32 if force else 14) else None


# ---------------------------------------------------------------- reading the message


class Q:
    """A number with its unit, in SI (exact), where it sits in the text and the words around it."""

    def __init__(self, val, dim: str, unit: str, given: str, pos: int, end: int):
        self.val, self.dim, self.unit, self.given, self.pos, self.end = val, dim, unit, given, pos, end
        self.pre = self.post = self.wpre = self.wpost = ""
        self.label = ""
        self.role = ""

    def shown(self) -> str:
        g = self.given if "e" not in self.given.lower() else num(R(self.given.replace(",", "")))
        sep = "" if self.unit in ("%", "°") else " "
        return f"{g}{sep}{self.unit}"

    def known(self, sym: str, si_val=None) -> str:
        si = SI[self.dim]
        v = self.val if si_val is None else si_val
        if self.unit == si or self.dim in ("angle", "pct"):
            return f"{sym} = {self.shown()}"
        return f"{sym} = {self.shown()} = {num(v)} {si}"

    def __repr__(self):
        return f"Q({self.given} {self.unit}={self.val} {self.dim} {self.role or ''})"


def _rat(s: str):
    return R(s.replace(",", ""))


def _prep(text: str):
    t = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace(" ", " ")
    t = t.replace("−", "-").replace("–", "-").replace("—", " - ").replace("…", "...")
    t = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺]+", lambda m: "^" + m.group().translate(SUPER), t)
    t = re.sub(r"[µμ](?=(?:m|s|g|l|j|w)\b)", "u", t)
    t = re.sub(r"(\d(?:\.\d+)?)\s*(?:x|×|\*|·|X)\s*10\s*\^\s*\(?\s*([+-]?\d+)\s*\)?", r"\1e\2", t)
    t = re.sub(r"(?<![\w.])10\s*\^\s*\(?([+-]?\d+)\)?(?!\s*[\d.])", r"1e\1", t)
    t = re.sub(r"(?<![\w.])(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)(?=\s*[a-zA-Z/%°])", r"\1 to \2", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s*/\s*", "/", t)
    t = re.sub(r"\s*\^\s*", "^", t)
    sig = dp = None
    m = re.search(r"(\d{1,2})\s*-?\s*(?:significant|sig\.?)\s*(?:figs?|figures?|digits?)\b|(\d{1,2})\s*(?:s\.\s?f\.?|sf|s\.f)(?![a-z])",
                  t, re.I)
    if m:
        sig = int(m.group(1) or m.group(2))
        t = t[:m.start()] + " " + t[m.end():]
    m = re.search(r"(\d{1,2})\s*(?:decimal places?|decimals?|dps?|d\.p\.?)(?![a-z])", t, re.I)
    if m:
        dp = int(m.group(1))
        t = t[:m.start()] + " " + t[m.end():]
    m = re.search(r"nearest (whole number|integer|unit|tenth|hundredth|thousandth)", t, re.I)
    if m:
        dp = {"tenth": 1, "hundredth": 2, "thousandth": 3}.get(m.group(1).lower(), 0)
    if sig is not None and not 1 <= sig <= 12:
        sig = None
    exact = bool(re.search(r"\bexact(?:ly)?\b|\bsurds?\b|\bin terms of (?:pi|π|root|sqrt)\b|\bsimplest (?:radical )?form\b",
                           t, re.I))
    frac = bool(re.search(r"\bfractions?\b|\bfractional\b", t, re.I))
    return re.sub(r"\s+", " ", t).strip(), sig, dp, exact, frac


def _unit(raw: str):
    if raw in ("mW", "mJ"):
        dim, _, disp = UNIT_INDEX[raw.lower()]
        return dim, R(1, 1000), "m" + disp[1:]
    return UNIT_INDEX[re.sub(r"\s+", " ", raw.lower())]


def _quantities(t: str) -> list[Q]:
    out: list[Q] = []
    for m in QTY.finditer(t):
        dim, factor, disp = _unit(m.group(2))
        out.append(Q(_rat(m.group(1)) * factor, dim, disp, m.group(1), m.start(), m.end()))
    starts = {q.pos for q in out}
    for q in list(out):  # "from 0 to 27 m/s": the bare 0 takes the unit of the 27
        m = re.search(rf"(?<![\w.^])({NUM})\s+(?:to|and)\s+$", t[:q.pos])
        if m and m.start(1) not in starts and (" to " in m.group(0) or re.search(r"between\s+$", t[:m.start(1)])):
            factor = q.val / _rat(q.given) if _rat(q.given) else UNIT_INDEX.get(q.unit.lower(), (0, 1))[1]
            out.append(Q(_rat(m.group(1)) * factor, q.dim, q.unit, m.group(1), m.start(1), m.end(1)))
            starts.add(m.start(1))
    # labelled numbers without a unit: "u = 0", "k = 200", "θ = 30"
    for m in re.finditer(rf"(?<![\w])(λ|θ|ρ|lambda|theta|rho|[a-zA-Z][a-zA-Z0-9]{{0,2}})\s*(?:=|:)\s*({NUM})(?![\d.])", t):
        if m.start(2) in starts:
            continue
        lab = {"lambda": "λ", "theta": "θ", "rho": "ρ"}.get(m.group(1).lower(), m.group(1))
        dim = LABEL_DIM.get(lab) or (LABEL_DIM.get(lab.lower()) if lab.lower() not in ("f",) else None)
        if not dim:
            continue
        rest = t[m.end(2):]
        if re.match(rf"\s*-?\s*(?:{UNIT_ALT})(?![a-z0-9])", rest, re.I):
            continue
        q = Q(_rat(m.group(2)), dim, SI[dim], m.group(2), m.start(2), m.end(2))
        q.label = lab
        out.append(q)
        starts.add(m.start(2))
    for pat, dim in ((r"(?:spring constant|stiffness|force constant)\s*(?:k\s*)?(?:of|is|=|:|equal to|equals|was|being)?\s*({NUM})", "spring"),
                     (r"(?:angle of|angle is|angle =|angle:|at an angle|inclined at|angle)\s*(?:of\s*)?({NUM})(?!\s*(?:%|kg|m|s|n)\b)", "angle"),
                     (r"\bat\s*({NUM})\s*(?:to|above|below|from|with)\s+the\s+(?:horizontal|vertical|ground|floor)", "angle"),
                     (r"efficiency\s*(?:of|is|=|:|was)?\s*({NUM})(?!\s*%)", "pct"),
                     (r"frequency\s*(?:of|is|=|:)?\s*({NUM})(?![\d.]*\s*(?:hz|khz|mhz|ghz|hertz))", "freq")):
        for m in re.finditer(pat.replace("{NUM}", NUM), t, re.I):
            if m.start(1) in starts:
                continue
            v = _rat(m.group(1))
            if dim == "pct" and v <= 1:
                v *= 100
            out.append(Q(v, dim, SI[dim], m.group(1), m.start(1), m.end(1)))
            starts.add(m.start(1))
    out.sort(key=lambda q: q.pos)
    low = t.lower()
    for i, q in enumerate(out):
        prev_end = out[i - 1].end if i else 0
        nxt = out[i + 1].pos if i + 1 < len(out) else len(t)
        q.pre, q.post = low[max(prev_end, q.pos - 45):q.pos], low[q.end:min(nxt, q.end + 45)]
        q.wpre, q.wpost = low[max(0, q.pos - 45):q.pos], low[q.end:q.end + 45]
        if not q.label:
            m = re.search(r"(?:^|[\s,;(])(λ|θ|ρ|[a-zA-Z][a-zA-Z0-9_]{0,3})\s*(?:=|:)\s*$", t[max(0, q.pos - 8):q.pos])
            if m:
                q.label = m.group(1)
    return out


# ---------------------------------------------------------------- what is asked

TARGETS = [
    ("avg", r"average (?:speed|velocity)|mean speed|avg\.? (?:speed|velocity)|overall (?:average )?speed"),
    ("J", r"impulse|change (?:in|of) (?:the |its )?momentum|momentum change"),
    ("KE", r"kinetic energy|\bk\.?e\.?(?![a-z])|\bkinetic\b"),
    ("PE", r"(?:gravitational |elastic |strain )?potential energy|\bg?p\.?e\.?(?![a-z])|\bgpe\b|elastic (?:potential )?energy"
           r"|energy (?:is )?stored|stored energy|strain energy|energy (?:does|will|would) it (?:store|have)"),
    ("eff", r"(?<!co)efficien(?:cy|t)"),
    ("k", r"spring constant|stiffness|force constant|constant of the spring|spring's constant"),
    ("x", r"\bextension\b|\bcompression\b|how (?:far|much) (?:does|will|did|would|is|was|has|must|should) (?:it|the [\w ]{0,20}?)"
          r" (?:be )?(?:stretch|extend|compress|squash|shorten|lengthen)\w*|how much (?:longer|shorter)|how (?:far|much) (?:does|will|would|did) [^?.]{0,40}?\b(?:stretch|extend|compress)\w*"),
    ("rho", r"\bdensity\b|how dense"),
    ("pressure", r"\bpressure\b"),
    ("area", r"\barea\b"),
    ("V", r"\bvolume\b|how much space|how many (?:litres|liters|millilitres|milliliters|ml|cm\^3|cm3|m\^3|m3|cubic)"),
    ("lam", r"wavelength|wave length|\bλ\b"),
    ("T", r"(?:time )?period\b|periodic time"),
    ("f", r"\bfrequency\b|how many (?:waves|oscillations|cycles|vibrations|swings) (?:per|each|a|every) second"),
    ("p", r"\bmomentum\b"),
    ("P", r"\bpower\b|wattage|rate of (?:doing )?work|rate (?:at which|of) (?:energy|work)|how many watts"),
    ("W", r"\bwork(?: done)?\b"),
    ("g", r"gravitational field strength|acceleration (?:due to|of) gravity|value of g\b|strength of gravity"
          r"|gravity (?:on|there|at)\b|\bg (?:on|there)\b"),
    ("weight", r"\bweight\b|\bweigh(?:s|ed)?\b|how heavy"),
    ("m", r"\bmass\b|how many (?:kg|kilograms|grams)\b|how much mass"),
    ("F", r"(?:net |resultant |average |avg\.? |braking |resistive |frictional |friction |applied |driving |unbalanced |total "
          r"|stopping |restoring |retarding |minimum |pushing |pulling |horizontal |upward |reaction |engine )?forces?"
          r"|how hard|\bthrust\b|\btension\b|\bfrictional\b|\bfriction\b|\bdrag\b|how much (?:push|pull)"),
    ("range", r"\brange\b|horizontal distance|how far (?:from|away from) the (?:base|bottom|foot|edge|table|cliff|building|"
              r"tower|wall)|how far (?:out|horizontally|forward)|distance from the (?:base|foot|bottom|edge)"),
    ("vx", r"horizontal (?:component|velocity|speed)"),
    ("vy", r"vertical (?:component|velocity|speed)"),
    ("u", r"initial (?:speed|velocity)|starting (?:speed|velocity)|launch (?:speed|velocity)|original (?:speed|velocity)"
          r"|(?:speed|velocity|how fast)[\w ]{0,25}?\b(?:was it|was the \w+|must it|should it|must the \w+|should the \w+"
          r"|did it|did the \w+) (?:be )?(?:thrown|launched|kicked|fired|projected|shot|hit|travell?ing|going|moving|driving)\b"),
    ("vf", r"final (?:speed|velocity)|impact (?:speed|velocity)|(?:speed|velocity) (?:on|at|of) impact|landing (?:speed|velocity)"
           r"|(?:speed|velocity) (?:just )?before (?:it )?(?:hits|hitting|lands|landing|impact)|recoil (?:speed|velocity)"),
    ("v", r"\bspeed\b|\bvelocity\b|how fast|how quickly"),
    ("a", r"\bacceleration\b|\bdeceleration\b|\bretardation\b|how quickly (?:does|did|will|is|was) (?:it|the [\w ]{0,15}?) "
          r"(?:accelerat|decelerat|slow)\w*"),
    ("h", r"max(?:imum)? height|highest point|greatest height|how high|\bheight\b|\baltitude\b|how tall|\bdepth\b|how deep"
          r"|how far (?:down|below|under)"),
    ("s", r"stopping distance|braking distance|thinking distance|\bdistance\b|displacement|how far|how much ground"
          r"|how long (?:is|must|should|does|will) the (?:runway|track|road|ramp|slope|skid|skid mark)s?(?: be| need to be)?"
          r"|length of (?:the )?(?:runway|track|skid)"),
    ("t", r"\btime\b|how long|how many (?:seconds|secs|minutes|mins|hours|hrs)|how much time|when (?:does|will|did|do) "
          r"(?:it|the [\w ]{0,15}?) (?:hit|land|reach|stop|return|come)|duration|how soon|how quickly (?:does|did|will|can) "
          r"(?:it|the [\w ]{0,15}?) (?:stop|reach|get)"),
    ("E", r"\benergy\b|how many (?:joules|kj|kwh|kilojoules|kilowatt[- ]hours)|how much electricity"),
    ("cost", r"\bcost\b|how much (?:will|would|does|did) it cost|\bprice\b|\bbill\b"),
]
_TARGET_RE = [(k, re.compile(p)) for k, p in TARGETS]
CUE = re.compile(r"\b(?:what|what's|whats|wat|which|how|find|calculate|calc|determine|work out|compute|estimate|"
                 r"solve for|figure out|tell me|give me)\b")
GIVEN_AFTER = re.compile(r"^\s*(?:of|is|was|=|:|being|equal to|equals|about|around|approximately|approx\.?|roughly|of about|"
                         r"of around|of approximately)?\s*(?:an? )?(?:about |around |approximately |roughly )?[-.]?\d")
GIVEN_BEFORE = re.compile(r"\d(?:[\d.]|,\d)*(?:e[+-]?\d+)?\s*-?\s*(?:[a-zµ°%/^·.\d-]+\s+){0,2}(?:of\s+)?(?:the\s+)?(?:(?:kinetic|potential|elastic|gravitational|useful|wasted|input|output|total|"
                          r"electrical|thermal|heat|chemical)\s+)?$")

TARGET_DIM = {"v": "vel", "u": "vel", "vf": "vel", "vx": "vel", "vy": "vel", "a": "acc", "s": "len", "h": "len",
              "range": "len", "t": "time", "T": "time", "m": "mass", "F": "force", "weight": "force", "E": "energy",
              "KE": "energy", "PE": "energy", "W": "energy", "J": "momentum", "p": "momentum", "P": "power",
              "f": "freq", "lam": "len", "x": "len", "k": "spring", "rho": "density", "pressure": "pressure",
              "area": "area", "V": "vol", "g": "acc"}


def _given_after(key: str, rest: str) -> bool:
    """"speed of 20 m/s" gives the speed; "momentum of a 2 kg ball" / "mass of 2 L" only name what it belongs to."""
    m = GIVEN_AFTER.match(rest)
    if not m:
        return False
    dim = TARGET_DIM.get(key)
    if dim is None:
        return True
    q = QTY.match(rest, m.end() - 1) or QTY.match(rest, max(0, m.end() - 2))
    if q is None:
        return True
    try:
        return _unit(q.group(2))[0] == dim
    except KeyError:
        return True


def _verb_between(before: str) -> bool:
    """"a 70 kg astronaut weigh": a word after the unit means the number belongs to something else."""
    m = re.search(rf"({UNIT_ALT})\s+([a-z]+)\s+(?:[a-z]+\s+)?$", before, re.I)
    return bool(m) and m.group(2) not in ("of", "the", "and", "a")


def _targets(low: str) -> list[str]:
    parts = []
    for sent in re.split(r"(?<=[!?;])\s*|(?<=\.)\s+(?=[a-z])|\n", low):
        m = CUE.search(sent)
        if sent.rstrip().endswith("?") or (parts and re.match(r"\s*(?:and|also|plus|then)\b", sent)):
            parts.append(sent)
        elif m:
            parts.append(sent[m.start():])

    def scan(s: str) -> list[str]:
        hits = []
        for key, rx in _TARGET_RE:
            for m in rx.finditer(s):
                pre = re.split(r"[.?!;]\s", s[max(0, m.start() - 30):m.start()])[-1]
                if _given_after(key, s[m.end():]) or (GIVEN_BEFORE.search(pre) and not _verb_between(pre)):
                    continue
                hits.append((m.start(), -(m.end() - m.start()), m.end(), key))
        hits.sort()
        out, last_end = [], -1
        for start, _, end, key in hits:
            if start < last_end:
                continue
            last_end = end
            if key not in out:
                out.append(key)
        return out

    found = []
    for p in parts:
        for k in scan(p):
            if k not in found:
                found.append(k)
    return found or scan(low)


# ---------------------------------------------------------------- context

FALL = r"\b(?:drop(?:s|ped)?|fall(?:s|ing)?|fell|released?|let go|free[- ]?fall(?:ing)?|freefall)\b"
UP = (r"\b(?:thrown|throws?|tossed|tosses?|launched|launches|fired|fires|shot|shoots|kicked|kicks|projected|hit|hits|"
      r"propelled|flung|flicked|jumps?|leaps?|bounces?)\s+(?:\w+\s+){0,3}?(?:straight |vertically |directly )?up(?:wards?)?\b"
      r"|\bvertically up(?:wards?)?\b|\bstraight up(?:wards?)?\b|\bupwards? (?:with|at)\b|\b(?:straight|vertically) into the air\b"
      r"|\bup into the air\b|\bthrown into the air\b|\bupward (?:speed|velocity|throw)\b")
DOWN = r"\b(?:thrown|throws?|fired|shot|projected|launched)\s+(?:\w+\s+){0,3}?(?:straight |vertically )?down(?:wards?)?\b"
HORIZ = (r"\bhorizontal(?:ly)?\b|\brolls? off\b|\bslides? off\b|\bruns? off\b|\bdrives? off\b|\brolled off\b"
         r"|\bkicked off\b|\bthrown off\b|\boff (?:the|a) (?:edge|table|cliff|roof|ledge|desk|building|bench|counter|bridge)\b")
BRAKE = (r"\bbrak(?:e|es|ed|ing)\b|\bstopping\b|\bskid(?:s|ded|ding)?\b|\bdecelerat\w*|\bcomes? to (?:a )?(?:rest|stop|halt|standstill)\b"
         r"|\b(?:to|until it) (?:a )?(?:stop|halt|standstill)\b|\bto rest\b|\bstops?\b|\bstopped\b|\bhalts?\b|\bretard\w*")
REST_START = (r"\bfrom rest\b|\bstarts? (?:off )?(?:at|from) rest\b|\b(?:initially|originally) (?:at rest|stationary)\b|\bat rest initially\b"
              r"|\bfrom (?:a )?stand ?still\b|\bfrom stationary\b|\bstarting from rest\b|\bfrom zero\b")
REST_END = (r"\b(?:comes?|came|coming|brought|bring|brings|slows?|slowed|slowing) (?:down )?to (?:a )?(?:rest|stop|halt|standstill)\b"
            r"|\bto rest\b|\bto a (?:stop|halt|standstill)\b|\bstops?\b|\bstopped\b|\bstopping\b|\bhalts?\b|\bbefore stopping\b")
ELECTRIC = (r"\bvolts?\b|\bvoltage\b|\bcurrent\b|(?<!air )\bresist(?:or|ors|ance)\b(?! (?:force|of air))|\bohms?\b|Ω|\bamps?\b|\bamperes?\b"
            r"|\bcircuit\b|\bcoulombs?\b|\bcapacit\w+|\bemf\b|potential difference|\bp\.d\.|\bcharge\b|\binduct\w+")
CHEM = (r"\bmol(?:e|es|ar|arity)?\b|\bph\b|\bconcentration\b|\bsolution\b|\bacid\b|\balkali\b|\breaction\b(?!\s+(?:time|times|force|forces|distance))|\btitrat\w+"
        r"|\bmolecul\w+|\bcompound\b|\batoms?\b|\bstoichiometr\w+|\benthalpy\b")
FINANCE = r"[$€£₹]|\binterest\b|\bloan\b|\binvest\w*|\bmortgage\b|\bsalary\b|\bprofit\b|\bdiscount\b|\btax\b"


class Ctx:
    def __init__(self, text: str):
        self.text = text
        self.t, self.sig, self.dp, self.exact, self.frac = _prep(text)
        self.low = self.t.lower()
        self.qs = _quantities(self.t)
        self.g, self.gnote, self.planet = self._gravity()
        self.mu = self._mu()
        self.targets = _targets(self.low)
        self.want = self.targets[0] if self.targets else None
        self.out = self._out_unit()

    # -- reading helpers
    def has(self, pattern: str) -> bool:
        return re.search(pattern, self.low) is not None

    def of(self, dim: str) -> list[Q]:
        return [q for q in self.qs if q.dim == dim and q.role != "gravity"]

    def ask_has(self, pattern: str) -> bool:
        parts = []
        for sent in re.split(r"(?<=[!?;])\s*|(?<=\.)\s+(?=[a-z])", self.low):
            m = CUE.search(sent)
            if m:
                parts.append(sent[m.start():])
            elif sent.rstrip().endswith("?"):
                parts.append(sent)
        return any(re.search(pattern, p) for p in (parts or [self.low]))

    def _gravity(self):
        planet = None
        m = re.search(r"\b(?:on|at|of|for|from|to) (?:the )?(moon|mars|jupiter|venus|mercury|saturn|uranus|neptune|pluto|sun|"
                      r"earth)\b|\b(lunar|martian|jovian)\b|\b(moon|mars|jupiter|venus|saturn|uranus|neptune|pluto)'s\b", self.low)
        if m:
            planet = m.group(1) or {"lunar": "moon", "martian": "mars", "jovian": "jupiter"}.get(m.group(2) or "") or m.group(3)
        gq = None
        for q in self.qs:
            if q.dim != "acc":
                continue
            if (re.search(r"(?:\bg\b|gravity|gravitational[\w ]*|free[- ]?fall acceleration|acceleration (?:due to|of) gravity|"
                          r"field strength)\s*(?:=|:|is|of|as|equals?|to be|on [\w ]+?(?: is| of)?|there is|there of|here is)?\s*"
                          r"(?:about |approximately |approx\.? |roughly |~ ?)?$", q.wpre)
                    or re.match(r"\s*(?:for|as) (?:g|gravity|the acceleration due to gravity)\b|\s*(?:of )?gravity\b", q.wpost)
                    or (planet and re.search(rf"{planet}\w*\W{{0,4}}(?:\(|,|:|-|is|where|with|has)?\s*(?:g\s*=\s*)?$", q.wpre))):
                q.role = "gravity"
                gq = gq or q
        if gq is None:
            m = (re.search(rf"(?<![\w])g\s*(?:=|:|≈|~|\bis\b|\bas\b|\bequals?\b|\bto be\b)\s*({NUM})", self.t)
                 or re.search(rf"(?:take|use|using|taking|assume|assuming|with)\s+({NUM})\s*(?:m/s\^2|n/kg|m/s2)?\s*(?:for|as)\s+"
                              rf"(?:g|gravity)\b", self.low)
                 or re.search(rf"(?:gravity|gravitational field strength|acceleration due to gravity)\s*(?:=|:|\bis\b|\bof\b|\bas\b)\s*"
                              rf"(?:about |approximately |roughly )?({NUM})(?!\s*-?\s*(?:{UNIT_ALT})(?![a-z0-9]))", self.low))
            if m:
                gv = _rat(m.group(1))
                if gv > 0:
                    for q in self.qs:
                        if q.pos == m.start(1) or (q.pos <= m.start(1) < q.end):
                            q.role = "gravity"
                    return gv, f"g = {num(gv)} m/s²", planet
        if gq is not None and gq.val > 0:
            where = f" on {planet.title() if planet != 'moon' else 'the Moon'}" if planet and planet != "earth" else ""
            return gq.val, f"g{where} = {num(gq.val)} m/s²", planet
        if planet and planet != "earth":
            name = "the Moon" if planet == "moon" else ("the Sun" if planet == "sun" else planet.title())
            return PLANETS[planet], f"g on {name} = {num(PLANETS[planet])} m/s²", planet
        return G0, "g = 9.81 m/s²", planet

    def _mu(self):
        m = re.search(rf"(?:coefficients? of (?:kinetic |static |sliding |rolling )?friction|friction(?:al)? coefficient|"
                      rf"(?<![a-z])μ|(?<![a-z])mu(?![a-z])|coeff(?:icient)?\.? of friction)\s*(?:\w+\s*){{0,4}}?(?:of|is|=|:|equal to|"
                      rf"equals|was|being)?\s*(?:about |approximately )?({NUM})", self.low)
        m = m or re.search(rf"({NUM})\s*(?:coefficient of friction|friction coefficient)", self.low)
        if m:
            v = _rat(m.group(1))
            if 0 < v < 5:
                for q in self.qs:
                    if q.pos == m.start(1):
                        q.role = "mu"
                return v
        return None

    def _out_unit(self):
        m = re.search(rf"\b(?:in|into|as|answer in|give it in|express it in)\s+(?:units of\s+)?({UNIT_ALT})(?![a-z0-9])\s*"
                      rf"(?:please|pls|plz|thanks|thank you|\?|\.|!|,|\)|$)", self.t, re.I)
        if not m:
            return None
        try:
            dim, factor, disp = _unit(m.group(1))
        except KeyError:
            return None
        return dim, factor, disp

    # -- formatting helpers
    def show(self, x, dim: str, unit: str | None = None) -> str:
        """The answer value: in the asked unit, else `unit`, else SI; exact form too when useful."""
        x = sp.nsimplify(x) if isinstance(x, float) else sp.sympify(x)
        disp = unit or SI.get(dim, "")
        factor = FACTOR.get(disp, 1) if unit else 1
        if self.out and self.out[0] == dim:
            factor, disp = self.out[1], self.out[2]
        v = sp.nsimplify(x / factor) if factor != 1 else x
        sep = "" if disp in ("%", "°") else " "
        dec = num(v, self.sig, self.dp)
        if self.frac and v.is_Rational and v.q != 1:
            return f"{v.p}/{v.q}{sep}{disp} {'=' if _terminates(v) else '≈'} {dec}{sep}{disp}".strip()
        ex = exact_form(v, force=self.exact)
        if ex and ex != dec:
            return f"{ex}{sep}{disp} ≈ {dec}{sep}{disp}".strip()
        return f"{dec}{sep}{disp}".strip()

    def sol(self, answer: str, steps: list[str], check: str = "") -> Solution:
        return Solution("physics", self.text.strip(), answer, steps, check=check, confidence=0.97)


def n(x) -> str:
    """A number inside a step: exact when short, else 4 significant figures."""
    return num(x)


def p(x) -> str:
    """A number inside a substitution, bracketed when negative."""
    s = num(x)
    return f"({s})" if s.startswith("-") else s


def _std(formula: str, known: list[str], sub: str, result: str, extra: list[str] | None = None) -> list[str]:
    steps = [f"formula: {formula}", "known: " + ", ".join(known)] + (extra or [])
    return steps + [f"substitute: {sub}", f"result: {result}"]


def _deg(q: Q):
    return q.val  # angles are kept in degrees


def _cos(deg):
    return sp.nsimplify(sp.cos(sp.pi * deg / 180))


def _sin(deg):
    return sp.nsimplify(sp.sin(sp.pi * deg / 180))


def _sqrt(x):
    return sp.sqrt(sp.nsimplify(x))


def _ok(x) -> bool:
    x = sp.sympify(x)
    return x.is_number and x.is_finite and x.is_real is not False


# ---------------------------------------------------------------- the SUVAT engine

EQS = [("v = u + a·t", "uvat", "v", "u + a·t"), ("s = ½·(u + v)·t", "uvst", "s", "½·(u + v)·t"),
       ("v² = u² + 2·a·s", "uvas", "v²", "u² + 2·a·s"), ("s = u·t + ½·a·t²", "uast", "s", "u·t + ½·a·t²"),
       ("s = v·t − ½·a·t²", "vast", "s", "v·t − ½·a·t²")]
REARR = {("v = u + a·t", "v"): "v = u + a·t", ("v = u + a·t", "u"): "u = v − a·t", ("v = u + a·t", "a"): "a = (v − u) / t",
         ("v = u + a·t", "t"): "t = (v − u) / a", ("s = ½·(u + v)·t", "s"): "s = ½·(u + v)·t",
         ("s = ½·(u + v)·t", "u"): "u = 2·s / t − v", ("s = ½·(u + v)·t", "v"): "v = 2·s / t − u",
         ("s = ½·(u + v)·t", "t"): "t = 2·s / (u + v)", ("v² = u² + 2·a·s", "v"): "v = √(u² + 2·a·s)",
         ("v² = u² + 2·a·s", "u"): "u = √(v² − 2·a·s)", ("v² = u² + 2·a·s", "a"): "a = (v² − u²) / (2·s)",
         ("v² = u² + 2·a·s", "s"): "s = (v² − u²) / (2·a)", ("s = u·t + ½·a·t²", "s"): "s = u·t + ½·a·t²",
         ("s = u·t + ½·a·t²", "u"): "u = (s − ½·a·t²) / t", ("s = u·t + ½·a·t²", "a"): "a = 2·(s − u·t) / t²",
         ("s = u·t + ½·a·t²", "t"): "½·a·t² + u·t − s = 0", ("s = v·t − ½·a·t²", "s"): "s = v·t − ½·a·t²",
         ("s = v·t − ½·a·t²", "v"): "v = (s + ½·a·t²) / t", ("s = v·t − ½·a·t²", "a"): "a = 2·(v·t − s) / t²",
         ("s = v·t − ½·a·t²", "t"): "½·a·t² − v·t + s = 0"}
SIDES = {"v = u + a·t": (lambda k: k["v"], lambda k: k["u"] + k["a"] * k["t"]),
         "s = ½·(u + v)·t": (lambda k: k["s"], lambda k: (k["u"] + k["v"]) * k["t"] / 2),
         "v² = u² + 2·a·s": (lambda k: k["v"] ** 2, lambda k: k["u"] ** 2 + 2 * k["a"] * k["s"]),
         "s = u·t + ½·a·t²": (lambda k: k["s"], lambda k: k["u"] * k["t"] + k["a"] * k["t"] ** 2 / 2),
         "s = v·t − ½·a·t²": (lambda k: k["s"], lambda k: k["v"] * k["t"] - k["a"] * k["t"] ** 2 / 2)}
SUVAT_DIM = {"u": "vel", "v": "vel", "a": "acc", "s": "len", "t": "time"}


def _quad(A, B, C) -> list:
    if A == 0:
        return [] if B == 0 else [-C / B]
    disc = B ** 2 - 4 * A * C
    if disc < 0:
        return []
    r = sp.sqrt(disc)
    return [(-B + r) / (2 * A), (-B - r) / (2 * A)]


def _closed(eq: str, want: str, k: dict) -> list:
    u, v, a, s, t = (k.get(x) for x in "uvast")
    try:
        if eq == "v = u + a·t":
            return [{"v": lambda: u + a * t, "u": lambda: v - a * t, "a": lambda: (v - u) / t, "t": lambda: (v - u) / a}[want]()]
        if eq == "s = ½·(u + v)·t":
            return [{"s": lambda: (u + v) * t / 2, "u": lambda: 2 * s / t - v, "v": lambda: 2 * s / t - u,
                     "t": lambda: 2 * s / (u + v)}[want]()]
        if eq == "v² = u² + 2·a·s":
            if want in ("v", "u"):
                sq = (u ** 2 + 2 * a * s) if want == "v" else (v ** 2 - 2 * a * s)
                if sq < 0:
                    return []
                r = sp.sqrt(sq)
                return [r, -r] if r != 0 else [r]
            return [{"a": lambda: (v ** 2 - u ** 2) / (2 * s), "s": lambda: (v ** 2 - u ** 2) / (2 * a)}[want]()]
        if eq == "s = u·t + ½·a·t²":
            if want == "t":
                return _quad(a / 2, u, -s)
            return [{"s": lambda: u * t + a * t ** 2 / 2, "u": lambda: (s - a * t ** 2 / 2) / t,
                     "a": lambda: 2 * (s - u * t) / t ** 2}[want]()]
        if eq == "s = v·t − ½·a·t²":
            if want == "t":
                return _quad(-a / 2, v, -s)
            return [{"s": lambda: v * t - a * t ** 2 / 2, "v": lambda: (s + a * t ** 2 / 2) / t,
                     "a": lambda: 2 * (v * t - s) / t ** 2}[want]()]
    except ZeroDivisionError:
        return []
    return []


def _pick_eq(k: dict, want: str):
    for name, vars_, _, _ in EQS:
        if want in vars_ and all(x in k for x in vars_ if x != want):
            return name
    return None


def _subst(template: str, k: dict) -> str:
    s = re.sub(r"(?<![a-zA-Z0-9_])([uvast])(?![a-zA-Z_])", lambda m: p(k[m.group(1)]) if m.group(1) in k else m.group(1),
               template)
    return s.replace("·", " × ")


def _fill(k: dict, prefer_up: bool = False) -> dict:
    """All five SUVAT values from any three (for the check)."""
    k = dict(k)
    for _ in range(2):
        for x in "uvast":
            if x in k:
                continue
            eq = _pick_eq(k, x)
            if not eq:
                continue
            roots = [r for r in _closed(eq, x, k) if _ok(r)]
            if x == "t":
                roots = sorted(r for r in roots if r > 0)
            if roots:
                k[x] = roots[0]
    return k


def suvat(c: Ctx, k: dict, wants: list[str], notes: dict, intro: list[str] | None = None, vertical: bool = False,
          speed_names: dict | None = None):
    """Solve for each wanted SUVAT letter; returns (answers, steps, check) or None."""
    k = {x: sp.nsimplify(v) for x, v in k.items()}
    if len([x for x in "uvast" if x in k]) < 3:
        return None
    steps = list(intro or [])
    knowns = [f"{x} = {n(k[x])} {SI[SUVAT_DIM[x]]}" + (f" ({notes[x]})" if notes.get(x) else "") for x in "uvast" if x in k]
    steps.append("known: " + ", ".join(knowns))
    answers, check = [], ""
    for want in wants:
        if want in k:
            continue
        eq = _pick_eq(k, want)
        if not eq:
            return None
        roots = [r for r in _closed(eq, want, k) if _ok(r)]
        if not roots:
            return None
        form = REARR[(eq, want)]
        if want == "t":
            pos = sorted({r for r in roots if r > 0})
            if not pos:
                return None
            if eq.startswith("s = u·t") and k.get("u") == 0:
                form = "t = √(2·s / a)"
            roots = pos if (vertical and len(pos) == 2) else pos[:1]
        elif want in ("u", "v") and len(roots) == 2:
            # the sign that keeps time positive (falling objects end up moving down)
            best = roots[0]
            for r in roots:
                trial = _fill({**k, want: r})
                if trial.get("t") is not None and trial["t"] > 0 and trial.get("t") == trial.get("t"):
                    ok_t = True
                    if "t" not in k:
                        eq2 = _pick_eq({**k, want: r}, "t")
                        cand = [x for x in _closed(eq2, "t", {**k, want: r})] if eq2 else []
                        ok_t = any(_ok(x) and x > 0 for x in cand) and not any(_ok(x) and x < 0 for x in cand if len(cand) == 1)
                    if ok_t:
                        best = r
                        break
            roots = [best]
        sub = form.split(" = ", 1)[1] if " = " in form and not form.endswith("= 0") else form
        lhs = form.split(" = ", 1)[0] if " = " in form and not form.endswith("= 0") else want
        steps.append(f"formula: {eq}" + (f"  →  {form}" if form != eq else ""))
        if form.endswith("= 0"):
            steps.append(f"substitute: {_subst(form, k)}, solve the quadratic for t (keep t > 0)")
        else:
            steps.append(f"substitute: {lhs} = {_subst(sub, k)}")
        unit = SI[SUVAT_DIM[want]]
        vals = []
        for r in roots:
            vals.append(r)
        k[want] = vals[0]
        if want == "t" and len(vals) == 2:
            res = f"t = {n(vals[0])} s (on the way up) or {n(vals[1])} s (on the way down)"
            ans = f"{c.show(vals[0], 'time')} or {c.show(vals[1], 'time')}"
        else:
            v0 = vals[0]
            res = f"{want} = {n(v0)} {unit}"
            name = (speed_names or {}).get(want, "")
            if want == "a" and v0 < 0:
                if c.ask_has(r"decelerat|retard"):
                    ans = c.show(-v0, "acc")
                    res += f", i.e. a deceleration of {n(-v0)} m/s²"
                else:
                    ans = c.show(v0, "acc") + " (slowing down)"
            elif want in ("u", "v") and v0 < 0:
                ans = c.show(-v0, "vel") + (f" {name}" if name else (" downwards" if vertical else " backwards"))
                res += f" (the minus sign: moving {'down' if vertical else 'backwards'})"
            elif want in ("s",) and v0 < 0:
                ans = c.show(-v0, "len") + (" below the start" if vertical else " backwards")
            else:
                ans = c.show(v0, SUVAT_DIM[want])
                if want in ("u", "v") and c.vel_unit():
                    vu = c.vel_unit()
                    if not c.out:
                        ans += f" ({num(v0 / FACTOR[vu], c.sig, c.dp)} {vu})"
        steps.append(f"result: {res}")
        answers.append((want, ans))
    full = _fill(k)
    used = {e for e, *_ in EQS}
    last = wants[-1]
    for name, vars_, lhs_t, rhs_t in EQS:
        if last in vars_ and all(x in full for x in vars_) and name in used:
            if name == _pick_eq({x: v for x, v in k.items() if x != last}, last):
                continue
            lf, rf = SIDES[name]
            lv, rv = lf(full), rf(full)
            if sp.simplify(lv - rv) == 0:
                extra = [x for x in vars_ if x not in k]
                pre = ", ".join(f"{x} = {n(full[x])} {SI[SUVAT_DIM[x]]}" for x in extra)
                check = (f"{pre}; " if pre else "") + f"{lhs_t} = {_subst(lhs_t, full)} = {n(lv)} and " \
                        f"{rhs_t} = {_subst(rhs_t, full)} = {n(rv)} ✓"
                break
    return answers, steps, check


def _join(answers) -> str:
    if len(answers) == 1:
        return answers[0][1]
    return ", ".join(f"{w} = {a}" for w, a in answers)


def _vel_role(q: Q) -> str | None:
    pre = q.pre.rstrip()
    lab = q.label.lower()
    if lab in ("u", "v0", "vi", "u1", "u2"):
        return "u"
    if lab in ("v", "vf"):
        return "v"
    if re.search(r"\b(?:to|reach\w*|until|up to|down to|becomes?|gets? to|got to|attains?|final(?:ly)?(?: (?:speed|velocity))?"
                 r"(?: of| is| was| =)?|increas\w* to|decreas\w* to|slows? (?:down )?to|speeds? up to|accelerat\w* to|"
                 r"hits? (?:the \w+ )?at|lands? at|impact (?:speed|velocity)(?: of)?)\s*$", pre):
        return "v"
    if re.search(r"\b(?:from|initial(?:ly)?(?: (?:speed|velocity))?(?: of| is| was| =)?|start\w*(?: off)?(?: at| with| moving at)?"
                 r"(?: a speed of| a velocity of)?|launch\w*(?: \w+)? (?:at|with)(?: a speed of| a velocity of)?|thrown(?: \w+){0,2} "
                 r"(?:at|with)(?: a speed of| a velocity of)?|projected(?: \w+)? (?:at|with)|fired(?: \w+)? (?:at|with)|"
                 r"kicked(?: \w+)? (?:at|with))\s*$", pre):
        return "u"
    if re.search(r"\binitial|\bstart", pre):
        return "u"
    if re.search(r"\bfinal\b", pre):
        return "v"
    return None


def _ctx_vel_unit(c: Ctx):
    for q in c.of("vel"):
        if q.unit != "m/s":
            return q.unit
    return None


Ctx.vel_unit = _ctx_vel_unit


# ---------------------------------------------------------------- handlers

def h_convert(c: Ctx):
    """'convert 2.5 kWh to joules', 'how many kJ is 5000 J', '72 km/h in m/s'."""
    qs = [q for q in c.qs if q.dim in ("energy", "vel", "power", "pressure", "density")]
    if len(qs) != 1 or len(c.qs) != 1:
        return None
    q = qs[0]
    m = re.search(rf"\b(?:in|into|to|as)\s+(?:units of\s+)?({UNIT_ALT})(?![a-z0-9])", c.t[q.end:], re.I) \
        or re.search(rf"how many ({UNIT_ALT})(?![a-z0-9])\s+(?:are|is|does|make|in|equal|=)", c.t[:q.pos], re.I) \
        or re.search(rf"\b({UNIT_ALT})(?![a-z0-9])\s+(?:are|is) (?:in|there in)\s*$", c.t[:q.pos], re.I)
    if not m or not c.has(r"\bconvert|\bin\b|\binto\b|how many|\bexpress|\bequals?\b|\bis\b|\bto\b"):
        return None
    dim, factor, disp = _unit(m.group(1))
    if dim != q.dim or disp == q.unit:
        return None
    v = q.val / factor
    src = FACTOR[q.unit]
    rule = f"1 {q.unit} = {n(src / factor)} {disp}" if src >= factor else f"1 {disp} = {n(factor / src)} {q.unit}"
    sub = (f"{q.shown()} × {n(src / factor)}" if src >= factor else f"{q.shown()} ÷ {n(factor / src)}")
    ans = c.show(v * factor, dim, disp) if not c.out else c.show(v * factor, dim)
    steps = [f"rule: {rule}", f"convert: {sub} = {n(v)} {disp}", f"result: {ans}"]
    back = v * factor / src
    return c.sol(ans, steps, f"{n(v)} {disp} → {n(back)} {q.unit} ✓")


def h_waves(c: Ctx):
    if not c.has(r"\bwaves?\b|frequency|wavelength|wave length|\bhz\b|hertz|\bperiod\b|oscillat|vibrat|\bsound\b|\blight\b|ripple|"
                 r"tuning fork|\bradio\b|\becho|microwave|x-ray|λ|electromagnetic|\bsonar\b|\bnote\b|\bstring\b|khz|mhz|ghz"):
        return None
    want = next((w for w in c.targets if w in ("lam", "f", "T", "v", "s", "t")), None)
    if want is None:
        return None
    fs, vs, ls, ts = c.of("freq"), c.of("vel"), c.of("len"), c.of("time")
    lam = dist = per = dur = None
    for q in ls:
        if re.search(r"wavelength|wave length|λ|lambda", q.pre) or q.label == "λ":
            lam = q
        elif re.search(r"travel|moves?|cover|distance|goes|across|away|apart|cliff|wall|far", q.pre + q.post):
            dist = q
        elif lam is None:
            lam = q
    for q in ts:
        if re.search(r"period|every|each (?:wave|oscillation|cycle|vibration|swing)|one (?:wave|oscillation|cycle|vibration|swing)"
                     r"(?: \w+)?$", q.pre) or q.label == "T":
            per = q
        else:
            dur = q
    count = re.search(rf"(?<![\w.])(\d+(?:\.\d+)?)\s+(?:complete |full )?(?:waves|oscillations|cycles|vibrations|swings|"
                      rf"crests|ripples|times)\b", c.low)
    speed, snote = (vs[0].val, vs[0].known("v")) if vs else (None, "")
    if speed is None and c.has(r"\blight\b|electromagnetic|\bem wave|\bradio\b|microwave|x-ray|gamma|infra-?red|ultraviolet|"
                               r"\buv\b|visible|laser|photon"):
        speed, snote = C_LIGHT, "v = c = 3 × 10⁸ m/s (speed of light)"
    elif speed is None and c.has(r"\bsound\b|\becho|\bsonar\b|\bnote\b|tuning fork") and not c.has(r"\bwater\b|\bsteel\b"):
        speed, snote = V_SOUND, "v = 343 m/s (speed of sound in air at 20 °C)"
    if c.has(r"\becho") and want in ("s", "t") and speed is not None:
        if want == "s" and (dur or per):
            tq = dur or per
            d = speed * tq.val / 2
            return c.sol(c.show(d, "len"), _std("d = v·t / 2  (the echo goes there and back)", [snote, tq.known("t")],
                                               f"d = {n(speed)} × {n(tq.val)} / 2", f"d = {n(d)} m"),
                         f"2 × {n(d)} / {n(speed)} = {n(2 * d / speed)} s ✓")
        if want == "t" and dist:
            tt = 2 * dist.val / speed
            return c.sol(c.show(tt, "time"), _std("t = 2·d / v  (there and back)", [snote, dist.known("d")],
                                                  f"t = 2 × {n(dist.val)} / {n(speed)}", f"t = {n(tt)} s"))
        return None
    f = fs[0].val if fs else None
    fnote = fs[0].known("f") if fs else ""
    if f is None and count and (dur or per):
        tq = dur or per
        cnt = R(count.group(1))
        f = cnt / tq.val
        if want == "f":
            return c.sol(c.show(f, "freq"), _std("f = number of waves / time", [f"N = {count.group(1)}", tq.known("t")],
                                                 f"f = {count.group(1)} / {n(tq.val)}", f"f = {n(f)} Hz"),
                         f"T = 1 / f = {n(1 / f)} s ✓")
        fnote = f"f = {count.group(1)} / {n(tq.val)} = {n(f)} Hz"
    T = per.val if per else None
    if want == "T":
        if f is not None:
            return c.sol(c.show(1 / f, "time"), _std("T = 1 / f", [fnote], f"T = 1 / {n(f)}", f"T = {n(1 / f)} s"),
                         f"f = 1 / T = {n(f)} Hz ✓")
        if lam and speed is not None:
            tt = lam.val / speed
            return c.sol(c.show(tt, "time"), _std("T = λ / v", [lam.known("λ"), snote], f"T = {n(lam.val)} / {n(speed)}",
                                                  f"T = {n(tt)} s"))
        return None
    if want == "f":
        if T is not None and not lam:
            return c.sol(c.show(1 / T, "freq"), _std("f = 1 / T", [per.known("T")], f"f = 1 / {n(T)}", f"f = {n(1 / T)} Hz"),
                         f"T = 1 / f = {n(T)} s ✓")
        if lam and speed is None and dist and dur:
            speed, snote = dist.val / dur.val, f"v = {n(dist.val)} m / {n(dur.val)} s = {n(dist.val / dur.val)} m/s"
        if lam and speed is not None:
            ff = speed / lam.val
            return c.sol(c.show(ff, "freq"), _std("f = v / λ  (from v = f·λ)", [snote, lam.known("λ")],
                                                  f"f = {n(speed)} / {n(lam.val)}", f"f = {n(ff)} Hz"),
                         f"f·λ = {n(ff)} × {n(lam.val)} = {n(ff * lam.val)} m/s ✓")
        if T is not None:
            return c.sol(c.show(1 / T, "freq"), _std("f = 1 / T", [per.known("T")], f"f = 1 / {n(T)}", f"f = {n(1 / T)} Hz"))
        return None
    if want == "lam":
        if speed is None and dist and dur:
            speed, snote = dist.val / dur.val, f"v = {n(dist.val)} m / {n(dur.val)} s = {n(dist.val / dur.val)} m/s"
        if speed is not None and f is not None:
            lv = speed / f
            ans = c.show(lv, "len")
            if lv < R(1, 1000) and not c.out:
                ans = c.show(lv, "len", "nm") if lv < R(1, 10**6) else ans
            return c.sol(ans, _std("λ = v / f  (from v = f·λ)", [snote, fnote], f"λ = {n(speed)} / {n(f)}", f"λ = {n(lv)} m"),
                         f"f·λ = {n(f)} × {n(lv)} = {n(f * lv)} m/s ✓")
        if speed is not None and T is not None:
            lv = speed * T
            return c.sol(c.show(lv, "len"), _std("λ = v·T", [snote, per.known("T")], f"λ = {n(speed)} × {n(T)}", f"λ = {n(lv)} m"))
        return None
    if want == "v" and lam:
        if f is not None:
            vv = f * lam.val
            return c.sol(c.show(vv, "vel"), _std("v = f·λ", [fnote, lam.known("λ")], f"v = {n(f)} × {n(lam.val)}",
                                                 f"v = {n(vv)} m/s"), f"λ = v / f = {n(vv / f)} m ✓")
        if T is not None:
            vv = lam.val / T
            return c.sol(c.show(vv, "vel"), _std("v = λ / T", [lam.known("λ"), per.known("T")], f"v = {n(lam.val)} / {n(T)}",
                                                 f"v = {n(vv)} m/s"))
    return None


def h_spring(c: Ctx):
    ks = c.of("spring")
    if not (ks or c.has(r"\bsprings?\b|hooke|elastic band|rubber band|bungee|catapult|slingshot|trampoline")):
        return None
    want = next((w for w in c.targets if w in ("F", "k", "x", "PE", "E", "W", "v", "m", "weight", "s")), None)
    if want is None:
        return None
    k = ks[0] if ks else None
    fs, ms, es, ls = c.of("force"), c.of("mass"), c.of("energy"), c.of("len")
    x = None
    xnote = ""
    if len(ls) == 2 and re.search(r"natural|original|unstretched|initial|from|relaxed|starts?|normal", c.low):
        a, b = ls
        x = abs(b.val - a.val)
        xnote = f"x = {b.shown()} − {a.shown()} = {n(x)} m" if b.val > a.val else f"x = {a.shown()} − {b.shown()} = {n(x)} m"
    elif len(ls) == 1:
        x = ls[0].val
        xnote = ls[0].known("x")
    elif len(ls) > 2:
        return None
    F = fnote = None
    if fs:
        F, fnote = fs[0].val, fs[0].known("F")
    elif ms and want not in ("m", "v") and c.has(r"\bhang|\bhung|attached|suspended|placed on|sits? on|put on|weight|load|"
                                                 r"hooked|supports?|holds?"):
        F = ms[0].val * c.g
        fnote = f"F = m·g = {n(ms[0].val)} × {n(c.g)} = {n(F)} N"
    E = es[0].val if es else None
    if want == "F" and k is not None and x is not None:
        ff = k.val * x
        return c.sol(c.show(ff, "force"), _std("F = k·x  (Hooke's law)", [k.known("k"), xnote], f"F = {n(k.val)} × {n(x)}",
                                                f"F = {n(ff)} N"), f"x = F / k = {n(ff / k.val)} m ✓")
    if want == "k":
        if F is not None and x:
            kv = F / x
            return c.sol(c.show(kv, "spring"), _std("k = F / x  (Hooke's law)", [fnote, xnote], f"k = {n(F)} / {n(x)}",
                                                    f"k = {n(kv)} N/m"), f"k·x = {n(kv)} × {n(x)} = {n(kv * x)} N ✓")
        if E is not None and x:
            kv = 2 * E / x ** 2
            return c.sol(c.show(kv, "spring"), _std("k = 2·E / x²  (from E = ½·k·x²)", [es[0].known("E"), xnote],
                                                    f"k = 2 × {n(E)} / {n(x)}²", f"k = {n(kv)} N/m"),
                         f"½ × {n(kv)} × {n(x)}² = {n(kv * x ** 2 / 2)} J ✓")
        return None
    if want in ("x", "s") and k is not None:
        if F is not None:
            xv = F / k.val
            ans = c.show(xv, "len") if c.out or xv >= 1 else f"{c.show(xv, 'len')} ({num(xv * 100, c.sig, c.dp)} cm)"
            return c.sol(ans, _std("x = F / k  (Hooke's law)", [fnote, k.known("k")], f"x = {n(F)} / {n(k.val)}",
                                   f"x = {n(xv)} m"), f"k·x = {n(k.val)} × {n(xv)} = {n(k.val * xv)} N ✓")
        if E is not None:
            xv = _sqrt(2 * E / k.val)
            ans = c.show(xv, "len")
            return c.sol(ans, _std("x = √(2·E / k)  (from E = ½·k·x²)", [es[0].known("E"), k.known("k")],
                                   f"x = √(2 × {n(E)} / {n(k.val)})", f"x = {n(xv)} m"),
                         f"½ × {n(k.val)} × {n(xv)}² = {n(k.val * xv ** 2 / 2)} J ✓")
        return None
    if want in ("PE", "E", "W") and x is not None:
        if k is not None:
            ev = k.val * x ** 2 / 2
            return c.sol(c.show(ev, "energy"), _std("E = ½·k·x²  (elastic potential energy)", [k.known("k"), xnote],
                                                    f"E = ½ × {n(k.val)} × {n(x)}²", f"E = {n(ev)} J"),
                         f"average force ½·k·x = {n(k.val * x / 2)} N over {n(x)} m = {n(k.val * x / 2 * x)} J ✓")
        if F is not None:
            ev = F * x / 2
            return c.sol(c.show(ev, "energy"), _std("E = ½·F·x  (force rises steadily from 0 to F)", [fnote, xnote],
                                                    f"E = ½ × {n(F)} × {n(x)}", f"E = {n(ev)} J"))
        return None
    if want == "v" and k is not None and x is not None and ms:
        m = ms[0].val
        vv = x * _sqrt(k.val / m)
        return c.sol(c.show(vv, "vel"), _std("½·k·x² = ½·m·v²  →  v = x·√(k / m)", [k.known("k"), xnote, ms[0].known("m")],
                                             f"v = {n(x)} × √({n(k.val)} / {n(m)})", f"v = {n(vv)} m/s"),
                     f"½ × {n(k.val)} × {n(x)}² = {n(k.val * x ** 2 / 2)} J = ½ × {n(m)} × {n(vv)}² = {n(m * vv ** 2 / 2)} J ✓")
    if want in ("m", "weight") and k is not None and x is not None and want == "m":
        mv = k.val * x / c.g
        return c.sol(c.show(mv, "mass"), _std("m·g = k·x  →  m = k·x / g", [k.known("k"), xnote, c.gnote],
                                              f"m = {n(k.val)} × {n(x)} / {n(c.g)}", f"m = {n(mv)} kg"))
    return None


def _eff_role(q: Q) -> str:
    near = q.wpre[-30:] + " | " + q.wpost[:30]
    pre, post = q.pre[-30:], q.post[:30]
    if re.search(r"wasted|waste|lost|losses|loses|dissipat", pre + " " + post[:15]):
        return "waste"
    if re.search(r"useful|output|outputs|gives? out|gives\b|produces?|delivers?|provides?|emits?|transfers? \w* ?useful", pre):
        return "out"
    if re.search(r"^\s*(?:of )?(?:useful|output|light|sound|kinetic|mechanical|work)", post):
        return "out"
    if re.search(r"input|supplied|supplies|uses?\b|used|consumes?|takes? in|put in|given|draws?|rated|total|electrical|fuel", pre):
        return "in"
    if re.search(r"^\s*(?:of )?(?:input|supplied|electrical|electricity|fuel|chemical)", post) or "bulb" in near or "motor" in near:
        return "in"
    return ""


def h_efficiency(c: Ctx):
    if not c.has(r"efficien|\buseful\b|\bwasted?\b|\blost as\b"):
        return None
    if c.has(ELECTRIC) and not c.has(r"efficien"):
        return None
    pcts = [q for q in c.of("pct")]
    for dim in ("energy", "power"):
        qs = c.of(dim)
        if not qs and not (dim == "energy" and c.of("mass")):
            continue
        roles = {q: _eff_role(q) for q in qs}
        ins = [q for q in qs if roles[q] == "in"]
        outs = [q for q in qs if roles[q] == "out"]
        wastes = [q for q in qs if roles[q] == "waste"]
        rest = [q for q in qs if not roles[q]]
        for q in sorted(rest, key=lambda q: -q.val):
            (ins if not ins else outs if not outs else wastes).append(q)
        u = "J" if dim == "energy" else "W"
        sym = "E" if dim == "energy" else "P"
        Ein = ins[0].val if ins else None
        Eout = outs[0].val if outs else None
        notes = []
        if ins:
            notes.append(ins[0].known(f"{sym} in"))
        if outs:
            notes.append(outs[0].known(f"{sym} useful"))
        if Eout is None and dim == "energy" and c.of("mass") and c.of("len") and c.has(r"lift|rais|hoist|winch|crane|climb|up\b"):
            m, h = c.of("mass")[0], c.of("len")[0]
            Eout = m.val * c.g * h.val
            notes.append(f"useful E = m·g·h = {n(m.val)} × {n(c.g)} × {n(h.val)} = {n(Eout)} J")
        if Eout is None and Ein is not None and wastes:
            Eout = Ein - wastes[0].val
            notes.append(f"useful = {n(Ein)} − {n(wastes[0].val)} = {n(Eout)} {u}")
        if Ein is None and Eout is not None and wastes:
            Ein = Eout + wastes[0].val
            notes.append(f"input = {n(Eout)} + {n(wastes[0].val)} = {n(Ein)} {u}")
        if c.want == "eff" and Ein and Eout is not None:
            eff = Eout / Ein * 100
            if eff > 100:
                return None
            return c.sol(c.show(eff, "pct"), _std("efficiency = useful output / total input × 100%", notes,
                                                  f"efficiency = {n(Eout)} / {n(Ein)} × 100%", f"efficiency = {n(eff)}%"),
                         f"wasted = {n(Ein - Eout)} {u} ({n(100 - eff)}%) ✓")
        if pcts and c.want in ("E", "P", "W", "eff") or (pcts and c.want is None):
            eta = pcts[0].val / 100
            ask_waste = c.ask_has(r"wasted|lost|waste")
            ask_in = c.ask_has(r"input|supplied|supply|put in|needed|required|must be|consume|use[sd]?\b|how much (?:energy|power) "
                               r"(?:does|must|will) (?:it|the \w+) (?:need|take|use)")
            if Ein is not None and (Eout is None or ask_waste):
                out = Ein * eta
                if ask_waste:
                    w = Ein - out
                    return c.sol(c.show(w, dim), _std("wasted = input × (1 − efficiency)", notes + [pcts[0].known("efficiency")],
                                                      f"wasted = {n(Ein)} × (1 − {n(eta)})", f"wasted = {n(w)} {u}"),
                                 f"useful {n(out)} + wasted {n(w)} = {n(Ein)} {u} ✓")
                return c.sol(c.show(out, dim), _std("useful output = efficiency × input", notes + [pcts[0].known("efficiency")],
                                                    f"useful = {n(eta)} × {n(Ein)}", f"useful output = {n(out)} {u}"),
                             f"{n(out)} / {n(Ein)} = {n(eta * 100)}% ✓")
            if Eout is not None and (Ein is None or ask_in):
                inp = Eout / eta
                if ask_waste:
                    return c.sol(c.show(inp - Eout, dim), _std("input = useful / efficiency, wasted = input − useful",
                                                               notes + [pcts[0].known("efficiency")],
                                                               f"input = {n(Eout)} / {n(eta)} = {n(inp)} {u}",
                                                               f"wasted = {n(inp - Eout)} {u}"))
                return c.sol(c.show(inp, dim), _std("input = useful output / efficiency", notes + [pcts[0].known("efficiency")],
                                                    f"input = {n(Eout)} / {n(eta)}", f"input = {n(inp)} {u}"),
                             f"{n(Eout)} / {n(inp)} = {n(eta * 100)}% ✓")
    return None


def _fluid(c: Ctx):
    ds = c.of("density")
    if ds:
        return ds[0].val, ds[0].known("ρ")
    for pat, rho, name in FLUIDS:
        if c.has(rf"\b(?:{pat})\b"):
            return rho, f"ρ({name}) = {n(rho)} kg/m³"
    return None, ""


def h_pressure(c: Ctx):
    want = next((w for w in c.targets if w in ("pressure", "h", "s", "F", "area", "rho")), None)
    if want is None:
        return None
    ps, fs, areas, ls = c.of("pressure"), c.of("force"), c.of("area"), c.of("len")
    if want != "pressure" and not ps:
        return None
    if want == "rho" and not (ps and ls):
        return None
    hydro = c.has(r"\bdepth\b|\bdeep\b|below the surface|beneath the surface|under ?water|\bsubmerged|\bdiver\b|\bsubmarine\b|"
                  r"\bliquid\b|\bfluid\b|column|\bbottom of\b|\bunder the (?:sea|water|surface)|\bocean\b|\bsea\b|\blake\b|"
                  r"\bpool\b|\btank\b|\bdam\b|\bwater\b|\bmercury\b|\boil\b") or c.of("density")
    if c.has(r"hydraulic|piston|\bjack\b|\bpress\b") and len(areas) == 2 and fs and want in ("F", "pressure"):
        a1, a2 = areas
        f1 = fs[0]
        if want == "F":
            f2 = f1.val * a2.val / a1.val
            return c.sol(c.show(f2, "force"), _std("F₂ = F₁ · A₂ / A₁  (same pressure on both pistons)",
                                                   [f1.known("F₁"), a1.known("A₁"), a2.known("A₂")],
                                                   f"F₂ = {n(f1.val)} × {n(a2.val)} / {n(a1.val)}", f"F₂ = {n(f2)} N"),
                         f"pressure {n(f1.val / a1.val)} Pa on both sides ✓")
    rho, rnote = _fluid(c)
    if want == "pressure":
        if fs or c.of("mass"):
            if not areas:
                return None if not (hydro and ls) else None
            if fs:
                F, fnote = fs[0].val, fs[0].known("F")
            else:
                m = c.of("mass")[0]
                F = m.val * c.g
                fnote = f"F = m·g = {n(m.val)} × {n(c.g)} = {n(F)} N"
            A = areas[0]
            pv = F / A.val
            res = f"P = {n(pv)} Pa" + (f" = {n(pv / 1000)} kPa" if pv >= 10000 else "")
            return c.sol(c.show(pv, "pressure"), _std("P = F / A", [fnote, A.known("A")], f"P = {n(F)} / {n(A.val)}", res),
                         f"P × A = {n(pv * A.val)} N ✓")
        if hydro and len(ls) == 1 and rho is not None:
            h = ls[0]
            pv = rho * c.g * h.val
            total = c.ask_has(r"\btotal\b|\babsolute\b|including (?:the )?atmospher|actual pressure")
            known = [rnote, c.gnote, h.known("h")]
            if total:
                patm = ps[0].val if ps else P_ATM
                tot = pv + patm
                known.append(ps[0].known("P₀") if ps else "P₀ = 101,325 Pa (1 atm)")
                return c.sol(c.show(tot, "pressure"), _std("P = P₀ + ρ·g·h", known, f"P = {n(patm)} + {n(rho)} × {n(c.g)} × {n(h.val)}",
                                                           f"P = {n(tot)} Pa"), f"ρ·g·h alone = {n(pv)} Pa ✓")
            res = f"P = {n(pv)} Pa" + (f" = {n(pv / 1000)} kPa" if pv >= 10000 else "")
            return c.sol(c.show(pv, "pressure"), _std("P = ρ·g·h  (pressure from the liquid above)", known,
                                                      f"P = {n(rho)} × {n(c.g)} × {n(h.val)}", res),
                         f"h = P / (ρ·g) = {n(pv / (rho * c.g))} m ✓")
        return None
    if want in ("h", "s") and hydro and rho is not None and ps and not fs:
        pq = ps[0]
        pv = pq.val
        if c.has(r"\btotal\b|\babsolute\b") and pv > P_ATM:
            pv = pv - P_ATM
        h = pv / (rho * c.g)
        return c.sol(c.show(h, "len"), _std("h = P / (ρ·g)  (from P = ρ·g·h)", [pq.known("P"), rnote, c.gnote],
                                            f"h = {n(pv)} / ({n(rho)} × {n(c.g)})", f"h = {n(h)} m"),
                     f"ρ·g·h = {n(rho * c.g * h)} Pa ✓")
    if want == "rho" and ps and len(ls) == 1:
        rv = ps[0].val / (c.g * ls[0].val)
        return c.sol(c.show(rv, "density"), _std("ρ = P / (g·h)", [ps[0].known("P"), c.gnote, ls[0].known("h")],
                                                 f"ρ = {n(ps[0].val)} / ({n(c.g)} × {n(ls[0].val)})", f"ρ = {n(rv)} kg/m³"))
    if want == "F" and ps and areas:
        fv = ps[0].val * areas[0].val
        return c.sol(c.show(fv, "force"), _std("F = P·A", [ps[0].known("P"), areas[0].known("A")],
                                               f"F = {n(ps[0].val)} × {n(areas[0].val)}", f"F = {n(fv)} N"),
                     f"F / A = {n(fv / areas[0].val)} Pa ✓")
    if want == "area" and ps and (fs or c.of("mass")):
        if fs:
            F, fnote = fs[0].val, fs[0].known("F")
        else:
            m = c.of("mass")[0]
            F, fnote = m.val * c.g, f"F = m·g = {n(m.val)} × {n(c.g)} = {n(m.val * c.g)} N"
        av = F / ps[0].val
        return c.sol(c.show(av, "area"), _std("A = F / P", [fnote, ps[0].known("P")], f"A = {n(F)} / {n(ps[0].val)}",
                                              f"A = {n(av)} m²"), f"F / A = {n(F / av)} Pa ✓")
    return None


def _box_volume(c: Ctx):
    m = re.search(rf"({NUM})\s*(cm|mm|m)?\s*(?:x|×|by|\*)\s*({NUM})\s*(cm|mm|m)?\s*(?:x|×|by|\*)\s*({NUM})\s*(cm|mm|m)\b", c.low)
    if m:
        unit = m.group(6)
        f = {"cm": R(1, 100), "mm": R(1, 1000), "m": R(1)}[unit]
        a, b, d = (_rat(m.group(i)) for i in (1, 3, 5))
        v = a * b * d
        return v * f ** 3, f"V = {m.group(1)} × {m.group(3)} × {m.group(5)} = {n(v)} {unit}³", unit
    m = re.search(rf"cube\b[^.?]*?(?:side|edge|sides|edges)(?: length)?(?: of| is| =)?\s*({NUM})\s*(cm|mm|m)\b|({NUM})\s*(cm|mm|m)\s+cube\b",
                  c.low)
    if m:
        s_, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        f = {"cm": R(1, 100), "mm": R(1, 1000), "m": R(1)}[unit]
        side = _rat(s_)
        return side ** 3 * f ** 3, f"V = {s_}³ = {n(side ** 3)} {unit}³", unit
    return None


def h_density(c: Ctx):
    want = next((w for w in c.targets if w in ("rho", "m", "V", "weight")), None)
    if want is None:
        return None
    ds, ms, vs = c.of("density"), c.of("mass"), c.of("vol")
    box = _box_volume(c)
    rho = rnote = None
    if ds:
        rho, rnote = ds[0].val, ds[0].known("ρ")
    else:
        for name in sorted(MATERIALS, key=len, reverse=True):
            if c.has(rf"\b{name}\b"):
                rho = MATERIALS[name]
                rnote = f"ρ({name}) = {n(rho)} kg/m³ = {n(rho / 1000)} g/cm³"
                break
    if not (ds or c.has(r"densit|dense")) and want == "rho":
        return None
    V = vnote = None
    gram_units = (ms and ms[0].unit in ("g", "mg")) or (vs and vs[0].unit in ("cm³", "mL", "mm³")) or \
                 (ds and ds[0].unit in ("g/cm³", "g/mL")) or (box and box[2] in ("cm", "mm"))
    if vs:
        V, vnote = vs[0].val, vs[0].known("V")
    elif box:
        V, vnote = box[0], box[1] + f" = {n(box[0])} m³"
    if want == "rho" and ms and V:
        rv = ms[0].val / V
        unit = "g/cm³" if gram_units else "kg/m³"
        other = f"{n(rv)} kg/m³" if gram_units else f"{n(rv / 1000)} g/cm³"
        return c.sol(c.show(rv, "density", unit), _std("ρ = m / V", [ms[0].known("m"), vnote], f"ρ = {n(ms[0].val)} / {n(V)}",
                                                       f"ρ = {n(rv / FACTOR[unit])} {unit} = {other}"),
                     f"ρ × V = {n(rv * V)} kg ✓")
    if want in ("m", "weight") and rho is not None and V and (ds or c.has(r"densit|dense") or not ms):
        mv = rho * V
        unit = "g" if gram_units and mv < 1 else "kg"
        ans = c.show(mv, "mass", unit)
        steps = _std("m = ρ·V", [rnote, vnote], f"m = {n(rho)} × {n(V)}", f"m = {n(mv)} kg" + (f" = {n(mv * 1000)} g" if unit == "g" else ""))
        if want == "weight":
            w = mv * c.g
            steps.append(f"weight W = m·g = {n(mv)} × {n(c.g)} = {n(w)} N")
            return c.sol(c.show(w, "force"), steps)
        return c.sol(ans, steps, f"m / V = {n(mv / V)} kg/m³ ✓")
    if want == "V" and rho is not None and ms:
        vv = ms[0].val / rho
        unit = "cm³" if gram_units or vv < R(1, 1000) else "m³"
        extra = f" = {n(vv * 1000)} L" if unit == "m³" else ""
        ans = c.show(vv, "vol", unit)
        if unit == "m³" and not c.out:
            ans += f" ({num(vv * 1000, c.sig, c.dp)} L)"
        return c.sol(ans, _std("V = m / ρ", [ms[0].known("m"), rnote], f"V = {n(ms[0].val)} / {n(rho)}",
                               f"V = {n(vv)} m³" + (f" = {n(vv * 10**6)} cm³" if unit == "cm³" else extra)),
                     f"ρ·V = {n(rho * vv)} kg ✓")
    return None


def _masses_vels(c: Ctx):
    ms, vs = c.of("mass"), c.of("vel")
    own: dict[int, list[Q]] = {i: [] for i in range(len(ms))}
    for v in vs:
        before = [i for i, m in enumerate(ms) if m.pos < v.pos]
        i = before[-1] if before else 0
        own[i].append(v)
    rest = {}
    for m in re.finditer(r"\bstationary\b|\bat rest\b|\bnot moving\b|\bmotionless\b|\bstill\b|\bparked\b", c.low):
        if not ms:
            break
        i = min(range(len(ms)), key=lambda j: min(abs(ms[j].pos - m.end()), abs(m.start() - ms[j].end)))
        rest[i] = True
    return ms, own, rest


def h_collision(c: Ctx):
    stick = c.has(r"stick|stuck|together|coupl|combine|join|embed|lodge|lock|entangle|as one|single (?:object|body|unit)|"
                  r"inelastic")
    recoil = c.has(r"recoil|\bfires?\b|\bfired\b|\bshoots?\b|explod|push(?:es)? (?:off|away|each other|apart)|pushes|jumps? "
                   r"(?:off|out|from)|throws?|kick back|spring apart|fly apart|separat")
    elastic = c.has(r"(?<!in)elastic collision|collide elastically|elastically") and not c.has(r"inelastic")
    if not (stick or recoil or elastic or c.has(r"collid|collision|crash|hits?\b|strikes?|bump|after the (?:collision|impact)")):
        return None
    if c.want not in ("v", "vf", "u", "p", "KE", "E", None):
        return None
    ms, own, rest = _masses_vels(c)
    if len(ms) != 2:
        return None
    m1, m2 = ms
    vel = []
    for i in (0, 1):
        if own[i]:
            q = own[i][0]
            val = q.val
            if i == 1 and re.search(r"opposite|towards? (?:it|each other|the first|them)|head[- ]on|other way|in reverse|"
                                    r"(?:the )?other direction", q.post + " " + q.pre[-25:]):
                val = -abs(val)
            vel.append(val)
        elif rest.get(i):
            vel.append(R(0))
        else:
            vel.append(None)
    if c.has(r"opposite directions|towards each other|head[- ]on") and vel[0] is not None and vel[1] is not None and vel[1] > 0 \
            and vel[0] > 0:
        vel[1] = -vel[1]
    if any(len(own[i]) > 1 for i in (0, 1)):
        return None
    if recoil and not stick:
        known = [i for i in (0, 1) if vel[i] not in (None,) and own[i]]
        if len(known) != 1:
            return None
        i = known[0]
        j = 1 - i
        mi, mj = ms[i], ms[j]
        vj = -mi.val * vel[i] / mj.val
        ans = c.show(abs(vj), "vel") + " in the opposite direction"
        steps = _std("total momentum before = 0 = m₁·v₁ + m₂·v₂  →  v₂ = −m₁·v₁ / m₂  (conservation of momentum)",
                     [mi.known("m₁"), own[i][0].known("v₁"), mj.known("m₂")],
                     f"v₂ = −{n(mi.val)} × {n(vel[i])} / {n(mj.val)}", f"v₂ = {n(vj)} m/s (minus: the opposite way)")
        return c.sol(ans, steps, f"{n(mi.val)} × {n(vel[i])} + {n(mj.val)} × ({n(vj)}) = 0 ✓")
    if vel[0] is None or vel[1] is None:
        return None
    u1, u2 = vel
    ptot = m1.val * u1 + m2.val * u2
    known = [m1.known("m₁"), f"u₁ = {n(u1)} m/s", m2.known("m₂"), f"u₂ = {n(u2)} m/s" + (" (at rest)" if u2 == 0 else "")]
    if elastic:
        v1 = ((m1.val - m2.val) * u1 + 2 * m2.val * u2) / (m1.val + m2.val)
        v2 = ((m2.val - m1.val) * u2 + 2 * m1.val * u1) / (m1.val + m2.val)
        ans = f"v₁ = {c.show(v1, 'vel')}, v₂ = {c.show(v2, 'vel')}"
        steps = ["formula: elastic collision (momentum and kinetic energy both conserved): "
                 "v₁ = ((m₁ − m₂)·u₁ + 2·m₂·u₂) / (m₁ + m₂), v₂ = ((m₂ − m₁)·u₂ + 2·m₁·u₁) / (m₁ + m₂)",
                 "known: " + ", ".join(known),
                 f"substitute: v₁ = (({n(m1.val)} − {n(m2.val)}) × {p(u1)} + 2 × {n(m2.val)} × {p(u2)}) / {n(m1.val + m2.val)}, "
                 f"v₂ = (({n(m2.val)} − {n(m1.val)}) × {p(u2)} + 2 × {n(m1.val)} × {p(u1)}) / {n(m1.val + m2.val)}",
                 f"result: v₁ = {n(v1)} m/s, v₂ = {n(v2)} m/s (minus means moving back)"]
        return c.sol(ans, steps, f"momentum {n(ptot)} = {n(m1.val * v1 + m2.val * v2)} kg·m/s ✓, kinetic energy "
                                 f"{n((m1.val * u1 ** 2 + m2.val * u2 ** 2) / 2)} J before and after ✓")
    after = re.search(rf"after(?: the (?:collision|impact|crash))?,? (?:the )?(?:{re.escape(m1.given)}|{re.escape(m2.given)})", c.low)
    if stick or not after:
        if not stick and not c.has(r"together|common velocity|combined"):
            return None
        v = ptot / (m1.val + m2.val)
        if c.want in ("KE", "E"):
            ke0 = (m1.val * u1 ** 2 + m2.val * u2 ** 2) / 2
            ke1 = (m1.val + m2.val) * v ** 2 / 2
            if c.ask_has(r"\blost|\bloss\b|\bconverted|\bwasted|\bchange"):
                return c.sol(c.show(ke0 - ke1, "energy"),
                             _std("KE lost = ½·m₁·u₁² + ½·m₂·u₂² − ½·(m₁ + m₂)·v², with v = (m₁·u₁ + m₂·u₂) / (m₁ + m₂)", known,
                                  f"v = {n(ptot)} / {n(m1.val + m2.val)} = {n(v)} m/s; KE before = {n(ke0)} J, after = {n(ke1)} J",
                                  f"KE lost = {n(ke0 - ke1)} J"))
            return None
        ans = c.show(abs(v), "vel") + (" in the direction the first object was moving" if v > 0 and u2 < 0 else
                                       " in the second object's direction" if v < 0 else "")
        steps = _std("m₁·u₁ + m₂·u₂ = (m₁ + m₂)·v  (momentum is conserved; they move together)", known,
                     f"v = ({n(m1.val)} × {p(u1)} + {n(m2.val)} × {p(u2)}) / ({n(m1.val)} + {n(m2.val)}) = {n(ptot)} / {n(m1.val + m2.val)}",
                     f"v = {n(v)} m/s")
        return c.sol(ans, steps, f"momentum before {n(ptot)} kg·m/s = after {n(m1.val + m2.val)} × {n(v)} = "
                                 f"{n((m1.val + m2.val) * v)} kg·m/s ✓")
    return None


def h_impulse(c: Ctx):
    if not (c.want in ("J", "F", "t", "v", "vf", "p") and ("J" in c.targets or c.has(r"impulse|rebound|bounces? (?:back|off)|"
                                                                                        r"contact|in contact|average force|stopped in|"
                                                                                        r"collision lasts|impact lasts|hit back|"
                                                                                        r"back at|returns? at|change in momentum"))):
        return None
    ms, vs, fs, ts, ps = c.of("mass"), c.of("vel"), c.of("force"), c.of("time"), c.of("momentum")
    want = c.want
    if want == "p":
        want = "J"
    if want == "J" and fs and ts and not vs:
        J = fs[0].val * ts[0].val
        return c.sol(c.show(J, "momentum", "N·s"), _std("J = F·Δt", [fs[0].known("F"), ts[0].known("Δt")],
                                                       f"J = {n(fs[0].val)} × {n(ts[0].val)}", f"J = {n(J)} N·s"),
                     f"= change in momentum {n(J)} kg·m/s")
    if len(ms) != 1 or len(vs) > 2:
        return None
    m = ms[0]
    rebound = c.has(r"rebound|bounces? (?:back|off)|back at|returns? at|reverses|opposite direction|hit back|struck back|"
                    r"comes? back|deflected back|batted back|kicked back")
    stop = c.has(r"\bstop(?:s|ped)?\b|brought to rest|comes? to rest|\bcatch(?:es)?\b|\bcaught\b|to a (?:stop|halt)")
    start = c.has(REST_START) or c.has(r"\bstationary\b|\bat rest\b")
    if len(vs) == 2:
        u, v = vs[0].val, vs[1].val
        if rebound:
            v = -v
        notes = [vs[0].known("u"), f"v = {n(v)} m/s" + (" (rebounds, so negative)" if rebound else "")]
    elif len(vs) == 1 and stop:
        u, v = vs[0].val, R(0)
        notes = [vs[0].known("u"), "v = 0 m/s (stopped)"]
    elif len(vs) == 1 and start:
        u, v = R(0), vs[0].val
        notes = ["u = 0 m/s (from rest)", vs[0].known("v")]
    elif ps and want in ("v", "vf"):
        J = ps[0].val
        if len(vs) == 1:
            u = vs[0].val
        else:
            u = R(0)
        v = u + J / m.val
        return c.sol(c.show(v, "vel"), _std("v = u + J / m  (impulse = change in momentum)", [m.known("m"), f"u = {n(u)} m/s",
                                                                                             ps[0].known("J")],
                                            f"v = {n(u)} + {n(J)} / {n(m.val)}", f"v = {n(v)} m/s"))
    else:
        return None
    dp = m.val * (v - u)
    known = [m.known("m")] + notes
    if want == "J":
        return c.sol(c.show(abs(dp), "momentum", "N·s"),
                     _std("J = Δp = m·(v − u)", known, f"J = {n(m.val)} × ({p(v)} − {p(u)})",
                          f"J = {n(dp)} N·s" + (" (minus: against the original motion)" if dp < 0 else "")),
                     f"momentum {n(m.val * u)} → {n(m.val * v)} kg·m/s ✓")
    if want == "F" and ts:
        F = dp / ts[0].val
        return c.sol(c.show(abs(F), "force"), _std("F = Δp / Δt = m·(v − u) / Δt", known + [ts[0].known("Δt")],
                                                   f"F = {n(m.val)} × ({p(v)} − {p(u)}) / {n(ts[0].val)}",
                                                   f"F = {n(F)} N" + (" (minus: against the original motion)" if F < 0 else "")),
                     f"F·Δt = {n(abs(F) * ts[0].val)} N·s = |Δp| ✓")
    if want == "t" and fs:
        tt = abs(dp) / fs[0].val
        return c.sol(c.show(tt, "time"), _std("Δt = Δp / F", known + [fs[0].known("F")], f"Δt = {n(abs(dp))} / {n(fs[0].val)}",
                                              f"Δt = {n(tt)} s"))
    return None


def h_momentum(c: Ctx):
    if c.want not in ("p", "m", "v", "vf"):
        return None
    ms, vs, ps = c.of("mass"), c.of("vel"), c.of("momentum")
    if c.want == "p" and len(ms) == 1 and len(vs) == 1:
        pv = ms[0].val * vs[0].val
        return c.sol(c.show(pv, "momentum"), _std("p = m·v", [ms[0].known("m"), vs[0].known("v")],
                                                  f"p = {n(ms[0].val)} × {n(vs[0].val)}", f"p = {n(pv)} kg·m/s"),
                     f"p / m = {n(pv / ms[0].val)} m/s ✓")
    if ps and len(ps) == 1:
        if c.want == "m" and len(vs) == 1:
            mv = ps[0].val / vs[0].val
            return c.sol(c.show(mv, "mass"), _std("m = p / v", [ps[0].known("p"), vs[0].known("v")],
                                                  f"m = {n(ps[0].val)} / {n(vs[0].val)}", f"m = {n(mv)} kg"),
                         f"m·v = {n(mv * vs[0].val)} kg·m/s ✓")
        if c.want in ("v", "vf") and len(ms) == 1 and not vs:
            vv = ps[0].val / ms[0].val
            return c.sol(c.show(vv, "vel"), _std("v = p / m", [ps[0].known("p"), ms[0].known("m")],
                                                 f"v = {n(ps[0].val)} / {n(ms[0].val)}", f"v = {n(vv)} m/s"),
                         f"m·v = {n(ms[0].val * vv)} kg·m/s ✓")
    return None


def _height_q(c: Ctx, ls: list[Q]):
    for q in ls:
        if re.search(r"high|tall|height|cliff|table|tower|building|roof|bridge|above|ledge|from a|from the top|off a|off the|"
                     r"window|balcony|wall|desk|bench|edge", q.pre[-30:] + " " + q.post[:25]):
            return q
    return ls[0] if len(ls) == 1 else None


def h_horizontal(c: Ctx):
    if not c.has(HORIZ) or c.has(UP):
        return None
    want = next((w for w in c.targets if w in ("range", "s", "t", "v", "vf", "vy", "vx", "u")), None)
    if want is None:
        return None
    vs, ls, ts = c.of("vel"), c.of("len"), c.of("time")
    if len(vs) > 1 or c.of("angle"):
        return None
    hq = _height_q(c, ls)
    if hq is None and not (ts and vs):
        return None
    g = c.g
    if hq is not None:
        t = _sqrt(2 * hq.val / g)
        tline = f"t = √(2·h / g) = √(2 × {n(hq.val)} / {n(g)}) = {n(t)} s"
        known = [hq.known("h"), c.gnote]
    else:
        t = ts[0].val
        tline = ts[0].known("t")
        known = [c.gnote]
    if vs:
        known.insert(0, vs[0].known("u"))
    if want == "t":
        return c.sol(c.show(t, "time"), _std("t = √(2·h / g)  (vertical fall from rest: horizontal speed doesn't matter)",
                                             known, f"t = √(2 × {n(hq.val)} / {n(g)})" if hq else tline, f"t = {n(t)} s"),
                     f"½·g·t² = {n(g * t ** 2 / 2)} m ✓")
    if not vs:
        rng = [q for q in ls if q is not hq]
        if want in ("u", "v", "vx") and rng and hq is not None:
            u = rng[0].val / t
            return c.sol(c.show(u, "vel"), _std("u = x / t, with t = √(2·h / g)", [rng[0].known("x")] + known, tline,
                                                f"u = {n(rng[0].val)} / {n(t)} = {n(u)} m/s"))
        return None
    u = vs[0].val
    if want in ("range", "s"):
        x = u * t
        return c.sol(c.show(x, "len"), _std("x = u·t, with t = √(2·h / g)", known, f"{tline}; x = {n(u)} × {n(t)}",
                                            f"x = {n(x)} m"), f"t = x / u = {n(x / u)} s ✓")
    if want == "vy":
        vy = g * t
        return c.sol(c.show(vy, "vel"), _std("v_y = g·t", known, f"{tline}; v_y = {n(g)} × {n(t)}", f"v_y = {n(vy)} m/s"))
    if want == "vx":
        return c.sol(c.show(u, "vel"), ["rule: with no air resistance nothing pushes sideways, so the horizontal speed stays "
                                        f"{n(u)} m/s", f"result: v_x = {n(u)} m/s"])
    if want in ("v", "vf"):
        vy = g * t
        vv = _sqrt(u ** 2 + vy ** 2)
        ang = sp.atan(vy / u) * 180 / sp.pi
        return c.sol(c.show(vv, "vel"), _std("v = √(u² + v_y²), with v_y = g·t", known,
                                             f"{tline}; v_y = {n(g)} × {n(t)} = {n(vy)} m/s; v = √({n(u)}² + {n(vy)}²)",
                                             f"v = {n(vv)} m/s at {n(sp.N(ang, 20))}° below the horizontal"),
                     f"energy: √(u² + 2·g·h) = {n(_sqrt(u ** 2 + 2 * g * hq.val)) if hq else n(vv)} m/s ✓")
    return None


def h_angled(c: Ctx):
    angs = c.of("angle")
    if not angs or c.has(HORIZ + r"|\bslope\b|\bincline|\bramp\b|\bhill\b") or c.of("force"):
        return None
    if not c.has(r"launch|kick|throw|thrown|fire|fired|shot|shoot|project|hit|hits|struck|served|lobbed|cannon|ball|arrow|"
                 r"javelin|golf"):
        return None
    want = next((w for w in c.targets if w in ("range", "s", "h", "t", "vx", "vy")), None)
    vs = c.of("vel")
    if want is None or len(vs) != 1 or len(angs) != 1:
        return None
    u, th = vs[0].val, angs[0].val
    if re.search(r"vertical", angs[0].post[:25]):
        th = 90 - th
    g = c.g
    s_, c_ = _sin(th), _cos(th)
    known = [vs[0].known("u"), f"θ = {n(th)}°", c.gnote]
    if want in ("range", "s"):
        rv = u ** 2 * _sin(2 * th) / g
        return c.sol(c.show(rv, "len"), _std("R = u²·sin(2θ) / g  (level ground, no air resistance)", known,
                                             f"R = {n(u)}² × sin({n(2 * th)}°) / {n(g)}", f"R = {n(rv)} m"),
                     f"time of flight {n(2 * u * s_ / g)} s × horizontal speed {n(u * c_)} m/s = {n(2 * u * s_ / g * u * c_)} m ✓")
    if want == "h":
        hv = (u * s_) ** 2 / (2 * g)
        return c.sol(c.show(hv, "len"), _std("H = (u·sin θ)² / (2g)", known, f"H = ({n(u)} × sin {n(th)}°)² / (2 × {n(g)})",
                                             f"H = {n(hv)} m"))
    if want == "t":
        tv = 2 * u * s_ / g
        return c.sol(c.show(tv, "time"), _std("T = 2·u·sin θ / g  (time of flight on level ground)", known,
                                              f"T = 2 × {n(u)} × sin {n(th)}° / {n(g)}", f"T = {n(tv)} s"))
    if want == "vx":
        return c.sol(c.show(u * c_, "vel"), _std("u_x = u·cos θ", known[:2], f"u_x = {n(u)} × cos {n(th)}°", f"u_x = {n(u * c_)} m/s"))
    if want == "vy":
        return c.sol(c.show(u * s_, "vel"), _std("u_y = u·sin θ", known[:2], f"u_y = {n(u)} × sin {n(th)}°", f"u_y = {n(u * s_)} m/s"))
    return None


def h_thrown_up(c: Ctx):
    if not c.has(UP):
        return None
    wants = [w for w in c.targets if w in ("h", "s", "t", "v", "vf", "u")]
    if not wants:
        return None
    g = c.g
    vs, ls, ts = c.of("vel"), c.of("len"), c.of("time")
    if len(vs) > 1 or len(ts) > 1 or len(ls) > 1:
        return None
    k, notes = {"a": -g}, {"a": f"{c.gnote}, taking up as positive"}
    cliff = None
    for q in ls:
        if re.search(r"cliff|building|tower|roof|bridge|ledge|above the (?:ground|sea|water)|from a|from the top|platform|"
                     r"balcony|window|off a|edge", q.pre[-30:] + " " + q.post[:30]):
            cliff = q
    ask = " ".join(c.targets)
    top = c.ask_has(r"\btop\b|highest|max|peak|apex|stops? (?:rising|going up|moving up)|stop\b|greatest height")
    back = c.ask_has(r"return|land|back|hits? the ground|hit the ground|reach the ground|in the air|flight|total time|caught|"
                     r"comes? down|fall back|hits the (?:floor|water|sea)")
    intro = []
    if vs:
        k["u"] = vs[0].val
        notes["u"] = "thrown up"
    elif not ls and not ts:
        return None
    want = wants[0]
    if want == "vf":
        want = "v"
    if vs and not ls and not ts and cliff is None:
        u = vs[0].val
        items = []
        for w in wants:
            if w in ("h", "s") and "h" not in items:
                items.append("h")
            elif w == "t":
                if top and "top" not in items:
                    items.append("top")
                if (back or not top) and "flight" not in items:
                    items.append("flight")
        if len(items) > 1 and u > 0:
            known = [vs[0].known("u"), c.gnote]
            res, steps = [], ["known: " + ", ".join(known)]
            for it in items:
                if it == "h":
                    hv = u ** 2 / (2 * g)
                    res.append(f"max height = {c.show(hv, 'len')}")
                    steps.append(f"max height: H = u² / (2·g) = {n(u)}² / (2 × {n(g)}) = {n(hv)} m")
                elif it == "top":
                    tv = u / g
                    res.append(f"time to top = {c.show(tv, 'time')}")
                    steps.append(f"time to the top (v = 0): t = u / g = {n(u)} / {n(g)} = {n(tv)} s")
                else:
                    tv = 2 * u / g
                    res.append(f"total flight time = {c.show(tv, 'time')}")
                    steps.append(f"total time in the air (back to launch height): T = 2·u / g = 2 × {n(u)} / {n(g)} = {n(tv)} s")
            return c.sol(", ".join(res), steps, f"up and down take equal times: 2 × {n(u / g)} = {n(2 * u / g)} s ✓")
    if not vs:  # find the launch speed from what it did
        if ls and (c.has(r"max(?:imum)? height|reaches|rises|goes up|highest|height of|gets to|climbs") or not ts):
            hv = ls[0].val
            u = _sqrt(2 * g * hv)
            return c.sol(c.show(u, "vel"), _std("u = √(2·g·h)  (at the top v = 0, from v² = u² − 2·g·h)",
                                                [ls[0].known("h"), c.gnote], f"u = √(2 × {n(g)} × {n(hv)})", f"u = {n(u)} m/s"),
                         f"u² / (2g) = {n(u ** 2 / (2 * g))} m ✓")
        if ts:
            tt = ts[0].val
            if c.has(r"return|land|back|in the air|caught|total|flight|comes? down|hits? the ground"):
                u = g * tt / 2
                return c.sol(c.show(u, "vel"), _std("u = g·T / 2  (it takes T/2 to rise and T/2 to fall back)",
                                                    [ts[0].known("T"), c.gnote], f"u = {n(g)} × {n(tt)} / 2", f"u = {n(u)} m/s"),
                             f"2u / g = {n(2 * u / g)} s ✓")
            u = g * tt
            return c.sol(c.show(u, "vel"), _std("u = g·t  (v = 0 at the top)", [ts[0].known("t"), c.gnote],
                                                f"u = {n(g)} × {n(tt)}", f"u = {n(u)} m/s"))
        return None
    if want == "u":
        return None
    if want in ("h", "s"):
        if ts:
            k["t"] = ts[0].val
        else:
            k["v"] = R(0)
            notes["v"] = "at the top"
        want = "s"
    elif want == "t":
        if ts and not ls:
            return None
        if top:
            k["v"] = R(0)
            notes["v"] = "at the top"
        elif cliff is not None and back:
            k["s"] = -cliff.val
            notes["s"] = "the ground is below the start"
        elif ls and not back:
            k["s"] = ls[0].val
            notes["s"] = "the height asked about"
        else:
            k["s"] = R(0)
            notes["s"] = "back at the launch height"
    elif want == "v":
        if ts:
            k["t"] = ts[0].val
        elif cliff is not None:
            k["s"] = -cliff.val
            notes["s"] = "the ground is below the start"
        elif ls:
            k["s"] = ls[0].val
        elif back:
            k["s"] = R(0)
            notes["s"] = "back at the launch height"
        else:
            return None
    res = suvat(c, k, [want], notes, intro, vertical=True)
    if not res:
        return None
    answers, steps, check = res
    if "max" in ask or top:
        pass
    return c.sol(_join(answers), steps, check)


def h_average(c: Ctx):
    if "avg" not in c.targets and not (c.want in ("v",) and c.has(r"whole (?:journey|trip|way|run|race)|entire (?:journey|trip)|"
                                                                   r"overall|round trip|total journey")):
        return None
    items = [q for q in c.qs if q.dim in ("len", "vel", "time")]
    legs, cur = [], {}
    for q in items:
        key = {"len": "d", "vel": "v", "time": "t"}[q.dim]
        if q.dim == "time" and re.search(r"\b(?:stop|stops|stopped|rest|rests|break|pause|pauses|wait|waits|parked|halt)\w*\b",
                                         q.pre[-25:] + " " + q.post[:12]):
            if cur:
                legs.append(cur)
                cur = {}
            legs.append({"d": None, "t": q, "stop": True})
            continue
        if key in cur:
            legs.append(cur)
            cur = {}
        cur[key] = q
        if len(cur) == 2:
            legs.append(cur)
            cur = {}
    if cur:
        legs.append(cur)
    speeds = [q for q in items if q.dim == "vel"]
    unit = speeds[0].unit if speeds else None
    if unit is None:
        lu = next((q.unit for q in items if q.dim == "len"), "m")
        tu = next((q.unit for q in items if q.dim == "time"), "s")
        unit = "km/h" if lu == "km" and tu in ("h", "min") else "mph" if lu == "miles" and tu in ("h", "min") else "m/s"
    du, tu = {"km/h": ("km", "h"), "mph": ("miles", "h"), "m/s": ("m", "s")}.get(unit, ("m", "s"))
    fd, ft = FACTOR[du], FACTOR[tu]
    equal_d = c.has(r"\bback\b|\breturn|\bhalf the (?:distance|way)|\bsame (?:distance|road|route|way)|round trip|"
                    r"there and back|each way|\bup\b.*\bdown\b|\bhome\b")
    equal_t = c.has(r"half the time|half (?:of )?the (?:journey )?time|equal times|same (?:time|amount of time)")
    if all(set(leg) == {"v"} for leg in legs) and len(legs) >= 2 and (equal_d or equal_t):
        vals = [leg["v"].val for leg in legs]
        if equal_t:
            avg = sum(vals) / len(vals)
            steps = ["rule: equal times at each speed, so the average speed is the plain mean of the speeds",
                     f"substitute: ({' + '.join(n(v / FACTOR[unit]) for v in vals)}) / {len(vals)}",
                     f"result: {n(avg / FACTOR[unit])} {unit}"]
            return c.sol(c.show(avg, "vel", unit), steps)
        avg = len(vals) / sum(1 / v for v in vals)
        mean = sum(vals) / len(vals)
        steps = ["rule: average speed = total distance / total time (not the mean of the speeds)",
                 f"each leg is the same distance d, so total time = {' + '.join(f'd / {n(v / FACTOR[unit])}' for v in vals)}",
                 f"formula: average = {len(vals)}·d / ({' + '.join(f'd / v{i + 1}' for i in range(len(vals)))}) "
                 f"= {len(vals)} / ({' + '.join(f'1/v{i + 1}' for i in range(len(vals)))})",
                 f"substitute: {len(vals)} / ({' + '.join(f'1/{n(v / FACTOR[unit])}' for v in vals)})",
                 f"result: {n(avg / FACTOR[unit])} {unit} (the plain mean, {n(mean / FACTOR[unit])} {unit}, is wrong: "
                 f"more time is spent at the slower speed)"]
        d = 120 * fd
        return c.sol(c.show(avg, "vel", unit), steps,
                     f"say each leg is 120 {du}: time = {' + '.join(n(d / v / ft) for v in vals)} = "
                     f"{n(sum(d / v for v in vals) / ft)} {tu}, and {n(len(vals) * 120)} {du} / {n(sum(d / v for v in vals) / ft)} {tu} = "
                     f"{n(len(vals) * d / sum(d / v for v in vals) / FACTOR[unit])} {unit} ✓")
    if len(legs) < 2 and "avg" not in c.targets:
        return None
    total_d, total_t = R(0), R(0)
    steps = ["rule: average speed = total distance / total time (not the mean of the speeds)"]
    for i, leg in enumerate(legs, 1):
        d, v, t = leg.get("d"), leg.get("v"), leg.get("t")
        if leg.get("stop"):
            total_t += t.val
            steps.append(f"stop {i}: {t.shown()} = {n(t.val / ft)} {tu}, no distance")
            continue
        if d and t:
            dd, tt = d.val, t.val
            line = f"{d.shown()} in {t.shown()}"
        elif d and v:
            dd, tt = d.val, d.val / v.val
            line = f"{d.shown()} at {v.shown()} → time = {n(dd / fd)} / {n(v.val / FACTOR[unit])} = {n(tt / ft)} {tu}"
        elif v and t:
            dd, tt = v.val * t.val, t.val
            line = f"{v.shown()} for {t.shown()} → distance = {n(v.val / FACTOR[unit])} × {n(tt / ft)} = {n(dd / fd)} {du}"
        else:
            return None
        total_d += dd
        total_t += tt
        steps.append(f"leg {i}: {line}")
    if total_t == 0 or len(legs) < 1:
        return None
    avg = total_d / total_t
    steps.append(f"total distance = {n(total_d / fd)} {du}, total time = {n(total_t / ft)} {tu}")
    steps.append(f"substitute: average = {n(total_d / fd)} / {n(total_t / ft)}")
    vals = [leg["v"].val for leg in legs if leg.get("v")]
    tail = ""
    if len(vals) >= 2 and sum(vals) / len(vals) != avg:
        tail = f" (the plain mean of the speeds, {n(sum(vals) / len(vals) / FACTOR[unit])} {unit}, would be wrong)"
    steps.append(f"result: {n(avg / FACTOR[unit])} {unit}{tail}")
    return c.sol(c.show(avg, "vel", unit), steps,
                 f"{n(avg / FACTOR[unit])} {unit} × {n(total_t / ft)} {tu} = {n(avg * total_t / fd)} {du} ✓")


def h_braking(c: Ctx):
    if not c.has(BRAKE) or c.has(UP):
        return None
    want = next((w for w in c.targets if w in ("s", "t", "a", "F", "u", "v", "W", "E")), None)
    if want is None:
        return None
    vs, ms, fs, accs, ls, ts = c.of("vel"), c.of("mass"), c.of("force"), c.of("acc"), c.of("len"), c.of("time")
    if len(vs) > 1 or len(ls) > 1 or len(fs) > 1 or len(accs) > 1:
        return None
    react = [q for q in ts if re.search(r"react|thinking|before (?:braking|the brakes|applying)|to respond|delay", q.pre + " " + q.post)]
    brake_t = [q for q in ts if q not in react]
    if len(brake_t) > 1:
        return None
    if want == "v" and not vs:
        want = "u"
    if want == "v" and vs:
        if c.ask_has(r"how fast (?:was|were)|initial|before|going|travell?ing"):
            want = "u"
        else:
            return None
    u = vs[0].val if vs else None
    known = [vs[0].known("u")] if vs else []
    dec = None
    if accs:
        dec = abs(accs[0].val)
        known.append(accs[0].known("deceleration a"))
    elif fs and ms:
        dec = fs[0].val / ms[0].val
        known += [ms[0].known("m"), fs[0].known("F"), f"a = F / m = {n(fs[0].val)} / {n(ms[0].val)} = {n(dec)} m/s²"]
    elif c.mu is not None:
        dec = c.mu * c.g
        known += [f"μ = {n(c.mu)}", c.gnote, f"a = μ·g = {n(c.mu)} × {n(c.g)} = {n(dec)} m/s²"]
    elif ms and not fs and want == "F" and u is not None and (ls or brake_t):
        pass
    if want == "u":
        if dec is not None and ls:
            uu = _sqrt(2 * dec * ls[0].val)
            return c.sol(c.show(uu, "vel"), _std("u = √(2·a·s)  (from 0 = u² − 2·a·s)", known + [ls[0].known("s")],
                                                 f"u = √(2 × {n(dec)} × {n(ls[0].val)})", f"u = {n(uu)} m/s"),
                         f"u² / (2a) = {n(uu ** 2 / (2 * dec))} m ✓")
        if dec is not None and brake_t:
            uu = dec * brake_t[0].val
            return c.sol(c.show(uu, "vel"), _std("u = a·t  (from 0 = u − a·t)", known + [brake_t[0].known("t")],
                                                 f"u = {n(dec)} × {n(brake_t[0].val)}", f"u = {n(uu)} m/s"))
        return None
    if u is None:
        return None
    if dec is None:
        if ls:
            dec = u ** 2 / (2 * ls[0].val)
            dline = f"a = u² / (2·s) = {n(u)}² / (2 × {n(ls[0].val)}) = {n(dec)} m/s²"
            known.append(ls[0].known("s"))
        elif brake_t:
            dec = u / brake_t[0].val
            dline = f"a = u / t = {n(u)} / {n(brake_t[0].val)} = {n(dec)} m/s²"
            known.append(brake_t[0].known("t"))
        else:
            return None
        if want == "a":
            return c.sol(c.show(dec, "acc"), ["formula: v² = u² − 2·a·s with v = 0" if ls else "formula: v = u − a·t with v = 0",
                                              "known: " + ", ".join(known), f"substitute: {dline}",
                                              f"result: deceleration = {n(dec)} m/s²"],
                         f"stopping time u / a = {n(u / dec)} s, distance ½·u·t = {n(u * (u / dec) / 2)} m ✓")
        if want == "F" and ms:
            F = ms[0].val * dec
            return c.sol(c.show(F, "force"), ["formula: a from the stop, then F = m·a", "known: " + ", ".join(known + [ms[0].known("m")]),
                                              f"substitute: {dline}; F = {n(ms[0].val)} × {n(dec)}", f"result: F = {n(F)} N"],
                         f"work done by the brakes F·s = {n(F * u ** 2 / (2 * dec))} J = KE ½·m·u² = "
                         f"{n(ms[0].val * u ** 2 / 2)} J ✓")
        if want == "t" and ls:
            tt = 2 * ls[0].val / u
            return c.sol(c.show(tt, "time"), _std("t = 2·s / u  (average speed u/2 while stopping)", known,
                                                  f"t = 2 × {n(ls[0].val)} / {n(u)}", f"t = {n(tt)} s"))
        if want == "s" and brake_t:
            sv = u * brake_t[0].val / 2
            return c.sol(c.show(sv, "len"), _std("s = ½·(u + v)·t with v = 0", known, f"s = ½ × {n(u)} × {n(brake_t[0].val)}",
                                                 f"s = {n(sv)} m"))
        return None
    if dec <= 0:
        return None
    if want == "a":
        return c.sol(c.show(dec, "acc"), ["formula: a = F / m" if fs else "formula: a = μ·g", "known: " + ", ".join(known),
                                          f"result: deceleration = {n(dec)} m/s²"])
    if want == "s":
        sb = u ** 2 / (2 * dec)
        if react:
            tr = react[0].val
            think = u * tr
            tot = think + sb
            steps = ["formula: stopping distance = thinking distance + braking distance = u·t_r + u² / (2·a)",
                     "known: " + ", ".join(known + [react[0].known("t_r")]),
                     f"substitute: {n(u)} × {n(tr)} + {n(u)}² / (2 × {n(dec)}) = {n(think)} + {n(sb)}", f"result: {n(tot)} m"]
            if c.ask_has(r"thinking"):
                return c.sol(c.show(think, "len"), _std("thinking distance = u·t_r", known + [react[0].known("t_r")],
                                                        f"{n(u)} × {n(tr)}", f"{n(think)} m"))
            if c.ask_has(r"braking distance"):
                return c.sol(c.show(sb, "len"), steps[:2] + [f"substitute: {n(u)}² / (2 × {n(dec)})", f"result: {n(sb)} m"])
            return c.sol(c.show(tot, "len"), steps, f"braking takes {n(u / dec)} s at an average {n(u / 2)} m/s = {n(u / dec * u / 2)} m ✓")
        steps = _std("s = u² / (2·a)  (from v² = u² − 2·a·s with v = 0)", known, f"s = {n(u)}² / (2 × {n(dec)})", f"s = {n(sb)} m")
        check = f"t = u / a = {n(u / dec)} s, and ½·u·t = {n(u * (u / dec) / 2)} m ✓"
        if fs and ms:
            check = f"work done by the brakes F·s = {n(fs[0].val)} × {n(sb)} = {n(fs[0].val * sb)} J = KE ½·m·u² = " \
                    f"{n(ms[0].val * u ** 2 / 2)} J ✓"
        return c.sol(c.show(sb, "len"), steps, check)
    if want == "t":
        tt = u / dec
        tr = react[0].val if react else 0
        steps = _std("t = u / a  (from 0 = u − a·t)", known, f"t = {n(u)} / {n(dec)}", f"t = {n(tt)} s")
        if react and not c.ask_has(r"braking time|brakes? for"):
            steps.append(f"plus the reaction time {n(tr)} s: {n(tt + tr)} s")
            return c.sol(c.show(tt + tr, "time"), steps)
        return c.sol(c.show(tt, "time"), steps, f"u − a·t = {n(u)} − {n(dec)} × {n(tt)} = 0 ✓")
    if want == "F" and ms:
        F = ms[0].val * dec
        return c.sol(c.show(F, "force"), _std("F = m·a", known + [ms[0].known("m")], f"F = {n(ms[0].val)} × {n(dec)}", f"F = {n(F)} N"))
    if want in ("W", "E") and ms:
        w = ms[0].val * u ** 2 / 2
        return c.sol(c.show(w, "energy"), _std("work done by the brakes = KE lost = ½·m·u²", [ms[0].known("m"), vs[0].known("u")],
                                               f"½ × {n(ms[0].val)} × {n(u)}²", f"W = {n(w)} J"))
    return None


def h_fall(c: Ctx):
    if not c.has(FALL) or c.has(UP) or c.has(HORIZ):
        return None
    wants = [w for w in c.targets if w in ("t", "v", "vf", "s", "h")]
    if not wants or c.want not in ("t", "v", "vf", "s", "h"):
        return None
    if c.of("force") or c.of("energy") or c.has(r"parachut|terminal|(?<!no )(?<!neglect )(?<!ignore )(?<!ignoring )"
                                                 r"(?<!neglecting )(?<!without )air resistance|(?<!no )drag"):
        return None

    def uniq(qs):  # "falls for 2.5 s ... at the end of the 2.5 s" is one quantity said twice
        out = []
        for q in qs:
            if not any(o.val == q.val for o in out):
                out.append(q)
        return out
    vs, ls, ts, accs = uniq(c.of("vel")), uniq(c.of("len")), uniq(c.of("time")), uniq(c.of("acc"))
    if len(ls) > 1 or len(ts) > 1 or len(vs) > 1 or len(accs) > 1:
        return None
    g = accs[0].val if accs else c.g
    k = {"a": g}
    notes = {"a": (accs[0].shown() if accs else c.gnote) + ", taking down as positive"}
    if c.has(DOWN) and vs and _vel_role(vs[0]) != "v":
        k["u"] = vs[0].val
        notes["u"] = "thrown down"
    else:
        k["u"] = R(0)
        notes["u"] = "dropped from rest"
        if vs:
            k["v"] = vs[0].val
    if ls:
        k["s"] = ls[0].val
    if ts:
        k["t"] = ts[0].val
    order = []
    for w in wants:
        w = {"vf": "v", "h": "s"}.get(w, w)
        if w not in k and w not in order:
            order.append(w)
    if not order:
        return None
    res = suvat(c, k, order, notes)
    if not res:
        return None
    answers, steps, check = res
    return c.sol(_join(answers), steps, check)


def h_kinematics(c: Ctx):
    wants = []
    for w in c.targets:
        w = {"vf": "v", "h": "s", "range": "s"}.get(w, w)
        if w in ("u", "v", "a", "s", "t") and w not in wants:
            wants.append(w)
    if not wants or c.want not in ("u", "v", "vf", "a", "s", "h", "t", "range"):
        return None
    vs, accs, ls, ts = c.of("vel"), c.of("acc"), c.of("len"), c.of("time")
    if len(accs) > 1 or len(ls) > 1 or len(ts) > 1 or len(vs) > 2:
        return None
    k, notes = {}, {}
    if c.has(REST_START):
        k["u"], notes["u"] = R(0), "from rest"
    if c.has(REST_END) and "u" not in k:
        k["v"], notes["v"] = R(0), "stops"
    free = []
    for q in vs:
        r = _vel_role(q)
        if r and r not in k:
            k[r] = q.val
        else:
            free.append(q)
    for q in free:
        slot = "u" if "u" not in k else "v" if "v" not in k else None
        if slot is None:
            return None
        if slot == "u" and "u" in wants and "v" not in k:
            slot = "v"
        k[slot] = q.val
    if accs:
        a = accs[0].val
        if a > 0 and c.has(r"decelerat|retard|slows?|slowing|brak|negative acceleration"):
            a = -a
            notes["a"] = "slowing, so negative"
        k["a"] = a
    elif c.has(r"constant (?:speed|velocity)|steady speed|uniform (?:speed|velocity)"):
        return None
    if ls:
        k["s"] = ls[0].val
    if ts:
        k["t"] = ts[0].val
    if "v" in wants and "v" in k and "u" not in k:
        wants = ["u" if w == "v" else w for w in wants]
    wants = [w for w in wants if w not in k]
    if not wants or len([x for x in "uvast" if x in k]) < 3:
        return None
    res = suvat(c, k, wants, notes)
    if not res:
        return None
    answers, steps, check = res
    return c.sol(_join(answers), steps, check)


def _force_info(c: Ctx, forces: list[Q]):
    info = {id(q): {"opp": False, "axis": None, "sign": 1} for q in forces}

    def nearest(m, prefer_next=False):
        prev = [q for q in forces if q.end <= m.start()]
        nxt = [q for q in forces if q.pos >= m.end()]
        cands = []
        if prev:
            q = prev[-1]
            gap = c.low[q.end:m.start()]
            cands.append((len(gap.strip()), 0, q))
        if nxt:
            q = nxt[0]
            gap = c.low[m.end():q.pos]
            if re.fullmatch(r"\s*(?:force\s*)?(?:of|is|=|:|equal to|equals|was|being|about|measuring)?\s*(?:an? )?(?:about )?", gap):
                return q
            cands.append((len(gap.strip()), 1 if not prefer_next else -1, q))
        if not cands:
            return None
        best = min(cands, key=lambda x: (x[0], x[1]))
        return best[2] if best[0] <= 40 else None

    for m in re.finditer(r"friction(?:al)?|drag|air resistance|resistance|resistive|resisting|retarding|braking|opposing force", c.low):
        if re.search(r"coeff\w*\.? of (?:\w+ )?$", c.low[:m.start()]) or re.match(r"(?:al)? coeff", c.low[m.end():]):
            continue
        q = nearest(m)
        if q is not None:
            info[id(q)]["opp"] = True
    for m in re.finditer(r"\b(?:against|opposed by|resisted by|opposing)\b", c.low):
        nxt = [q for q in forces if q.pos >= m.end() and q.pos - m.end() < 30]
        if nxt:
            info[id(nxt[0])]["opp"] = True
    for pat, axis, sign in ((r"\b(?:east(?:wards?)?|to the right|rightwards?|forwards?|ahead)\b", "x", 1),
                            (r"\b(?:west(?:wards?)?|to the left|leftwards?|backwards?)\b", "x", -1),
                            (r"\b(?:north(?:wards?)?|upwards?|up)\b", "y", 1),
                            (r"\b(?:south(?:wards?)?|downwards?|down)\b", "y", -1),
                            (r"\bright\b", "x", 1), (r"\bleft\b", "x", -1)):
        for m in re.finditer(pat, c.low):
            q = nearest(m)
            if q is not None and info[id(q)]["axis"] is None:
                info[id(q)]["axis"], info[id(q)]["sign"] = axis, sign
    return info


def h_forces(c: Ctx):
    want = c.want
    if want not in ("F", "a", "m"):
        return None
    if c.has(r"\bspring|\bpressure\b|\bimpulse|\bmomentum\b"):
        return None
    forces = [q for q in c.of("force") if not re.search(r"weigh", q.wpre[-12:])]
    ms, accs = c.of("mass"), c.of("acc")
    m = ms[0] if len(ms) == 1 else None
    g = c.g
    perp = c.has(r"right angles?|perpendicular|\b90 ?(?:°|degrees?)")
    info = _force_info(c, forces)
    fric = c.ask_has(r"friction|resistive|resistance|drag")
    net_asked = c.ask_has(r"\bnet\b|resultant|unbalanced|overall|total force|combined")
    friction_mu = None
    if c.mu is not None and m is not None:
        friction_mu = c.mu * m.val * g
    if want == "F" and fric and not forces and friction_mu is not None:
        return c.sol(c.show(friction_mu, "force"), _std("F = μ·m·g  (friction on a level surface: normal force = m·g)",
                                                        [f"μ = {n(c.mu)}", m.known("m"), c.gnote],
                                                        f"F = {n(c.mu)} × {n(m.val)} × {n(g)}", f"F = {n(friction_mu)} N"))
    if len(forces) >= 2 or (forces and (friction_mu is not None)):
        axes = {info[id(q)]["axis"] for q in forces if info[id(q)]["axis"]}
        if perp and len(forces) == 2 and not friction_mu:
            f1, f2 = forces
            Fr = _sqrt(f1.val ** 2 + f2.val ** 2)
            ang = sp.atan(f2.val / f1.val) * 180 / sp.pi
            steps = _std("F = √(F₁² + F₂²)  (forces at right angles)", [f1.known("F₁"), f2.known("F₂")],
                         f"F = √({n(f1.val)}² + {n(f2.val)}²)", f"F = {n(Fr)} N at {n(sp.N(ang, 20))}° to the {n(f1.val)} N force")
            if want == "a" and m:
                return c.sol(c.show(Fr / m.val, "acc"), steps + [f"a = F / m = {n(Fr)} / {n(m.val)} = {n(Fr / m.val)} m/s²"])
            if want == "F":
                return c.sol(c.show(Fr, "force"), steps, f"{n(Fr)}² = {n(Fr ** 2)} = {n(f1.val ** 2)} + {n(f2.val ** 2)} ✓")
            return None
        if axes == {"x", "y"}:
            fx = sum(info[id(q)]["sign"] * q.val for q in forces if info[id(q)]["axis"] == "x")
            fy = sum(info[id(q)]["sign"] * q.val for q in forces if info[id(q)]["axis"] == "y")
            Fr = _sqrt(fx ** 2 + fy ** 2)
            steps = _std("F = √(Fx² + Fy²)", [q.known("F") for q in forces], f"Fx = {n(fx)} N, Fy = {n(fy)} N; F = √({p(fx)}² + {p(fy)}²)",
                         f"F = {n(Fr)} N")
            if want == "a" and m:
                return c.sol(c.show(Fr / m.val, "acc"), steps + [f"a = F / m = {n(Fr / m.val)} m/s²"])
            return c.sol(c.show(Fr, "force"), steps) if want == "F" else None
        total, parts, known = R(0), [], []
        opposite = c.has(r"opposite directions?|in opposite|opposing each other")
        same = c.has(r"same direction")
        first_sign = None
        for i, q in enumerate(forces):
            inf = info[id(q)]
            s = inf["sign"] if inf["axis"] else 1
            if inf["opp"]:
                s = -1
            elif opposite and not same and i == len(forces) - 1 and not inf["axis"] and len(forces) == 2:
                s = -1
            if first_sign is None:
                first_sign = s
            total += s * q.val
            parts.append(("+ " if s > 0 else "− ") + n(q.val))
            known.append(q.known("F") + (" (opposing)" if s < 0 and inf["opp"] else ""))
        if friction_mu is not None:
            total -= friction_mu
            parts.append(f"− {n(friction_mu)}")
            known.append(f"friction = μ·m·g = {n(c.mu)} × {n(m.val)} × {n(g)} = {n(friction_mu)} N")
        expr = " ".join(parts).lstrip("+ ").replace("− ", "−", 1) if parts[0].startswith("−") else " ".join(parts)[2:]
        net_line = f"F_net = {expr} = {n(total)} N"
        if want == "a" and m:
            a = total / m.val
            steps = ["formula: a = F_net / m, with F_net = sum of the forces (opposing ones negative)",
                     "known: " + ", ".join(known + [m.known("m")]), f"substitute: {net_line}; a = {n(total)} / {n(m.val)}",
                     f"result: a = {n(a)} m/s²"]
            return c.sol(c.show(a, "acc"), steps, f"m·a = {n(m.val * a)} N = F_net ✓")
        if want == "F" and (net_asked or not fric):
            direction = ""
            dirs = [info[id(q)] for q in forces if info[id(q)]["axis"]]
            if dirs and total != 0:
                ax = dirs[0]["axis"]
                direction = {("x", 1): " east" if c.has(r"\beast") else " to the right" if c.has(r"\bright\b") else " forwards",
                             ("x", -1): " west" if c.has(r"\bwest") else " to the left" if c.has(r"\bleft\b") else " backwards",
                             ("y", 1): " north" if c.has(r"\bnorth") else " upwards",
                             ("y", -1): " south" if c.has(r"\bsouth") else " downwards"}[(ax, 1 if total > 0 else -1)]
            steps = ["formula: F_net = sum of the forces along the line (opposing ones negative)", "known: " + ", ".join(known),
                     f"substitute: {net_line}", f"result: F_net = {n(total)} N{direction}"]
            return c.sol(c.show(abs(total), "force") + direction, steps)
        if want == "F" and fric and m and accs and forces:
            applied = forces[0].val
            fr = applied - m.val * accs[0].val
            return c.sol(c.show(fr, "force"), _std("friction = F_applied − m·a  (F_net = m·a)", [forces[0].known("F"), m.known("m"),
                                                                                              accs[0].known("a")],
                                                   f"friction = {n(applied)} − {n(m.val)} × {n(accs[0].val)}", f"friction = {n(fr)} N"))
        return None
    if want == "F" and forces and fric and m and accs:
        fr = forces[0].val - m.val * accs[0].val
        return c.sol(c.show(fr, "force"), _std("friction = F_applied − m·a  (F_net = m·a)",
                                               [forces[0].known("F"), m.known("m"), accs[0].known("a")],
                                               f"friction = {n(forces[0].val)} − {n(m.val)} × {n(accs[0].val)}", f"friction = {n(fr)} N"))
    if want == "F" and m is not None:
        steady = c.has(r"constant (?:speed|velocity)|steady speed|uniform (?:speed|velocity)|at a constant|without accelerat")
        if steady and friction_mu is not None:
            return c.sol(c.show(friction_mu, "force"), _std("F = friction = μ·m·g  (constant speed: net force 0)",
                                                            [f"μ = {n(c.mu)}", m.known("m"), c.gnote],
                                                            f"F = {n(c.mu)} × {n(m.val)} × {n(g)}", f"F = {n(friction_mu)} N"))
        a = None
        known = [m.known("m")]
        aline = ""
        if accs:
            a = accs[0].val
            known.append(accs[0].known("a"))
        else:
            sub = Ctx.__new__(Ctx)
            sub.__dict__.update(c.__dict__)
            sub.targets, sub.want = ["a"], "a"
            ks = h_kinematics(sub) if not c.has(FALL) else None
            if ks is None and c.has(BRAKE):
                ks = h_braking(sub)
            if ks is None:
                return None
            vals = [s for s in ks.steps if s.startswith("result:")]
            a_val = _first_value(ks)
            if a_val is None:
                return None
            a = a_val
            aline = f"a = {n(a)} m/s² ({vals[-1][8:].strip() if vals else ''})"
            known = [m.known("m")] + [s[7:] for s in ks.steps if s.startswith("known:")]
        extra = R(0)
        if friction_mu is not None:
            extra = friction_mu
            known.append(f"friction = μ·m·g = {n(friction_mu)} N")
        elif forces and info[id(forces[0])]["opp"]:
            extra = forces[0].val
            known.append(forces[0].known("friction"))
        F = m.val * abs(a) + extra
        formula = "F = m·a" + (" + friction" if extra else "") + "  (Newton's second law)"
        sub_ = f"F = {n(m.val)} × {n(abs(a))}" + (f" + {n(extra)}" if extra else "")
        steps = _std(formula, known, (aline + "; " if aline else "") + sub_, f"F = {n(F)} N")
        return c.sol(c.show(F, "force"), steps, f"F / m = {n(F / m.val)} m/s² ✓" if not extra else "")
    if want == "a" and len(forces) == 1 and m is not None and not friction_mu:
        F = forces[0]
        a = F.val / m.val
        return c.sol(c.show(a, "acc"), _std("a = F / m  (Newton's second law)", [F.known("F"), m.known("m")],
                                            f"a = {n(F.val)} / {n(m.val)}", f"a = {n(a)} m/s²"), f"m·a = {n(m.val * a)} N ✓")
    if want == "m" and len(forces) == 1 and len(accs) == 1:
        mv = forces[0].val / accs[0].val
        return c.sol(c.show(mv, "mass"), _std("m = F / a  (Newton's second law)", [forces[0].known("F"), accs[0].known("a")],
                                              f"m = {n(forces[0].val)} / {n(accs[0].val)}", f"m = {n(mv)} kg"),
                     f"m·a = {n(mv * accs[0].val)} N ✓")
    return None


def _first_value(sol: Solution):
    for s in sol.steps:
        m = re.match(r"result: a = (-?[\d,]*\.?\d+(?:e[+-]?\d+)?)", s)
        if m:
            return R(m.group(1).replace(",", "")) if _short(R(m.group(1).replace(",", ""))) else None
    return None


def h_weight(c: Ctx):
    want = c.want
    if want not in ("weight", "m", "g", "F"):
        return None
    ms, fs = c.of("mass"), c.of("force")
    if want == "F" and not c.has(r"\bweigh|gravit|on (?:the )?(?:moon|mars|jupiter|venus|mercury|saturn|earth|pluto|neptune|"
                                 r"uranus)"):
        return None
    if c.of("vel") or c.of("acc") or c.of("len") or c.of("energy") or c.of("area") or c.of("vol"):
        return None
    if want in ("weight", "F") and len(ms) == 1 and not fs:
        w = ms[0].val * c.g
        return c.sol(c.show(w, "force"), _std("W = m·g", [ms[0].known("m"), c.gnote], f"W = {n(ms[0].val)} × {n(c.g)}",
                                              f"W = {n(w)} N"), f"W / g = {n(w / c.g)} kg ✓ (the mass is the same everywhere)")
    if want in ("weight", "F") and len(fs) == 1 and not ms and c.planet and c.planet != "earth" and c.has(r"\bon (?:the )?earth\b"):
        we = fs[0].val
        mv = we / G0
        wp = mv * c.g
        return c.sol(c.show(wp, "force"), _std("W = m·g, with m = W_earth / g_earth", [fs[0].known("W on Earth"), "g on Earth = 9.81 m/s²",
                                                                                       c.gnote],
                                               f"m = {n(we)} / 9.81 = {n(mv)} kg; W = {n(mv)} × {n(c.g)}", f"W = {n(wp)} N"),
                     f"ratio {n(c.g)} / 9.81 = {n(c.g / G0)}, and {n(we)} × {n(c.g / G0)} = {n(wp)} N ✓")
    if want == "m" and len(fs) == 1 and not ms:
        mv = fs[0].val / c.g
        return c.sol(c.show(mv, "mass"), _std("m = W / g", [fs[0].known("W"), c.gnote], f"m = {n(fs[0].val)} / {n(c.g)}",
                                              f"m = {n(mv)} kg"), f"m·g = {n(mv * c.g)} N ✓")
    if want == "g" and len(fs) == 1 and len(ms) == 1:
        gv = fs[0].val / ms[0].val
        return c.sol(c.show(gv, "acc", "N/kg") if False else f"{num(gv, c.sig, c.dp)} N/kg",
                     _std("g = W / m", [fs[0].known("W"), ms[0].known("m")], f"g = {n(fs[0].val)} / {n(ms[0].val)}",
                          f"g = {n(gv)} N/kg (= m/s²)"))
    return None


def h_work(c: Ctx):
    want = c.want
    lift = c.has(r"\blift(?:s|ed|ing)?\b|\brais(?:e|es|ed|ing)\b|\bhoist|\bwinch|\bcrane|\bclimb|\bcarr(?:y|ies|ied) \w+ up|"
                 r"\bup (?:a|the|some|\d)|\bstairs\b|\bagainst gravity\b|\bupwards?\b|\belevator\b|\blift\b|\bhigh\b|\bheight\b|"
                 r"\bladder\b|\bshelf\b|\bpicks? up\b|\bpicked up\b|\bto a height\b|\bon top\b|\babove\b")
    if want not in ("W", "E", "F", "s", "h") or c.of("power") or (c.of("time") and want in ("W", "E")):
        return None
    if want in ("F", "s", "h") and not c.of("energy"):
        return None
    if want == "E" and not (lift or c.has(r"\bpush|\bpull|\bdrag|\bmove")):
        return None
    fs, ls, ms, angs, es, vs = c.of("force"), c.of("len"), c.of("mass"), c.of("angle"), c.of("energy"), c.of("vel")
    if want in ("W", "E"):
        if len(fs) == 1 and len(ls) == 1:
            F, d = fs[0], ls[0]
            if angs:
                th = angs[0].val
                cs = _cos(th)
                w = F.val * d.val * cs
                ans = c.show(w, "energy")
                return c.sol(ans, _std("W = F·d·cos θ  (only the part of the force along the motion does work)",
                                       [F.known("F"), d.known("d"), f"θ = {n(th)}°"], f"W = {n(F.val)} × {n(d.val)} × cos {n(th)}°",
                                       f"W = {n(w)} J"), f"F along the motion = {n(F.val * cs)} N × {n(d.val)} m = {n(w)} J ✓")
            w = F.val * d.val
            what = "weight × height" if re.search(r"weigh", F.wpre[-12:]) else "F·d"
            return c.sol(c.show(w, "energy"), _std(f"W = {what}" if what != "F·d" else "W = F·d  (force along the motion)",
                                                   [F.known("F"), d.known("d")], f"W = {n(F.val)} × {n(d.val)}", f"W = {n(w)} J"),
                         f"W / d = {n(w / d.val)} N ✓")
        if len(ms) == 1 and len(ls) == 1 and not fs:
            m, h = ms[0], ls[0]
            if c.mu is not None and not lift:
                w = c.mu * m.val * c.g * h.val
                return c.sol(c.show(w, "energy"), _std("W = μ·m·g·d  (work against friction)", [f"μ = {n(c.mu)}", m.known("m"), c.gnote,
                                                                                               h.known("d")],
                                                       f"W = {n(c.mu)} × {n(m.val)} × {n(c.g)} × {n(h.val)}", f"W = {n(w)} J"))
            if not lift:
                return None
            w = m.val * c.g * h.val
            return c.sol(c.show(w, "energy"), _std("W = m·g·h  (work against gravity = gain in potential energy)",
                                                   [m.known("m"), c.gnote, h.known("h")], f"W = {n(m.val)} × {n(c.g)} × {n(h.val)}",
                                                   f"W = {n(w)} J"), f"weight {n(m.val * c.g)} N × {n(h.val)} m = {n(w)} J ✓")
        if len(ms) == 1 and len(vs) == 2 and not fs and not ls:
            u, v = vs[0].val, vs[1].val
            w = ms[0].val * (v ** 2 - u ** 2) / 2
            return c.sol(c.show(w, "energy"), _std("W = ΔKE = ½·m·(v² − u²)  (work-energy theorem)",
                                                   [ms[0].known("m"), vs[0].known("u"), vs[1].known("v")],
                                                   f"W = ½ × {n(ms[0].val)} × ({n(v)}² − {n(u)}²)", f"W = {n(w)} J"))
        if len(ms) == 1 and len(vs) == 1 and not fs and not ls and c.has(REST_START):
            w = ms[0].val * vs[0].val ** 2 / 2
            return c.sol(c.show(w, "energy"), _std("W = ΔKE = ½·m·v²  (from rest)", [ms[0].known("m"), vs[0].known("v")],
                                                   f"W = ½ × {n(ms[0].val)} × {n(vs[0].val)}²", f"W = {n(w)} J"))
        return None
    if want == "F" and es and len(ls) == 1:
        F = es[0].val / ls[0].val
        return c.sol(c.show(F, "force"), _std("F = W / d", [es[0].known("W"), ls[0].known("d")], f"F = {n(es[0].val)} / {n(ls[0].val)}",
                                              f"F = {n(F)} N"), f"F·d = {n(F * ls[0].val)} J ✓")
    if want in ("s", "h") and es and len(fs) == 1:
        d = es[0].val / fs[0].val
        return c.sol(c.show(d, "len"), _std("d = W / F", [es[0].known("W"), fs[0].known("F")], f"d = {n(es[0].val)} / {n(fs[0].val)}",
                                            f"d = {n(d)} m"), f"F·d = {n(fs[0].val * d)} J ✓")
    return None


def h_power(c: Ctx):
    want = c.want
    ps, es, ts, ms, ls, fs, vs = (c.of(d) for d in ("power", "energy", "time", "mass", "len", "force", "vel"))
    if c.has(ELECTRIC):
        return None
    if want == "P":
        if len(es) == 1 and len(ts) == 1:
            pv = es[0].val / ts[0].val
            return c.sol(c.show(pv, "power"), _std("P = W / t", [es[0].known("W"), ts[0].known("t")],
                                                   f"P = {n(es[0].val)} / {n(ts[0].val)}", f"P = {n(pv)} W"),
                         f"P·t = {n(pv * ts[0].val)} J ✓")
        if len(ms) == 1 and len(ls) == 1 and len(ts) == 1 and not fs:
            m, h, t = ms[0], ls[0], ts[0]
            w = m.val * c.g * h.val
            pv = w / t.val
            return c.sol(c.show(pv, "power"), _std("P = W / t = m·g·h / t  (work against gravity per second)",
                                                   [m.known("m"), c.gnote, h.known("h"), t.known("t")],
                                                   f"W = {n(m.val)} × {n(c.g)} × {n(h.val)} = {n(w)} J; P = {n(w)} / {n(t.val)}",
                                                   f"P = {n(pv)} W"), f"P·t = {n(pv * t.val)} J = m·g·h ✓")
        if len(fs) == 1 and len(ls) == 1 and len(ts) == 1:
            w = fs[0].val * ls[0].val
            pv = w / ts[0].val
            return c.sol(c.show(pv, "power"), _std("P = F·d / t", [fs[0].known("F"), ls[0].known("d"), ts[0].known("t")],
                                                   f"P = {n(fs[0].val)} × {n(ls[0].val)} / {n(ts[0].val)}", f"P = {n(pv)} W"))
        if len(fs) == 1 and len(vs) == 1 and not ts:
            pv = fs[0].val * vs[0].val
            return c.sol(c.show(pv, "power"), _std("P = F·v", [fs[0].known("F"), vs[0].known("v")],
                                                   f"P = {n(fs[0].val)} × {n(vs[0].val)}", f"P = {n(pv)} W"),
                         f"P / v = {n(pv / vs[0].val)} N ✓")
        return None
    if not ps:
        return None
    P = ps[0]
    if want in ("W", "E", "cost") and len(ts) == 1 and not es:
        t = ts[0]
        w = P.val * t.val
        kwh = w / 3_600_000
        price = re.search(rf"({NUM})\s*(?:p|c|cents?|pence)?\s*(?:per|/|a|each)\s*(?:kwh|kw h|unit|kilowatt[- ]hour)", c.low)
        if want == "cost" or (price and c.ask_has(r"cost|price|bill|how much (?:will|would|does)")):
            if not price:
                return None
            rate = _rat(price.group(1))
            cost = kwh * rate
            return c.sol(f"{float(cost):,.2f}", _std("cost = energy in kWh × price per kWh, with E = P·t",
                                                     [P.known("P"), t.known("t"), f"price = {price.group(1)} per kWh"],
                                                     f"E = {n(P.val / 1000)} kW × {n(t.val / 3600)} h = {n(kwh)} kWh; "
                                                     f"cost = {n(kwh)} × {price.group(1)}", f"cost = {float(cost):,.2f}"))
        steps = _std("E = P·t", [P.known("P"), t.known("t")], f"E = {n(P.val)} × {n(t.val)}",
                     f"E = {n(w)} J" + (f" = {n(w / 1000)} kJ" if w >= 10000 else "") + f" = {n(kwh)} kWh")
        if c.ask_has(r"kwh|kilowatt[- ]hours?|units") and not c.out:
            return c.sol(c.show(kwh, "energy", "kWh"), steps, f"{n(kwh)} kWh × 3.6 × 10⁶ = {n(w)} J ✓")
        return c.sol(c.show(w, "energy"), steps, f"E / t = {n(w / t.val)} W ✓")
    if want == "t":
        if len(es) == 1:
            tt = es[0].val / P.val
            return c.sol(c.show(tt, "time"), _std("t = W / P", [es[0].known("W"), P.known("P")], f"t = {n(es[0].val)} / {n(P.val)}",
                                                  f"t = {n(tt)} s"), f"P·t = {n(P.val * tt)} J ✓")
        if len(ms) == 1 and len(ls) == 1:
            w = ms[0].val * c.g * ls[0].val
            tt = w / P.val
            return c.sol(c.show(tt, "time"), _std("t = m·g·h / P", [ms[0].known("m"), c.gnote, ls[0].known("h"), P.known("P")],
                                                  f"W = {n(ms[0].val)} × {n(c.g)} × {n(ls[0].val)} = {n(w)} J; t = {n(w)} / {n(P.val)}",
                                                  f"t = {n(tt)} s"), f"P·t = {n(P.val * tt)} J ✓")
    if want in ("h", "s") and len(ms) == 1 and len(ts) == 1:
        h = P.val * ts[0].val / (ms[0].val * c.g)
        return c.sol(c.show(h, "len"), _std("h = P·t / (m·g)", [P.known("P"), ts[0].known("t"), ms[0].known("m"), c.gnote],
                                            f"h = {n(P.val)} × {n(ts[0].val)} / ({n(ms[0].val)} × {n(c.g)})", f"h = {n(h)} m"))
    if want == "m" and len(ls) == 1 and len(ts) == 1:
        mv = P.val * ts[0].val / (c.g * ls[0].val)
        return c.sol(c.show(mv, "mass"), _std("m = P·t / (g·h)", [P.known("P"), ts[0].known("t"), ls[0].known("h"), c.gnote],
                                              f"m = {n(P.val)} × {n(ts[0].val)} / ({n(c.g)} × {n(ls[0].val)})", f"m = {n(mv)} kg"))
    if want in ("F",) and len(vs) == 1:
        F = P.val / vs[0].val
        return c.sol(c.show(F, "force"), _std("F = P / v", [P.known("P"), vs[0].known("v")], f"F = {n(P.val)} / {n(vs[0].val)}",
                                              f"F = {n(F)} N"))
    if want in ("v",) and len(fs) == 1:
        vv = P.val / fs[0].val
        return c.sol(c.show(vv, "vel"), _std("v = P / F", [P.known("P"), fs[0].known("F")], f"v = {n(P.val)} / {n(fs[0].val)}",
                                             f"v = {n(vv)} m/s"))
    return None


def h_energy(c: Ctx):
    want = c.want
    ms, vs, ls, es = c.of("mass"), c.of("vel"), c.of("len"), c.of("energy")
    if c.of("power") or c.of("force") or c.of("spring"):
        return None
    slide = c.has(r"slide|slides|roll|rolls|swing|swings|coaster|pendulum|ramp|slope|hill|frictionless|falls?|dropped|drop|"
                  r"released|bob|skier|sledge|sled|down|chute|track")
    if want == "KE":
        if len(ms) == 1 and len(vs) == 1:
            m, v = ms[0], vs[0]
            ke = m.val * v.val ** 2 / 2
            return c.sol(c.show(ke, "energy"), _std("KE = ½·m·v²", [m.known("m"), v.known("v")],
                                                    f"KE = ½ × {n(m.val)} × {n(v.val)}²", f"KE = {n(ke)} J"),
                         f"v = √(2·KE / m) = {n(_sqrt(2 * ke / m.val))} m/s ✓")
        if len(ms) == 1 and len(ls) == 1 and not vs and slide:
            ke = ms[0].val * c.g * ls[0].val
            return c.sol(c.show(ke, "energy"), _std("KE gained = PE lost = m·g·h  (no air resistance)",
                                                    [ms[0].known("m"), c.gnote, ls[0].known("h")],
                                                    f"KE = {n(ms[0].val)} × {n(c.g)} × {n(ls[0].val)}", f"KE = {n(ke)} J"))
        return None
    if want == "PE" or (want == "E" and len(ms) == 1 and len(ls) == 1 and not vs):
        if len(ms) == 1 and len(ls) == 1:
            m, h = ms[0], ls[0]
            pe = m.val * c.g * h.val
            return c.sol(c.show(pe, "energy"), _std("PE = m·g·h", [m.known("m"), c.gnote, h.known("h")],
                                                    f"PE = {n(m.val)} × {n(c.g)} × {n(h.val)}", f"PE = {n(pe)} J"),
                         f"h = PE / (m·g) = {n(pe / (m.val * c.g))} m ✓")
        return None
    if want == "E" and len(ms) == 1 and len(vs) == 1 and not ls:
        m, v = ms[0], vs[0]
        ke = m.val * v.val ** 2 / 2
        return c.sol(c.show(ke, "energy"), _std("KE = ½·m·v²", [m.known("m"), v.known("v")],
                                                f"KE = ½ × {n(m.val)} × {n(v.val)}²", f"KE = {n(ke)} J"))
    if want in ("v", "vf", "u"):
        if len(es) == 1 and len(ms) == 1 and not ls:
            v = _sqrt(2 * es[0].val / ms[0].val)
            return c.sol(c.show(v, "vel"), _std("v = √(2·KE / m)  (from KE = ½·m·v²)", [es[0].known("KE"), ms[0].known("m")],
                                                f"v = √(2 × {n(es[0].val)} / {n(ms[0].val)})", f"v = {n(v)} m/s"),
                         f"½ × {n(ms[0].val)} × {n(v)}² = {n(ms[0].val * v ** 2 / 2)} J ✓")
        if len(ls) == 1 and slide and len(vs) <= 1 and not es:
            h = ls[0]
            u = vs[0].val if vs else R(0)
            v = _sqrt(u ** 2 + 2 * c.g * h.val)
            formula = "v = √(2·g·h)  (PE lost = KE gained: m·g·h = ½·m·v², mass cancels)" if not vs else \
                "v = √(u² + 2·g·h)  (energy conservation)"
            known = ([vs[0].known("u")] if vs else []) + [h.known("h"), c.gnote]
            sub = f"v = √(2 × {n(c.g)} × {n(h.val)})" if not vs else f"v = √({n(u)}² + 2 × {n(c.g)} × {n(h.val)})"
            return c.sol(c.show(v, "vel"), _std(formula, known, sub, f"v = {n(v)} m/s"),
                         f"v² / (2g) = {n((v ** 2 - u ** 2) / (2 * c.g))} m ✓")
    if want in ("h", "s"):
        if len(es) == 1 and len(ms) == 1:
            h = es[0].val / (ms[0].val * c.g)
            return c.sol(c.show(h, "len"), _std("h = PE / (m·g)", [es[0].known("PE"), ms[0].known("m"), c.gnote],
                                                f"h = {n(es[0].val)} / ({n(ms[0].val)} × {n(c.g)})", f"h = {n(h)} m"),
                         f"m·g·h = {n(ms[0].val * c.g * h)} J ✓")
        if len(vs) == 1 and not ls and c.has(r"swing|pendulum|ramp|slope|hill|rise|rises|roll|rolls|slide|slides|coaster|"
                                             r"skateboard|up\b|climb"):
            v = vs[0].val
            h = v ** 2 / (2 * c.g)
            return c.sol(c.show(h, "len"), _std("h = v² / (2·g)  (KE becomes PE: ½·m·v² = m·g·h)", [vs[0].known("v"), c.gnote],
                                                f"h = {n(v)}² / (2 × {n(c.g)})", f"h = {n(h)} m"),
                         f"√(2·g·h) = {n(_sqrt(2 * c.g * h))} m/s ✓")
    if want == "m":
        if len(es) == 1 and len(vs) == 1 and not ls:
            mv = 2 * es[0].val / vs[0].val ** 2
            return c.sol(c.show(mv, "mass"), _std("m = 2·KE / v²", [es[0].known("KE"), vs[0].known("v")],
                                                  f"m = 2 × {n(es[0].val)} / {n(vs[0].val)}²", f"m = {n(mv)} kg"))
        if len(es) == 1 and len(ls) == 1 and not vs:
            mv = es[0].val / (c.g * ls[0].val)
            return c.sol(c.show(mv, "mass"), _std("m = PE / (g·h)", [es[0].known("PE"), c.gnote, ls[0].known("h")],
                                                  f"m = {n(es[0].val)} / ({n(c.g)} × {n(ls[0].val)})", f"m = {n(mv)} kg"))
    return None


def h_sdt(c: Ctx):
    """Constant speed: speed = distance / time and its rearrangements, in the user's units."""
    want = c.want
    if want not in ("v", "s", "t"):
        return None
    if c.of("acc") or c.has(FALL + "|" + UP + r"|accelerat|decelerat|brak"):
        return None
    vs, ls, ts = c.of("vel"), c.of("len"), c.of("time")
    if want == "v" and len(ls) == 1 and len(ts) == 1 and not vs:
        d, t = ls[0], ts[0]
        unit = {("km", "h"): "km/h", ("km", "min"): "km/h", ("miles", "h"): "mph", ("miles", "min"): "mph"}.get((d.unit, t.unit), "m/s")
        v = d.val / t.val
        ans = c.show(v, "vel", unit)
        extra = f" = {n(v)} m/s" if unit != "m/s" else ""
        return c.sol(ans, _std("speed = distance / time", [d.known("d"), t.known("t")],
                               f"v = {n(d.val / FACTOR[{'km/h': 'km', 'mph': 'miles'}.get(unit, 'm')])} / "
                               f"{n(t.val / FACTOR[{'km/h': 'h', 'mph': 'h'}.get(unit, 's')])}",
                               f"v = {n(v / FACTOR[unit])} {unit}{extra}"),
                     f"{n(v / FACTOR[unit])} {unit} × {n(t.val / FACTOR[{'km/h': 'h', 'mph': 'h'}.get(unit, 's')])} = "
                     f"{n(d.val / FACTOR[{'km/h': 'km', 'mph': 'miles'}.get(unit, 'm')])} ✓")
    if want == "t" and len(ls) == 1 and len(vs) == 1 and not ts:
        d, v = ls[0], vs[0]
        tt = d.val / v.val
        unit = "h" if v.unit in ("km/h", "mph", "knots") else "s"
        ans = c.show(tt, "time", unit)
        if unit == "h" and not c.out and tt / 3600 != int(tt / 3600):
            mins = tt / 60
            if mins < 60:
                ans = c.show(tt, "time", "min")
            else:
                hh = int(tt // 3600)
                mm = (tt - hh * 3600) / 60
                if mm == int(mm):
                    ans += f" ({hh} h {int(mm)} min)"
        du = {"km/h": "km", "mph": "miles"}.get(v.unit, "m")
        return c.sol(ans, _std("time = distance / speed", [d.known("d"), v.known("v")],
                               f"t = {n(d.val / FACTOR[du])} / {n(v.val / FACTOR[v.unit if v.unit in FACTOR else 'm/s'])}",
                               f"t = {n(tt / FACTOR[unit])} {unit}"), f"{n(v.val / FACTOR[v.unit])} × {n(tt / FACTOR[unit])} = "
                                                                       f"{n(d.val / FACTOR[du])} {du} ✓")
    if want == "s" and len(vs) == 1 and len(ts) == 1 and not ls:
        v, t = vs[0], ts[0]
        d = v.val * t.val
        du = {"km/h": "km", "mph": "miles"}.get(v.unit, "m")
        tu = "h" if du != "m" else "s"
        return c.sol(c.show(d, "len", du), _std("distance = speed × time", [v.known("v"), t.known("t")],
                                                f"d = {n(v.val / FACTOR[v.unit])} × {n(t.val / FACTOR[tu])}",
                                                f"d = {n(d / FACTOR[du])} {du}"), f"{n(d / FACTOR[du])} / {n(t.val / FACTOR[tu])} = "
                                                                                 f"{n(v.val / FACTOR[v.unit])} {v.unit} ✓")
    return None


HANDLERS = [h_convert, h_waves, h_spring, h_efficiency, h_pressure, h_density, h_impulse, h_collision, h_momentum,
            h_horizontal, h_angled, h_thrown_up, h_average, h_braking, h_fall, h_kinematics, h_forces, h_weight, h_work,
            h_power, h_energy, h_sdt]


def solve(text: str) -> Solution | None:
    """A mechanics or basic physics problem in plain English, solved with steps; None when it isn't one."""
    if not text or len(text) > 600 or not re.search(r"\d", text):
        return None
    low = text.lower()
    if re.search(ELECTRIC, low) or re.search(CHEM, low) or re.search(FINANCE, low.replace("per kwh", "")):
        if not (re.search(r"per kwh|/kwh|a kwh|per unit", low) and not re.search(ELECTRIC, low)):
            return None
    if re.match(r"\s*(?:what|who|why|when|where)(?:'s| is| are| was| were| does| do)\s+(?:an? |the )?[a-z' ]{2,40}\??\s*$", low):
        return None
    c = Ctx(text)
    if not c.qs:
        return None
    for h in HANDLERS:
        sol = _run(h, c)
        if sol is not None:
            if h in MULTI and len(c.targets) > 1:
                sol = _combine(h, c, sol)
            return sol
    return None


_ERRS = (ValueError, ZeroDivisionError, TypeError, KeyError, IndexError, AttributeError, OverflowError)
MULTI = {h_waves, h_spring, h_impulse, h_momentum, h_work, h_power, h_energy, h_density, h_pressure, h_weight}
LABEL = {"v": "speed", "T": "period", "f": "frequency", "lam": "wavelength", "PE": "energy", "E": "energy", "KE": "kinetic energy",
         "F": "force", "J": "impulse", "x": "extension", "k": "spring constant", "p": "momentum", "W": "work", "P": "power",
         "t": "time", "m": "mass", "rho": "density", "pressure": "pressure", "V": "volume", "weight": "weight", "s": "distance"}


def _run(h, c):
    try:
        return h(c)
    except _ERRS:
        return None


def _combine(h, c: Ctx, first: Solution) -> Solution:
    """Several things asked ("speed and period", "energy and force"): answer each one the same handler can."""
    parts, steps, seen = [], [], set()
    orig_t, orig_w = c.targets, c.want
    try:
        for t in orig_t:
            c.targets, c.want = [t] + [x for x in orig_t if x != t], t
            s = first if t == orig_t[0] else _run(h, c)
            if s is None or s.answer in seen:
                continue
            seen.add(s.answer)
            label = LABEL.get(t, t)
            parts.append(f"{label} = {s.answer}")
            steps += [f"{label}: {x}" for x in s.steps]
    finally:
        c.targets, c.want = orig_t, orig_w
    if len(parts) < 2:
        return first
    return c.sol(", ".join(parts), steps, first.check)
