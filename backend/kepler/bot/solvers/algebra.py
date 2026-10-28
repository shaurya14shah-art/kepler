"""Algebra in plain English: equations, systems, inequalities, absolute values, factoring and expanding, vertex,
discriminant, evaluating an expression, and simple linear word problems, each solved exactly (sympy) with steps.

    "what are the roots of x^2 - 5x + 6 = 0"   → x = 2 or x = 3
    "x + y = 10 and x - y = 4"                 → x = 7, y = 3
    "what x values make 4 - 2x > 10 true"      → x < -3

Chatter around the problem is tolerated. Anything that isn't one of these problems (Kepler commands, definition
questions) returns None.
"""
import math
import re

import sympy as sp
from sympy.parsing.sympy_parser import convert_xor, parse_expr, standard_transformations

from ..fields import money
from ..reasoning import Solution
from ..reasoning import fmt as _rfmt

CONF = 0.96
FUNCS = {"sqrt": "sqrt", "abs": "Abs"}
LETTERS = {c: sp.Symbol(c, real=True) for c in "abcdefghjklmnpqrstuvwxyz"}
_TRANS = standard_transformations + (convert_xor,)
NUMWORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
            "ten": 10, "twice": 2, "double": 2, "thrice": 3, "triple": 3}


class _Bad(Exception):
    pass


# ---------------------------------------------------------------- text → sympy

def _clean(text: str) -> str:
    t = text.lower()
    for a, b in (("²", "^2"), ("³", "^3"), ("−", "-"), ("–", "-"), ("×", "*"), ("÷", "/"), ("≤", "<="), ("≥", ">="),
                 ("=<", "<="), ("=>", ">="), ("**", "^"), ("·", "*")):
        t = t.replace(a, b)
    t = re.sub(r"\b[fgh]\s*\(\s*x\s*\)\s*=", "y =", t)
    t = re.sub(r"(\d),(\d{3})\b", r"\1\2", t)
    return t


_TOK = re.compile(r"\d+(?:\.\d+)?|[a-z]+|<=|>=|[+\-*/^()=<>|]|\s+|.", re.S)
_OPS = set("+-*/^()=<>|") | {"<=", ">="}


def _segments(t: str) -> list[str]:
    """Runs of math-looking tokens: numbers, single letters (or letter runs like xy), operators."""
    segs, cur = [], []

    def flush():
        s = "".join(cur).strip()
        if s:
            segs.append(s)
        cur.clear()

    toks = _TOK.findall(t)
    for i, tok in enumerate(toks):
        prev = toks[i - 1] if i else " "
        nxt = toks[i + 1] if i + 1 < len(toks) else " "
        if tok.isspace():
            cur.append(tok)
        elif tok in _OPS or tok[0].isdigit():
            cur.append(tok)
        elif tok.isalpha() and (tok in FUNCS or len(tok) == 1 or (
                len(tok) <= 3 and (prev[-1].isdigit() or prev in _OPS or nxt in ("^", "(")))):
            cur.append(tok)
        else:
            flush()
    flush()
    out = []
    for s in segs:
        s = s.strip()
        if s.endswith("."):
            s = s[:-1]
        # a run that is only words (no digit, no operator) is English, e.g. "a", "x y"
        if any(c.isdigit() for c in s) or any(c in "+-*/^=<>|" for c in s):
            out.append(s.strip())
    return out


def _prep(s: str) -> str:
    s = re.sub(r"\|([^|]+)\|", r"abs(\1)", s)
    toks = re.findall(r"\d+(?:\.\d+)?|[a-z]+|\S", s)
    out: list[str] = []
    for tok in toks:
        if tok.isalpha() and tok not in FUNCS:
            parts = list(tok)
        elif tok.isalpha():
            parts = [FUNCS[tok]]
        else:
            parts = [tok]
        for p in parts:
            if out:
                prev = out[-1]
                prev_val = prev[-1].isalnum() or prev == ")"
                is_fn = prev in FUNCS.values()
                if prev_val and not is_fn and (p[0].isalnum() or p == "(") and not (p[0].isdigit() and prev[-1].isdigit()):
                    out.append("*")
            out.append(p)
    return "".join(out)


def _parse(s: str):
    s = s.strip()
    if not s or re.search(r"[=<>]", s):
        raise _Bad(s)
    if s.count("(") != s.count(")"):
        raise _Bad(s)
    try:
        e = parse_expr(_prep(s), local_dict={**LETTERS, "Abs": sp.Abs, "sqrt": sp.sqrt}, transformations=_TRANS,
                       evaluate=True)
    except Exception as exc:  # noqa: BLE001
        raise _Bad(s) from exc
    if not isinstance(e, sp.Expr):
        raise _Bad(s)
    return sp.nsimplify(e, rational=True) if e.has(sp.Float) else e


def _rel(s: str):
    m = re.match(r"^(.*?)(<=|>=|=|<|>)(.*)$", s)
    if not m or re.search(r"[=<>]", m.group(3)):
        raise _Bad(s)
    return _parse(m.group(1)), m.group(2), _parse(m.group(3))


# ---------------------------------------------------------------- formatting

def pretty(e) -> str:
    s = _rfmt(e) if not isinstance(e, str) else e
    s = re.sub(r"(\d)·(?=[a-zA-Z(√|])", r"\1", s)
    s = re.sub(r"(?<=[a-z)])·(?=[a-z(√])", "", s)
    while "Abs(" in s:
        i = s.index("Abs(")
        depth, j = 0, i + 3
        for j in range(i + 3, len(s)):
            depth += {"(": 1, ")": -1}.get(s[j], 0)
            if depth == 0:
                break
        s = s[:i] + "|" + s[i + 4:j] + "|" + s[j + 1:]
    return s


def _sub(a, b) -> str:
    """'a - b' with the sign of b folded in."""
    return f"{pretty(a)} - {pretty(b)}" if b >= 0 else f"{pretty(a)} + {pretty(-b)}"


def ex(x) -> str:
    """Exact value plus a decimal when it adds something: 5/2 = 2.5, 1/3 ≈ 0.3333, 2 + √3 ≈ 3.732."""
    x = sp.nsimplify(sp.sympify(x))
    if x.is_Integer:
        return str(int(x))
    if x.is_Rational:
        q = int(x.q)
        while q % 2 == 0:
            q //= 2
        while q % 5 == 0:
            q //= 5
        dec = f"{float(x):.10g}" if q == 1 else f"{float(x):.4g}"
        return f"{x.p}/{x.q} {'=' if q == 1 else '≈'} {dec}"
    s = sp.sstr(x).replace("**", "^").replace("*", "·").replace("sqrt", "√").replace("I", "i")
    s = re.sub(r"(\d)·(?=[a-zA-Z(√])", r"\1", s)
    s = re.sub(r"√\((\d+)\)", r"√\1", s)
    if x.is_real:
        return f"{s} ≈ {float(x):.4g}"
    re_, im_ = x.as_real_imag()
    if re_.is_Rational and im_.is_Rational:
        return s
    return f"{s} ≈ {float(re_):.4g} {'+' if float(im_) >= 0 else '-'} {abs(float(im_)):.4g}i"


def _short(x) -> str:
    x = sp.nsimplify(sp.sympify(x))
    if x.is_Integer:
        return str(int(x))
    if x.is_Rational:
        return f"{x.p}/{x.q}"
    return ex(x).split(" ≈ ")[0]


def _sol(kind, problem, steps, answer, check="") -> Solution:
    return Solution(kind, problem, answer, steps + [f"result: {answer}"], check=check, confidence=CONF)


# ---------------------------------------------------------------- solvers

def _equation(problem, lhs, rhs) -> Solution | None:
    expr = sp.together(lhs - rhs)
    syms = sorted(expr.free_symbols, key=str)
    if len(syms) != 1:
        return None
    x = syms[0]
    steps = [f"equation: {pretty(lhs)} = {pretty(rhs)}"]
    if expr.has(sp.Abs):
        return _abs_eq(problem, lhs, rhs, x)
    num, den = sp.fraction(sp.together(expr))
    num = sp.expand(num)
    if den != 1:
        steps.append(f"multiply both sides by {pretty(den)} (x ≠ excluded values): {pretty(num)} = 0")
    if not num.is_polynomial(x):
        sols = sp.solve(sp.Eq(lhs, rhs), x)
        if not sols:
            return None
        sols = [s for s in sols if s.is_real]
        steps.append("rule: isolate " + str(x))
    else:
        poly = sp.Poly(num, x)
        deg = poly.degree()
        if deg == 0:
            ans = "no solution" if num != 0 else f"every real {x} is a solution"
            return _sol("algebra", problem, steps + ["both sides simplify to constants"], ans)
        if deg == 1:
            a, b = poly.all_coeffs()
            steps.append(f"rearrange: {pretty(a * x)} = {pretty(-b)}")
            steps.append(f"divide by {pretty(a)}: {x} = {_short(-b / a)}")
            sols = [-b / a]
        elif deg == 2:
            a, b, c = poly.all_coeffs()
            d = b ** 2 - 4 * a * c
            steps += [f"formula: {x} = (-b ± √(b² - 4ac)) / 2a",
                      f"known: a = {pretty(a)}, b = {pretty(b)}, c = {pretty(c)}",
                      f"discriminant: b² - 4ac = {_sub(b ** 2, 4 * a * c)} = {pretty(d)}",
                      f"substitute: {x} = ({pretty(-b)} ± √{pretty(d)}) / {pretty(2 * a)}"]
            z = sp.Symbol("z")
            sols = sorted(set(sp.solve(num.subs(x, z), z)), key=lambda s: (float(sp.re(s)), float(sp.im(s))))
            if d < 0:
                ans = "no real roots; complex roots " + " and ".join(f"{x} = {ex(s)}" for s in sols)
                return _sol("algebra", problem, steps, ans)
        else:
            steps.append(f"factor: {pretty(sp.factor(num))} = 0")
            sols = sorted((s for s in sp.solve(num, x) if s.is_real), key=lambda s: float(s))
    sols = [s for s in sols if den == 1 or sp.simplify(den.subs(x, s)) != 0]
    if not sols:
        return _sol("algebra", problem, steps, "no real solution")
    ans = " or ".join(f"{x} = {ex(s)}" for s in sols)
    chk = "; ".join(f"{x} = {_short(s)}: left {_short(sp.simplify(lhs.subs(x, s)))}, "
                    f"right {_short(sp.simplify(rhs.subs(x, s)))}" for s in sols)
    return _sol("algebra", problem, steps, ans, "check: " + chk)


def _abs_eq(problem, lhs, rhs, x) -> Solution | None:
    if not isinstance(lhs, sp.Abs):
        lhs, rhs = rhs, lhs
    if not isinstance(lhs, sp.Abs) or rhs.has(sp.Abs) or rhs.free_symbols:
        sols = sp.solve(sp.Eq(lhs, rhs), x)
        if not sols:
            return _sol("algebra", problem, ["solve both cases of the absolute value"], "no solution")
        return _sol("algebra", problem, ["split into cases inside the absolute value"],
                    " or ".join(f"{x} = {ex(s)}" for s in sorted(sols, key=float)))
    inner = lhs.args[0]
    steps = [f"equation: |{pretty(inner)}| = {pretty(rhs)}"]
    if rhs < 0:
        return _sol("algebra", problem, steps + ["an absolute value is never negative"], "no solution")
    steps.append(f"rule: |A| = c means A = c or A = -c → {pretty(inner)} = {pretty(rhs)} or {pretty(inner)} = "
                 f"{pretty(-rhs)}")
    sols = sorted(set(sp.solve(inner - rhs, x) + sp.solve(inner + rhs, x)), key=float)
    ans = " or ".join(f"{x} = {ex(s)}" for s in sols)
    chk = "; ".join(f"|{pretty(inner)}| at {x} = {_short(s)} is {_short(abs(inner.subs(x, s)))}" for s in sols)
    return _sol("algebra", problem, steps, ans, "check: " + chk)


def _set_text(s, x) -> str:
    if s == sp.S.EmptySet:
        return "no solution"
    if s == sp.S.Reals:
        return f"all real {x}"
    parts = s.args if isinstance(s, sp.Union) else [s]
    out = []
    for p in parts:
        if isinstance(p, sp.FiniteSet):
            out += [f"{x} = {_short(v)}" for v in p]
            continue
        lo, hi = p.start, p.end
        lop = "<" if p.left_open else "≤"
        hip = "<" if p.right_open else "≤"
        if lo == -sp.oo:
            out.append(f"{x} {hip} {_short(hi)}")
        elif hi == sp.oo:
            out.append(f"{x} {'>' if p.left_open else '≥'} {_short(lo)}")
        else:
            out.append(f"{_short(lo)} {lop} {x} {hip} {_short(hi)}")
    return " or ".join(out)


_SYM = {"<": "<", ">": ">", "<=": "≤", ">=": "≥"}
_FLIP = {"<": ">", ">": "<", "<=": ">=", ">=": "<="}


def _inequality(problem, lhs, op, rhs) -> Solution | None:
    syms = (lhs - rhs).free_symbols
    if len(syms) != 1:
        return None
    x = next(iter(syms))
    rel = {"<": sp.Lt, ">": sp.Gt, "<=": sp.Le, ">=": sp.Ge}[op](lhs, rhs)
    steps = [f"inequality: {pretty(lhs)} {_SYM[op]} {pretty(rhs)}"]
    expr = sp.expand(lhs - rhs)
    if not expr.has(sp.Abs) and expr.is_polynomial(x) and sp.degree(expr, x) == 1:
        a = expr.coeff(x, 1)
        b = expr - a * x
        steps.append(f"rearrange: {pretty(a * x)} {_SYM[op]} {pretty(-b)}")
        nop = op if a > 0 else _FLIP[op]
        steps.append(f"divide by {pretty(a)}" + (" (negative, so the sign flips)" if a < 0 else "")
                     + f": {x} {_SYM[nop]} {_short(-b / a)}")
    elif expr.has(sp.Abs):
        steps.append("rule: |A| < c means -c < A < c; |A| > c means A < -c or A > c")
    sol = sp.solveset(rel, x, sp.S.Reals)
    ans = _set_text(sol, x)
    chk = ""
    if isinstance(sol, sp.Interval):
        pt = sol.start + 1 if sol.end == sp.oo else (sol.end - 1 if sol.start == -sp.oo else (sol.start + sol.end) / 2)
        chk = f"check: {x} = {_short(pt)} gives {pretty(lhs.subs(x, pt))} {_SYM[op]} {pretty(rhs.subs(x, pt))} ✓"
    return _sol("algebra", problem, steps, ans, chk)


def _system(problem, eqs) -> Solution | None:
    exprs = [lhs - rhs for lhs, rhs in eqs]
    syms = sorted(set().union(*(e.free_symbols for e in exprs)), key=str)
    if not 2 <= len(syms) <= 3 or len(exprs) != len(syms):
        return None
    if any(not e.is_polynomial(*syms) or sp.Poly(e, *syms).total_degree() != 1 for e in exprs):
        return None
    steps = [f"equation {i + 1}: {pretty(lhs)} = {pretty(rhs)}" for i, (lhs, rhs) in enumerate(eqs)]
    A, bvec = sp.linear_eq_to_matrix(exprs, syms)
    det = A.det()
    steps.append(f"rule: elimination (matrix determinant {pretty(det)})")
    res = sp.linsolve((A, bvec), syms)
    if not res:
        return _sol("algebra", problem, steps, "no solution (the equations are inconsistent)")
    vals = list(res)[0]
    if any(v.free_symbols for v in vals):
        return _sol("algebra", problem, steps, "infinitely many solutions (the equations are dependent)")
    if len(syms) == 2:
        x, y = syms
        sx = sp.solve(exprs[0], x)
        if sx:
            sub = sp.expand(exprs[1].subs(x, sx[0]))
            steps.append(f"substitute: from equation 1, {x} = {pretty(sx[0])}; into equation 2: {pretty(sub)} = 0")
    ans = ", ".join(f"{s} = {ex(v)}" for s, v in zip(syms, vals))
    chk = "; ".join(f"eq {i + 1}: {_short(lhs.subs(dict(zip(syms, vals))))} = {_short(rhs.subs(dict(zip(syms, vals))))}"
                    for i, (lhs, rhs) in enumerate(eqs))
    return _sol("algebra", problem, steps, ans, "check: " + chk)


def _quadratic_of(seg):
    s = re.sub(r"^\s*y\s*=", "", seg)
    if "=" in s:
        lhs, op, rhs = _rel(s)
        if op != "=":
            return None
        e = sp.expand(lhs - rhs)
    else:
        e = sp.expand(_parse(s))
    syms = e.free_symbols
    if len(syms) != 1:
        return None
    x = next(iter(syms))
    if not e.is_polynomial(x) or sp.degree(e, x) != 2:
        return None
    a, b, c = sp.Poly(e, x).all_coeffs()
    return e, x, a, b, c


def _vertex(problem, seg) -> Solution | None:
    q = _quadratic_of(seg)
    if not q:
        return None
    e, x, a, b, c = q
    h = -b / (2 * a)
    k = e.subs(x, h)
    steps = [f"formula: vertex at {x} = -b / 2a, then y = f(-b / 2a)",
             f"known: a = {pretty(a)}, b = {pretty(b)}, c = {pretty(c)}",
             f"substitute: {x} = {pretty(-b)} / {pretty(2 * a)} = {_short(h)}; y = {_short(k)}"]
    kind = "minimum" if a > 0 else "maximum"
    ans = f"vertex ({_short(h)}, {_short(k)}), a {kind}"
    chk = f"check: vertex form y = {pretty(a)}({x} - {_short(h)})² + {_short(k)} expands to {pretty(e)}"
    chk = chk.replace("- -", "+ ").replace("+ -", "- ")
    return _sol("algebra", problem, steps, ans, chk)


def _discriminant(problem, seg) -> Solution | None:
    q = _quadratic_of(seg)
    if not q:
        return None
    e, x, a, b, c = q
    d = b ** 2 - 4 * a * c
    steps = ["formula: D = b² - 4ac", f"known: a = {pretty(a)}, b = {pretty(b)}, c = {pretty(c)}",
             f"substitute: D = ({pretty(b)})² - 4·({pretty(a)})·({pretty(c)}) = {pretty(d)}"]
    if d > 0:
        nature = "two distinct real roots" + (" (rational)" if sp.sqrt(d).is_Rational else " (irrational)")
    elif d == 0:
        nature = "one repeated real root"
    else:
        nature = "no real roots (two complex conjugate roots)"
    return _sol("algebra", problem, steps, f"D = {pretty(d)}: {nature}")


def _factor(problem, e) -> Solution | None:
    f = sp.factor(e)
    steps = [f"expression: {pretty(e)}"]
    syms = sorted(e.free_symbols, key=str)
    if len(syms) == 1 and e.is_polynomial(syms[0]) and sp.degree(e, syms[0]) == 2:
        a, b, c = sp.Poly(e, syms[0]).all_coeffs()
        steps.append(f"rule: find two numbers with product a·c = {pretty(a * c)} and sum b = {pretty(b)}")
    elif len(e.as_ordered_terms()) == 2:
        steps.append("rule: difference of squares A² - B² = (A - B)(A + B)")
    steps.append(f"factor: {pretty(f)}")
    if f == e:
        return _sol("algebra", problem, steps, f"{pretty(e)} does not factor over the rationals")
    return _sol("algebra", problem, steps, pretty(f), f"check: expanding gives {pretty(sp.expand(f))}")


def _expand(problem, e) -> Solution:
    x = sp.expand(e)
    steps = [f"expression: {pretty(e)}", "rule: distribute every term (FOIL for two binomials)", f"expand: {pretty(x)}"]
    return _sol("algebra", problem, steps, pretty(x), f"check: factoring back gives {pretty(sp.factor(x))}")


def _evaluate(problem, e, vals) -> Solution | None:
    if not e.free_symbols or not e.free_symbols <= set(vals):
        return None
    known = ", ".join(f"{k} = {_short(v)}" for k, v in vals.items() if k in e.free_symbols)
    sub = pretty(e)
    for k, v in vals.items():
        sub = re.sub(str(k), f"({_short(v)})", sub)
    sub = re.sub(r"\)\(", ")·(", sub)
    r = sp.simplify(e.subs(vals))
    if r.has(sp.zoo, sp.nan):
        return _sol("algebra", problem, [f"substitute: {sub}"], "undefined (division by zero)")
    steps = [f"formula: {pretty(e)}", f"known: {known}", f"substitute: {sub}"]
    return _sol("algebra", problem, steps, ex(r))


# ---------------------------------------------------------------- word problems

def _n(s: str) -> float:
    return float(NUMWORDS.get(s, s) if s in NUMWORDS else s)


def _plan(t: str) -> Solution | None:
    m_rate = re.search(r"\$\s*(\d+(?:\.\d+)?)\s*(?:per|a|an|for each|each)\s+(?!month|year|week|day)([a-z]+)", t)
    m_fix = re.search(r"\$\s*(\d+(?:\.\d+)?)\s*(?:a|per|each|every)\s+(month|year|week|day)", t)
    if not m_fix:
        m_fix = re.search(r"\$\s*(\d+(?:\.\d+)?)\s*(?:flat|fixed|base|up ?front|fee)", t)
    m_bud = re.search(r"\$\s*(\d+(?:\.\d+)?)\s*(?:(?:monthly|weekly|yearly|daily|total|spending)\s+)?(?:budget|limit|total|to spend)|(?:budget|spend|afford|has|have|only)"
                      r"[^$]{0,20}\$\s*(\d+(?:\.\d+)?)", t)
    if not (m_rate and m_fix and m_bud) or m_rate.start() == m_fix.start():
        return None
    F, r = float(m_fix.group(1)), float(m_rate.group(1))
    B = float(m_bud.group(1) or m_bud.group(2))
    unit = m_rate.group(2)
    if r <= 0 or B < F:
        return None
    exact = sp.nsimplify((sp.Rational(str(B)) - sp.Rational(str(F))) / sp.Rational(str(r)))
    n = math.floor(exact)
    steps = [f"formula: {money(F)} + {money(r)}·n ≤ {money(B)}", f"known: fixed {money(F)}, {money(r)} per {unit}, "
             f"budget {money(B)}", f"substitute: n ≤ ({money(B)} - {money(F)}) / {money(r)} = {_short(exact)}"]
    units = unit if unit.endswith("s") or n == 1 else unit + "s"
    ans = f"at most {n} {units}"
    return _sol("algebra", t, steps, ans, f"check: {money(F)} + {money(r)} × {n} = ${money(F + r * n)} ≤ ${money(B)}")


def _rectangle(t: str) -> Solution | None:
    if "rectangle" not in t and "rectangular" not in t:
        return None
    m = re.search(r"length (?:of (?:a|the) (?:rectangle|rectangular \w+) )?is (\d+(?:\.\d+)?|[a-z]+) (?:m |cm |ft |units )?(more|less|longer|shorter) than "
                  r"(?:(twice|double|triple|thrice|\w+ times|\d+ times) )?(?:the |its )?width", t)
    p = re.search(r"perimeter (?:is |of )?(\d+(?:\.\d+)?)\s*([a-z]*)", t)
    if not m or not p:
        return None
    d = sp.Rational(str(_n(m.group(1))))
    if m.group(2) in ("less", "shorter"):
        d = -d
    k = m.group(3) or "1 times"
    k = sp.Rational(str(_n(k.split()[0])))
    P = sp.Rational(p.group(1))
    unit = p.group(2) if p.group(2) in ("m", "cm", "mm", "km", "ft", "in", "inches", "feet", "units", "yd") else ""
    w = (P - 2 * d) / (2 * k + 2)
    L = k * w + d
    if w <= 0 or L <= 0:
        return None
    u = f" {unit}" if unit else ""
    steps = [f"formula: P = 2L + 2W with L = {_short(k)}W {'+' if d >= 0 else '-'} {_short(abs(d))}",
             f"known: P = {_short(P)}{u}",
             f"substitute: 2({_short(k)}W {'+' if d >= 0 else '-'} {_short(abs(d))}) + 2W = {_short(P)} → "
             f"{_short(2 * k + 2)}W = {_short(P - 2 * d)} → W = {_short(w)}"]
    ans = f"width {_short(w)}{u}, length {_short(L)}{u}"
    return _sol("algebra", t, steps, ans, f"check: 2({_short(L)}) + 2({_short(w)}) = {_short(2 * L + 2 * w)}")


# ---------------------------------------------------------------- dispatch

_DEFN = re.compile(r"^\s*(?:what|whats|what's)\s+(?:is|are|'s)\s+(?:a|an|the)?\s*[a-z ]+\??\s*$")


def solve(text: str) -> Solution | None:
    if len(text) > 400:
        return None
    t = _clean(text)
    if _DEFN.match(t):
        return None
    problem = text.strip()
    for wp in (_plan, _rectangle):
        sol = wp(t)
        if sol:
            sol.problem = problem
            return sol
    segs = _segments(t)
    if not segs:
        return None
    try:
        return _dispatch(problem, t, segs)
    except _Bad:
        return None


def _dispatch(problem, t, segs) -> Solution | None:
    has = lambda *w: any(re.search(rf"\b{x}", t) for x in w)  # noqa: E731
    if has("vertex", "turning point"):
        for s in segs:
            r = _vertex(problem, s)
            if r:
                return r
        return None
    if has("discriminant", "nature of the roots", "how many real roots", "how many roots", "how many solutions"):
        for s in segs:
            r = _discriminant(problem, s)
            if r:
                return r
        return None
    if has("factor", "factorise", "factorize"):
        for s in segs:
            if "=" not in s and "<" not in s and ">" not in s:
                e = _parse(s)
                if e.free_symbols and len(sp.Add.make_args(sp.expand(e))) > 1:
                    return _factor(problem, sp.expand(e))
    if has("expand", "multiply out", "simplify", "foil"):
        for s in segs:
            if not re.search(r"[=<>]", s):
                e = _parse(s)
                if e.free_symbols:
                    return _expand(problem, e)
    # evaluation: an expression plus assignments "x = 2", "a = 5 and b = -3"
    assign = {}
    rest = []
    for s in segs:
        for part in re.split(r",|;", s):
            part = part.strip()
            m = re.fullmatch(r"([a-z])\s*=\s*(-?\s*\d+(?:\.\d+)?(?:\s*/\s*\d+)?)", part)
            if m:
                assign[LETTERS[m.group(1)]] = sp.nsimplify(m.group(2).replace(" ", ""), rational=True)
            elif part:
                rest.append(part)
    exprs = [s for s in rest if not re.search(r"[=<>]", s)]
    if assign and exprs and has(r"at", "when", "for", "if", "where", "with", "evaluate", "plug", "value", "substitut"):
        e = _parse(exprs[0])
        r = _evaluate(problem, e, assign)
        if r:
            return r
    # equations, systems, inequalities
    rels = []
    for s in segs:
        for part in re.split(r"[,;]", s):
            if re.search(r"[=<>]", part):
                rels.append(part.strip())
    if not rels:
        return None
    parsed = [_rel(r) for r in rels]
    eqs = [(lhs, rhs) for lhs, op, rhs in parsed if op == "="]
    ineqs = [(lhs, op, rhs) for lhs, op, rhs in parsed if op != "="]
    if ineqs and not eqs and len(ineqs) == 1:
        return _inequality(problem, *ineqs[0])
    if len(eqs) >= 2 and not ineqs:
        return _system(problem, eqs)
    if len(eqs) == 1 and not ineqs:
        return _equation(problem, *eqs[0])
    return None
