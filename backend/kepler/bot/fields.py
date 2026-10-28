"""Field-specific reasoning: physics, electrical, chemistry, finance, statistics and geometry problems in plain English.

"A car accelerates from 0 to 27 m/s in 9 seconds, what is its acceleration?" → reads the quantities with their units,
works out what is asked, picks the formula, and answers with every step: formula, knowns (in SI units), substitution,
result with its unit, and a check. Deterministic and exact where it can be (sympy), no language model.

Each handler fires only when the question names what it asks (acceleration, current, molar mass, monthly payment…)
and gives the quantities it needs, so "what is the current status" or "switch to area" never land here.
"""
import math
import re

import sympy as sp
from scipy.special import ndtr

from .reasoning import Solution

G = 9.81  # m/s², standard gravity

# ---------------------------------------------------------------- quantities with units

# unit spelling → (dimension, factor to SI). Longest spellings first when matching.
UNITS = {
    "m/s^2": ("acc", 1), "m/s²": ("acc", 1), "m/s2": ("acc", 1), "meters per second squared": ("acc", 1),
    "km/h": ("vel", 1 / 3.6), "kmph": ("vel", 1 / 3.6), "kph": ("vel", 1 / 3.6), "mph": ("vel", 0.44704),
    "m/s": ("vel", 1), "meters per second": ("vel", 1), "metres per second": ("vel", 1),
    "kg/m^3": ("density", 1), "kg/m³": ("density", 1), "g/cm^3": ("density", 1000), "g/cm³": ("density", 1000),
    "g/ml": ("density", 1000), "g/mol": ("molar_mass", 1),
    "km": ("len", 1000), "cm": ("len", 0.01), "mm": ("len", 0.001), "m": ("len", 1), "meter": ("len", 1),
    "meters": ("len", 1), "metre": ("len", 1), "metres": ("len", 1), "mile": ("len", 1609.344),
    "miles": ("len", 1609.344), "ft": ("len", 0.3048), "feet": ("len", 0.3048), "foot": ("len", 0.3048),
    "ms": ("time", 0.001), "s": ("time", 1), "sec": ("time", 1), "secs": ("time", 1), "second": ("time", 1),
    "seconds": ("time", 1), "min": ("time", 60), "mins": ("time", 60), "minute": ("time", 60),
    "minutes": ("time", 60), "h": ("time", 3600), "hr": ("time", 3600), "hrs": ("time", 3600),
    "hour": ("time", 3600), "hours": ("time", 3600), "day": ("time", 86400), "days": ("time", 86400),
    "kg": ("mass", 1), "g": ("mass", 0.001), "gram": ("mass", 0.001), "grams": ("mass", 0.001),
    "mg": ("mass", 1e-6), "tonne": ("mass", 1000), "tonnes": ("mass", 1000),
    "kn": ("force", 1000), "n": ("force", 1), "newton": ("force", 1), "newtons": ("force", 1),
    "kwh": ("energy", 3.6e6), "wh": ("energy", 3600), "kj": ("energy", 1000), "j": ("energy", 1),
    "joule": ("energy", 1), "joules": ("energy", 1),
    "kw": ("power", 1000), "w": ("power", 1), "watt": ("power", 1), "watts": ("power", 1),
    "v": ("voltage", 1), "volt": ("voltage", 1), "volts": ("voltage", 1),
    "ma": ("current", 0.001), "a": ("current", 1), "amp": ("current", 1), "amps": ("current", 1),
    "ampere": ("current", 1), "amperes": ("current", 1),
    "kohm": ("resistance", 1000), "kω": ("resistance", 1000), "ohm": ("resistance", 1), "ohms": ("resistance", 1),
    "ω": ("resistance", 1),
    "khz": ("freq", 1000), "hz": ("freq", 1), "hertz": ("freq", 1),
    "mol": ("amount", 1), "mole": ("amount", 1), "moles": ("amount", 1),
    "ml": ("vol", 1e-6), "l": ("vol", 1e-3), "litre": ("vol", 1e-3), "litres": ("vol", 1e-3),
    "liter": ("vol", 1e-3), "liters": ("vol", 1e-3), "m^3": ("vol", 1), "m³": ("vol", 1),
    "m^2": ("area", 1), "m²": ("area", 1), "cm^2": ("area", 1e-4), "cm²": ("area", 1e-4),
    "kpa": ("pressure", 1000), "pa": ("pressure", 1),
    "°": ("angle", 1), "deg": ("angle", 1), "degree": ("angle", 1), "degrees": ("angle", 1),
    "%": ("rate", 0.01), "percent": ("rate", 0.01),
}
SI = {"acc": "m/s²", "vel": "m/s", "len": "m", "time": "s", "mass": "kg", "force": "N", "energy": "J", "power": "W",
      "voltage": "V", "current": "A", "resistance": "Ω", "freq": "Hz", "amount": "mol", "vol": "m³", "area": "m²",
      "pressure": "Pa", "density": "kg/m³", "molar_mass": "g/mol"}
_UNIT_RE = "|".join(re.escape(u) for u in sorted(UNITS, key=len, reverse=True))
NUM = r"-?\d+(?:,\d{3})*(?:\.\d+)?(?:e-?\d+)?"
QTY = re.compile(rf"({NUM})\s*({_UNIT_RE})(?![a-z])", re.I)


class Q:
    def __init__(self, value: float, dim: str, raw: str, pos: int):
        self.value, self.dim, self.raw, self.pos = value, dim, raw, pos


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def quantities(text: str) -> list[Q]:
    """Numbers with units, in SI. "from 0 to 27 m/s" gives the bare 0 the unit of the 27."""
    out = []
    for m in QTY.finditer(text):
        dim, factor = UNITS[m.group(2).lower()]
        out.append(Q(_num(m.group(1)) * factor, dim, m.group(0), m.start()))
    for m in re.finditer(rf"from\s+({NUM})\s+to\s+({NUM})\s*({_UNIT_RE})(?![a-z])", text, re.I):
        dim, factor = UNITS[m.group(3).lower()]
        out.append(Q(_num(m.group(1)) * factor, dim, m.group(1), m.start(1)))
    if re.search(r"\b(?:from rest|starts? at rest|at rest|dropped|released)\b", text, re.I):
        out.append(Q(0.0, "vel", "rest", -1))
    return sorted(out, key=lambda q: q.pos)


def _of(qs: list[Q], dim: str) -> list[float]:
    return [q.value for q in qs if q.dim == dim]


def _numbers(text: str) -> list[float]:
    return [_num(n) for n in re.findall(NUM, text)]


def fmt(x: float, unit: str = "") -> str:
    """4 significant figures, thousands separators, no trailing zeros."""
    if x == 0:
        s = "0"
    elif abs(x) >= 1e7 or abs(x) < 1e-3:
        s = f"{x:.4g}"
    else:
        digits = max(0, 4 - int(math.floor(math.log10(abs(x)))) - 1)
        s = f"{x:,.{digits}f}"
        if "." in s:
            s = s.rstrip("0").rstrip(".")
    return f"{s} {unit}".strip()


def money(x: float) -> str:
    return f"{x:,.2f}"


def _sol(kind: str, problem: str, formula: str, knowns: list[str], sub: str, answer: str, check: str = "") -> Solution:
    steps = [f"formula: {formula}", "known: " + ", ".join(knowns), f"substitute: {sub}", f"result: {answer}"]
    return Solution(kind, problem, answer, steps, check=check, confidence=0.97)


def _asks(t: str, *words: str) -> bool:
    return any(re.search(rf"\b{w}\b", t) for w in words)


# ---------------------------------------------------------------- physics

def physics(text: str, t: str, qs: list[Q]) -> Solution | None:
    vel, acc, tim, mass, force = _of(qs, "vel"), _of(qs, "acc"), _of(qs, "time"), _of(qs, "mass"), _of(qs, "force")
    length, energy, power, vol, area, freq = (_of(qs, d) for d in ("len", "energy", "power", "vol", "area", "freq"))
    fall = _asks(t, "fall", "falls", "falling", "dropped", "drop", "drops", "free fall")
    if _asks(t, "acceleration", "accelerate", "accelerates") and _asks(t, "what", "find", "calculate", "how much"):
        if len(vel) >= 2 and tim:
            u, v, dt = vel[0], vel[-1], tim[0]
            a = (v - u) / dt
            return _sol("physics", text, "a = (v − u) / t", [f"u = {fmt(u, 'm/s')}", f"v = {fmt(v, 'm/s')}", f"t = {fmt(dt, 's')}"],
                        f"a = ({fmt(v)} − {fmt(u)}) / {fmt(dt)}", fmt(a, "m/s²"),
                        f"v = u + a·t = {fmt(u)} + {fmt(a)} × {fmt(dt)} = {fmt(u + a * dt)} m/s ✓")
        if force and mass:
            a = force[0] / mass[0]
            return _sol("physics", text, "a = F / m  (Newton's second law)", [f"F = {fmt(force[0], 'N')}", f"m = {fmt(mass[0], 'kg')}"],
                        f"a = {fmt(force[0])} / {fmt(mass[0])}", fmt(a, "m/s²"), f"F = m·a = {fmt(mass[0] * a)} N ✓")
    if _asks(t, "kinetic energy", "ke") and mass and vel:
        m, v = mass[0], vel[-1]
        ke = 0.5 * m * v * v
        return _sol("physics", text, "KE = ½ · m · v²", [f"m = {fmt(m, 'kg')}", f"v = {fmt(v, 'm/s')}"],
                    f"KE = 0.5 × {fmt(m)} × {fmt(v)}²", fmt(ke, "J"), f"v = √(2·KE/m) = {fmt(math.sqrt(2 * ke / m))} m/s ✓")
    if _asks(t, "potential energy", "pe", "gpe") and mass and length:
        m, h = mass[0], length[0]
        return _sol("physics", text, "PE = m · g · h", [f"m = {fmt(m, 'kg')}", f"g = {G} m/s²", f"h = {fmt(h, 'm')}"],
                    f"PE = {fmt(m)} × {G} × {fmt(h)}", fmt(m * G * h, "J"))
    if fall and not [q for q in qs if q.dim == "vel" and q.raw != "rest"] and (tim or length):
        if tim and _asks(t, "how far", "distance", "how much", "how many meters", "how deep"):
            s = 0.5 * G * tim[0] ** 2
            return _sol("physics", text, "s = ½ · g · t²  (free fall from rest, no air resistance)",
                        [f"g = {G} m/s²", f"t = {fmt(tim[0], 's')}"], f"s = 0.5 × {G} × {fmt(tim[0])}²", fmt(s, "m"),
                        f"t = √(2s/g) = {fmt(math.sqrt(2 * s / G))} s ✓")
        if length and _asks(t, "how long", "time", "how many seconds"):
            tt = math.sqrt(2 * length[0] / G)
            return _sol("physics", text, "t = √(2h / g)  (free fall from rest)", [f"h = {fmt(length[0], 'm')}", f"g = {G} m/s²"],
                        f"t = √(2 × {fmt(length[0])} / {G})", fmt(tt, "s"), f"h = ½·g·t² = {fmt(0.5 * G * tt * tt)} m ✓")
        if length and _asks(t, "how fast", "speed", "velocity", "impact"):
            v = math.sqrt(2 * G * length[0])
            return _sol("physics", text, "v = √(2 · g · h)  (free fall from rest)", [f"h = {fmt(length[0], 'm')}", f"g = {G} m/s²"],
                        f"v = √(2 × {G} × {fmt(length[0])})", fmt(v, "m/s"))
    if _asks(t, "force", "net force") and mass and acc and not _asks(t, "acceleration of"):
        f = mass[0] * acc[0]
        return _sol("physics", text, "F = m · a  (Newton's second law)", [f"m = {fmt(mass[0], 'kg')}", f"a = {fmt(acc[0], 'm/s²')}"],
                    f"F = {fmt(mass[0])} × {fmt(acc[0])}", fmt(f, "N"))
    if _asks(t, "weight") and mass and not force:
        return _sol("physics", text, "W = m · g", [f"m = {fmt(mass[0], 'kg')}", f"g = {G} m/s²"], f"W = {fmt(mass[0])} × {G}",
                    fmt(mass[0] * G, "N"))
    if _asks(t, "momentum") and mass and vel:
        return _sol("physics", text, "p = m · v", [f"m = {fmt(mass[0], 'kg')}", f"v = {fmt(vel[-1], 'm/s')}"],
                    f"p = {fmt(mass[0])} × {fmt(vel[-1])}", fmt(mass[0] * vel[-1], "kg·m/s"))
    if _asks(t, "final velocity", "final speed") and vel and acc and tim:
        v = vel[0] + acc[0] * tim[0]
        return _sol("physics", text, "v = u + a · t", [f"u = {fmt(vel[0], 'm/s')}", f"a = {fmt(acc[0], 'm/s²')}", f"t = {fmt(tim[0], 's')}"],
                    f"v = {fmt(vel[0])} + {fmt(acc[0])} × {fmt(tim[0])}", fmt(v, "m/s"))
    if _asks(t, "work", "work done") and force and length:
        return _sol("physics", text, "W = F · d", [f"F = {fmt(force[0], 'N')}", f"d = {fmt(length[0], 'm')}"],
                    f"W = {fmt(force[0])} × {fmt(length[0])}", fmt(force[0] * length[0], "J"))
    if _asks(t, "density") and mass and vol:
        return _sol("physics", text, "ρ = m / V", [f"m = {fmt(mass[0], 'kg')}", f"V = {fmt(vol[0], 'm³')}"],
                    f"ρ = {fmt(mass[0])} / {fmt(vol[0])}", fmt(mass[0] / vol[0], "kg/m³"))
    if _asks(t, "pressure") and force and area:
        return _sol("physics", text, "P = F / A", [f"F = {fmt(force[0], 'N')}", f"A = {fmt(area[0], 'm²')}"],
                    f"P = {fmt(force[0])} / {fmt(area[0])}", fmt(force[0] / area[0], "Pa"))
    if _asks(t, "wavelength") and vel and freq:
        return _sol("physics", text, "λ = v / f", [f"v = {fmt(vel[0], 'm/s')}", f"f = {fmt(freq[0], 'Hz')}"],
                    f"λ = {fmt(vel[0])} / {fmt(freq[0])}", fmt(vel[0] / freq[0], "m"))
    if _asks(t, "power") and energy and tim and not _of(qs, "voltage"):
        return _sol("physics", text, "P = E / t", [f"E = {fmt(energy[0], 'J')}", f"t = {fmt(tim[0], 's')}"],
                    f"P = {fmt(energy[0])} / {fmt(tim[0])}", fmt(energy[0] / tim[0], "W"))
    return None


# ---------------------------------------------------------------- electrical

def electrical(text: str, t: str, qs: list[Q]) -> Solution | None:
    v, i, r, p, tim = _of(qs, "voltage"), _of(qs, "current"), _of(qs, "resistance"), _of(qs, "power"), _of(qs, "time")
    if _asks(t, "current", "amps", "amperes") and v and r:
        return _sol("electrical", text, "I = V / R  (Ohm's law)", [f"V = {fmt(v[0], 'V')}", f"R = {fmt(r[0], 'Ω')}"],
                    f"I = {fmt(v[0])} / {fmt(r[0])}", fmt(v[0] / r[0], "A"), f"V = I·R = {fmt(v[0] / r[0] * r[0])} V ✓")
    if _asks(t, "voltage", "volts", "potential difference") and i and r:
        return _sol("electrical", text, "V = I · R  (Ohm's law)", [f"I = {fmt(i[0], 'A')}", f"R = {fmt(r[0], 'Ω')}"],
                    f"V = {fmt(i[0])} × {fmt(r[0])}", fmt(i[0] * r[0], "V"))
    if _asks(t, "resistance", "ohms") and v and i:
        return _sol("electrical", text, "R = V / I  (Ohm's law)", [f"V = {fmt(v[0], 'V')}", f"I = {fmt(i[0], 'A')}"],
                    f"R = {fmt(v[0])} / {fmt(i[0])}", fmt(v[0] / i[0], "Ω"))
    if _asks(t, "power", "watts") and not p:
        if v and i:
            return _sol("electrical", text, "P = V · I", [f"V = {fmt(v[0], 'V')}", f"I = {fmt(i[0], 'A')}"],
                        f"P = {fmt(v[0])} × {fmt(i[0])}", fmt(v[0] * i[0], "W"))
        if i and r:
            return _sol("electrical", text, "P = I² · R", [f"I = {fmt(i[0], 'A')}", f"R = {fmt(r[0], 'Ω')}"],
                        f"P = {fmt(i[0])}² × {fmt(r[0])}", fmt(i[0] ** 2 * r[0], "W"))
        if v and r:
            return _sol("electrical", text, "P = V² / R", [f"V = {fmt(v[0], 'V')}", f"R = {fmt(r[0], 'Ω')}"],
                        f"P = {fmt(v[0])}² / {fmt(r[0])}", fmt(v[0] ** 2 / r[0], "W"))
    if p and tim and _asks(t, "energy", "kwh", "units", "how much", "consume", "consumes", "used", "uses", "cost"):
        e_kwh = p[0] * tim[0] / 3.6e6
        sol = _sol("electrical", text, "E = P · t", [f"P = {fmt(p[0], 'W')}", f"t = {fmt(tim[0] / 3600, 'h')}"],
                   f"E = {fmt(p[0])} W × {fmt(tim[0] / 3600)} h = {fmt(p[0] * tim[0] / 3600)} Wh", fmt(e_kwh, "kWh"))
        price = re.search(rf"({NUM})\s*(?:per|/|a)\s*(?:kwh|unit)", t)
        if price and _asks(t, "cost", "price", "bill"):
            cost = e_kwh * _num(price.group(1))
            sol.steps.append(f"cost: {fmt(e_kwh)} kWh × {price.group(1)} per kWh = {fmt(cost)}")
            sol.answer = f"{fmt(e_kwh, 'kWh')}, costing {fmt(cost)}"
        return sol
    return None


# ---------------------------------------------------------------- chemistry

ATOMIC = {"H": 1.008, "He": 4.0026, "Li": 6.94, "Be": 9.0122, "B": 10.81, "C": 12.011, "N": 14.007, "O": 15.999,
          "F": 18.998, "Ne": 20.180, "Na": 22.990, "Mg": 24.305, "Al": 26.982, "Si": 28.085, "P": 30.974, "S": 32.06,
          "Cl": 35.45, "Ar": 39.948, "K": 39.098, "Ca": 40.078, "Sc": 44.956, "Ti": 47.867, "V": 50.942, "Cr": 51.996,
          "Mn": 54.938, "Fe": 55.845, "Co": 58.933, "Ni": 58.693, "Cu": 63.546, "Zn": 65.38, "Ga": 69.723,
          "Ge": 72.630, "As": 74.922, "Se": 78.971, "Br": 79.904, "Kr": 83.798, "Rb": 85.468, "Sr": 87.62,
          "Ag": 107.87, "Sn": 118.71, "I": 126.90, "Ba": 137.33, "Pt": 195.08, "Au": 196.97, "Hg": 200.59,
          "Pb": 207.2, "U": 238.03}
NAMES = {"water": "H2O", "salt": "NaCl", "table salt": "NaCl", "sodium chloride": "NaCl", "carbon dioxide": "CO2",
         "oxygen gas": "O2", "oxygen": "O2", "hydrogen gas": "H2", "nitrogen gas": "N2", "methane": "CH4",
         "ammonia": "NH3", "glucose": "C6H12O6", "sugar": "C12H22O11", "sucrose": "C12H22O11", "ethanol": "C2H5OH",
         "sulfuric acid": "H2SO4", "sulphuric acid": "H2SO4", "hydrochloric acid": "HCl", "nitric acid": "HNO3",
         "sodium hydroxide": "NaOH", "potassium hydroxide": "KOH", "calcium carbonate": "CaCO3",
         "baking soda": "NaHCO3", "sodium bicarbonate": "NaHCO3", "calcium hydroxide": "Ca(OH)2"}
STRONG_ACIDS = {"HCl": 1, "HNO3": 1, "HBr": 1, "HI": 1, "HClO4": 1, "H2SO4": 2}
STRONG_BASES = {"NaOH": 1, "KOH": 1, "LiOH": 1, "Ca(OH)2": 2, "Ba(OH)2": 2}
FORMULA = re.compile(r"\b((?:[A-Z][a-z]?\d*|\((?:[A-Z][a-z]?\d*)+\)\d*)+)")


def formula_mass(formula: str) -> tuple[float, list[str]] | None:
    """Molar mass of a formula like C6H12O6 or Ca(OH)2, with the per-element working; None if it isn't one."""
    counts: dict[str, int] = {}

    def parse(s: str, mult: int) -> None:
        i = 0
        while i < len(s):
            if s[i] == "(":
                depth, j = 1, i + 1
                while depth:
                    depth += {"(": 1, ")": -1}.get(s[j], 0)
                    j += 1
                n = re.match(r"\d*", s[j:]).group(0)
                parse(s[i + 1:j - 1], mult * (int(n) if n else 1))
                i = j + len(n)
                continue
            m = re.match(r"([A-Z][a-z]?)(\d*)", s[i:])
            if not m or m.group(1) not in ATOMIC:
                raise ValueError(s)
            counts[m.group(1)] = counts.get(m.group(1), 0) + mult * (int(m.group(2)) if m.group(2) else 1)
            i += len(m.group(0))
    try:
        parse(formula, 1)
    except (ValueError, IndexError):
        return None
    if not counts:
        return None
    parts = [f"{el} {n} × {ATOMIC[el]}" for el, n in counts.items()]
    return sum(ATOMIC[el] * n for el, n in counts.items()), parts


# formulas people type in lower case ("h2o", "hcl"); only unambiguous ones ("co" could be Co or CO)
LOWER = {f.lower(): f for f in ("H2O", "CO2", "NaCl", "HCl", "H2SO4", "HNO3", "NaOH", "KOH", "NH3", "CH4", "C6H12O6",
                                "CaCO3", "NaHCO3", "O2", "H2", "N2", "C2H5OH", "C12H22O11", "Ca(OH)2", "HBr", "LiOH")}


def _compound(text: str) -> str | None:
    low = text.lower()
    for name in sorted(NAMES, key=len, reverse=True):
        if re.search(rf"\b{name}\b", low):
            return NAMES[name]
    for f in sorted(LOWER, key=len, reverse=True):
        if re.search(rf"(?<![\w(]){re.escape(f)}(?![\w)])", low):
            return LOWER[f]
    for m in FORMULA.finditer(text):
        f = m.group(1)
        if (len(f) >= 2 or re.search(r"\d", f)) and formula_mass(f):
            return f
    return None


def chemistry(text: str, t: str, qs: list[Q]) -> Solution | None:
    compound = _compound(text)
    if _asks(t, "ph", "poh"):
        conc = re.search(rf"({NUM})\s*(?:M\b|mol/l|molar|mol per l)", text, re.I)
        if conc and compound:
            c = _num(conc.group(1))
            if compound in STRONG_ACIDS:
                h = c * STRONG_ACIDS[compound]
                ph = -math.log10(h)
                return _sol("chemistry", text, "pH = −log₁₀[H⁺]  (strong acid: fully dissociated)",
                            [f"[{compound}] = {fmt(c, 'M')}", f"H⁺ per molecule = {STRONG_ACIDS[compound]}", f"[H⁺] = {fmt(h, 'M')}"],
                            f"pH = −log₁₀({fmt(h)})", fmt(ph), f"10^−{fmt(ph)} = {fmt(10 ** -ph)} M ✓")
            if compound in STRONG_BASES:
                oh = c * STRONG_BASES[compound]
                poh = -math.log10(oh)
                return _sol("chemistry", text, "pOH = −log₁₀[OH⁻], pH = 14 − pOH  (strong base, 25 °C)",
                            [f"[{compound}] = {fmt(c, 'M')}", f"[OH⁻] = {fmt(oh, 'M')}"],
                            f"pOH = −log₁₀({fmt(oh)}) = {fmt(poh)}; pH = 14 − {fmt(poh)}", fmt(14 - poh))
    if not compound:
        return None
    mm = formula_mass(compound)
    if not mm:
        return None
    m_mass, parts = mm
    mass, amount = _of(qs, "mass"), _of(qs, "amount")
    if _asks(t, "moles", "mol", "how many moles") and mass and not amount:
        grams = mass[0] * 1000
        n = grams / m_mass
        return _sol("chemistry", text, "n = m / M", [f"m = {fmt(grams, 'g')}", f"M({compound}) = {fmt(m_mass, 'g/mol')}"],
                    f"n = {fmt(grams)} / {fmt(m_mass)}", fmt(n, "mol"), f"n × M = {fmt(n * m_mass)} g ✓")
    if _asks(t, "mass", "grams", "how many grams", "weigh") and amount and not mass:
        g = amount[0] * m_mass
        return _sol("chemistry", text, "m = n · M", [f"n = {fmt(amount[0], 'mol')}", f"M({compound}) = {fmt(m_mass, 'g/mol')}"],
                    f"m = {fmt(amount[0])} × {fmt(m_mass)}", fmt(g, "g"))
    if _asks(t, "molarity", "concentration") and amount and _of(qs, "vol"):
        litres = _of(qs, "vol")[0] * 1000
        return _sol("chemistry", text, "c = n / V", [f"n = {fmt(amount[0], 'mol')}", f"V = {fmt(litres, 'L')}"],
                    f"c = {fmt(amount[0])} / {fmt(litres)}", fmt(amount[0] / litres, "M"))
    if _asks(t, "molar mass", "molecular weight", "molecular mass", "formula mass"):
        return _sol("chemistry", text, "M = Σ (atoms × atomic mass)", [compound], " + ".join(parts), fmt(m_mass, "g/mol"))
    return None


# ---------------------------------------------------------------- finance

def _money(t: str) -> list[float]:
    """Amounts that aren't rates, years or months: the principal, a contribution."""
    out = []
    for m in re.finditer(rf"(?:[$₹€£]|rs\.?\s*)?({NUM})(?!\s*(?:%|percent|years?|yrs?|months?|days?))", t):
        out.append(_num(m.group(1)))
    return out


def finance(text: str, t: str, qs: list[Q]) -> Solution | None:
    rate = re.search(rf"({NUM})\s*(?:%|percent)", t)
    years = re.search(rf"({NUM})\s*(?:years?|yrs?)", t)
    months = re.search(rf"({NUM})\s*months?", t)
    if not rate or not (years or months):
        return None
    r_year = _num(rate.group(1)) / 100
    n = int(round(_num(years.group(1)) * 12)) if years else int(_num(months.group(1)))
    r = r_year / 12
    amounts = [a for a in _money(t) if a not in (_num(rate.group(1)),) and (not years or a != _num(years.group(1)))
               and (not months or a != _num(months.group(1)))]
    if not amounts:
        return None
    if _asks(t, "payment", "payments", "emi", "installment", "instalment", "repayment", "pay per month", "pay each month"):
        p = amounts[0]
        pmt = p * r / (1 - (1 + r) ** -n) if r else p / n
        total = pmt * n
        sol = _sol("finance", text, "PMT = P · r / (1 − (1 + r)^−n)  (fixed-rate loan, monthly)",
                   [f"P = {money(p)}", f"r = {fmt(r_year * 100)}% / 12 = {r:.6f} a month", f"n = {n} months"],
                   f"PMT = {money(p)} × {r:.6f} / (1 − {1 + r:.6f}^−{n})", f"{money(pmt)} a month",
                   f"total paid {money(total)} = principal {money(p)} + interest {money(total - p)}")
        return sol
    if _asks(t, "invest", "save", "saving", "deposit", "contribute", "put away") and _asks(t, "month", "monthly", "a month", "per month", "every month"):
        pmt = amounts[0]
        fv = pmt * ((1 + r) ** n - 1) / r if r else pmt * n
        return _sol("finance", text, "FV = PMT · ((1 + r)^n − 1) / r  (monthly contributions, monthly compounding)",
                    [f"PMT = {money(pmt)} a month", f"r = {fmt(r_year * 100)}% / 12", f"n = {n} months"],
                    f"FV = {money(pmt)} × ((1 + {r:.6f})^{n} − 1) / {r:.6f}", money(fv),
                    f"you put in {money(pmt * n)}, growth {money(fv - pmt * n)}")
    return None


def cagr(text: str, t: str) -> Solution | None:
    m = re.search(rf"(?:grew|grows|went|increased|rose|growth)\D*?from\s*[$₹€£]?({NUM})\s*to\s*[$₹€£]?({NUM})\D*?({NUM})\s*years?", t)
    if not m or not _asks(t, "rate", "cagr", "growth rate", "annual", "per year", "a year"):
        return None
    a, b, yrs = _num(m.group(1)), _num(m.group(2)), _num(m.group(3))
    g = (b / a) ** (1 / yrs) - 1
    return _sol("finance", text, "CAGR = (end / start)^(1/years) − 1", [f"start = {fmt(a)}", f"end = {fmt(b)}", f"years = {fmt(yrs)}"],
                f"CAGR = ({fmt(b)} / {fmt(a)})^(1/{fmt(yrs)}) − 1", f"{fmt(g * 100)}% a year",
                f"{fmt(a)} × {1 + g:.4f}^{fmt(yrs)} = {fmt(a * (1 + g) ** yrs)} ✓")


# ---------------------------------------------------------------- statistics

def statistics(text: str, t: str) -> Solution | None:
    mean = re.search(rf"(?:mean|average|μ)\s*(?:is|of|=|:)?\s*({NUM})", t)
    sd = re.search(rf"(?:sd|s\.d\.|std|standard deviation|σ)\s*(?:is|of|=|:)?\s*({NUM})", t)
    if not (mean and sd):
        return None
    mu, sigma = _num(mean.group(1)), _num(sd.group(1))
    if sigma <= 0:
        return None
    if _asks(t, "z score", "z-score", "zscore", "standard score", "z"):
        x = next((v for v in _numbers(t) if v not in (mu, sigma)), None)
        if x is None:
            return None
        z = (x - mu) / sigma
        pct = float(ndtr(z)) * 100
        return _sol("statistics", text, "z = (x − μ) / σ", [f"x = {fmt(x)}", f"μ = {fmt(mu)}", f"σ = {fmt(sigma)}"],
                    f"z = ({fmt(x)} − {fmt(mu)}) / {fmt(sigma)}", f"z = {fmt(z)} (higher than {fmt(pct)}% of values, for a normal distribution)")
    below = re.search(rf"(?:less than|below|under|at most)\s*({NUM})", t)
    above = re.search(rf"(?:more than|greater than|above|over|at least)\s*({NUM})", t)
    if _asks(t, "probability", "chance", "percent", "percentage", "proportion") and (below or above):
        x = _num((below or above).group(1))
        z = (x - mu) / sigma
        p = float(ndtr(z)) if below else 1 - float(ndtr(z))
        side = "P(X < x) = Φ(z)" if below else "P(X > x) = 1 − Φ(z)"
        return _sol("statistics", text, f"z = (x − μ) / σ, {side}  (normal distribution)",
                    [f"x = {fmt(x)}", f"μ = {fmt(mu)}", f"σ = {fmt(sigma)}"], f"z = {fmt(z)}", f"{fmt(p)} ({fmt(p * 100)}%)")
    return None


# ---------------------------------------------------------------- geometry and trigonometry

def _measure(t: str, *names: str) -> float | None:
    for n in names:
        m = re.search(rf"\b{n}\s*(?:is|of|=|:)?\s*({NUM})", t) or re.search(rf"({NUM})\s*(?:cm|m|mm|km|units?)?\s*{n}\b", t)
        if m:
            return _num(m.group(1))
    return None


def geometry(text: str, t: str) -> Solution | None:
    r = _measure(t, "radius", "r")
    d = _measure(t, "diameter")
    if r is None and d is not None:
        r = d / 2
    unit = (re.search(rf"{NUM}\s*(cm|mm|km|m)\b", t) or [None, ""])[1] or ""
    u2, u3 = (f"{unit}²" if unit else "square units"), (f"{unit}³" if unit else "cubic units")
    if "circle" in t and r is not None:
        if _asks(t, "area"):
            return _sol("geometry", text, "A = π · r²", [f"r = {fmt(r, unit)}"], f"A = π × {fmt(r)}²",
                        f"{fmt(math.pi * r * r, u2)} (exactly {sp.pretty(sp.pi * sp.nsimplify(r) ** 2)})")
        if _asks(t, "circumference", "perimeter"):
            return _sol("geometry", text, "C = 2 · π · r", [f"r = {fmt(r, unit)}"], f"C = 2 × π × {fmt(r)}",
                        fmt(2 * math.pi * r, unit))
    if "sphere" in t and r is not None:
        if _asks(t, "volume"):
            return _sol("geometry", text, "V = (4/3) · π · r³", [f"r = {fmt(r, unit)}"], f"V = 4/3 × π × {fmt(r)}³",
                        fmt(4 / 3 * math.pi * r ** 3, u3))
        if _asks(t, "surface area", "area"):
            return _sol("geometry", text, "A = 4 · π · r²", [f"r = {fmt(r, unit)}"], f"A = 4 × π × {fmt(r)}²",
                        fmt(4 * math.pi * r * r, u2))
    h = _measure(t, "height", "h", "tall")
    if ("cylinder" in t or "cone" in t) and r is not None and h is not None and _asks(t, "volume"):
        cone = "cone" in t
        v = (1 / 3 if cone else 1) * math.pi * r * r * h
        f = "V = (1/3) · π · r² · h" if cone else "V = π · r² · h"
        return _sol("geometry", text, f, [f"r = {fmt(r, unit)}", f"h = {fmt(h, unit)}"], f.replace("V = ", "V = ").replace("r²", f"{fmt(r)}²").replace("h", fmt(h)),
                    fmt(v, u3))
    if _asks(t, "hypotenuse") or ("right triangle" in t and _asks(t, "third side", "missing side", "other side")):
        legs = _numbers(re.sub(r"\b(?:90|right)\b", "", t))[:2]
        if len(legs) == 2:
            a, b = legs
            c = math.hypot(a, b)
            exact = sp.sqrt(sp.nsimplify(a) ** 2 + sp.nsimplify(b) ** 2)
            return _sol("geometry", text, "c = √(a² + b²)  (Pythagoras)", [f"a = {fmt(a)}", f"b = {fmt(b)}"],
                        f"c = √({fmt(a)}² + {fmt(b)}²) = √{fmt(a * a + b * b)}", fmt(c, unit) + ("" if exact.is_Integer else f" (exactly {exact})"),
                        f"{fmt(a)}² + {fmt(b)}² = {fmt(c)}² ✓")
    if ("rectangle" in t or "square" in t) and _asks(t, "area", "perimeter"):
        side = _measure(t, "side")
        w, l_ = _measure(t, "width", "wide", "breadth"), _measure(t, "length", "long")
        if "square" in t and side is not None:
            w = l_ = side
        if w is None or l_ is None:
            nums = _numbers(t)[:2]
            if len(nums) == 2:
                l_, w = nums
            elif len(nums) == 1 and "square" in t:
                l_ = w = nums[0]
        if w is not None and l_ is not None:
            if _asks(t, "area"):
                return _sol("geometry", text, "A = length × width", [f"length = {fmt(l_, unit)}", f"width = {fmt(w, unit)}"],
                            f"A = {fmt(l_)} × {fmt(w)}", fmt(l_ * w, u2))
            return _sol("geometry", text, "P = 2 · (length + width)", [f"length = {fmt(l_, unit)}", f"width = {fmt(w, unit)}"],
                        f"P = 2 × ({fmt(l_)} + {fmt(w)})", fmt(2 * (l_ + w), unit))
    if "triangle" in t and _asks(t, "area"):
        b, hh = _measure(t, "base"), _measure(t, "height", "h")
        if b is not None and hh is not None:
            return _sol("geometry", text, "A = ½ · base · height", [f"base = {fmt(b, unit)}", f"height = {fmt(hh, unit)}"],
                        f"A = 0.5 × {fmt(b)} × {fmt(hh)}", fmt(0.5 * b * hh, u2))
    return None


def trigonometry(text: str, t: str) -> Solution | None:
    # "sin 30 degrees" is plain arithmetic (reasoning.arithmetic); this reads the English forms: "sin of 30°", "cosine of 60 degrees"
    m = re.search(rf"\b(?:(sin|cos|tan)\s+of|(sine|cosine|tangent)(?:\s+of)?)\s*\(?\s*({NUM})\s*(?:°|deg|degrees?)\)?", t)
    if not m:
        return None
    fn = m.group(1) or {"sine": "sin", "cosine": "cos", "tangent": "tan"}[m.group(2)]
    deg = _num(m.group(3))
    exact = getattr(sp, fn)(sp.rad(sp.nsimplify(deg)))
    exact = sp.nsimplify(sp.simplify(exact))
    if exact is sp.zoo:
        return _sol("trigonometry", text, f"{fn}(θ), θ in degrees", [f"θ = {fmt(deg)}°"], f"{fn}({fmt(deg)}°)", "undefined (tan of an odd multiple of 90°)")
    approx = float(exact)
    shown = re.sub(r"sqrt\((\d+)\)", r"√\1", str(exact)) if exact.is_rational or exact.atoms(sp.Pow) else fmt(approx)
    answer = shown if shown == fmt(approx) else f"{shown} ≈ {fmt(approx)}"
    return _sol("trigonometry", text, f"{fn}(θ) with θ = {fmt(deg)}° = {sp.rad(sp.nsimplify(deg))} rad", [f"θ = {fmt(deg)}°"],
                f"{fn}({sp.rad(sp.nsimplify(deg))})", answer)


# ---------------------------------------------------------------- two things, their total and their difference

def sum_and_difference(text: str, t: str) -> Solution | None:
    """"A bat and a ball cost 1.10 in total. The bat costs 1.00 more than the ball. How much is the ball?" → 0.05.

    The quick answer (1.10 − 1.00 = 0.10) is the classic trap: then the bat is 1.10 and the total 1.20."""
    cur = r"(?:[$₹€£]|rs\.?\s*)?"
    both = re.search(rf"(?:an? |the )?(\w+) and (?:an? |the )?(\w+) (?:cost|costs|together cost|weigh|add up to) (?:a total of )?{cur}({NUM})", t)
    more = re.search(rf"(?:the )?(\w+) (?:costs|is|weighs) {cur}({NUM}) (?:more|greater|heavier) than (?:the )?(\w+)", t)
    asked = re.search(r"how much (?:is|does|did|do) (?:the )?(\w+)|what (?:is|does) (?:the )?(\w+) cost|(?:the )?(\w+) costs? how much", t)
    if not (both and more and asked):
        return None
    a, b = both.group(1), both.group(2)
    big, small = more.group(1), more.group(3)
    want = next(g for g in asked.groups() if g)
    if {big, small} != {a, b} or want not in (a, b):
        return None
    total, diff = sp.nsimplify(both.group(3).replace(",", "")), sp.nsimplify(more.group(2).replace(",", ""))
    x = (total - diff) / 2
    y = x + diff
    cents = "." in both.group(3) + more.group(2)
    show = (lambda v: f"{float(v):,.2f}") if cents else (lambda v: fmt(float(v)))
    ans = x if want == small else y
    steps = [f"let the {small} cost x, so the {big} costs x + {show(diff)}",
             f"together: x + (x + {show(diff)}) = {show(total)}  →  2x = {show(total - diff)}",
             f"x = {show(x)}, so the {small} costs {show(x)} and the {big} {show(y)}"]
    if want == small:
        steps.append(f"(the quick answer {show(total - diff)} is wrong: the {big} would then be {show(total)} and the total "
                     f"{show(total - diff + total)})")
    return Solution("word_problem", text, show(ans), steps,
                    check=f"{show(y)} + {show(x)} = {show(total)} ✓ and {show(y)} − {show(x)} = {show(diff)} ✓", confidence=0.97)


# ---------------------------------------------------------------- entry point

TRIGGERS = re.compile(
    r"\b(?:acceleration|accelerat\w*|velocity|speed|how fast|how far|distance|fall|falls|dropped|force|kinetic|potential|"
    r"momentum|work|power|energy|density|pressure|wavelength|weight|current|voltage|resistance|ohm|watts?|kwh|ph|poh|"
    r"moles?|molar|molarity|molecular|grams|payment|emi|instal?lment|invest|save|deposit|cagr|growth|z[ -]?score|"
    r"standard score|probability|chance|mean|average|circle|sphere|cylinder|cone|hypotenuse|triangle|rectangle|square|"
    r"sin|cos|tan|sine|cosine|tangent|how long|costs?|more than)\b|°")


def solve(text: str) -> Solution | None:
    """A field-specific problem in plain English, solved with steps; None when it isn't one (so others try)."""
    t = " " + text.lower().replace("’", "'") + " "
    if len(text) > 400 or not TRIGGERS.search(t):  # each solver below needs its own quantities ("molar mass of water" has none)
        return None
    try:
        qs = quantities(text)
        for fn in (lambda: sum_and_difference(text, t), lambda: trigonometry(text, t), lambda: chemistry(text, t, qs), lambda: electrical(text, t, qs),
                   lambda: finance(text, t, qs), lambda: cagr(text, t), lambda: statistics(text, t),
                   lambda: geometry(text, t), lambda: physics(text, t, qs)):
            sol = fn()
            if sol:
                return sol
    except (ValueError, ZeroDivisionError, OverflowError, TypeError, AttributeError):
        return None
    return None
