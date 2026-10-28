"""Calculus in plain English: derivatives, integrals, limits, tangent lines, stationary points and extrema,
optimisation word problems, motion and marginal analysis, each solved exactly (sympy) with the rule used and a check.

    "derivative of x^2 * sin(x)? i keep mixing up the product rule"  → product rule, u, v, u′, v′ → x^2·cos(x) + 2x·sin(x)
    "from 0 to 2 of 3x^2 dx"                                         → F(x) = x^3, F(2) − F(0) → 8
    "max area with 40 m of fencing"                                  → A(x) = x(20 − x), A′(x) = 0 → 100 m²

Chatter around the problem is tolerated ("quick one:", "pls", "for my homework", "4 sig figs", "exact form if you can",
"? i keep mixing up the product rule"), and expressions may use implicit multiplication (3x, x e^x, x ln x, sin x cos x).
Anything that isn't one of these problems, Kepler commands and definition questions ("what is a derivative") included,
returns None so the other solvers and the bot get it.
"""
import math
import re
import threading

import sympy as sp
from sympy.integrals.manualintegrate import integral_steps, manualintegrate
from sympy.printing.str import StrPrinter

from ..fields import fmt as _fmt4
from ..fields import money
from ..reasoning import Solution

TIME_LIMIT = 2.0  # seconds for one piece of symbolic work
CONF = 0.97


class _Bad(Exception):
    """The text isn't a readable expression."""


class _Fail(Exception):
    """A calculus problem we recognised but can't finish (no closed form, too slow)."""


def _timed(fn, *args, limit: float = TIME_LIMIT):
    box: dict = {}

    def run():
        try:
            box["v"] = fn(*args)
        except Exception as e:  # noqa: BLE001 - re-raised in the caller's thread
            box["e"] = e

    th = threading.Thread(target=run, daemon=True)
    th.start()
    th.join(limit)
    if th.is_alive():
        raise _Fail("that took too long to work out exactly")
    if "e" in box:
        raise box["e"]
    return box["v"]


# ---------------------------------------------------------------- reading expressions: text → sympy

VARS = set("xtquyzsvwrp")  # single letters that can be the variable; any other letter means "this is English"
FUNCS = {"arcsin": sp.asin, "arccos": sp.acos, "arctan": sp.atan, "asin": sp.asin, "acos": sp.acos, "atan": sp.atan,
         "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh, "sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "sec": sp.sec,
         "cosec": sp.csc, "csc": sp.csc, "cot": sp.cot, "ln": sp.log, "log": lambda a: sp.log(a, 10), "exp": sp.exp,
         "sqrt": sp.sqrt, "cbrt": sp.cbrt, "abs": sp.Abs}
INVERSE = {"sin": sp.asin, "cos": sp.acos, "tan": sp.atan}
_NAMES = sorted([*FUNCS, "pi", "e"], key=len, reverse=True)
_LEX = re.compile(r"(\d+(?:\.\d+)?|\.\d+)|([a-z]+)|(\*\*|[-+*/^()\[\]{}])|(\s+)")


def _letters(run: str) -> list[str] | None:
    """'xlnx' → ['x', 'ln', 'x']; None when the run has letters that aren't maths."""
    out, i = [], 0
    while i < len(run):
        for n in _NAMES:
            if run.startswith(n, i):
                out.append(n)
                i += len(n)
                break
        else:
            if run[i] not in VARS:
                return None
            out.append(run[i])
            i += 1
    return out


def _lex(s: str) -> list[tuple[str, str, bool]] | None:
    """Tokens (kind, text, glued-to-previous)."""
    toks, pos, glued = [], 0, False
    while pos < len(s):
        m = _LEX.match(s, pos)
        if not m:
            return None
        pos = m.end()
        if m.group(4):
            glued = False
            continue
        if m.group(1):
            if len(m.group(1)) > 12:
                return None
            toks.append(("num", m.group(1), glued))
        elif m.group(2):
            parts = _letters(m.group(2))
            if parts is None:
                return None
            for i, p in enumerate(parts):
                kind = "func" if p in FUNCS else "const" if p in ("pi", "e") else "var"
                toks.append((kind, p, glued or i > 0))
        else:
            op = m.group(3)
            toks.append(("op", {"**": "^", "[": "(", "]": ")", "{": "(", "}": ")"}.get(op, op), glued))
        glued = True
    return toks if 0 < len(toks) <= 120 else None


class _Parser:
    """Recursive descent with implicit multiplication: 3x, x e^x, x ln x, sin x cos x, e^2x (= e^(2x)), sin^2 x."""

    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self, k: int = 0):
        j = self.i + k
        return self.t[j] if j < len(self.t) else ("end", "", False)

    def take(self):
        if self.i >= len(self.t):
            raise _Bad
        tok = self.t[self.i]
        self.i += 1
        return tok

    def expect(self, v: str):
        if self.take()[1] != v:
            raise _Bad

    def expr(self):
        v = self.term()
        while self.peek()[1] in ("+", "-"):
            op = self.take()[1]
            r = self.term()
            v = v + r if op == "+" else v - r
        return v

    def _starts_atom(self, tok) -> bool:
        return tok[0] in ("num", "var", "const", "func") or tok[1] == "("

    def term(self):
        v = self.unary()
        while True:
            tok = self.peek()
            if tok[1] in ("*", "/"):
                self.take()
                r = self.unary()
                if tok[1] == "/":
                    if r == 0:
                        raise _Bad
                    v = v / r
                else:
                    v = v * r
            elif self._starts_atom(tok):
                v = v * self.power()
            else:
                return v

    def unary(self):
        if self.peek()[1] == "-":
            self.take()
            return -self.unary()
        if self.peek()[1] == "+":
            self.take()
            return self.unary()
        return self.power()

    def power(self):
        base = self.atom()
        if self.peek()[1] == "^":
            self.take()
            base = self._pow(base, self.exponent(base is sp.E))
        return base

    def exponent(self, glue: bool):
        if self.peek()[1] == "-":
            self.take()
            return -self.exponent(glue)
        if self.peek()[1] == "+":
            self.take()
            return self.exponent(glue)
        a = self.atom()
        if glue and a.is_Number:  # e^2x → e^(2x): the usual shorthand
            while self.peek()[0] in ("var", "const") and self.peek()[2]:
                a = a * self.atom()
        if self.peek()[1] == "^":
            self.take()
            a = self._pow(a, self.exponent(False))
        return a

    @staticmethod
    def _pow(b, n):
        if n.is_Number and abs(n) > 100:
            raise _Bad
        if b.is_Number and n.is_Number and abs(b) > 1000 and n > 10:
            raise _Bad
        if b == 0 and n.is_Number and n <= 0:
            raise _Bad
        return b ** n

    def atom(self):
        kind, val, _ = self.peek()
        if kind == "num":
            self.take()
            return sp.Rational(val)
        if kind == "var":
            self.take()
            return sp.Symbol(val)
        if kind == "const":
            self.take()
            return sp.pi if val == "pi" else sp.E
        if val == "(":
            self.take()
            v = self.expr()
            self.expect(")")
            return v
        if kind == "func":
            self.take()
            return self.func(val)
        raise _Bad

    def func(self, name: str):
        fn, power = FUNCS[name], None
        if self.peek()[1] == "^":  # sin^2 x, sin^-1 x
            self.take()
            neg = self.peek()[1] == "-"
            if neg:
                self.take()
            kind, val, _ = self.take()
            if kind != "num":
                raise _Bad
            n = sp.Rational(val) * (-1 if neg else 1)
            if n == -1 and name in INVERSE:
                fn = INVERSE[name]
            else:
                power = n
        v = fn(self.funcarg())
        return v ** power if power is not None else v

    def funcarg(self):
        if self.peek()[1] == "(":
            self.take()
            v = self.expr()
            self.expect(")")
            return v
        if self.peek()[1] == "-":
            self.take()
            return -self.funcarg()
        v = self.power()  # sin x^2 = sin(x^2); sin 2x = sin(2x); sin x cos x = sin(x)·cos(x)
        while self.peek()[0] in ("num", "var") or self.peek()[1] == "pi":
            v = v * self.power()
        return v


def parse(s: str):
    """A whitelisted expression → sympy, or None."""
    s = s.strip()
    if not s or len(s) > 200:
        return None
    s = re.sub(r"\|([^|]+)\|", r"abs(\1)", s)
    toks = _lex(s)
    if not toks:
        return None
    p = _Parser(toks)
    try:
        v = p.expr()
    except (_Bad, ZeroDivisionError, TypeError, ValueError, RecursionError, OverflowError):
        return None
    if p.i != len(toks):
        return None
    v = sp.sympify(v)
    if v.has(sp.zoo, sp.nan, sp.oo, -sp.oo, sp.I):
        return None
    return v


def _ok(e, var: str | None, allow_const: bool = False):
    """The expression's variable, if it uses exactly one (the one asked for, when one is)."""
    syms = e.free_symbols
    if var:
        v = sp.Symbol(var)
        if syms == {v} or (allow_const and not syms):
            return v
        return None
    if len(syms) == 1:
        return next(iter(syms))
    if allow_const and not syms:
        return sp.Symbol("x")
    return None


_LEAD = re.compile(r"^(?:\s*(?:(?:of|the|a|an|function|expression|curve|graph|equation|polynomial|parabola|is|this|"
                   r"following|given|by|for)\b|[:,=]))*\s*(?:[a-z]\s*(?:\(\s*[a-z]\s*\))?\s*=(?![=>])\s*)?")
_STOP = re.compile(r"\s*(?:[?;!,]|\.(?!\d)|:|<|>|\s-{2,}|\b(?:with respect to|w\.?r\.?t\.?|wrt|respect|at|when|where|"
                   r"whenever|if|for|from|between|on|over|as|in|then|please|pls|plz|thanks|thank|thx|show|using|use|with|"
                   r"and|i|i'm|im|i've|what|what's|whats|find|is|are|it|it's|its|the|by|to|of|into|so|but|or|because|"
                   r"cuz|since|ok|okay|give|answer|steps?|my|me|you|can|could|would|need|help|via|which|that|evaluate|"
                   r"evaluated|do|does|exactly|exact|equals?|gives?|has|have|its?|keep|than|like|ans|rule|correct|right|"
                   r"x-axis|y-axis|axis)\b|(?<![a-z])d[a-z](?![a-z]))")


def _prefix(seg: str, var: str | None = None, allow_const: bool = False):
    words = seg.split()
    for k in range(len(words), 0, -1):
        text = " ".join(words[:k])
        e = parse(text)
        if e is not None:
            v = _ok(e, var, allow_const)
            if v is not None:
                return e, v, text
    return None


def _after(seg: str, var: str | None = None, allow_const: bool = False):
    """The expression at the start of seg ("of x ln x, show steps" → x·ln(x)), as (expr, var, text) or None."""
    seg = _LEAD.sub("", seg, count=1)
    m = _STOP.search(seg)
    if m:
        seg = seg[:m.start()]
    return _prefix(seg, var, allow_const)


def _lexable(w: str) -> bool:
    return _lex(w) is not None


def _scan(seg: str, var: str | None = None):
    """The longest stretch of seg that reads as an expression in one variable, as (expr, var, text) or None."""
    best = None
    for piece in re.split(r"[?;!,:]|\.(?!\d)|<|>|\s-{2,}", seg):
        words = piece.split()
        ok = [_lexable(w) for w in words]
        i = 0
        while i < len(words):
            if not ok[i]:
                i += 1
                continue
            j = i
            while j < len(words) and ok[j]:
                j += 1
            found = None
            for n in range(j - i, 0, -1):
                for s in range(i, j - n + 1):
                    text = " ".join(words[s:s + n])
                    e = parse(text)
                    v = _ok(e, var) if e is not None else None
                    if v is not None:
                        found = (e, v, text)
                        break
                if found:
                    break
            if found and (best is None or len(found[2]) > len(best[2])):
                best = found
            i = j
    return best


_DEF = re.compile(r"(?<![a-z'/^])([a-z])\s*(?:\(\s*([a-z])\s*\))?\s*=(?![=>])\s*")


def _definition(t: str, names: str | None = None, var: str | None = None):
    """'f(x) = x^3 - 3x' / 'y = e^(x^2)' / 's(t) = ...' → (name, expr, var) for the first one that reads."""
    for m in _DEF.finditer(t):
        name = m.group(1)
        if names is not None and name not in names:
            continue
        r = _after(t[m.end():], var or m.group(2))
        if r:
            return name, r[0], r[1]
    return None


# ---------------------------------------------------------------- numbers, points and intervals

_B = r"(-?[\w.^/()]+)"


def _number(s: str | None):
    if s is None:
        return None
    s = s.strip().rstrip(".,;?")
    while s.endswith(")") and s.count(")") > s.count("("):
        s = s[:-1]
    while s.startswith("(") and s.count("(") > s.count(")"):
        s = s[1:]
    if s in ("infinity", "inf", "oo", "+infinity"):
        return sp.oo
    if s in ("-infinity", "-inf", "-oo"):
        return -sp.oo
    e = parse(s)
    if e is None or e.free_symbols or not e.is_real:
        return None
    return e


_BOUNDS = [re.compile(p) for p in (
    rf"\bfrom\s+(?:[a-z]\s*=\s*)?{_B}\s*(?:to|till|until|up to|upto|->)\s*(?:[a-z]\s*=\s*)?{_B}",
    rf"\bbetween\s+(?:[a-z]\s*=\s*)?{_B}\s+and\s+(?:[a-z]\s*=\s*)?{_B}",
    rf"[\[(]\s*{_B}\s*,\s*{_B}\s*[\])]",
    rf"(?<![\w.]){_B}\s*<=?\s*[a-z]\s*<=?\s*{_B}",
    rf"\b(?:limits?|bounds?)\s+(?:of\s+|are\s+|is\s+)?{_B}\s+(?:to|and)\s+{_B}",
    rf"(?<![a-z])[a-z]\s*=\s*{_B}\s+(?:to|and)\s+[a-z]\s*=\s*{_B}",
    rf"\bintegral\s*_\s*{_B}\s*\^\s*{_B}",
    rf"\bintegra(?:l|te)\s+(?:from\s+)?{_B}\s+to\s+{_B}",
    rf"\bfirst\s+()(\d+(?:\.\d+)?)\s*(?:s|secs?|seconds?|minutes?|mins?|hours?|hrs?|units?)\b",
)]


def _bounds(t: str):
    """(a, b, matched span) for 'from 0 to 2', 'between 1 and e', 'on [0, pi]', 'the first 4 seconds'."""
    for rx in _BOUNDS:
        for m in rx.finditer(t):
            a = sp.Integer(0) if m.group(1) == "" else _number(m.group(1))
            b = _number(m.group(2))
            if a is not None and b is not None and a != b:
                return a, b, m.span()
    return None


def _point(t: str, var: str):
    """The x-value in 'at x = 2', 'when t = 3', 'at the point (1, 4)', 'f'(2)'; (value, y-value or None)."""
    v = re.escape(var)
    for rx in (rf"\b(?:at|when|where|for|if|with)\s+(?:the\s+point\s+(?:where\s+)?)?{v}\s*(?:=|is|equals)\s*{_B}",
               rf"\b(?:at|through)\s+(?:the\s+point\s+)?\(\s*{_B}\s*,\s*{_B}\s*\)",
               rf"(?<![a-z(]){v}\s*=\s*{_B}",
               rf"\b[a-z]\s*'*\s*\(\s*{_B}\s*\)"):
        for m in re.finditer(rx, t):
            a = _number(m.group(1))
            if a is not None and a.is_finite:
                y = _number(m.group(2)) if m.lastindex and m.lastindex >= 2 else None
                return a, y
    return None


# ---------------------------------------------------------------- showing results

class _Printer(StrPrinter):
    def _print_Exp1(self, e):
        return "e"

    def _print_Pi(self, e):
        return "π"

    def _print_Infinity(self, e):
        return "∞"

    def _print_NegativeInfinity(self, e):
        return "-∞"

    def _print_ImaginaryUnit(self, e):
        return "i"

    def _atomic(self, e) -> bool:
        return e.is_Symbol or (e.is_Integer and e >= 0) or e in (sp.pi, sp.E) or isinstance(e, sp.Function)

    def _wrap(self, e) -> str:
        s = self._print(e)
        return s if self._atomic(e) else f"({s})"

    def _print_exp(self, e):
        a = e.args[0]
        return f"e^{self._print(a)}" if (a.is_Symbol or (a.is_Integer and a > 0)) else f"e^({self._print(a)})"

    def _print_log(self, e):
        a = e.args[0]
        if isinstance(a, sp.Abs):
            return f"ln|{self._print(a.args[0])}|"
        return f"ln({self._print(a)})"

    def _print_Abs(self, e):
        return f"|{self._print(e.args[0])}|"

    def _print_asin(self, e):
        return f"arcsin({self._print(e.args[0])})"

    def _print_acos(self, e):
        return f"arccos({self._print(e.args[0])})"

    def _print_atan(self, e):
        return f"arctan({self._print(e.args[0])})"

    def _print_Pow(self, e, rational=False):
        b, n = e.base, e.exp
        if n == sp.S.Half:
            return "√" + self._wrap(b)
        if n == -sp.S.Half:
            return "1/√" + self._wrap(b)
        if n.is_Rational and n.is_negative:
            inner = sp.Pow(b, -n)
            s = self._print(inner)
            return f"1/{s}" if (self._atomic(inner) or inner.is_Pow) else f"1/({s})"
        ex = self._print(n)
        if not (n.is_Symbol or (n.is_Integer and n >= 0)):
            ex = f"({ex})"
        return f"{self._wrap(b)}^{ex}"


_PR = _Printer()


def pe(e) -> str:
    """Readable maths: x^2·sin(x), e^(3x)/3, √(4x + 9), ln|x|."""
    s = _PR.doprint(sp.sympify(e)).replace("*", "·")
    return re.sub(r"(?<![\w.^])(\d+)·(?=[a-zπ√(|])", r"\1", s)


def _pw(e) -> str:
    """pe() in brackets when it's a sum or negative, for writing products out."""
    s = pe(e)
    return f"({s})" if (isinstance(e, sp.Add) or s.startswith("-")) else s


class _Opts:
    def __init__(self, sig: int | None = None, dp: int | None = None, fraction: bool = False):
        self.sig, self.dp, self.fraction = sig, dp, fraction


def _dec(x: float, o: _Opts) -> str:
    if o.dp is not None:
        return f"{x:,.{o.dp}f}"
    if o.sig:
        if x == 0:
            return "0"
        s = f"{x:#.{o.sig}g}"
        return s.rstrip(".") if "e" not in s else s
    return _fmt4(x)


def _int(v) -> str:
    return f"{int(v):,}" if abs(v) >= 10000 else str(int(v))


def _val(v, o: _Opts, unit: str = "") -> str:
    """Exact value, plus a decimal where useful: 8 · 1/2 = 0.5 · e - 1 ≈ 1.718 · √2/2 ≈ 0.7071."""
    v = sp.sympify(v)
    if v is sp.oo:
        s = "∞"
    elif v is -sp.oo:
        s = "-∞"
    elif v.is_Integer:
        s = _int(v)
    elif v.is_Rational:
        frac = f"{v.p}/{v.q}"
        terminating = set(sp.factorint(v.q)) <= {2, 5}
        if o.fraction:
            s = frac
        elif terminating and o.sig is None and o.dp is None:
            s = f"{frac} = {float(v):g}"
        else:
            s = f"{frac} ≈ {_dec(float(v), o)}"
    elif v.is_number and v.is_real:
        s = f"{pe(v)} ≈ {_dec(float(v), o)}"
    else:
        s = pe(v)
    return f"{s} {unit}".rstrip()


def _short(v) -> str:
    """A value inside a step: exact, with a decimal when it's irrational."""
    v = sp.sympify(v)
    if v.is_number and v.is_real and not v.is_Rational and v.is_finite:
        return f"{pe(v)} ≈ {_fmt4(float(v))}"
    return pe(v)


def _nice(e):
    """The simplest-looking of the usual forms (factored rational functions, expanded polynomials)."""
    base = pe(e)
    cands = [e]
    for fn in (sp.expand, sp.factor, sp.cancel, sp.simplify):
        try:
            cands.append(_timed(fn, e, limit=1.0))
        except Exception:  # noqa: BLE001 - a simplification we can do without
            continue
    best = min(cands, key=lambda c: len(pe(c)))
    if len(pe(best)) < 0.85 * len(base):
        return best
    ex = cands[1] if len(cands) > 1 else e
    return ex if len(pe(ex)) <= len(base) else e


def _f(e, x, a) -> float | None:
    try:
        v = complex(e.subs(x, a).evalf(20))
    except (TypeError, ValueError, ZeroDivisionError, OverflowError):
        return None
    if abs(v.imag) > 1e-9 * max(1.0, abs(v.real)) or not math.isfinite(v.real):
        return None
    return v.real


def _sol(kind, problem, answer, steps, check="", tex_statement="", tex_answer="") -> Solution:
    return Solution(kind, problem, answer, steps, check=check, confidence=CONF, tex_statement=tex_statement,
                    tex_answer=tex_answer)


# ---------------------------------------------------------------- explaining derivatives

_DTABLE = {sp.sin: ("sin", "cos(u)"), sp.cos: ("cos", "-sin(u)"), sp.tan: ("tan", "sec(u)^2"),
           sp.sec: ("sec", "sec(u)·tan(u)"), sp.csc: ("csc", "-csc(u)·cot(u)"), sp.cot: ("cot", "-csc(u)^2"),
           sp.asin: ("arcsin", "1/√(1 - u^2)"), sp.acos: ("arccos", "-1/√(1 - u^2)"), sp.atan: ("arctan", "1/(1 + u^2)"),
           sp.sinh: ("sinh", "cosh(u)"), sp.cosh: ("cosh", "sinh(u)"), sp.tanh: ("tanh", "1 - tanh(u)^2")}


def _tag(term, x) -> str:
    """A few words naming the rule for one term."""
    _, g = term.as_independent(x, as_Add=False)
    if not g.has(x):
        return "constant"
    if g == x:
        return f"d/d{x} {x} = 1"
    if g.is_Pow and g.base == x and not g.exp.has(x):
        return "power rule"
    if g.is_Mul:
        num, den = sp.fraction(g)
        return "quotient rule" if num.has(x) and den.has(x) else "product rule" if not den.has(x) else "chain rule"
    if isinstance(g, (sp.exp, sp.log)) or g.func in _DTABLE:
        return "standard derivative" if g.args[0] == x else "chain rule"
    if g.is_Pow:
        return "chain rule"
    return "standard derivative"


def _explain_d(g, x) -> list[str]:
    """Rule and working for one term without a constant factor."""
    d = sp.Symbol("d")
    dx = f"d/d{x}"
    if not g.has(x):
        return ["rule: the derivative of a constant is 0"]
    if g == x:
        return [f"rule: {dx} {x} = 1"]
    num, den = sp.fraction(g)
    if g.is_Mul and num.has(x) and den.has(x):
        u, v = num, den
        du, dv = sp.diff(u, x), sp.diff(v, x)
        return ["rule: quotient rule (u/v)′ = (u′v − uv′)/v²", f"u = {pe(u)}, v = {pe(v)}", f"u′ = {pe(du)}, v′ = {pe(dv)}",
                f"substitute: ({_pw(du)}·{_pw(v)} − {_pw(u)}·{_pw(dv)}) / {_pw(v)}^2"]
    if g.is_Mul and not den.has(x):
        fs = [a for a in sp.Mul.make_args(g) if a.has(x)]
        u, v = fs[0], sp.Mul(*fs[1:])
        du, dv = sp.diff(u, x), sp.diff(v, x)
        return ["rule: product rule (uv)′ = u′v + uv′", f"u = {pe(u)}, v = {pe(v)}", f"u′ = {pe(du)}, v′ = {pe(dv)}",
                f"substitute: u′v + uv′ = {_pw(du)}·{_pw(v)} + {_pw(u)}·{_pw(dv)}"]
    if g.is_Pow:
        b, n = g.base, g.exp
        if not n.has(x):
            if b == x:
                return [f"rule: power rule {dx} {x}ⁿ = n·{x}ⁿ⁻¹, with n = {pe(n)}",
                        f"substitute: {_pw(n)}·{x}^{_pw(n - 1)}"]
            db = sp.diff(b, x)
            return [f"rule: chain rule with the power rule, {dx} [g]ⁿ = n·gⁿ⁻¹·g′",
                    f"g = {pe(b)}, n = {pe(n)}, g′ = {pe(db)}", f"substitute: {_pw(n)}·{_pw(b)}^{_pw(n - 1)}·{_pw(db)}"]
        if not b.has(x):
            dn = sp.diff(n, x)
            return [f"rule: {dx} aᵍ = aᵍ·ln(a)·g′ (exponential, chain rule)", f"a = {pe(b)}, g = {pe(n)}, g′ = {pe(dn)}"]
        return ["rule: logarithmic differentiation: take ln of both sides, then differentiate"]
    if isinstance(g, sp.exp):
        u = g.args[0]
        if u == x:
            return [f"rule: {dx} e^{x} = e^{x}"]
        return [f"rule: chain rule, {dx} e^g = e^g·g′", f"g = {pe(u)}, g′ = {pe(sp.diff(u, x))}",
                f"substitute: {pe(g)}·{_pw(sp.diff(u, x))}"]
    if isinstance(g, sp.log):
        u = g.args[0]
        if u == x:
            return [f"rule: {dx} ln({x}) = 1/{x}"]
        return [f"rule: chain rule, {dx} ln(g) = g′/g", f"g = {pe(u)}, g′ = {pe(sp.diff(u, x))}",
                f"substitute: {_pw(sp.diff(u, x))} / {_pw(u)}"]
    if g.func in _DTABLE:
        name, der = _DTABLE[g.func]
        u = g.args[0]
        if u == x:
            return [f"rule: {dx} {name}({x}) = {der.replace('u', str(x))}"]
        return [f"rule: chain rule, {dx} {name}(g) = {der.replace('u', 'g')}·g′", f"g = {pe(u)}, g′ = {pe(sp.diff(u, x))}"]
    del d
    return ["rule: standard derivatives"]


def _d_steps(f, x) -> list[str]:
    terms = sp.Add.make_args(f)
    if len(terms) > 1:
        steps = ["rule: sum rule, differentiate term by term"]
        for term in terms[:8]:
            steps.append(f"d/d{x} [{pe(term)}] = {pe(sp.diff(term, x))}  ({_tag(term, x)})")
        return steps
    c, g = f.as_independent(x, as_Add=False)
    steps = []
    if c != 1 and g.has(x):
        steps.append(f"rule: constant multiple, keep {pe(c)} and differentiate {pe(g)}")
    return steps + _explain_d(g, x)


def _prime(n: int) -> str:
    return {1: "′", 2: "″", 3: "‴"}.get(n, f"^({n})")


def _slope_check(f, d, x, at=None) -> str:
    """Numerical slope of f near a point agrees with f′ there."""
    pts = ([at] if at is not None else []) + [sp.Integer(1), sp.Rational(1, 2), sp.Integer(2), sp.Rational(3, 10), sp.Integer(3)]
    for a in pts:
        da = _f(d, x, a)
        if da is None:
            continue
        h = 1e-6
        lo, hi = _f(f, x, sp.Float(float(a) - h, 30)), _f(f, x, sp.Float(float(a) + h, 30))
        if lo is None or hi is None:
            continue
        slope = (hi - lo) / (2 * h)
        if abs(slope - da) <= 1e-4 * max(1.0, abs(da)):
            return f"numerical slope of f at {x} = {pe(a)}: {_fmt4(slope)} = f′({pe(a)}) ✓"
        return ""
    return ""


# ---------------------------------------------------------------- derivatives

_D_WORDS = re.compile(r"\b(?:derivatives?|differentiate|differentiation|differentiating|diff|derive)\b|"
                      r"\bd\^?\d?\s*[a-z]?\s*/\s*d[a-z]\b|\b[a-z]\s*'+\s*\(|\b[a-z]'+(?![a-z])|\brate of change\b")


def derivative(t: str, o: _Opts) -> Solution | None:
    if not _D_WORDS.search(t):
        return None
    order = 1
    if re.search(r"\b(?:second|2nd)\b[\w\s-]{0,10}\bderivative|''|\bd\^?2\s*[a-z]?\s*/\s*d[a-z]\s*\^?2|\btwice\b", t):
        order = 2
    if re.search(r"\b(?:third|3rd)\b[\w\s-]{0,10}\bderivative|'''|\bd\^?3\s*[a-z]?\s*/\s*d[a-z]\s*\^?3", t):
        order = 3
    var = None
    m = re.search(r"\bd\^?\d?\s*[a-z]?\s*/\s*d([a-z])\b", t)
    if m:
        var = m.group(1)
    m = re.search(r"(?:with respect to|w\.?r\.?t\.?|wrt)\s+([a-z])\b", t)
    if m:
        var = m.group(1)
    found = None
    for k in re.finditer(r"\b(?:derivatives?|differentiate|diff|derive|rate of change)\b(?:\s+of)?|"
                         r"\bd\^?\d?\s*[a-z]?\s*/\s*d[a-z]\s*\^?\d?(?:\s*of)?", t):
        found = _after(t[k.end():], var)
        if found:
            break
    if not found:
        d = _definition(t, var=var)
        if d:
            found = (d[1], d[2], "")
    if not found:
        return None
    f, x, _ = found
    at = None
    m = re.search(r"\b[a-z]\s*('+)\s*\(\s*([^()]+?)\s*\)", t)
    if m:
        order = max(order, len(m.group(1)))
        a = _number(m.group(2))
        if a is not None:
            at = a
    if at is None:
        p = _point(t, str(x))
        if p and not re.search(rf"\b[a-z]\s*\(\s*{x}\s*\)\s*=\s*{re.escape(pe(p[0]))}\b", t):
            at = p[0]
    raw = _timed(sp.diff, f, x, order)
    d = _nice(raw)
    steps = _d_steps(f, x)
    name = f"f{_prime(order)}({x})"
    if order > 1:
        prev = f
        for k in range(1, order):
            prev = _nice(sp.diff(prev, x))
            steps.append(f"f{_prime(k)}({x}) = {pe(prev)}")
        steps.append(f"differentiate again: {name} = {pe(d)}")
    dd = "d" if order == 1 else f"d^{order}"
    problem = f"{dd}/d{x}{'' if order == 1 else '^' + str(order)} [{pe(f)}]"
    tex = f"\\frac{{d{'' if order == 1 else '^' + str(order)}}}{{d{x}{'' if order == 1 else '^' + str(order)}}}\\left[{sp.latex(f)}\\right]"
    if at is not None:
        val = sp.simplify(d.subs(x, at))
        if val.has(sp.zoo, sp.nan) or not val.is_finite:
            raise _Fail(f"the derivative isn't defined at {x} = {pe(at)}")
        steps += [f"{name} = {pe(d)}", f"substitute: f{_prime(order)}({pe(at)}) = {pe(d.subs(x, sp.Symbol('(' + pe(at) + ')')))}",
                  f"result: f{_prime(order)}({pe(at)}) = {_short(val)}"]
        check = _slope_check(f, d, x, at) if order == 1 else ""
        return _sol("derivative", f"{problem} at {x} = {pe(at)}", _val(val, o), steps, check,
                    tex_statement=tex, tex_answer=f"{sp.latex(val)}")
    steps.append(f"result: {name} = {pe(d)}")
    check = _slope_check(f, d, x) if order == 1 else ""
    return _sol("derivative", problem, pe(d), steps, check, tex_statement=tex, tex_answer=f"{tex} = {sp.latex(d)}")


# ---------------------------------------------------------------- integrals

def _rule_name(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", " ", name.replace("Rule", "")).lower()


def _explain_i(rule, x, depth: int = 0) -> list[str]:
    name = type(rule).__name__
    if depth > 3:
        return []
    if name == "AlternativeRule":
        return _explain_i(rule.alternatives[0], x, depth)
    if name == "AddRule":
        out = ["rule: sum rule, integrate term by term"]
        for s in rule.substeps[:8]:
            out.append(f"∫ {pe(s.integrand)} d{x} = {pe(s.eval())}  ({_i_tag(s)})")
        return out
    if name == "ConstantTimesRule":
        return [f"rule: constant multiple, take {pe(rule.constant)} outside the integral"] + _explain_i(rule.substep, x, depth + 1)
    if name == "PowerRule":
        return [f"rule: power rule ∫ {x}ⁿ d{x} = {x}ⁿ⁺¹/(n + 1), with n = {pe(rule.exp)}"]
    if name == "ReciprocalRule":
        return [f"rule: ∫ 1/{x} d{x} = ln|{x}|"]
    if name == "ExpRule":
        return [f"rule: ∫ e^{x} d{x} = e^{x}"] if rule.base == sp.E else [f"rule: ∫ aˣ d{x} = aˣ/ln(a), with a = {pe(rule.base)}"]
    if name == "ConstantRule":
        return [f"rule: ∫ c d{x} = c·{x}"]
    if name == "URule":
        u = rule.u_func
        return [f"rule: substitution u = {pe(u)}, du = {pe(sp.diff(u, x))} d{x}",
                f"in terms of u: ∫ {pe(rule.substep.integrand.subs(rule.u_var, sp.Symbol('u')))} du"]
    if name == "PartsRule":
        v = rule.v_step.eval()
        return ["rule: integration by parts ∫ u dv = uv − ∫ v du", f"u = {pe(rule.u)}, dv = {pe(rule.dv)} d{x}",
                f"du = {pe(sp.diff(rule.u, x))} d{x}, v = {pe(v)}"]
    if name == "RewriteRule":
        return [f"rewrite the integrand as {pe(rule.rewritten)}"] + _explain_i(rule.substep, x, depth + 1)
    if name in ("DontKnowRule",):
        return []
    return [f"rule: standard integral ({_rule_name(name)}): ∫ {pe(rule.integrand)} d{x} = {pe(rule.eval())}"]


def _i_tag(rule) -> str:
    name = type(rule).__name__
    if name == "ConstantTimesRule":
        return _i_tag(rule.substep)
    if name == "AlternativeRule":
        return _i_tag(rule.alternatives[0])
    return {"PowerRule": "power rule", "ConstantRule": "constant", "ReciprocalRule": "1/x → ln|x|", "ExpRule": "exponential",
            "URule": "substitution", "PartsRule": "by parts"}.get(name, "standard integral")


def _antiderivative(f, x):
    """(F, steps): F′ = f, with the rule used; raises _Fail when there's no closed form."""
    steps: list[str] = []
    F = None
    try:
        rule = _timed(integral_steps, f, x, limit=1.5)
        if "DontKnowRule" not in repr(rule):
            F = rule.eval()
            steps = _explain_i(rule, x)
    except _Fail:
        raise
    except Exception:  # noqa: BLE001 - manual integration can't do everything; sympy's full integrator may
        F = None
    if F is None or F.has(sp.Integral):
        try:
            F = _timed(manualintegrate, f, x, limit=1.0)
        except Exception:  # noqa: BLE001
            F = None
    if F is None or F.has(sp.Integral):
        F = _timed(sp.integrate, f, x)
        steps = steps or ["rule: standard integrals (sympy's Risch–Norman integrator)"]
    if F.has(sp.Integral):
        raise _Fail(f"∫ {pe(f)} d{x} has no closed form I can find")
    F = _nice(F)
    return F, steps


def _abs_logs(F, f, x):
    """ln(u) from integrating 1/u is ln|u| (unless u is always positive): ∫ 1/(2x) dx = ln|x|/2."""
    if f.has(sp.log):
        return F
    xr = sp.Symbol(str(x), real=True)

    def fix(e):
        u = e.args[0]
        return sp.log(sp.Abs(u)) if u.subs(x, xr).is_positive is not True else e
    return F.replace(lambda e: isinstance(e, sp.log), fix)


def _quad_check(f, x, a, b, val) -> str:
    try:
        from scipy.integrate import quad
        fn = sp.lambdify(x, f, "math")
        lo = float(a) if a.is_finite else (-math.inf)
        hi = float(b) if b.is_finite else math.inf
        num, err = quad(lambda v: float(fn(v)), lo, hi, limit=200)
    except Exception:  # noqa: BLE001 - the check is a bonus, not the answer
        return ""
    if not math.isfinite(num) or not val.is_finite:
        return ""
    if abs(num - float(val)) <= 1e-6 * max(1.0, abs(num)):
        return f"numerical integration gives {_fmt4(num)} ✓"
    return ""


_I_WORDS = re.compile(r"\b(?:integrate|integral|integration|antiderivative|anti-derivative|antidifferentiate|"
                      r"primitive)\b|\barea\s+(?:under|beneath|below|bounded by|enclosed by|between)\b")


def integral(t: str, o: _Opts) -> Solution | None:
    m = _I_WORDS.search(t)
    if not m:
        return None
    area = m.group(0).startswith("area")
    var = None
    dm = re.search(r"(?<![a-z/])d([a-z])(?![a-z])", t)
    if dm:
        var = dm.group(1)
    wm = re.search(r"(?:with respect to|w\.?r\.?t\.?|wrt)\s+([a-z])\b", t)
    if wm:
        var = wm.group(1)
    bounds = _bounds(t)
    rest = t[m.end():]
    rest = re.sub(r"^\s*(?:of\s+|the\s+|curve\s+|graph\s+|function\s+)*", "", rest)
    if bounds:  # "integral from 0 to 2 of 3x^2 dx": skip the bounds when they come first
        s0, s1 = bounds[2]
        if s0 >= m.end() and t[m.end():s0].strip() in ("", "of", "the", "of the"):
            rest = t[s1:]
    rest = re.sub(r"^\s*(?:of\s+|the\s+|curve\s+|graph\s+(?:of\s+)?|function\s+)*", "", rest)
    found = _after(rest, var)
    if not found:
        d = _definition(t, var=var)
        if d:
            found = (d[1], d[2], "")
    if not found:
        segment = t if not bounds else t[:bounds[2][0]] + " , " + t[bounds[2][1]:]
        found = _scan(segment, var)
    if not found:
        return None
    f, x, _ = found
    if area and not bounds and re.search(r"\b(?:x-axis|x axis|axis)\b", t):
        roots = _real_roots(f, x)
        if len(roots) >= 2:
            bounds = (roots[0], roots[-1], (0, 0))
    if bounds:
        return _definite(f, x, bounds[0], bounds[1], area, o)
    if area:
        return None
    F, steps = _antiderivative(f, x)
    shown = _abs_logs(F, f, x)
    back = _timed(lambda: sp.simplify(sp.diff(F, x) - f) == 0, limit=1.5)
    steps.append(f"result: {pe(shown)} + C")
    return _sol("integral", f"∫ {pe(f)} d{x}", f"{pe(shown)} + C", steps,
                f"d/d{x} [{pe(F)}] = {pe(f)} {'✓' if back else '✗'}",
                tex_statement=f"\\int {sp.latex(f)}\\, d{x}", tex_answer=f"\\int {sp.latex(f)}\\, d{x} = {sp.latex(shown)} + C")


def _real_roots(f, x) -> list:
    try:
        sols = _timed(sp.solveset, f, x, sp.S.Reals, limit=1.5)
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(sols, sp.FiniteSet):
        return []
    return sorted((s for s in sols if s.is_real), key=lambda s: float(s))


def _definite(f, x, a, b, area: bool, o: _Opts) -> Solution:
    if a.is_finite and b.is_finite and float(a) > float(b) and area:
        a, b = b, a
    F, steps = _antiderivative(f, x)
    val = _timed(sp.integrate, f, (x, a, b))
    if val.has(sp.Integral):
        raise _Fail("I couldn't evaluate that integral exactly")
    if val.has(sp.nan, sp.zoo) or val in (sp.oo, -sp.oo):
        return _sol("definite_integral", f"∫ from {pe(a)} to {pe(b)} of {pe(f)} d{x}", "diverges (the integral is infinite)",
                    steps + [f"antiderivative F({x}) = {pe(F)}", "the integrand blows up inside the interval, so the area is infinite"])
    val = _nice(sp.simplify(val))
    steps.append(f"antiderivative: F({x}) = {pe(_abs_logs(F, f, x))}")
    steps.append(f"formula: ∫ from a to b of f({x}) d{x} = F(b) − F(a)  (fundamental theorem of calculus)")
    if a.is_finite and b.is_finite:
        Fa, Fb = sp.simplify(F.subs(x, a)), sp.simplify(F.subs(x, b))
        steps.append(f"substitute: F({pe(b)}) − F({pe(a)}) = {_pw(Fb)} − {_pw(Fa)}")
    else:
        steps.append(f"improper integral: take the limit of F at {'∞' if not b.is_finite else '-∞'}")
    unit = ""
    if area:
        unit = "square units"
        cuts = [r for r in _real_roots(f, x) if float(a) < float(r) < float(b)]
        if cuts:
            pts = [a, *cuts, b]
            pieces = [sp.simplify(_timed(sp.integrate, f, (x, p, q))) for p, q in zip(pts, pts[1:])]
            total = _nice(sp.simplify(sum(abs(p) for p in pieces)))
            steps.append(f"f({x}) changes sign at {x} = {', '.join(pe(c) for c in cuts)}, so area = ∫|f| = "
                         + " + ".join(_pw(abs(p)) for p in pieces))
            val = total
        elif val.is_negative:
            steps.append(f"the curve is below the axis there, so the area is |{pe(val)}|")
            val = -val
    steps.append(f"result: {_short(val)}" + (f" {unit}" if unit else ""))
    check = _quad_check(abs(f) if area else f, x, a, b, val)
    problem = f"{'area: ' if area else ''}∫ from {pe(a)} to {pe(b)} of {pe(f)} d{x}"
    return _sol("definite_integral", problem, _val(val, o, unit), steps, check,
                tex_statement=f"\\int_{{{sp.latex(a)}}}^{{{sp.latex(b)}}} {sp.latex(f)}\\, d{x}",
                tex_answer=f"\\int_{{{sp.latex(a)}}}^{{{sp.latex(b)}}} {sp.latex(f)}\\, d{x} = {sp.latex(val)}")


# ---------------------------------------------------------------- limits

_APPROACH = r"(?:->|-->|=>|approaches|approaching|goes to|going to|tends to|tending to|tends towards|heads to|heads towards|gets close to|gets closer to|nears|to)"
_TARGET = r"(negative infinity|minus infinity|-\s*infinity|\+?\s*infinity|-?inf\b|[-+]?[\w.^/()]+?)(\^?[+-](?![\w(]))?(?=\s|$|[,?;:)}])"


def limit(t: str, o: _Opts) -> Solution | None:
    a_m = re.search(rf"\blim(?:it)?\b\s*(?:of\s+)?(?:_\s*)?\(?\{{?\s*(?:as\s+)?([a-z])\s*{_APPROACH}\s*{_TARGET}\s*\}}?\)?", t)
    b_m = re.search(rf"\bas\s+([a-z])\s*{_APPROACH}\s*{_TARGET}", t)
    m = a_m or b_m
    if not m or not (a_m or re.search(r"\blim(?:it)?\b|\bapproach(?:es)?\b|\bwhat does\b|\bvalue\b|\btend\b|\bgo(?:es)? to\b", t)):
        return None
    var, tgt, side = m.group(1), m.group(2).replace(" ", ""), m.group(3)
    if tgt in ("negativeinfinity", "minusinfinity", "-infinity", "-inf"):
        a = -sp.oo
    elif tgt in ("infinity", "+infinity", "inf"):
        a = sp.oo
    else:
        a = _number(tgt)
    if a is None:
        return None
    direction = None
    if side:
        direction = "+" if "+" in side else "-"
    sm = re.search(r"from\s+the\s+(right|left|above|below)|\b(right|left)[- ]hand(?:ed)?\b|\bfrom\s+(right|left|above|below)\b", t)
    if sm:
        word = next(g for g in sm.groups() if g)
        direction = "+" if word in ("right", "above") else "-"
    segment = t[:m.start()] + " , " + t[m.end():]
    segment = re.sub(r"\b(?:from\s+the\s+(?:right|left|above|below)|(?:right|left)[- ]hand(?:ed)?(?:\s+limit)?)\b", " , ", segment)
    found = None
    if m is a_m:
        found = _after(t[m.end():], var)
    if not found:
        after = t[m.end():]
        if re.match(r"\s*,?\s*(?:of\b|\()", after):
            found = _after(after, var)
    if not found:
        found = _scan(segment, var)
    if not found:
        return None
    f, x, _ = found
    if not f.has(x):
        return None
    return _limit(f, x, a, direction, o)


def _limit(f, x, a, direction, o: _Opts) -> Solution:
    arrow = f"{x}→{pe(a)}{direction or ''}"
    problem = f"lim {arrow} {pe(f)}"
    tex = f"\\lim_{{{x} \\to {sp.latex(a)}{'^' + direction if direction else ''}}} {sp.latex(f)}"
    steps: list[str] = []
    if a.is_finite and not direction:
        right = _timed(sp.limit, f, x, a, "+")
        left = _timed(sp.limit, f, x, a, "-")
        if right != left:
            steps.append(f"from the left: {pe(left)}; from the right: {pe(right)}")
            steps.append("result: the one-sided limits differ, so the limit does not exist")
            return _sol("limit", problem, f"does not exist (left {pe(left)}, right {pe(right)})", steps, tex_statement=tex)
        L = right
    else:
        L = _timed(sp.limit, f, x, a, direction or "+")
    if L.has(sp.Limit) or L.has(sp.nan) or isinstance(L, sp.AccumBounds):
        if isinstance(L, sp.AccumBounds):
            return _sol("limit", problem, "does not exist (it keeps oscillating)",
                        [f"as {x} → {pe(a)} the function oscillates between {pe(L.min)} and {pe(L.max)}"], tex_statement=tex)
        raise _Fail("I couldn't evaluate that limit")
    steps += _limit_steps(f, x, a, L)
    steps.append(f"result: {_short(L)}")
    check = ""
    try:
        if a.is_finite:
            eps = 1e-4
            pts = [float(a) + eps] if direction == "+" else [float(a) - eps] if direction == "-" else [float(a) - eps, float(a) + eps]
            vals = [_f(f, x, sp.Float(p, 30)) for p in pts]
            if L.is_finite and all(v is not None and abs(v - float(L)) < 1e-2 * max(1.0, abs(float(L))) for v in vals):
                check = f"near {x} = {pe(a)}: f ≈ {', '.join(_fmt4(v) for v in vals)} → {_short(L)} ✓"
        else:
            big = sp.Integer(10) ** 6 * (1 if a == sp.oo else -1)
            v = _f(f, x, big)
            if L.is_finite and v is not None and abs(v - float(L)) < 1e-2 * max(1.0, abs(float(L))):
                check = f"at {x} = {pe(big)}: f ≈ {_fmt4(v)} → {_short(L)} ✓"
    except (TypeError, ValueError, OverflowError):
        check = ""
    return _sol("limit", problem, _val(L, o), steps, check, tex_statement=tex, tex_answer=f"{tex} = {sp.latex(L)}")


def _limit_steps(f, x, a, L) -> list[str]:
    num, den = sp.fraction(sp.together(f))
    if a.is_finite:
        try:
            direct = f.subs(x, a)
        except (TypeError, ValueError, ZeroDivisionError):
            direct = sp.nan
        if direct.is_finite and not direct.has(sp.nan, sp.zoo) and sp.simplify(direct - L) == 0:
            return [f"f is continuous at {x} = {pe(a)}: substitute directly, f({pe(a)}) = {_short(direct)}"]
        n0, d0 = sp.simplify(num.subs(x, a)), sp.simplify(den.subs(x, a))
        if d0 == 0 and n0 != 0:
            return [f"substituting gives {_short(n0)}/0: the denominator → 0 while the numerator doesn't, so f grows without bound"]
        if n0 == 0 and d0 == 0:
            steps = [f"substitute {x} = {pe(a)}: 0/0, indeterminate"]
            if f.is_rational_function(x):
                g = sp.cancel(f)
                fn, fd = sp.factor(num), sp.factor(den)
                common = sp.gcd(num, den)
                steps.append(f"factor: {_pw(fn)} / {_pw(fd)}")
                if common.has(x):
                    steps.append(f"cancel the common factor {_pw(sp.factor(common))}: f = {pe(g)} for {x} ≠ {pe(a)}")
                steps.append(f"substitute: {pe(g)} at {x} = {pe(a)} → {_short(L)}")
                return steps
            steps.append("rule: L'Hôpital — differentiate the top and the bottom")
            for _ in range(4):
                num, den = sp.diff(num, x), sp.diff(den, x)
                steps.append(f"lim {_pw(num)} / {_pw(den)}")
                n0, d0 = sp.simplify(num.subs(x, a)), sp.simplify(den.subs(x, a))
                if not (n0 == 0 and d0 == 0):
                    break
            if d0 != 0:
                steps.append(f"substitute {x} = {pe(a)}: {_short(n0)}/{_short(d0)} = {_short(L)}")
            return steps
        return [f"evaluate the limit as {x} → {pe(a)}"]
    if f.is_rational_function(x) and den.has(x):
        pn, pd = sp.degree(num, x), sp.degree(den, x)
        ln, ld = sp.LC(sp.Poly(num, x)), sp.LC(sp.Poly(den, x))
        steps = [f"rational function: divide top and bottom by {x}^{pd}, the highest power in the denominator"]
        if pn < pd:
            steps.append(f"degree of top ({pn}) < degree of bottom ({pd}), so f → 0")
        elif pn == pd:
            steps.append(f"same degree ({pn}): the limit is the ratio of leading coefficients {pe(ln)}/{pe(ld)}")
        else:
            steps.append(f"degree of top ({pn}) > degree of bottom ({pd}), so f grows without bound")
        return steps
    if den.has(x) and num.has(x):
        n_inf, d_inf = sp.limit(num, x, a), sp.limit(den, x, a)
        if n_inf.is_infinite and d_inf.is_infinite:
            nd, dd = sp.diff(num, x), sp.diff(den, x)
            return [f"{pe(num)} and {pe(den)} both → ∞: L'Hôpital's rule", f"lim {_pw(nd)} / {_pw(dd)} = {_short(L)}"]
    return [f"as {x} → {pe(a)}, f({x}) = {pe(f)} → {_short(L)}"]


# ---------------------------------------------------------------- tangent and normal lines, slopes

def tangent(t: str, o: _Opts) -> Solution | None:
    m = re.search(r"\btangent\b|\bnormal\s+(?:line|to)\b|\b(?:slope|gradient|steepness)\b", t)
    if not m:
        return None
    normal = bool(re.search(r"\bnormal\b", t))
    slope_only = bool(re.search(r"\b(?:slope|gradient|steepness)\b", t)) and not re.search(r"\b(?:equation|line)\b", t)
    if re.search(r"\b(?:slope|gradient)\s+of\s+(?:the\s+)?(?:tangent|normal)\b", t) and not re.search(r"\bequation\b", t):
        slope_only = True
    d = _definition(t)
    found = (d[1], d[2], "") if d else None
    if not found:
        for k in re.finditer(r"\b(?:tangent|normal)(?:\s+line)?\s+(?:to|of|for|on|at)\b(?:\s+the)?(?:\s+(?:curve|graph|function|parabola))?(?:\s+of)?|"
                             r"\b(?:slope|gradient|steepness)\s+(?:of|for)\b(?:\s+the)?(?:\s+(?:curve|graph|function|parabola|tangent(?:\s+line)?(?:\s+to)?))?(?:\s+the)?(?:\s+(?:curve|graph))?(?:\s+of)?", t):
            found = _after(t[k.end():])
            if found:
                break
    if not found:
        return None
    f, x, _ = found
    p = _point(t, str(x))
    horizontal = re.search(r"\bhorizontal\b", t)
    if not p and not horizontal:
        return None
    fp = _nice(_timed(sp.diff, f, x))
    steps = _d_steps(f, x) + [f"f′({x}) = {pe(fp)}"]
    if horizontal and not p:
        xs = _real_roots(fp, x)
        if not xs:
            return _sol("tangent", f"horizontal tangents of y = {pe(f)}", "none (f′ is never 0)", steps + [f"f′({x}) = 0 has no real solution"])
        pts = [f"({_short(c)}, {_short(sp.simplify(f.subs(x, c)))})" for c in xs]
        steps.append(f"horizontal tangent where f′({x}) = 0: {x} = {', '.join(pe(c) for c in xs)}")
        return _sol("tangent", f"horizontal tangents of y = {pe(f)}", "at " + ", ".join(pts), steps)
    a, y_given = p
    fa = sp.simplify(f.subs(x, a))
    if not fa.is_finite:
        raise _Fail(f"the curve isn't defined at {x} = {pe(a)}")
    m_ = sp.simplify(fp.subs(x, a))
    if not m_.is_finite:
        raise _Fail(f"the tangent at {x} = {pe(a)} is vertical (the slope is infinite)")
    note = ""
    if y_given is not None and sp.simplify(y_given - fa) != 0:
        note = f" (note: ({pe(a)}, {pe(y_given)}) isn't on the curve; f({pe(a)}) = {pe(fa)})"
    steps.append(f"slope at {x} = {pe(a)}: f′({pe(a)}) = {_short(m_)}")
    if slope_only and not normal:
        steps.append(f"result: slope = {_short(m_)}")
        return _sol("tangent", f"slope of y = {pe(f)} at {x} = {pe(a)}", _val(m_, o) + note, steps,
                    _slope_check(f, fp, x, a))
    if normal:
        if m_ == 0:
            line = sp.Eq(x, a)
            steps.append("the tangent is horizontal, so the normal is vertical")
            ans = f"{x} = {pe(a)}"
            return _sol("tangent", f"normal to y = {pe(f)} at {x} = {pe(a)}", ans + note, steps)
        slope = -1 / m_
        steps.append(f"normal slope = −1/f′({pe(a)}) = {_short(slope)}")
        if slope_only:
            return _sol("tangent", f"slope of the normal to y = {pe(f)} at {x} = {pe(a)}", _val(slope, o) + note, steps)
    else:
        slope = m_
    y = sp.Symbol("y")
    line = sp.expand(slope * (x - a) + fa)
    steps += [f"formula: y − f(a) = m({x} − a)", f"known: a = {pe(a)}, f({pe(a)}) = {_short(fa)}, m = {_short(slope)}",
              f"substitute: y − {_pw(fa)} = {_pw(slope)}({x} − {_pw(a)})", f"result: y = {pe(line)}"]
    check = f"at {x} = {pe(a)} the line gives y = {pe(sp.simplify(line.subs(x, a)))} = f({pe(a)}) ✓"
    del y
    kind = "normal" if normal else "tangent"
    return _sol("tangent", f"{kind} to y = {pe(f)} at {x} = {pe(a)}", f"y = {pe(line)}" + note, steps, check)


# ---------------------------------------------------------------- stationary points, maxima and minima

_X_WORDS = re.compile(r"\b(?:stationary|turning|critical|extreme)\s+(?:points?|values?|numbers?)\b|\bextrem(?:a|um|ums)\b|"
                      r"\b(?:local|relative|global|absolute)\s+(?:max\w*|min\w*|extrem\w*)|\bmaximi[sz]e\b|\bminimi[sz]e\b|"
                      r"\b(?:max(?:imum|ima)?|min(?:imum|ima)?)\b|\b(?:largest|smallest|greatest|least|highest|lowest|biggest)\s+"
                      r"(?:possible\s+)?(?:value|point|output|height)\b|\binflection\b|\b(?:increasing|decreasing)\b|\bvertex\b|"
                      r"\bconcav\w*")


def extrema(t: str, o: _Opts) -> Solution | None:
    m = _X_WORDS.search(t)
    if not m:
        return None
    bounds = _bounds(t)
    d = _definition(t)
    found = (d[1], d[2], d[0]) if d else None
    if not found:
        for k in re.finditer(r"\b(?:max(?:imum)?|min(?:imum)?|values?|points?|extrema|extremum|vertex|maximi[sz]e|minimi[sz]e|"
                             r"inflection|increasing|decreasing|concave(?:\s+up|\s+down)?)\b(?:\s+(?:value|point)s?)?(?:\s+of)?", t):
            found = _after(t[k.end():])
            if found:
                break
    if not found:
        segment = t if not bounds else t[:bounds[2][0]] + " , " + t[bounds[2][1]:]
        found = _scan(segment)
    if not found:
        return None
    f, x, fname = found
    if not f.has(x):
        return None
    fname = fname if fname and fname not in "yx" else "f"
    want_max = bool(re.search(r"\bmax\w*|\b(?:largest|greatest|highest|biggest)\b", t))
    want_min = bool(re.search(r"\bmin\w*|\b(?:smallest|least|lowest)\b", t))
    if re.search(r"\binflection\b|\bconcav", t):
        return _inflection(f, x, o)
    if re.search(r"\b(?:increasing|decreasing)\b", t) and not (want_max or want_min):
        return _monotone(f, x)
    if re.search(r"\b(?:stationary|turning|critical)\b|\b(?:local|relative)\b|\bextrem", t) or not (want_max or want_min):
        want_max = want_min = True
        all_points = True
    else:
        all_points = False
    return _extrema(f, x, bounds, want_max, want_min, all_points, fname, o, t)


def _classify(f, x, c):
    d1, d2 = sp.diff(f, x), sp.diff(f, x, 2)
    s = sp.simplify(d2.subs(x, c))
    if s.is_positive:
        return "minimum", f"{pe(sp.Symbol('f″'))}({pe(c)}) = {_short(s)} > 0 → local minimum"
    if s.is_negative:
        return "maximum", f"f″({pe(c)}) = {_short(s)} < 0 → local maximum"
    h = sp.Rational(1, 100)
    lo, hi = _f(d1, x, c - h), _f(d1, x, c + h)
    if lo is None or hi is None:
        return "unknown", f"f″({pe(c)}) = 0 and the sign test fails"
    if lo < 0 < hi:
        return "minimum", f"f″({pe(c)}) = 0; f′ goes − to + → local minimum"
    if lo > 0 > hi:
        return "maximum", f"f″({pe(c)}) = 0; f′ goes + to − → local maximum"
    return "inflection", f"f″({pe(c)}) = 0 and f′ doesn't change sign → stationary point of inflection"


def _unit(t: str) -> tuple[str, str]:
    """(output unit, input unit) when the problem gives them: '... height in metres', 'profit in $'."""
    m = re.search(r"\b(?:in\s+)(metres|meters|m|feet|ft|cm|km)\b", t)
    u = {"metres": "m", "meters": "m", "feet": "ft"}.get(m.group(1), m.group(1)) if m else ""
    return u, ""


def _extrema(f, x, bounds, want_max, want_min, all_points, fname, o: _Opts, t: str) -> Solution:
    fp = _nice(_timed(sp.diff, f, x))
    dom = sp.Interval(min(bounds[0], bounds[1]), max(bounds[0], bounds[1])) if bounds else sp.S.Reals
    crit = _timed(sp.solveset, fp, x, dom)
    steps = ["formula: stationary points are where f′(x) = 0".replace("x", str(x))]
    steps += [s for s in _d_steps(f, x) if not s.startswith("result")][:5]
    steps.append(f"f′({x}) = {pe(fp)}")
    if not isinstance(crit, sp.FiniteSet):
        raise _Fail("f′ = 0 has infinitely many solutions; give an interval, e.g. 'on [0, 2pi]'")
    cs = sorted((c for c in crit if c.is_real), key=lambda c: float(c))
    if len(cs) > 8:
        raise _Fail("too many stationary points to list")
    steps.append(f"solve {pe(fp)} = 0: " + (", ".join(f"{x} = {_short(c)}" for c in cs) if cs else "no real solutions"))
    if cs and len(cs) <= 6:
        steps.append(f"f″({x}) = {pe(_nice(sp.diff(f, x, 2)))}")
    pts = []
    for c in cs:
        kind, why = _classify(f, x, c)
        v = sp.simplify(f.subs(x, c))
        pts.append((c, v, kind))
        steps.append(f"{x} = {pe(c)}: {why.replace('f″', 'f″')}, {fname}({pe(c)}) = {_short(v)}")
    out_unit = _unit(t)[0]
    unit = f" {out_unit}" if out_unit else ""
    if bounds:
        a, b = dom.start, dom.end
        fa, fb = sp.simplify(f.subs(x, a)), sp.simplify(f.subs(x, b))
        steps.append(f"endpoints: {fname}({pe(a)}) = {_short(fa)}, {fname}({pe(b)}) = {_short(fb)}")
        cands = [(a, fa), *[(c, v) for c, v, _ in pts], (b, fb)]
        cands = [(c, v) for c, v in cands if v.is_finite]
        hi = max(cands, key=lambda cv: float(cv[1]))
        lo = min(cands, key=lambda cv: float(cv[1]))
        parts = []
        if want_max:
            parts.append(f"maximum {_val(hi[1], o)}{unit} at {x} = {_short(hi[0])}")
        if want_min:
            parts.append(f"minimum {_val(lo[1], o)}{unit} at {x} = {_short(lo[0])}")
        steps.append("result: compare the stationary values with the endpoints: " + "; ".join(parts))
        return _sol("extrema", f"extrema of {fname}({x}) = {pe(f)} on [{pe(a)}, {pe(b)}]", "; ".join(parts), steps,
                    f"largest of {', '.join(_fmt4(float(v)) for _, v in cands)} is {_fmt4(float(hi[1]))} ✓" if want_max and not want_min
                    else f"smallest of {', '.join(_fmt4(float(v)) for _, v in cands)} is {_fmt4(float(lo[1]))} ✓" if want_min and not want_max else "")
    if not cs:
        return _sol("extrema", f"stationary points of {fname}({x}) = {pe(f)}", "none: f′ is never 0, so there's no local max or min",
                    steps + ["result: no stationary points"])
    try:
        ends = [_timed(sp.limit, f, x, sp.oo, limit=1.0), _timed(sp.limit, f, x, -sp.oo, limit=1.0)]
    except Exception:  # noqa: BLE001
        ends = []
    maxes = [(c, v) for c, v, k in pts if k == "maximum"]
    mins = [(c, v) for c, v, k in pts if k == "minimum"]
    infl = [(c, v) for c, v, k in pts if k == "inflection"]
    check = ""
    if pts:
        c, v, k = pts[0]
        h = sp.Rational(1, 10)
        lo_, hi_ = _f(f, x, c - h), _f(f, x, c + h)
        if lo_ is not None and hi_ is not None and k in ("maximum", "minimum"):
            ok = (lo_ < float(v) and hi_ < float(v)) if k == "maximum" else (lo_ > float(v) and hi_ > float(v))
            check = (f"{fname}({pe(c - h)}) = {_fmt4(lo_)} and {fname}({pe(c + h)}) = {_fmt4(hi_)} are both "
                     f"{'below' if k == 'maximum' else 'above'} {_fmt4(float(v))} {'✓' if ok else '✗'}")
    if all_points:
        parts = [f"local maximum at ({_short(c)}, {_short(v)})" for c, v in maxes]
        parts += [f"local minimum at ({_short(c)}, {_short(v)})" for c, v in mins]
        parts += [f"stationary inflection at ({_short(c)}, {_short(v)})" for c, v in infl]
        parts.sort(key=lambda s: float(sp.sympify(next(c for c, v, k in pts if f"({_short(c)}," in s))))
        steps.append("result: " + "; ".join(parts))
        return _sol("extrema", f"stationary points of {fname}({x}) = {pe(f)}", "; ".join(parts), steps, check)
    parts = []
    for want, lst, word, sign in ((want_max, maxes, "maximum", 1), (want_min, mins, "minimum", -1)):
        if not want:
            continue
        if not lst:
            parts.append(f"no {word} ({fname} has no local {word})")
            continue
        c, v = max(lst, key=lambda cv: sign * float(cv[1]))
        beyond = [e for e in ends if (sign * e).is_infinite and sign * e > 0] if ends else []
        unbounded_end = any(sign * float(e) > sign * float(v) if e.is_finite else (sign * e) is sp.oo for e in ends)
        if beyond or unbounded_end:
            parts.append(f"no global {word} ({fname} → {'∞' if sign > 0 else '-∞'}); local {word} {_val(v, o)}{unit} at {x} = {_short(c)}")
        else:
            parts.append(f"{word} {_val(v, o)}{unit} at {x} = {_short(c)}")
    steps.append("result: " + "; ".join(parts))
    return _sol("extrema", f"{'max' if want_max else 'min'} of {fname}({x}) = {pe(f)}", "; ".join(parts), steps, check)


def _inflection(f, x, o: _Opts) -> Solution:
    f2 = _nice(sp.diff(f, x, 2))
    roots = _real_roots(f2, x)
    steps = [f"f′({x}) = {pe(_nice(sp.diff(f, x)))}", f"f″({x}) = {pe(f2)}", "formula: inflection where f″ changes sign"]
    pts = []
    for c in roots:
        h = sp.Rational(1, 100)
        lo, hi = _f(f2, x, c - h), _f(f2, x, c + h)
        if lo is not None and hi is not None and lo * hi < 0:
            v = sp.simplify(f.subs(x, c))
            pts.append(f"({_short(c)}, {_short(v)})")
            steps.append(f"{x} = {pe(c)}: f″ changes sign ({'−→+' if lo < 0 else '+→−'}), f = {_short(v)}")
        else:
            steps.append(f"{x} = {pe(c)}: f″ = 0 but doesn't change sign, so not an inflection point")
    ans = "inflection at " + ", ".join(pts) if pts else "no inflection points"
    steps.append(f"result: {ans}")
    return _sol("extrema", f"inflection points of {pe(f)}", ans, steps)


def _monotone(f, x) -> Solution:
    fp = _nice(sp.diff(f, x))
    up = _timed(sp.solve_univariate_inequality, sp.Gt(fp, 0), x, False, sp.S.Reals, limit=1.5)
    down = _timed(sp.solve_univariate_inequality, sp.Lt(fp, 0), x, False, sp.S.Reals, limit=1.5)

    def show(s):
        if s is sp.EmptySet:
            return "nowhere"
        parts = sp.Union.make_args(s) if isinstance(s, sp.Union) else [s]
        return " ∪ ".join(f"({pe(p.start)}, {pe(p.end)})" if isinstance(p, sp.Interval) else pe(p) for p in parts)
    steps = [f"f′({x}) = {pe(fp)}", "formula: f is increasing where f′ > 0 and decreasing where f′ < 0",
             f"f′ > 0 on {show(up)}", f"f′ < 0 on {show(down)}"]
    ans = f"increasing on {show(up)}; decreasing on {show(down)}"
    steps.append(f"result: {ans}")
    return _sol("extrema", f"where {pe(f)} increases and decreases", ans, steps)


# ---------------------------------------------------------------- optimisation word problems

_LEN = r"(m|metres?|meters?|ft|feet|foot|yd|yards?|km|cm|mm|in|inch(?:es)?)"
_LEN_SHORT = {"metre": "m", "metres": "m", "meter": "m", "meters": "m", "feet": "ft", "foot": "ft", "yard": "yd",
              "yards": "yd", "inch": "in", "inches": "in"}
_COUNT = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6}


def _u(s: str | None) -> str:
    return _LEN_SHORT.get(s, s) if s else ""


def optimisation(t: str, o: _Opts) -> Solution | None:
    for fn in (_fencing, _box, _two_numbers, _can):
        sol = fn(t, o)
        if sol:
            return sol
    return None


def _fencing(t: str, o: _Opts) -> Solution | None:
    if not (re.search(r"\bfenc(?:e|es|ing)\b|\bperimeter\b", t) and re.search(r"\b(?:area|enclose\w*|pen|pens|field|garden|paddock|plot|yard|enclosure|rectangle|rectangular|region)\b", t)):
        return None
    wall = bool(re.search(r"\b(?:wall|river|barn|building|house|stream|cliff|existing fence|three sides|3 sides)\b|\bone side (?:is|doesn't|does not|needs no|won't|against|along)", t))
    km = re.search(r"\b(?:divided|split|separated|partitioned)\s+into\s+(two|three|four|five|six|\d)\s+(?:equal\s+|identical\s+|adjacent\s+)?(?:pens|parts|sections|plots|rectangles|enclosures|areas|fields|paddocks)|\b(two|three|four|five|six|\d)\s+(?:equal\s+|identical\s+|adjacent\s+)?(?:pens|paddocks|enclosures)\b", t)
    k = _COUNT.get((km.group(1) or km.group(2)), 1) if km else 1
    s = 1 if wall else 2
    least = re.search(r"\b(?:least|minimum|minimi[sz]e|smallest|shortest|min)\b", t)
    if least:
        am = re.search(rf"(\d+(?:\.\d+)?)\s*(?:sq(?:uare)?\.?\s*{_LEN}|{_LEN}\s*(?:\^2|2\b|squared))", t)
        if not am:
            return None
        area_v = sp.Rational(am.group(1))
        unit = _u(am.group(2) or am.group(3))
        # minimise (k+1)x + s·y with x·y = A: y = A/x, L(x) = (k+1)x + sA/x, L′ = 0 → x = √(sA/(k+1))
        xx = sp.sqrt(s * area_v / (k + 1))
        yy = area_v / xx
        total = sp.nsimplify((k + 1) * xx + s * yy)
        X = sp.Symbol("x")
        L = (k + 1) * X + s * area_v / X
        steps = [f"let x be the side{' perpendicular to the wall' if wall else ''} and y the other side; area x·y = {pe(area_v)} → y = {pe(area_v)}/x",
                 f"fencing L(x) = {pe(L)}", f"L′(x) = {pe(sp.diff(L, X))} = 0 → x = {_short(xx)}",
                 f"L″(x) = {pe(sp.diff(L, X, 2))} > 0 → minimum", f"y = {_short(yy)}",
                 f"result: {_short(total)} {unit} of fencing"]
        return _sol("optimisation", f"least fencing for {pe(area_v)} {unit}²", _val(total, o, unit),
                    steps, f"{_fmt4(float(xx))} × {_fmt4(float(yy))} = {_fmt4(float(xx * yy))} {unit}² ✓")
    if not re.search(r"\b(?:max\w*|largest|greatest|biggest|most|optimal|best|dimensions)\b", t):
        return None
    pm = re.search(rf"(\d+(?:\.\d+)?)\s*{_LEN}\b(?:\s+(?:of|worth of|long))?(?:\s+\w+){{0,2}}?\s*(?:fenc|wire|perimeter|of\s+fenc)", t) \
        or re.search(rf"(?:perimeter|fenc\w*)\D{{0,30}}?(\d+(?:\.\d+)?)\s*{_LEN}?\b", t)
    if not pm:
        return None
    P = sp.Rational(pm.group(1))
    unit = _u(pm.group(2))
    X = sp.Symbol("x")
    # (k+1) widths x and s lengths y: (k+1)x + s·y = P → y = (P − (k+1)x)/s, A(x) = x·y
    y_expr = (P - (k + 1) * X) / s
    A = sp.expand(X * y_expr)
    dA = sp.diff(A, X)
    xs = sp.solve(dA, X)[0]
    ys = y_expr.subs(X, xs)
    Amax = A.subs(X, xs)
    u2 = f"{unit}²" if unit else "square units"
    widths = f"{k + 1} sides of length x" if k > 1 else "2 sides of length x" if not wall else "the 2 sides of length x (perpendicular to the wall)"
    steps = [f"let x be the width and y the length; fencing covers {widths} and {s} side{'s' if s > 1 else ''} of length y",
             f"constraint: {k + 1}x + {'' if s == 1 else '2'}y = {pe(P)} → y = {pe(y_expr)}",
             f"area: A(x) = x·y = {pe(A)}", f"A′(x) = {pe(dA)} = 0 → x = {_short(xs)}",
             f"A″(x) = {pe(sp.diff(A, X, 2))} < 0 → maximum", f"y = {_short(ys)}",
             f"result: {_short(Amax)} {u2} ({_short(xs)} {unit} × {_short(ys)} {unit})".replace("  ", " ")]
    near = [A.subs(X, xs - 1), A.subs(X, xs + 1)] if xs > 1 else [A.subs(X, xs * sp.Rational(9, 10)), A.subs(X, xs * sp.Rational(11, 10))]
    check = f"nearby widths give {', '.join(_fmt4(float(v)) for v in near)} {u2}, both less ✓"
    dims = f"{_short(xs)} {unit} by {_short(ys)} {unit}".replace("  ", " ").strip()
    return _sol("optimisation", f"maximum area with {pe(P)} {unit} of fencing".replace("  ", " "),
                f"{_val(Amax, o, u2)} ({dims})", steps, check)


def _box(t: str, o: _Opts) -> Solution | None:
    if not (re.search(r"\bbox\b|\btray\b", t) and re.search(r"\b(?:cut|cutting|corners?|squares?)\b", t)
            and re.search(r"\b(?:volume|max\w*|largest|greatest|biggest)\b", t)):
        return None
    dm = re.search(rf"(\d+(?:\.\d+)?)\s*{_LEN}?\s*(?:by|x|\*)\s*(\d+(?:\.\d+)?)\s*{_LEN}?", t)
    if dm:
        a, b = sp.Rational(dm.group(1)), sp.Rational(dm.group(3))
        unit = _u(dm.group(2) or dm.group(4))
    else:
        sm = re.search(rf"(\d+(?:\.\d+)?)\s*-?\s*{_LEN}?\s*(?:-|\s)?(?:by\s+\d+\s+)?square\b|\bsquare\b[^.?]*?(?:side|sides|of|measuring|is)\D{{0,20}}?(\d+(?:\.\d+)?)\s*{_LEN}?", t)
        if not sm:
            return None
        a = b = sp.Rational(sm.group(1) or sm.group(3))
        unit = _u(sm.group(2) or sm.group(4))
    X = sp.Symbol("x")
    V = X * (a - 2 * X) * (b - 2 * X)
    dV = sp.expand(sp.diff(V, X))
    roots = [r for r in sp.solve(dV, X) if r.is_real and 0 < r < min(a, b) / 2]
    if not roots:
        return None
    xs = roots[0]
    Vmax = sp.nsimplify(sp.expand(V.subs(X, xs)))
    u3 = f"{unit}³" if unit else "cubic units"
    steps = [f"cut squares of side x from each corner and fold up: the box is {pe(a - 2 * X)} by {pe(b - 2 * X)} by x",
             f"volume: V(x) = x({pe(a - 2 * X)})({pe(b - 2 * X)})", f"V′(x) = {pe(dV)} = 0",
             f"x = {_short(xs)} (the other root makes a side ≤ 0), 0 < x < {pe(min(a, b) / 2)}",
             f"V″({pe(xs)}) = {_short(sp.diff(V, X, 2).subs(X, xs))} < 0 → maximum",
             f"result: V = {_short(Vmax)} {u3}"]
    h = min(sp.Rational(1, 2), xs / 2)
    near = [V.subs(X, xs - h), V.subs(X, xs + h)]
    check = f"x = {pe(xs - h)} and {pe(xs + h)} give {', '.join(_fmt4(float(v)) for v in near)} {u3}, both less ✓"
    return _sol("optimisation", f"open box from a {pe(a)} × {pe(b)} {unit} sheet, maximum volume".replace("  ", " "),
                f"{_val(Vmax, o, u3)} (cut {_short(xs)} {unit} squares)".replace("  ", " "), steps, check)


def _two_numbers(t: str, o: _Opts) -> Solution | None:
    if not re.search(r"\btwo\s+(?:positive\s+|non-negative\s+|real\s+)*numbers\b", t):
        return None
    sm = re.search(r"\bsum\s+(?:is|of|=|equals|equal to|to)?\s*(\d+(?:\.\d+)?)|\b(?:add|adds|sum)\s+(?:up\s+)?to\s+(\d+(?:\.\d+)?)", t)
    pm = re.search(r"\bproduct\s+(?:is|of|=|equals|equal to)?\s*(\d+(?:\.\d+)?)", t)
    X = sp.Symbol("x")
    if sm and re.search(r"\bproduct\b", t) and re.search(r"\b(?:max\w*|largest|greatest|biggest|as large)\b", t):
        S = sp.Rational(sm.group(1) or sm.group(2))
        P = X * (S - X)
        steps = [f"numbers x and {pe(S)} − x; product P(x) = {pe(sp.expand(P))}", f"P′(x) = {pe(sp.diff(P, X))} = 0 → x = {pe(S / 2)}",
                 "P″(x) = -2 < 0 → maximum", f"result: {pe(S / 2)} and {pe(S / 2)}, product {pe(S ** 2 / 4)}"]
        return _sol("optimisation", f"two numbers with sum {pe(S)}, maximum product", f"{_val(S / 2, o)} and {_val(S / 2, o)} (product {_val(S ** 2 / 4, o)})",
                    steps, f"{pe(S / 2 - 1)} × {pe(S / 2 + 1)} = {pe((S / 2 - 1) * (S / 2 + 1))} < {pe(S ** 2 / 4)} ✓")
    if pm and re.search(r"\bsum\b", t) and re.search(r"\b(?:min\w*|smallest|least)\b", t):
        P = sp.Rational(pm.group(1))
        S = X + P / X
        xs = sp.sqrt(P)
        steps = [f"numbers x and {pe(P)}/x; sum S(x) = {pe(S)}", f"S′(x) = {pe(sp.diff(S, X))} = 0 → x = {_short(xs)}",
                 f"S″(x) = {pe(sp.diff(S, X, 2))} > 0 → minimum", f"result: {_short(xs)} and {_short(xs)}, sum {_short(2 * xs)}"]
        return _sol("optimisation", f"two positive numbers with product {pe(P)}, minimum sum",
                    f"{_val(xs, o)} and {_val(xs, o)} (sum {_val(2 * xs, o)})", steps)
    return None


def _can(t: str, o: _Opts) -> Solution | None:
    if not (re.search(r"\b(?:can|cylinder|cylindrical|tin)\b", t) and re.search(r"\b(?:minimi[sz]e|least|minimum|smallest|min)\b", t)
            and re.search(r"\b(?:surface|material|metal|area|aluminium|aluminum|sheet)\b", t)):
        return None
    vm = re.search(r"(\d+(?:\.\d+)?)\s*(cm\^3|cm3|cubic\s+(?:cm|centimetres?|centimeters?|m|metres?|meters?|in|inches)|ml|m\^3|m3|in\^3)", t)
    if not vm:
        return None
    V = sp.Rational(vm.group(1))
    u = vm.group(2)
    unit = "cm" if ("cm" in u or "cent" in u or u == "ml") else "in" if "in" in u else "m"
    open_top = bool(re.search(r"\b(?:open|no lid|without a lid|no top|open-top)\b", t))
    r = sp.Symbol("r")
    # closed: A = 2πr² + 2V/r; open: A = πr² + 2V/r
    A = (1 if open_top else 2) * sp.pi * r ** 2 + 2 * V / r
    rs = sp.root(V / sp.pi, 3) if open_top else sp.root(V / (2 * sp.pi), 3)
    hs = sp.simplify(V / (sp.pi * rs ** 2))
    Amin = sp.simplify(A.subs(r, rs))
    steps = [f"volume πr²h = {pe(V)} → h = {pe(V)}/(πr²)", f"surface area A(r) = {pe(A)}",
             f"A′(r) = {pe(sp.diff(A, r))} = 0 → r³ = {pe(V / sp.pi if open_top else V / (2 * sp.pi))}",
             f"r = {_short(rs)} {unit}, h = {_short(hs)} {unit} ({'h = r' if open_top else 'h = 2r'})",
             f"A″(r) > 0 → minimum; A = {_short(Amin)} {unit}²"]
    return _sol("optimisation", f"{'open' if open_top else 'closed'} cylinder of volume {pe(V)} {unit}³, least surface area",
                f"r = {_val(rs, o, unit)}, h = {_val(hs, o, unit)}", steps,
                f"πr²h = {_fmt4(float(sp.pi * rs ** 2 * hs))} {unit}³ ✓")


# ---------------------------------------------------------------- motion

_POS_NAMES, _VEL_NAMES, _ACC_NAMES = "sxphdy", "v", "a"


def motion(t: str, o: _Opts) -> Solution | None:
    asks_v = bool(re.search(r"\b(?:velocity|speed|how fast)\b", t))
    asks_a = bool(re.search(r"\bacceleration\b", t))
    asks_d = bool(re.search(r"\b(?:distance|how far|travel(?:s|led|ed|s)?)\b", t))
    asks_disp = bool(re.search(r"\b(?:displacement|net change in position|change in position)\b", t))
    asks_rest = bool(re.search(r"\b(?:at rest|stops|stop moving|momentarily stationary|changes? direction)\b", t))
    asks_pos = bool(re.search(r"\bposition\b", t))
    if not (asks_v or asks_a or asks_d or asks_disp or asks_rest):
        return None
    given, f, x = None, None, None
    d = _definition(t, names=_POS_NAMES + _VEL_NAMES + _ACC_NAMES)
    if d and d[2] == sp.Symbol("t") or (d and d[0] in _VEL_NAMES + _ACC_NAMES + "s"):
        name, f, x = d
        given = "pos" if name in _POS_NAMES else "vel" if name in _VEL_NAMES else "acc"
    else:
        for word, kind in (("position", "pos"), ("displacement", "pos"), ("height", "pos"), ("velocity", "vel"), ("acceleration", "acc")):
            mm = re.search(rf"\b{word}(?:\s+function)?\s+(?:is|of|given by|equals|=)\s+(?:given\s+by\s+)?", t)
            if mm:
                r = _after(t[mm.end():])
                if r:
                    f, x, given = r[0], r[1], kind
                    break
    if f is None:
        return None
    if given == "vel" and asks_v and not (asks_a or asks_d or asks_disp or asks_rest or asks_pos):
        given_word = "velocity"
    else:
        given_word = {"pos": "position", "vel": "velocity", "acc": "acceleration"}[given]
    lu = re.search(r"\b(metres|meters|metre|meter|km|cm|feet|foot|ft|miles?)\b|\bin\s+(m)\b|\b(m)/s\b|\b(m)\b(?=\s*(?:\)|,|$|and|\.))", t)
    L = ""
    if lu:
        L = _u(next(g for g in lu.groups() if g))
        L = {"mile": "miles", "miles": "miles"}.get(L, L)
    T = "s"
    if re.search(r"\b(?:minutes?|mins?)\b", t) and not re.search(r"\bseconds?\b", t):
        T = "min"
    elif re.search(r"\b(?:hours?|hrs?)\b", t) and not re.search(r"\bseconds?\b", t):
        T = "h"
    vu, au, du = (f"{L}/{T}", f"{L}/{T}²", L) if L else ("", "", "")
    bounds = _bounds(t)
    tp = None
    pm = re.search(rf"\b(?:at|when|after|for)\s+(?:time\s+)?(?:{x}\s*(?:=|is)\s*)?{_B}\s*(?:s|secs?|seconds?|minutes?|mins?|hours?|hrs?|h)?\b", t)
    if pm:
        tp = _number(pm.group(1))
    if tp is None:
        p = _point(t, str(x))
        tp = p[0] if p else None
    fname = {"pos": "s", "vel": "v", "acc": "a"}[given]
    problem = f"{given_word} {fname}({x}) = {pe(f)}"
    if (asks_d or asks_disp) and bounds:
        a, b = bounds[0], bounds[1]
        if given == "pos":
            v = _nice(sp.diff(f, x))
            pos = f
        elif given == "vel":
            v, pos = f, _antiderivative(f, x)[0]
        else:
            return None
        cuts = [c for c in _real_roots(v, x) if float(a) < float(c) < float(b)]
        pts = [a, *cuts, b]
        vals = [sp.simplify(pos.subs(x, p_)) for p_ in pts]
        disp = sp.simplify(vals[-1] - vals[0])
        steps = [f"velocity v({x}) = {pe(v)}" if given == "pos" else f"position (antiderivative) s({x}) = {pe(pos)} + C"]
        if asks_disp and not asks_d:
            steps += ["formula: displacement = s(b) − s(a) = ∫ v dt", f"substitute: s({pe(b)}) − s({pe(a)}) = {_pw(vals[-1])} − {_pw(vals[0])}",
                      f"result: {_short(disp)} {du}".rstrip()]
            return _sol("motion", f"{problem}, displacement from {x} = {pe(a)} to {pe(b)}", _val(disp, o, du), steps,
                        _quad_check(v, x, a, b, disp))
        legs = [sp.simplify(abs(q - p_)) for p_, q in zip(vals, vals[1:])]
        dist = _nice(sp.simplify(sum(legs)))
        steps.append("formula: distance = ∫ |v| dt (add up each leg, since direction can change)")
        if cuts:
            steps.append(f"v = 0 at {x} = {', '.join(_short(c) for c in cuts)}: the object turns around there")
        steps.append("substitute: " + " + ".join(f"|s({pe(q)}) − s({pe(p_)})|" for p_, q in zip(pts, pts[1:]))
                     + " = " + " + ".join(_pw(leg) for leg in legs))
        steps.append(f"result: {_short(dist)} {du}".rstrip())
        check = _quad_check(sp.Abs(v), x, a, b, dist)
        if asks_disp:
            steps.append(f"(displacement: {_short(disp)} {du})".replace(" )", ")"))
        return _sol("motion", f"{problem}, distance from {x} = {pe(a)} to {pe(b)}", _val(dist, o, du), steps, check)
    if asks_rest and not tp:
        v = _nice(sp.diff(f, x)) if given == "pos" else f if given == "vel" else None
        if v is None:
            return None
        ts = [c for c in _real_roots(v, x) if c >= 0]
        steps = [f"velocity v({x}) = {pe(v)}", f"at rest when v({x}) = 0: {x} = " + (", ".join(_short(c) for c in ts) if ts else "never (for t ≥ 0)")]
        ans = ", ".join(f"{x} = {_val(c, o, T)}" for c in ts) if ts else "never"
        steps.append(f"result: {ans}")
        return _sol("motion", f"{problem}, when at rest", ans, steps)
    if tp is None:
        if asks_a and given in ("pos", "vel"):
            acc = _nice(sp.diff(f, x, 2 if given == "pos" else 1))
            return _sol("motion", f"{problem}, acceleration", f"a({x}) = {pe(acc)}", _d_steps(f, x) + [f"result: a({x}) = {pe(acc)}"])
        if asks_v and given == "pos":
            v = _nice(sp.diff(f, x))
            return _sol("motion", f"{problem}, velocity", f"v({x}) = {pe(v)}", ["formula: v = ds/dt"] + _d_steps(f, x) + [f"result: v({x}) = {pe(v)}"])
        return None
    if asks_a:
        if given == "pos":
            v = _nice(sp.diff(f, x))
            acc = _nice(sp.diff(f, x, 2))
            steps = ["formula: a = dv/dt = d²s/dt²", f"v({x}) = {pe(v)}", f"a({x}) = {pe(acc)}"]
        elif given == "vel":
            acc = _nice(sp.diff(f, x))
            steps = ["formula: a = dv/dt"] + _d_steps(f, x) + [f"a({x}) = {pe(acc)}"]
        else:
            acc = f
            steps = []
        val = sp.simplify(acc.subs(x, tp))
        steps += [f"substitute: a({pe(tp)}) = {pe(acc.subs(x, sp.Symbol('(' + pe(tp) + ')')))}", f"result: {_short(val)} {au}".rstrip()]
        return _sol("motion", f"{problem}, acceleration at {x} = {pe(tp)}", _val(val, o, au), steps)
    if asks_v or (asks_pos and given == "vel"):
        if given == "pos":
            v = _nice(sp.diff(f, x))
            steps = ["formula: v = ds/dt"] + _d_steps(f, x) + [f"v({x}) = {pe(v)}"]
        elif given == "vel":
            v = f
            steps = []
        else:
            return None
        val = sp.simplify(v.subs(x, tp))
        speed = re.search(r"\bspeed\b", t) and not re.search(r"\bvelocity\b", t)
        steps.append(f"substitute: v({pe(tp)}) = {pe(v.subs(x, sp.Symbol('(' + pe(tp) + ')')))}")
        if speed:
            steps.append(f"speed = |v| = {_short(abs(val))}")
            val = abs(val)
        steps.append(f"result: {_short(val)} {vu}".rstrip())
        check = _slope_check(f, v, x, tp) if given == "pos" else ""
        return _sol("motion", f"{problem}, {'speed' if speed else 'velocity'} at {x} = {pe(tp)}", _val(val, o, vu), steps, check)
    return None


# ---------------------------------------------------------------- marginal revenue, cost and profit

def marginal(t: str, o: _Opts) -> Solution | None:
    m = re.search(r"\bmarginal\s+(revenue|cost|profit)\b|\b(mr|mc)\b", t)
    if not m:
        return None
    what = m.group(1) or {"mr": "revenue", "mc": "cost"}[m.group(2)]
    letter = {"revenue": "r", "cost": "c", "profit": "p"}[what]
    F, x = None, None
    d = _definition(t, names=letter)
    if d:
        F, x = d[1], d[2]
    elif what == "profit":
        r_, c_ = _definition(t, names="r"), _definition(t, names="c")
        if r_ and c_ and r_[2] == c_[2]:
            F, x = r_[1] - c_[1], r_[2]
    if F is None:
        mm = re.search(rf"\b{what}(?:\s+function)?\s+(?:is|of|given by|=)\s+", t)
        if mm:
            r = _after(t[mm.end():])
            if r:
                F, x = r[0], r[1]
    if F is None and what == "revenue":
        pm = re.search(r"\b(?:price|demand)\b[^.?]*?\bp\s*=\s*", t) or re.search(r"(?<![a-z])p\s*=\s*", t)
        if pm:
            r = _after(t[pm.end():])
            if r:
                F, x = sp.expand(r[0] * r[1]), r[1]
    if F is None:
        return None
    cur = next((c for c in ("$", "£", "€", "₹") if c in t), "$" if re.search(r"\bdollars?\b", t) else "")
    sym = {"revenue": "R", "cost": "C", "profit": "P"}[what]
    dF = _nice(sp.diff(F, x))
    steps = [f"formula: marginal {what} = {sym}′({x}), the extra {what} per extra unit"] + _d_steps(F, x) + [f"{sym}′({x}) = {pe(dF)}"]
    q = None
    pm = re.search(rf"\b(?:at|when|for)\s+(?:a\s+(?:production|output|sales)\s+level\s+of\s+)?(?:{x}\s*=\s*)?(\d+(?:\.\d+)?)\b", t) \
        or re.search(r"\bwhen\s+(\d+(?:\.\d+)?)\s+(?:\w+\s+){0,2}(?:are|is)\s+(?:produced|sold|made|manufactured)", t) \
        or re.search(r"\b(?:production|output|sales)\s+(?:level\s+)?(?:of|is)\s+(\d+(?:\.\d+)?)", t) \
        or re.search(rf"(?<![a-z]){x}\s*=\s*(\d+(?:\.\d+)?)", t)
    nth = re.search(r"\b(\d+)(?:st|nd|rd|th)\s+(?:unit|item)", t)
    if nth:
        q = sp.Integer(nth.group(1)) - 1
        steps.append(f"the {nth.group(1)}th unit comes after {pe(q)} units, so evaluate at {x} = {pe(q)}")
    elif pm:
        q = sp.Rational(pm.group(1))
    if q is None:
        steps.append(f"result: {sym}′({x}) = {pe(dF)}")
        return _sol("marginal", f"marginal {what} of {sym}({x}) = {pe(F)}", f"{sym}′({x}) = {pe(dF)}", steps)
    val = sp.simplify(dF.subs(x, q))
    if not val.is_real:
        return None
    amount = f"{'-' if val < 0 else ''}{cur}{money(abs(float(val)))} per unit"
    steps += [f"substitute: {sym}′({pe(q)}) = {pe(dF.subs(x, sp.Symbol('(' + pe(q) + ')')))}", f"result: {amount}"]
    step1 = sp.simplify(F.subs(x, q + 1) - F.subs(x, q))
    check = f"{sym}({pe(q + 1)}) − {sym}({pe(q)}) = {money(float(step1))}, close to the marginal value ✓"
    return _sol("marginal", f"marginal {what} of {sym}({x}) = {pe(F)} at {x} = {pe(q)}", amount, steps, check)


# ---------------------------------------------------------------- entry point

_UNI = [("’", "'"), ("‘", "'"), ("`", "'"), ("“", '"'), ("”", '"'), ("−", "-"), ("–", "-"), ("—", " , "), ("×", "*"),
        ("·", "*"), ("∙", "*"), ("⋅", "*"), ("÷", "/"), ("²", "^2"), ("³", "^3"), ("⁴", "^4"), ("π", "pi"), ("√", "sqrt"),
        ("∛", "cbrt"), ("∞", "infinity"), ("→", "->"), ("⟶", "->"), ("″", "''"), ("′", "'"), ("∫", " integral "),
        ("≤", "<="), ("≥", ">="), (" ", " ")]
_WORDS = [(r"\bsquare root of\b|\broot of\b", "sqrt "), (r"\bcube root of\b", "cbrt "),
          (r"\bnatural log(?:arithm)?(?: of)?\b", "ln "), (r"\b(sin|cos|tan|sec|csc|cot|ln|log|exp|sqrt)\s+of\s+", r"\1 "),
          (r"\bsine\b(?: of)?", "sin"), (r"\bcosine\b(?: of)?", "cos"), (r"\bsquared\b", "^2"), (r"\bcubed\b", "^3"),
          (r"\bto the power of\b|\braised to the power of\b|\braised to\b", "^"),
          (r"\b(e|\d+|[xtquyzsvwrp]|\))\s+to the\s+(?:power\s+(?:of\s+)?)?", r"\1^"),
          (r"\btimes\b|\bmultiplied by\b", "*"), (r"\bdivided by\b", "/"), (r"\bplus\b", "+"), (r"\bminus\b", "-"),
          (r"\binfinite\b|\binfinity\b|\binf\b", "infinity"), (r"\blim_", "lim "), (r"\bd/d([a-z])\s*\(", r"d/d\1 (")]
_CHATTER = [r"\b(?:to|in|at|with|using)?\s*\d+\s*(?:sig(?:nificant)?\.?\s*(?:fig(?:ure)?s?|digits?)|s\.f\.?|sf)(?![a-z])",
            r"\b(?:to|in|at|with|using)?\s*\d+\s*(?:decimal\s+places?|d\.p\.?|dp|decimals?)(?![a-z])",
            r"\b(?:give|leave|put|write|express|want|need)\s+(?:it|the answer|your answer|the result|me the answer|answer|that)?\s*(?:as|in)\s+(?:a\s+)?(?:fraction|exact form|decimal|surd form|simplest form)\b",
            r"\b(?:as\s+a\s+fraction|in\s+exact\s+form|exact\s+form|exact\s+answer|exact\s+value|exactly)(?:\s+if\s+(?:you\s+)?(?:can|possible))?\b",
            r"\bshow\s+(?:me\s+)?(?:all\s+)?(?:the\s+|your\s+)?(?:steps|working|work|workings)\b",
            r"\b(?:step by step|step-by-step|with steps|with working|with workings)\b",
            r"\b(?:for\s+)?my\s+(?:homework|hw|assignment|class|exam|test|quiz|revision|calc class)\b|\bfor\s+(?:homework|hw|class)\b",
            r"^\s*(?:(?:quick\s+(?:one|question|q)|hey\s+kepler|hey|hi|hello|ok|okay|so|kepler|um+|hmm+|yo|right)\b[\s,:!.-]*)+",
            r"\b(?:please|pls|plz|thanks|thank you|thx|ty)\b", r"\b(?:can|could|would) you\b", r"\bhelp me\b", r"\bfor me\b",
            r"\bif you can\b", r"\bif possible\b"]
_ANY = re.compile(r"\b(?:derivative|differentiat\w*|diff|derive|d/d[a-z]|d[a-z]/d[a-z]|integra\w*|antiderivative|anti-derivative|"
                  r"area|lim|limit|approach\w*|tends?|goes to|tangent|normal|slope|gradient|stationary|turning|critical|"
                  r"max\w*|min\w*|optimi[sz]\w*|largest|smallest|greatest|least|highest|lowest|velocity|speed|acceleration|"
                  r"distance|displacement|at rest|how far|marginal|mr|mc|rate of change|inflection|concav\w*|increasing|"
                  r"decreasing|extrem\w*|vertex|box)\b|->|'\s*\(|[a-z]'|∫")
_DEFINITION = re.compile(r"^\s*(?:what(?:'s| is| are| does)?|whats|define|explain|meaning of|what do you mean by|tell me about|"
                         r"how do (?:i|you) (?:find|do|use|compute|calculate))\s+(?:an?\s+|the\s+)?[a-z' -]*\s*\??\s*$")


def _clean(text: str) -> tuple[str, _Opts]:
    t = " ".join(text.lower().split())
    for a, b in _UNI:
        t = t.replace(a, b)
    sig = re.search(r"(\d+)\s*(?:sig(?:nificant)?\.?\s*(?:fig(?:ure)?s?|digits?)|s\.f\.?|sf)(?![a-z])", t)
    dp = re.search(r"(\d+)\s*(?:decimal\s+places?|d\.p\.?|dp|decimals?)(?![a-z])", t)
    frac = bool(re.search(r"\bfractions?\b", t)) and not re.search(r"\bpartial fractions?\b", t)
    o = _Opts(sig=min(int(sig.group(1)), 15) if sig and int(sig.group(1)) > 0 else None,
              dp=min(int(dp.group(1)), 12) if dp else None, fraction=frac)
    for pat in _CHATTER:
        t = re.sub(pat, " ", t)
    for pat, rep in _WORDS:
        t = re.sub(pat, rep, t)
    t = re.sub(r"\bas\s+a\s+fraction\b|\bfraction\b", " ", t)
    return " ".join(t.split()), o


def solve(text: str) -> Solution | None:
    """A calculus problem in plain English, solved with steps; None when it isn't one (so others try)."""
    if not text or len(text) > 400:
        return None
    t, o = _clean(text)
    if re.match(r"^(?:from|between)\s+\S+\s+(?:to|and)\s+\S+\s+of\s+.+\bd[a-z]\W*$", t):
        t = "integral " + t  # "from 0 to 2 of 3x^2 dx": the dx says it's an integral
    if not t or not _ANY.search(t):
        return None
    if _DEFINITION.match(t) and not re.search(r"\d|[=^()]", t) and not re.search(r"\bof\s+[a-z]\b", t):
        return None  # "what is a derivative": a definition, answered elsewhere
    for fn in (optimisation, marginal, motion, tangent, extrema, integral, limit, derivative):
        try:
            sol = fn(t, o)
        except _Fail as e:
            return Solution(fn.__name__, text.strip()[:80], str(e), ok=False, confidence=0.9)
        except (_Bad, ValueError, TypeError, ZeroDivisionError, AttributeError, KeyError, IndexError, NotImplementedError,
                RecursionError, OverflowError, sp.SympifyError, sp.PolynomialError):
            continue
        if sol is not None:
            return sol
    return None
