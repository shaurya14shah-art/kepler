"""Kepler's reasoning engine for maths: question → parsed problem → exact answer, worked steps and a check.

No language model. Each question is matched to a problem type, parsed into an exact expression (sympy), solved
deterministically, and explained step by step; answers are verified where possible (equations are substituted
back, derivatives of integrals are compared, percentages are recomputed).

What it handles
  arithmetic         12*(3+4)^2 / 7 · 2^10 · 17 mod 5 · 5! · sqrt(144) · 3.5e3 · word operators (plus, times, …)
  functions          sin cos tan (radians, or "30 degrees") · log (base 10) · ln · log2 · exp · abs · floor · ceil
  percentages        15% of 200 · 30 is what percent of 120 · change from 120 to 150 · increase 80 by 25%
  statistics         average / mean / median / mode / sum / product / min / max / range / std / variance of a list
  number theory      gcd / lcm of a list · is 97 prime · prime factors of 360
  algebra            solve 2x + 3 = 7 · x^2 - 5x + 6 = 0 · systems (x + y = 10, x - y = 2) · factor · expand · simplify
  calculus           derivative of x^3 sin x · integrate x^2 [from 0 to 3] · limit of sin(x)/x as x approaches 0

Safety: input is tokenised against a whitelist (numbers, operators, known function names, single-letter
variables), sizes are estimated before anything is computed (no 9^9^9), and symbolic work runs with a time limit.
"""
import ast
import math
import re
import threading
import tokenize
from dataclasses import dataclass, field

import sympy as sp
from rich.console import Group
from rich.text import Text
from sympy.parsing.sympy_parser import (convert_xor, implicit_multiplication_application, parse_expr,
                                        standard_transformations)

MAX_LEN = 240           # characters of maths
MAX_DIGITS = 5000       # largest exact result we compute
MAX_STEPS = 14          # worked steps shown for long arithmetic
TIME_LIMIT = 4.0        # seconds for symbolic work (solve, integrate, …)

FUNCS = {"sqrt", "cbrt", "abs", "sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh", "log", "ln",
         "log2", "exp", "factorial", "floor", "ceil", "round"}
CONSTS = {"pi", "e"}
STRONG_WORDS = re.compile(r"\b(solve|derivative|differentiate|integrate|integral|factorial|square root|cube root|"
                          r"plus|minus|times|multiplied by|divided by|to the power|squared|cubed|percent of|gcd|lcm|"
                          r"prime factors|simplify|expand|factori[sz]e)\b")


@dataclass
class Solution:
    kind: str
    problem: str
    answer: str = ""
    steps: list[str] = field(default_factory=list)
    check: str = ""
    ok: bool = True
    confidence: float = 0.99
    # LaTeX for formal write-ups (kepler write / /pdf); empty means "convert the plain text"
    tex_statement: str = ""
    tex_steps: list[str] = field(default_factory=list)
    tex_answer: str = ""

    def decision(self) -> dict:
        return {"decision": "intent", "intent": "math", "confidence": self.confidence,
                "slots": {"kind": self.kind}, "alternatives": []}


class MathError(Exception):
    pass


# ---------------------------------------------------------------- formatting

def fmt(x) -> str:
    if isinstance(x, (list, tuple)):
        return ", ".join(fmt(i) for i in x)
    x = sp.sympify(x)
    if x.is_Rational and not x.is_Integer and set(sp.factorint(x.q)) <= {2, 5} and x.q < 10 ** 12 and abs(x) < 1e15:
        return f"{float(x):,.12g}" if abs(x) >= 10000 else f"{float(x):.12g}"  # 1/4 → 0.25 (exact: it terminates)
    if x.is_Integer:
        s = str(x)
        if len(s.lstrip("-")) > 60:
            return f"{s[:12]}…{s[-6:]} ({len(s.lstrip('-'))} digits)"
        return f"{int(x):,}" if abs(x) >= 10000 else s
    s = sp.sstr(x)
    s = s.replace("**", "^").replace("*", "·").replace("sqrt", "√").replace("pi", "π").replace("log(", "ln(")
    s = re.sub(r"\bE\b", "e", s)
    return re.sub(r"\bI\b", "i", s)


def approx(x) -> str:
    """Decimal value, or '' when the exact form already is one."""
    x = sp.sympify(x)
    if not x.is_number or x.is_Integer or x.has(sp.zoo, sp.oo, sp.nan):
        return ""
    v = sp.N(x, 12)
    if v.is_real:
        f = float(v)
        s = f"{f:.10g}" if abs(f) < 1e15 else sp.sstr(sp.N(x, 10))
    else:
        s = sp.sstr(sp.N(x, 8)).replace("*I", "i")
    return "" if s == fmt(x) else s


def show(x) -> str:
    x = sp.sympify(x)
    if x.is_number and not x.is_real and all(p.is_Rational for p in x.as_real_imag()):
        return fmt(x)  # 2 + 3i is already exact and readable
    a = approx(x)
    return f"{fmt(x)} ≈ {a}" if a else fmt(x)


# ---------------------------------------------------------------- size guard

def _digits(e) -> float:
    """Rough number of decimal digits an expression evaluates to (unevaluated tree; inf when unknowable/huge)."""
    if e.is_Integer or e.is_Rational:
        n = max(abs(e.p), abs(e.q)) if e.is_Rational else abs(e)
        return len(str(n))
    if e.is_Float or e.is_Symbol or e.is_NumberSymbol or not e.args:
        return 1
    if isinstance(e, sp.Pow):
        b, x = e.args
        if _digits(x) > 6:
            return math.inf
        xv = abs(float(x.evalf())) if x.is_number and x.evalf().is_real else 50
        return max(1, _digits(b)) * max(1, xv)
    if isinstance(e, sp.factorial):
        (n,) = e.args
        if _digits(n) > 5:
            return math.inf
        nv = abs(float(n.evalf())) if n.is_number else 50
        return nv * math.log10(max(nv, 2))
    if isinstance(e, sp.Mul):
        return sum(_digits(a) for a in e.args)
    return max(_digits(a) for a in e.args) + 1


def _guard(e):
    d = _digits(e)
    if d > MAX_DIGITS:
        raise MathError("that number is too large to compute exactly"
                        + (f" (about {int(d):,} digits)" if d < 1e15 else ""))


def _timed(fn, *args):
    box: dict = {}

    def run():
        try:
            box["v"] = fn(*args)
        except Exception as e:  # noqa: BLE001 - reported to the user as "couldn't solve"
            box["e"] = e

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(TIME_LIMIT)
    if t.is_alive():
        raise MathError(f"that took longer than {TIME_LIMIT:.0f} s; try a simpler form")
    if "e" in box:
        raise MathError(f"couldn't solve that ({type(box['e']).__name__})")
    return box["v"]


# ---------------------------------------------------------------- text → expression

FILLER = re.compile(r"^(?:(?:hey|hi|ok|so|kepler|please|can you|could you|would you|pls|quickly|tell me|"
                    r"what(?:'s| is| are| does)?|whats|how much is|how much are|calculate|compute|evaluate|"
                    r"work out|find(?: the)?|give me(?: the)?|determine|the value of|value of|answer|the)[\s,:]+)+")
TRAIL = re.compile(r"(?:\s*(?:\?|please|for me|thanks|equals?|=\s*\?|is equal to))+\s*$")

WORDS = [
    (r"\bmultiplied by\b|\btimes\b|×|∙|·", "*"), (r"\bdivided by\b|\bover\b|÷", "/"),
    (r"\bplus\b", "+"), (r"\bminus\b|−|–", "-"), (r"\bto the power of\b|\braised to(?: the power of)?\b|\bpower\b", "^"),
    (r"\bsquared\b", "^2"), (r"\bcubed\b", "^3"), (r"\bmodulo\b|\bmod\b", " mod "), (r"π", "pi"),
    (r"\bsquare root of\b|\broot of\b|√", "sqrt "), (r"\bcube root of\b|∛", "cbrt "),
    (r"\bfactorial of\b", "factorial "), (r"\bnatural log(?:arithm)? of\b", "ln "),
    (r"\blog(?:arithm)? of\b", "log "), (r"\babsolute value of\b", "abs "),
    (r"(\d+(?:\.\d+)?)\s*(?:degrees?|deg|°)", r"(\1*pi/180)"),
]
TOKEN = re.compile(r"\s*(?:(\d+(?:\.\d+)?(?:e[+-]?\d+)?|\.\d+)|([a-z]+)|(\*\*|[-+*/%^(),=!<>]))")


def _words_to_symbols(s: str) -> str:
    s = re.sub(r"(\d),(\d{3})\b", r"\1\2", s)  # 1,000 → 1000
    s = re.sub(r"(\d),(\d{3})\b", r"\1\2", s)
    for pat, rep in WORDS:
        s = re.sub(pat, rep, s)
    # "sqrt 144" / "sin 30" / "factorial 5" → call with the next number or parenthesised group
    s = re.sub(rf"\b({'|'.join(sorted(FUNCS, key=len, reverse=True))})\s+(\d+(?:\.\d+)?|[a-z]\b|\([^()]*\))",
               r"\1(\2)", s)
    s = re.sub(r"(\d+(?:\.\d+)?|\))\s*!", r"factorial(\1)", s)
    s = s.replace(" mod ", " % ")
    return s.strip()


def _tokens(s: str) -> list[str]:
    out, pos = [], 0
    s = s.strip()
    while pos < len(s):
        m = TOKEN.match(s, pos)
        if not m or m.end() == pos:
            raise MathError(f"I can't read '{s[pos:pos + 12].strip()}' as maths")
        num, name, op = m.groups()
        if name and name not in FUNCS and name not in CONSTS and len(name) != 1:
            # "xy" / "2ab": implicit products of single-letter variables are fine
            if not all(ch.isalpha() for ch in name) or len(name) > 3:
                raise MathError(f"I don't know the word '{name}' in maths")
        if num and len(num.split("e")[0].replace(".", "")) > 60:
            raise MathError("numbers longer than 60 digits aren't supported")
        if num and "e" in num and abs(int(num.split("e")[1])) > 300:
            raise MathError("exponents beyond e±300 aren't supported")
        out.append(num or name or op)
        pos = m.end()
    return out


def is_expression(s: str) -> bool:
    try:
        toks = _tokens(s)
    except MathError:
        return False
    names = [t for t in toks if t.isalpha()]
    if any(len(n) > 1 and n not in FUNCS and n not in CONSTS for n in names):
        return False  # multi-letter non-function words → probably English
    ops = [t for t in toks if t in "+-*/%^**()=!<>" or t in FUNCS]
    has_num = any(t[0].isdigit() or t[0] == "." for t in toks)
    return bool(ops) and (has_num or "=" in toks or any(n in FUNCS for n in names))


LOCALS = {"log": lambda x: sp.log(x, 10), "ln": sp.log, "log2": lambda x: sp.log(x, 2), "cbrt": sp.cbrt,
          "e": sp.E, "pi": sp.pi, "abs": sp.Abs, "ceil": sp.ceiling, "floor": sp.floor, "round": lambda x: sp.floor(x + sp.Rational(1, 2)),
          "factorial": sp.factorial, "sqrt": sp.sqrt, "exp": sp.exp, "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
          "asin": sp.asin, "acos": sp.acos, "atan": sp.atan, "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh}
TRANSFORMS = standard_transformations + (implicit_multiplication_application, convert_xor)
# only what the parser's generated code needs: no Python builtins (pow, eval, …), no sympy helpers like var()
GLOBALS = {"__builtins__": {}, **{n: getattr(sp, n) for n in (
    "Symbol", "Integer", "Float", "Rational", "Function", "Add", "Mul", "Pow", "Mod", "factorial", "factorial2")}}


def to_expr(s: str):
    """Whitelisted text → sympy expression (size-checked before evaluation)."""
    toks = _tokens(s)
    if "=" in toks:
        raise MathError("unexpected '='")
    text = " ".join(toks).replace("%", " mod ")
    text = re.sub(r"\bmod\b", "%", text)
    if len(text) > MAX_LEN:
        raise MathError(f"that's longer than {MAX_LEN} characters")
    letters = {t for t in toks if t.isalpha() and t not in FUNCS and t not in CONSTS}
    local = dict(LOCALS)
    for name in letters:
        for ch in name:
            local.setdefault(ch, sp.Symbol(ch))
    try:
        raw = parse_expr(text, local_dict=local, global_dict=dict(GLOBALS), transformations=TRANSFORMS, evaluate=False)
        _guard(raw)
        return parse_expr(text, local_dict=local, global_dict=dict(GLOBALS), transformations=TRANSFORMS)
    except MathError:
        raise
    except (SyntaxError, TypeError, ValueError, AttributeError, NameError, ZeroDivisionError, IndexError, KeyError,
            NotImplementedError, sp.SympifyError, tokenize.TokenError) as e:  # TokenError: a stray '!' ("!5")
        raise MathError("that doesn't look like a complete expression") from e


# ---------------------------------------------------------------- arithmetic with worked steps

OPS = {ast.Add: "+", ast.Sub: "−", ast.Mult: "×", ast.Div: "÷", ast.Pow: "^", ast.Mod: "mod"}
CALLS = {"sqrt": sp.sqrt, "cbrt": sp.cbrt, "abs": sp.Abs, "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
         "asin": sp.asin, "acos": sp.acos, "atan": sp.atan, "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh,
         "log": lambda x: sp.log(x, 10), "ln": sp.log, "log2": lambda x: sp.log(x, 2), "exp": sp.exp,
         "factorial": sp.factorial, "floor": sp.floor, "ceil": sp.ceiling, "round": lambda x: sp.floor(x + sp.Rational(1, 2))}


def _num(text: str):
    return sp.Integer(text) if re.fullmatch(r"\d+", text) else sp.Rational(text)


def arithmetic(expr_text: str, asked: str = "") -> Solution:
    toks = _tokens(expr_text)
    py = " ".join("**" if t == "^" else t for t in toks)
    py = re.sub(r"(\d|\))\s+(\(|[a-z])", r"\1 * \2", py)       # 2(3+4) / 2 pi → explicit ×
    py = re.sub(r"\)\s+(\d)", r") * \1", py)
    try:
        tree = ast.parse(py, mode="eval")
    except SyntaxError as e:
        raise MathError("that doesn't look like a complete expression") from e
    steps: list[str] = []

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            seg = ast.get_source_segment(py, n) or repr(n.value)
            return _num(seg) if "e" not in seg else sp.Rational(sp.Float(seg, 30))
        if isinstance(n, ast.Name) and n.id in CONSTS:
            return sp.pi if n.id == "pi" else sp.E
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = ev(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.BinOp) and type(n.op) in OPS:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, (ast.Div, ast.Mod)) and b == 0:
                raise MathError("division by zero is undefined")
            if isinstance(n.op, ast.Pow):
                _guard(sp.Pow(a, b, evaluate=False))
                if a == 0 and b.is_negative:
                    raise MathError("0 to a negative power is undefined (division by zero)")
            r = {ast.Add: lambda: a + b, ast.Sub: lambda: a - b, ast.Mult: lambda: a * b, ast.Div: lambda: a / b,
                 ast.Pow: lambda: a ** b, ast.Mod: lambda: sp.Mod(a, b)}[type(n.op)]()
            steps.append(f"{fmt(a)} {OPS[type(n.op)]} {fmt(b)} = {show(r)}")
            return r
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in CALLS and len(n.args) == 1 and not n.keywords:
            v = ev(n.args[0])
            name = n.func.id
            if name == "factorial":
                if not (v.is_integer and v >= 0):
                    raise MathError("factorial needs a whole number ≥ 0")
                _guard(sp.factorial(v, evaluate=False))
            if name in ("log", "ln", "log2") and v.is_number and v <= 0:
                raise MathError(f"{name} is only defined for positive numbers")
            r = CALLS[name](v)
            label = {"log": "log₁₀", "ln": "ln", "log2": "log₂"}.get(name, name)
            steps.append(f"{_paren(v)}! = {show(r)}" if name == "factorial" else f"{label}({fmt(v)}) = {show(r)}")
            return r
        raise MathError("that expression uses something I can't evaluate")

    result = ev(tree)
    if result.has(sp.zoo, sp.nan):
        raise MathError("that's undefined")
    shown = steps if len(steps) <= MAX_STEPS else steps[:MAX_STEPS // 2] + [f"… {len(steps) - MAX_STEPS} more steps …"] + steps[-MAX_STEPS // 2:]
    if len(steps) > 1:
        shown = ["Work inside brackets first, then powers, then × ÷, then + − (left to right):"] + shown
    notes = []
    if any(t in ("sin", "cos", "tan") for t in toks) and "pi" not in toks:
        notes.append("Angles are in radians (write '30 degrees' for degrees).")
    if "log" in toks:
        notes.append("log is base 10; use ln for the natural log.")
    return Solution("arithmetic", pretty(asked or expr_text), show(result), shown + notes)


def pretty(s: str) -> str:
    s = re.sub(r"\s*\*\*\s*|\s*\^\s*", "^", s)
    s = re.sub(r"\s*\*\s*", " × ", s)
    s = re.sub(r"\s*/\s*", " ÷ ", s)
    s = re.sub(r"\s*([+=])\s*", r" \1 ", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------- percentages

NUM = r"(-?\d+(?:\.\d+)?)"


def _n(s):
    return sp.Rational(s)


def percentages(q: str) -> Solution | None:
    m = re.fullmatch(rf"{NUM}\s*(?:%|percent)\s+of\s+(.+)", q)
    if m:
        p, base = _n(m.group(1)), _expr_or_num(m.group(2))
        r = p / 100 * base
        return Solution("percent_of", f"{fmt(p)}% of {fmt(base)}", show(r),
                        [f"{fmt(p)}% = {fmt(p)} ÷ 100 = {show(p / 100)}", f"{show(p / 100)} × {fmt(base)} = {show(r)}"],
                        f"{show(r)} ÷ {fmt(base)} × 100 = {fmt(r / base * 100)}% ✓" if base != 0 else "")
    m = (re.fullmatch(rf"{NUM}\s+is\s+what\s+(?:%|percent(?:age)?)\s+of\s+{NUM}", q)
         or re.fullmatch(rf"what\s+(?:%|percent(?:age)?)\s+of\s+{NUM}\s+is\s+{NUM}", q))
    if m:
        a, b = (_n(m.group(1)), _n(m.group(2))) if q[0].isdigit() or q[0] == "-" else (_n(m.group(2)), _n(m.group(1)))
        if b == 0:
            raise MathError("can't take a percentage of 0")
        r = a / b * 100
        return Solution("what_percent", f"{fmt(a)} as a % of {fmt(b)}", f"{show(r)}%",
                        [f"part ÷ whole = {fmt(a)} ÷ {fmt(b)} = {show(a / b)}", f"× 100 = {show(r)}%"],
                        f"{show(r)}% of {fmt(b)} = {show(r / 100 * b)} ✓")
    m = re.search(rf"(?:change|increase|decrease|growth|difference)?\s*from\s+{NUM}\s+to\s+{NUM}", q)
    if m and re.search(r"percent|%|change|increase|decrease|growth|grow", q):
        a, b = _n(m.group(1)), _n(m.group(2))
        if a == 0:
            raise MathError("percent change from 0 is undefined")
        r = (b - a) / abs(a) * 100
        word = "increase" if r > 0 else "decrease" if r < 0 else "no change"
        return Solution("percent_change", f"change from {fmt(a)} to {fmt(b)}", f"{'+' if r > 0 else ''}{show(r)}% ({word})",
                        [f"difference = {fmt(b)} − {fmt(a)} = {fmt(b - a)}", f"÷ starting value {fmt(abs(a))} = {show((b - a) / abs(a))}",
                         f"× 100 = {show(r)}%"],
                        f"{fmt(a)} × (1 {'+' if r >= 0 else '−'} {show(abs(r) / 100)}) = {show(a * (1 + r / 100))} ✓")
    m = (re.fullmatch(rf"(increase|raise|decrease|reduce|lower)\s+{NUM}\s+by\s+{NUM}\s*(?:%|percent)", q)
         or re.fullmatch(rf"{NUM}\s+(increased|decreased|reduced|raised|plus|minus|\+|-)\s*(?:by\s+)?{NUM}\s*(?:%|percent)", q))
    if m:
        if m.group(1)[0].isalpha():
            verb, a, p = m.group(1), _n(m.group(2)), _n(m.group(3))
        else:
            a, verb, p = _n(m.group(1)), m.group(2), _n(m.group(3))
        up = verb in ("increase", "raise", "increased", "raised", "plus", "+")
        f = 1 + p / 100 if up else 1 - p / 100
        r = a * f
        return Solution("percent_adjust", f"{fmt(a)} {'+' if up else '−'} {fmt(p)}%", show(r),
                        [f"{fmt(p)}% of {fmt(a)} = {show(a * p / 100)}",
                         f"{fmt(a)} {'+' if up else '−'} {show(a * p / 100)} = {show(r)}"],
                        f"{fmt(a)} × {show(f)} = {show(r)} ✓")
    return None


def _expr_or_num(s: str):
    s = s.strip()
    return _n(s) if re.fullmatch(NUM, s) else sp.sympify(arithmetic_value(s))


def arithmetic_value(s: str):
    return sp.sympify(to_expr(_words_to_symbols(s)))


# ---------------------------------------------------------------- statistics and number theory

def _numbers(s: str) -> list:
    parts = [p for p in re.split(r"\s*(?:,|\band\b|;|\s)\s*", s.strip()) if p]
    if not parts or not all(re.fullmatch(NUM, p) for p in parts):
        raise MathError("give the numbers as a list, e.g. 'average of 4, 8 and 15'")
    if len(parts) > 500:
        raise MathError("that's more than 500 numbers")
    return [_n(p) for p in parts]


STAT = re.compile(r"(average|mean|median|mode|sum|total|product|min(?:imum)?|max(?:imum)?|range|"
                  r"std|standard deviation|variance|gcd|hcf|greatest common divisor|lcm|least common multiple)"
                  r"\s+(?:of\s+)?(?:the\s+)?(?:numbers\s+)?(.+)")


def statistics(q: str) -> Solution | None:
    m = STAT.fullmatch(q)
    if not m:
        return None
    try:
        op, xs = m.group(1), _numbers(m.group(2))
    except MathError:
        return None  # "average of signups" is a question about a metric, not arithmetic
    n = len(xs)
    lst = ", ".join(fmt(x) for x in xs)
    if op in ("average", "mean"):
        s = sum(xs)
        r = s / n
        return Solution("mean", f"mean of {lst}", show(r), [f"sum = {fmt(s)}", f"count = {n}", f"mean = {fmt(s)} ÷ {n} = {show(r)}"],
                        f"{show(r)} × {n} = {fmt(r * n)} = sum ✓")
    if op == "median":
        ys = sorted(xs)
        mid = n // 2
        r = ys[mid] if n % 2 else (ys[mid - 1] + ys[mid]) / 2
        why = f"middle value (position {mid + 1})" if n % 2 else f"average of the two middle values {fmt(ys[mid - 1])} and {fmt(ys[mid])}"
        return Solution("median", f"median of {lst}", show(r), [f"sorted: {', '.join(fmt(y) for y in ys)}", f"{n} values → {why} = {show(r)}"])
    if op == "mode":
        counts: dict = {}
        for x in xs:
            counts[x] = counts.get(x, 0) + 1
        top = max(counts.values())
        modes = [k for k, v in counts.items() if v == top]
        if top == 1:
            return Solution("mode", f"mode of {lst}", "no mode (every value appears once)", ["each value appears exactly once"])
        return Solution("mode", f"mode of {lst}", ", ".join(fmt(x) for x in modes), [f"most frequent: appears {top} times"])
    if op in ("sum", "total"):
        return Solution("sum", f"sum of {lst}", show(sum(xs)), [" + ".join(fmt(x) for x in xs) + f" = {show(sum(xs))}"])
    if op == "product":
        p = sp.Integer(1)
        for x in xs:
            p *= x
            _guard(p)
        return Solution("product", f"product of {lst}", show(p), [" × ".join(fmt(x) for x in xs) + f" = {show(p)}"])
    if op.startswith("min") or op.startswith("max") or op == "range":
        lo, hi = min(xs), max(xs)
        if op == "range":
            return Solution("range", f"range of {lst}", show(hi - lo), [f"max = {fmt(hi)}, min = {fmt(lo)}", f"{fmt(hi)} − {fmt(lo)} = {show(hi - lo)}"])
        r = lo if op.startswith("min") else hi
        return Solution(op[:3], f"{op[:3]} of {lst}", show(r), [f"compare all {n} values → {fmt(r)}"])
    if op in ("std", "standard deviation", "variance"):
        if n < 2:
            raise MathError("need at least 2 numbers")
        mean = sum(xs) / n
        var = sum((x - mean) ** 2 for x in xs) / n
        steps = [f"mean = {show(mean)}", f"squared distances from the mean: {', '.join(show((x - mean) ** 2) for x in xs[:8])}{' …' if n > 8 else ''}",
                 f"variance (population) = their average = {show(var)}"]
        if op == "variance":
            return Solution("variance", f"variance of {lst}", show(var), steps + [f"(sample variance, ÷ {n - 1}: {show(var * n / (n - 1))})"])
        sd = sp.sqrt(var)
        return Solution("std", f"standard deviation of {lst}", show(sd), steps + [f"std = √variance = {show(sd)}",
                        f"(sample std, ÷ {n - 1}: {show(sp.sqrt(var * n / (n - 1)))})"])
    # gcd / lcm
    if not all(x.is_integer for x in xs):
        raise MathError(f"{op} needs whole numbers")
    ints = [int(x) for x in xs]
    if op in ("gcd", "hcf", "greatest common divisor"):
        r = math.gcd(*ints)
        steps = [f"{x} = {_factor_str(x)}" for x in ints[:6]] + ["take each prime at its lowest power in all of them"]
        return Solution("gcd", f"gcd of {lst}", str(r), steps, "divides all of them ✓" if r and all(x % r == 0 for x in ints) else "")
    r = math.lcm(*ints)
    steps = [f"{x} = {_factor_str(x)}" for x in ints[:6]] + ["take each prime at its highest power in any of them"]
    return Solution("lcm", f"lcm of {lst}", f"{r:,}", steps, "every number divides it ✓" if all(x and r % x == 0 for x in ints) else "")


def _factor_str(n: int) -> str:
    if abs(n) < 2:
        return str(n)
    f = sp.factorint(abs(n))
    return ("−" if n < 0 else "") + " × ".join(f"{p}^{k}" if k > 1 else str(p) for p, k in f.items())


def number_theory(q: str) -> Solution | None:
    m = re.fullmatch(r"(?:is\s+)?(\d+)\s+(?:a\s+)?prime(?:\s+number)?", q) or re.fullmatch(r"is\s+(\d+)\s+prime", q)
    if m:
        n = int(m.group(1))
        if n > 10 ** 30:
            raise MathError("that number is too large to test here")
        if n < 2:
            return Solution("prime", f"is {n} prime?", "no", [f"{n} is less than 2, and primes start at 2"])
        f = sp.factorint(n)
        if f == {n: 1}:
            return Solution("prime", f"is {n} prime?", "yes", [f"no divisor between 2 and √{n} ≈ {math.isqrt(n)}"], "only divisors are 1 and itself ✓")
        p = min(f)
        return Solution("prime", f"is {n} prime?", "no", [f"{n} = {p} × {n // p}", f"prime factors: {_factor_str(n)}"])
    m = re.fullmatch(r"(?:prime\s+factori[sz]ation|prime\s+factors|factori[sz]e|factor)\s+(?:of\s+)?(\d+)", q)
    if m:
        n = int(m.group(1))
        if n < 2 or n > 10 ** 30:
            raise MathError("give a whole number between 2 and 10^30")
        f = sp.factorint(n)
        steps, rest = [], n
        for p, k in f.items():
            for _ in range(k):
                steps.append(f"{rest} ÷ {p} = {rest // p}")
                rest //= p
        return Solution("prime_factors", f"prime factors of {n}", _factor_str(n), steps[:MAX_STEPS],
                        f"multiplying back gives {n} ✓")
    return None


# ---------------------------------------------------------------- algebra and calculus

def _var(expr, hint: str | None = None):
    syms = sorted(expr.free_symbols, key=lambda s: s.name)
    if hint:
        return sp.Symbol(hint)
    for pref in ("x", "y", "t", "n"):
        if sp.Symbol(pref) in syms:
            return sp.Symbol(pref)
    if not syms:
        raise MathError("there's no variable to work with")
    return syms[0]


def _eq_sides(s: str):
    if s.count("=") != 1:
        raise MathError("an equation needs exactly one '='")
    left, right = s.split("=")
    return to_expr(_words_to_symbols(left)), to_expr(_words_to_symbols(right))


def solve(q: str) -> Solution:
    m = re.fullmatch(r"(?:solve\s+)?(?:for\s+([a-z])\s*[:,]?\s+)?(.+?)(?:\s+for\s+([a-z]))?", q)
    body, hint = m.group(2), m.group(1) or m.group(3)
    eqs = [e for e in re.split(r"\s*(?:,|;|\band\b)\s*", body) if e]
    if len(eqs) > 1:
        return _system(eqs)
    if "=" not in body:
        body += " = 0"
    left, right = _eq_sides(body)
    zero = sp.expand(left - right)
    x = _var(zero, hint)
    steps = [f"Equation: {fmt(left)} = {fmt(right)}"]
    if right != 0:
        steps.append(f"Move everything to one side: {fmt(zero)} = 0")
    poly = None
    try:
        poly = sp.Poly(zero, x) if zero.is_polynomial(x) else None
    except sp.PolynomialError:
        poly = None
    if poly is not None and poly.degree() == 1:
        a, b = poly.all_coeffs()
        steps += [f"Linear in {x}: {fmt(a)}·{x} + ({fmt(b)}) = 0", f"{x} = −({fmt(b)}) ÷ {fmt(a)}"]
    elif poly is not None and poly.degree() == 2 and not (poly.free_symbols - {x}):
        a, b, c = poly.all_coeffs()
        disc = b ** 2 - 4 * a * c
        steps += [f"Quadratic: a = {fmt(a)}, b = {fmt(b)}, c = {fmt(c)}",
                  f"Discriminant b² − 4ac = {_paren(b)}² − 4·{_paren(a)}·{_paren(c)} = {fmt(disc)}"
                  + (" > 0 → two real roots" if disc > 0 else " = 0 → one repeated root" if disc == 0 else " < 0 → two complex roots"),
                  f"{x} = (−b ± √disc) ÷ 2a = ({fmt(-b)} ± √{fmt(disc)}) ÷ {fmt(2 * a)}"]
    elif poly is not None and poly.degree() > 2:
        f = sp.factor(zero)
        if f != zero:
            steps.append(f"Factor: {fmt(f)} = 0, so each factor can be 0")
    if poly is not None and poly.degree() == 0:
        ok = zero == 0
        return Solution("solve", f"{fmt(left)} = {fmt(right)}", "true for every value" if ok else "no solution",
                        steps + ([f"{fmt(zero)} = 0 always holds"] if ok else [f"{fmt(zero)} = 0 is never true"]))
    sols = _timed(sp.solve, zero, x)
    if not sols:
        return Solution("solve", f"{fmt(left)} = {fmt(right)}", "no solution", steps + ["no value makes both sides equal"])
    answer = ", ".join(f"{x} = {show(s)}" for s in sols)
    tex = [f"\\text{{Rearrange: }} {sp.latex(zero)} = 0"]
    if poly is not None and poly.degree() == 2:
        a2, b2, c2 = poly.all_coeffs()
        tex.append(f"\\text{{Quadratic formula: }} {sp.latex(x)} = \\frac{{-b \\pm \\sqrt{{b^2-4ac}}}}{{2a}}"
                   f" = \\frac{{{sp.latex(-b2)} \\pm \\sqrt{{{sp.latex(b2**2 - 4 * a2 * c2)}}}}}{{{sp.latex(2 * a2)}}}")
    tex_answer = ",\\quad ".join(f"{sp.latex(x)} = {sp.latex(s)}" for s in sols)
    checks = []
    for s in sols[:3]:
        lv, rv = sp.simplify(left.subs(x, s)), sp.simplify(right.subs(x, s))
        same = sp.simplify(lv - rv) == 0
        checks.append(f"{x} = {fmt(s)}: {fmt(lv)} = {fmt(rv)} {'✓' if same else '✗'}")
    return Solution("solve", f"{fmt(left)} = {fmt(right)}", answer, steps, "check: " + "; ".join(checks),
                    tex_statement=f"\\text{{Solve }} {sp.latex(left)} = {sp.latex(right)}", tex_steps=tex, tex_answer=tex_answer)


def _paren(v) -> str:
    return f"({fmt(v)})" if v.is_number and v < 0 else fmt(v)


def _system(eqs: list[str]) -> Solution:
    if len(eqs) > 6:
        raise MathError("up to 6 equations at once")
    pairs = [_eq_sides(e if "=" in e else e + " = 0") for e in eqs]
    exprs = [left - right for left, right in pairs]
    syms = sorted(set().union(*(e.free_symbols for e in exprs)), key=lambda s: s.name)
    if not syms:
        raise MathError("there's no variable to solve for")
    sol = _timed(lambda: sp.solve(exprs, syms, dict=True))
    steps = [f"{len(exprs)} equations, unknowns {', '.join(map(str, syms))}"] + [f"  {fmt(a)} = {fmt(b)}" for a, b in pairs]
    if not sol:
        return Solution("solve_system", "; ".join(eqs), "no solution", steps + ["the equations contradict each other"])
    s0 = sol[0]
    steps.append("eliminate one unknown at a time (substitution), then back-substitute")
    answer = ", ".join(f"{k} = {show(v)}" for k, v in s0.items())
    ok = all(sp.simplify(e.subs(s0)) == 0 for e in exprs)
    return Solution("solve_system", "; ".join(eqs), answer, steps, f"substituting back satisfies all {len(exprs)} equations {'✓' if ok else '✗'}")


def calculus(q: str) -> Solution | None:
    m = re.fullmatch(r"(?:the\s+)?(?:derivative|differentiate|d/d([a-z]))\s*(?:of\s+)?(.+?)(?:\s+(?:with respect to|wrt)\s+([a-z]))?", q)
    if m:
        f = to_expr(_words_to_symbols(m.group(2)))
        x = _var(f, m.group(1) or m.group(3))
        raw = _timed(sp.diff, f, x)
        d = sp.expand(raw)
        short = min((sp.simplify(raw), raw), key=lambda e: len(str(e)))
        if len(str(d)) > 1.5 * len(str(short)):
            d = short
        steps = []
        terms = sp.Add.make_args(sp.expand(f)) if f.is_polynomial(x) else [f]
        if len(terms) > 1:
            steps.append("differentiate term by term:")
            for t in terms[:8]:
                rule = "power rule: n·xⁿ⁻¹" if t.is_polynomial(x) and sp.degree(t, x) > 0 else "constant → 0" if not t.has(x) else ""
                steps.append(f"  d/d{x} {fmt(t)} = {fmt(sp.diff(t, x))}" + (f"   ({rule})" if rule else ""))
        else:
            steps.append(f"apply the {_rule(f, x)}")
            parts = [a for a in sp.Mul.make_args(f) if a.has(x)]
            if isinstance(f, sp.Mul) and len(parts) == 2:
                c = sp.Mul(*[a for a in f.args if not a.has(x)])
                u, v = parts
                steps += [f"u = {fmt(u)}, v = {fmt(v)}" + (f"  (times the constant {fmt(c)})" if c != 1 else ""),
                          f"u′ = {fmt(sp.diff(u, x))}, v′ = {fmt(sp.diff(v, x))}",
                          f"u′v + uv′ = {fmt(sp.diff(u, x) * v)} + {fmt(u * sp.diff(v, x))}"]
        return Solution("derivative", f"d/d{x} [{fmt(f)}]", fmt(d), steps,
                        tex_statement=f"\\frac{{d}}{{d{x}}}\\left[{sp.latex(f)}\\right]",
                        tex_answer=f"\\frac{{d}}{{d{x}}}\\left[{sp.latex(f)}\\right] = {sp.latex(d)}")
    m = re.fullmatch(r"(?:the\s+)?(?:integral|integrate|antiderivative)\s*(?:of\s+)?(.+?)(?:\s+d([a-z]))?(?:\s+from\s+(\S+)\s+to\s+(\S+))?(?:\s+d([a-z]))?", q)
    if m:
        f = to_expr(_words_to_symbols(m.group(1)))
        x = _var(f, m.group(2) or m.group(5))
        F = _timed(sp.integrate, f, x)
        if F.has(sp.Integral):
            raise MathError("I couldn't find a closed-form integral for that")
        if m.group(3):
            a, b = arithmetic_value(m.group(3)), arithmetic_value(m.group(4))
            val = sp.simplify(F.subs(x, b) - F.subs(x, a))
            return Solution("definite_integral", f"∫ from {fmt(a)} to {fmt(b)} of {fmt(f)} d{x}", show(val),
                            [f"antiderivative F({x}) = {fmt(F)}", f"F({fmt(b)}) − F({fmt(a)}) = {show(F.subs(x, b))} − {show(F.subs(x, a))} = {show(val)}"],
                            tex_statement=f"\\int_{{{sp.latex(a)}}}^{{{sp.latex(b)}}} {sp.latex(f)}\\, d{x}",
                            tex_steps=[f"F({x}) = {sp.latex(F)}", f"F({sp.latex(b)}) - F({sp.latex(a)}) = {sp.latex(val)}"],
                            tex_answer=f"\\int_{{{sp.latex(a)}}}^{{{sp.latex(b)}}} {sp.latex(f)}\\, d{x} = {sp.latex(val)}")
        back = sp.simplify(sp.diff(F, x) - f) == 0
        return Solution("integral", f"∫ {fmt(f)} d{x}", f"{fmt(F)} + C", [f"find F with F′({x}) = {fmt(f)}"],
                        f"d/d{x} [{fmt(F)}] = {fmt(f)} {'✓' if back else '✗'}",
                        tex_statement=f"\\int {sp.latex(f)}\\, d{x}", tex_answer=f"\\int {sp.latex(f)}\\, d{x} = {sp.latex(F)} + C")
    m = re.fullmatch(r"(?:the\s+)?limit\s+(?:of\s+)?(.+?)\s+as\s+([a-z])\s+(?:approaches|goes to|tends to|->|→)\s+(.+)", q)
    if m:
        f = to_expr(_words_to_symbols(m.group(1)))
        x = sp.Symbol(m.group(2))
        tgt = m.group(3).strip()
        a = sp.oo if tgt in ("infinity", "inf", "∞") else -sp.oo if tgt in ("-infinity", "-inf") else arithmetic_value(tgt)
        L = _timed(sp.limit, f, x, a)
        direct = None
        try:
            direct = f.subs(x, a) if a not in (sp.oo, -sp.oo) else None
        except (TypeError, ValueError):
            pass
        steps = [f"substitute {x} = {fmt(a)} directly: {fmt(direct)}" + (" (undefined, so simplify / use L'Hôpital)" if direct is not None and direct.has(sp.nan, sp.zoo) else "")] if direct is not None else [f"look at the behaviour as {x} grows without bound"]
        return Solution("limit", f"lim {x}→{fmt(a)} {fmt(f)}", show(L), steps)
    m = re.fullmatch(r"(factor|factori[sz]e|expand|simplify)\s+(.+)", q)
    if m:
        op, f = m.group(1), to_expr(_words_to_symbols(m.group(2)))
        fn = {"expand": sp.expand, "simplify": sp.simplify}.get(op, sp.factor)
        r = _timed(fn, f)
        same = sp.simplify(r - f) == 0
        return Solution({"expand": "expand", "simplify": "simplify"}.get(op, "factor"), fmt(f), fmt(r), [f"{op} {fmt(f)}"], f"both forms are equal {'✓' if same else '✗'}")
    return None


def _rule(f, x) -> str:
    if isinstance(f, sp.Mul) and sum(1 for a in f.args if a.has(x)) > 1:
        return "product rule: (uv)′ = u′v + uv′"
    if isinstance(f, sp.Pow) and f.exp.has(x):
        return "exponential rule"
    if isinstance(f, sp.Pow) and f.base.has(x) and f.base != x:
        return "chain rule: d/dx f(g(x)) = f′(g(x))·g′(x)"
    if isinstance(f, sp.Function) and f.args and f.args[0] != x:
        return "chain rule: d/dx f(g(x)) = f′(g(x))·g′(x)"
    return "standard derivative"


# ---------------------------------------------------------------- entry point

def _clean(text: str) -> str:
    q = text.lower().strip()
    q = q.replace("’", "'").replace("“", "").replace("”", "")
    q = TRAIL.sub("", q)
    q = FILLER.sub("", q)
    q = TRAIL.sub("", q).strip(" ?.,:")
    q = re.sub(r"(?<![\d)])!+$", "", q).strip()  # "5!" is a factorial; "hello!" is excitement
    # "is the answer to" style
    q = re.sub(r"^(?:the\s+)?(?:result|answer)\s+(?:of|to)\s+", "", q)
    return q


def _words(text: str) -> Solution | None:
    from . import wordmath
    try:
        return wordmath.solve(text)
    except MathError as e:
        return Solution("error", text.strip()[:80], str(e), ok=False, confidence=0.9)
    except RecursionError:
        return Solution("error", text.strip()[:80], "that's nested too deeply", ok=False, confidence=0.9)
    except (TypeError, ValueError, AttributeError, KeyError, IndexError, ZeroDivisionError, sp.SympifyError,
            NotImplementedError):
        return None  # a reader tripped on an odd sentence: let the bot handle it rather than crash the chat


def solve_text(text: str) -> Solution | None:
    """Returns a Solution when the message is a maths question, else None (so the intent classifier handles it)."""
    if len(text) > 600:
        return None
    from . import advanced
    deep = advanced.solve(text)  # proofs, matrices, ODEs, number theory, convergence, the conjecture lab, open problems
    if deep:
        return deep
    from . import fields
    field = fields.solve(text)  # physics, electrical, chemistry, finance, statistics, geometry in plain English
    if field:
        return field
    if not re.search(r"[\d=^√π]|\b(?:solve|derivative|differentiate|integrate|integral|limit|"
                     r"factor|factori[sz]e|expand|simplify|sqrt|sin|cos|tan|log|ln|pi)\b", text.lower()):
        return _words(text)  # "sum of the first n natural numbers", "a number doubled is …"
    q = _clean(text)
    if not q:
        return None
    if len(q) > MAX_LEN:
        return Solution("error", q[:40] + "…", f"that's longer than {MAX_LEN} characters", ok=False, confidence=0.9)
    mathy = re.search(r"[\d=^+*/()√π]", q) is not None   # English sentences ("what factor caused it") stay with the bot
    try:
        for fn in (percentages, statistics, number_theory, calculus):
            sol = fn(q)
            if sol:
                return sol
        sol = _words(text)  # word problems, series, sequences, units, conditional algebra
        if sol:
            return sol
        if re.match(r"solve\b", q) or ("=" in q and re.search(r"[a-z]", q.replace("sqrt", "").replace("pi", ""))):
            return solve(q)
        expr = _words_to_symbols(q)
        if is_expression(expr):
            toks = _tokens(expr)
            if any(t.isalpha() and t not in FUNCS and t not in CONSTS for t in toks):
                f = to_expr(expr)
                s = _timed(sp.simplify, f)
                return Solution("simplify", fmt(f), fmt(s), [f"simplify {fmt(f)}"])
            return arithmetic(expr, q)
    except MathError as e:
        return Solution("error", q, str(e), ok=False, confidence=0.9) if mathy else None
    except RecursionError:
        return Solution("error", q, "that's nested too deeply", ok=False, confidence=0.9)
    except (TypeError, ValueError, AttributeError, KeyError, IndexError, ZeroDivisionError, NotImplementedError,
            sp.SympifyError):
        return Solution("error", q, "I couldn't work that out", ok=False, confidence=0.6) if mathy else None
    if STRONG_WORDS.search(q) and mathy:
        return Solution("error", q, "that looks like maths, but I couldn't read it. Try e.g. '12 * (3 + 4)', "
                        "'15% of 200', 'solve 2x + 3 = 7', 'derivative of x^3'", ok=False, confidence=0.6)
    return None


def render(sol: Solution):
    if not sol.ok:
        return Group(Text(f"✗ {sol.answer}", style="yellow"))
    out = [Text.assemble(("Problem  ", "grey50"), (sol.problem, "bold"))]
    if sol.steps:
        out.append(Text("Reasoning", style="grey50"))
        for i, s in enumerate(sol.steps, 1):
            out.append(Text.assemble((f"  {i}. ", "grey50"), s))
    out.append(Text.assemble(("Answer   ", "grey50"), (sol.answer, "bold green")))
    if sol.check:
        out.append(Text.assemble(("Check    ", "grey50"), (sol.check, "grey70")))
    return Group(*out)
