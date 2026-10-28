"""Word problems, series and textual maths for Kepler's reasoning engine: English → equations → exact answer.

Deterministic, no language model: each kind of question has a reader that turns the sentence into numbers and
equations (e.g. "5 more than twice a number is 17" → 2x + 5 = 17), solves them exactly with sympy, explains every
step and checks the result.

  series        sum of the first n natural / odd / even numbers, squares, cubes (formula for symbolic n), sum of
                integers from a to b, multiples of 3 or 5 below 1000, Σ k^2 for k from 1 to 10, sum of digits
  sequences     next number in 2, 6, 12, 20 · 20th term of 3, 7, 11 · nth term · sum of first 10 terms of …
  number facts  10th prime · primes below 50 · 30th fibonacci · divisors of 36 · perfect / even / odd / square ·
                binary / hex / octal / roman · square, cube, reciprocal, half, twice of a number
  counting      10 choose 3 · arrange 5 books · letters of BANANA · handshakes among 10 people
  probability   sum 7 with two dice · exactly 3 heads in 5 tosses · drawing an ace / heart / face card
  units         5 km to miles · 100 f to c · how many seconds in a day · 2 gb in mb · 60 mph in km/h
  algebra       if a + b = 10 and a - b = 4, what is ab · f(x) = 2x + 3, find f(5) · find x if 3x - 7 = 11
  "a number"    5 more than twice a number is 17 · a number is doubled and increased by 7, the result is 31
  word problems two numbers (sum, difference, product, ratio, "one is 3 times the other") · consecutive integers ·
                ages (now / in N years / N years ago) · heads and legs · speed, distance, time (and round-trip
                average speed) · discount, tax, profit / loss · simple and compound interest · unitary and inverse
                proportion · working together / pipes · missing value for an average · dividing in a ratio
"""
import math
import re

import sympy as sp

from .reasoning import MathError, Solution, _timed, arithmetic_value, fmt, show, to_expr, _words_to_symbols

N = r"(-?\d+(?:\.\d+)?)"
P = r"(\d+(?:\.\d+)?)"   # positive


def num(s) -> sp.Rational:
    return sp.Rational(str(s))


def cap(n, limit, what):
    if n > limit:
        raise MathError(f"{what} is capped at {limit:,} here")


# ---------------------------------------------------------------- reading numbers written as words

ONES = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                   "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}
SCALES = {"hundred": 100, "thousand": 1000, "million": 10 ** 6, "billion": 10 ** 9, "dozen": 12}
_W = "|".join(sorted([*ONES, *TENS, *SCALES], key=len, reverse=True))
RUN = re.compile(rf"\b(?:{_W})(?:(?:\s+and\s+|[\s-]+)(?:{_W}))*\b")


def _run_value(run: str) -> int:
    total, cur = 0, 0
    for w in re.split(r"[\s-]+", run):
        if w == "and":
            continue
        if w in ONES:
            cur += ONES[w]
        elif w in TENS:
            cur += TENS[w]
        elif w == "hundred":
            cur = max(cur, 1) * 100
        else:
            total += max(cur, 1) * SCALES[w]
            cur = 0
    return total + cur


def words_to_numbers(t: str) -> str:
    def sub(m):
        run = m.group(0)
        if run == "one":  # "one is 3 times the other", "which one" — keep the word
            return run
        return str(_run_value(run))
    t = re.sub(r"\b(?:a|one) dozen\b", "12", t)
    t = re.sub(r"\bhalf a dozen\b", "6", t)
    return RUN.sub(sub, t)


def prepare(text: str) -> tuple[str, str]:
    """Lower-cased text with number words as digits, currency symbols and thousands separators removed."""
    t = text.lower().strip().replace("’", "'").replace("×", "*").replace("−", "-")
    t = re.sub(r'["“”]([^"“”]{1,30})["“”]', r"\1", t)  # 'the sum of "x" digits' → 'the sum of x digits'
    cur = ""
    m = re.search(r"([$£€₹])\s?\d|\brs\.?\s?\d|\binr\b|\busd\b", t)
    if m:
        cur = m.group(1) if m.group(1) else "₹"
    t = re.sub(r"[$£€₹]\s?", "", t)
    t = re.sub(r"\brs\.?\s?(?=\d)", "", t)
    for _ in range(2):
        t = re.sub(r"(\d),(\d{3})\b", r"\1\2", t)
    t = words_to_numbers(t)
    t = re.sub(r"\btwice\b", "2 times", t)
    t = re.sub(r"\b(thrice|triple)\b", "3 times", t)
    return re.sub(r"\s+", " ", t), cur


def money(x, cur: str) -> str:
    x = sp.nsimplify(x)
    if x.is_Integer:
        return f"{cur}{int(x):,}"
    return f"{cur}{float(x):,.2f}"


def nice(x) -> str:
    """Number for word-problem answers: exact if short, else 4 decimals."""
    x = sp.nsimplify(x) if not isinstance(x, sp.Basic) else x
    if x.is_Integer or (x.is_Rational and set(sp.factorint(x.q)) <= {2, 5}):
        return fmt(x)
    if x.is_number and x.is_real:
        return f"{float(x):,.4g}" if abs(float(x)) < 1000 else f"{float(x):,.0f}"
    return show(x)


def plural(word: str) -> str:
    return word[:-1] if word.endswith("s") and not word.endswith("ss") else word


# ---------------------------------------------------------------- digits of constants and big numbers

CONSTANTS = [  # (pattern, sympy value, display name)
    (r"pi|π|the pi", sp.pi, "π"),
    (r"e|euler'?s number|the number e|napier'?s constant", sp.E, "e"),
    (r"(?:the )?golden ratio|phi|φ", sp.GoldenRatio, "φ (golden ratio)"),
    (r"(?:the )?square root of 2|sqrt ?\(?2\)?|root 2|√2", sp.sqrt(2), "√2"),
    (r"(?:the )?square root of 3|sqrt ?\(?3\)?|root 3|√3", sp.sqrt(3), "√3"),
    (r"(?:the )?square root of 5|sqrt ?\(?5\)?|root 5|√5", sp.sqrt(5), "√5"),
    (r"ln ?\(?2\)?|(?:the )?natural log(?:arithm)? of 2", sp.log(2), "ln 2"),
    (r"(?:the )?euler.mascheroni constant|gamma|γ", sp.EulerGamma, "γ (Euler–Mascheroni)"),
    (r"tau|τ", 2 * sp.pi, "τ = 2π"),
]
_CONST = "|".join(f"(?:{p})" for p, _, _ in CONSTANTS)
MAX_CONST_DIGITS = 100_000
DIGIT_WORD = r"(?:decimal )?(?:digits?|decimals|decimal places|places|figures|numbers)"


def _constant(name: str):
    for pat, val, label in CONSTANTS:
        if re.fullmatch(pat, name.strip()):
            return val, label
    return None


def _digits_of(value, n: int, decimals: bool) -> str:
    """First n digits (decimals=True: after the point) as a string, exact (computed with guard digits)."""
    s = sp.N(value, n + 30).__str__().replace("-", "")
    whole, _, frac = s.partition(".")
    whole = whole.lstrip("0") or ""
    return frac[:n] if decimals else (whole + frac)[:n]


def _show_digits(d: str, limit: int = 60) -> str:
    return d if len(d) <= limit else f"{d[:limit]}… ({len(d):,} digits)"


def constant_digits(t: str) -> Solution | None:
    if not re.search(rf"\bof (?:the )?(?:{_CONST})\b|\b(?:{_CONST}) (?:to|up to)\b", t):
        return None
    after_point = lambda s: bool(re.search(r"decimal|after the (?:decimal )?point|places", s))  # noqa: E731
    # sum / product / average of the first N digits ("x" or "n" for N means: any N)
    m = re.search(rf"(sum|total|product|average|mean)(?: of)?(?: all)?(?: the)? (?:(first|last) )?(\d+|[a-z])(?:st|nd|rd|th)? ?{DIGIT_WORD}"
                  rf"(?: after the (?:decimal )?point)? of (?:the )?({_CONST})\b", t)
    if m:
        which, n_txt, cname = m.group(2), m.group(3), m.group(4)
    else:
        m = re.search(rf"(sum|total|product|average|mean)(?: of)?(?: all)?(?: the)? {DIGIT_WORD} of (?:the )?({_CONST})\b", t)
        if m:
            which, n_txt, cname = None, None, m.group(2)
    if m:
        op = {"total": "sum", "mean": "average"}.get(m.group(1), m.group(1))
        const = _constant(cname)
        if not const:
            return None
        value, label = const
        dec = after_point(m.group(0))
        if which == "last":
            raise MathError(f"{label} has infinitely many digits, so there's no 'last' digit")
        if n_txt is None or not n_txt.isdigit():
            n = 10
            d = _digits_of(value, n, dec)
            s = sum(map(int, d))
            return Solution("constant_digits", f"{op} of the first {n_txt or 'n'} digits of {label}",
                            f"no formula: {label} is irrational and its digits follow no known pattern",
                            [f"the digits of {label} never repeat or end, so there's no closed formula in n",
                             f"I can compute it exactly for any n up to {MAX_CONST_DIGITS:,}: e.g. 'sum of the first 100 digits of {cname}'",
                             f"example, n = 10: {' + '.join(d)} = {s}"], confidence=0.9)
        n = int(n_txt)
        if n < 1:
            raise MathError("ask for at least 1 digit")
        cap(n, MAX_CONST_DIGITS, "the number of digits")
        d = _digits_of(value, n, dec)
        nums = [int(c) for c in d]
        r = {"sum": sum(nums), "product": math.prod(nums), "average": sp.Rational(sum(nums), len(nums))}[op]
        reading = ("the first n digits after the decimal point" if dec else
                   f"the first n digits including the leading {str(sp.N(value, 5))[0]}")
        alt_d = _digits_of(value, n, not dec)
        alt = {"sum": sum(map(int, alt_d)), "product": math.prod(map(int, alt_d)), "average": sp.Rational(sum(map(int, alt_d)), n)}[op]
        sign = {"sum": " + ", "product": " × ", "average": " + "}[op]
        shown = sign.join(d[:24]) + (sign + "…" if len(d) > 24 else "")
        head = str(sp.N(value, 70))  # exact digits, cut (never rounded) for display
        steps = [f"{label} = {head[:min(n, 40) + 2]}…",
                 f"reading '{n} digits' as {reading}",
                 f"digits: {_show_digits(d)}",
                 f"{shown} = {fmt(r) if op != 'average' else fmt(sum(nums))}"]
        if op == "average":
            steps.append(f"average = {sum(nums)} ÷ {n} = {show(r)}")
        steps.append(f"(if you meant {'including the leading digit' if dec else 'only the decimals'}: {show(alt)})")
        return Solution("constant_digits", f"{op} of the first {n:,} {'decimal ' if dec else ''}digits of {label}",
                        show(r), steps, f"computed {n + 30:,} digits of {label} exactly and used the first {n:,} ✓")
    # how many 7s in the first N digits
    m = re.search(rf"how many (\d)'?s? (?:are )?(?:there )?(?:in|among) (?:the )?first (\d+) {DIGIT_WORD} of (?:the )?({_CONST})\b", t)
    if m:
        dig, n, cname = m.group(1), int(m.group(2)), m.group(3)
        value, label = _constant(cname) or (None, None)
        if value is None:
            return None
        cap(n, MAX_CONST_DIGITS, "the number of digits")
        d = _digits_of(value, n, after_point(m.group(0)))
        c = d.count(dig)
        return Solution("constant_digits", f"how many {dig}s in the first {n:,} digits of {label}", str(c),
                        [f"digits: {_show_digits(d)}", f"count of '{dig}': {c} ({c / n:.1%}; a random digit would be about 10%)"])
    # list the first N digits / constant to N places
    m = re.search(rf"(?:first|the first|show(?: me)?(?: the)? first|list(?: the)? first)? ?(\d+) {DIGIT_WORD}(?: after the (?:decimal )?point)? of (?:the )?({_CONST})\b", t) \
        or re.search(rf"\b({_CONST}) (?:to|up to) (\d+) ({DIGIT_WORD})", t)
    if m:
        if m.re.pattern.startswith(r"\b("):
            cname, n, dec = m.group(1), int(m.group(2)), after_point(m.group(3))
        else:
            n, cname, dec = int(m.group(1)), m.group(2), after_point(m.group(0))
        const = _constant(cname)
        if not const:
            return None
        value, label = const
        cap(n, MAX_CONST_DIGITS, "the number of digits")
        if re.search(rf"{DIGIT_WORD} of", t) and not re.search(r"\bto \d+", t) and not dec:
            d = _digits_of(value, n, False)
            ans = d if n <= 2000 else _show_digits(d, 2000)
            return Solution("constant_digits", f"the first {n:,} digits of {label}", ans,
                            [f"{label} = {str(sp.N(value, n + 30))[:n + 1]}…" if n <= 60 else f"{n:,} digits computed exactly",
                             "counting the leading digit (say 'decimal places' for only the digits after the point)"])
        txt = str(sp.N(value, n + 30))
        whole, _, frac = txt.partition(".")
        val = f"{whole}.{frac[:n]}"
        return Solution("constant_digits", f"{label} to {n:,} decimal places",
                        val if n <= 2000 else f"{val[:2000]}… ({n:,} places)",
                        ["computed exactly with 30 guard digits, then cut (not rounded) after the last place"])
    # the Nth digit
    m = re.search(rf"(?:the )?(\d+)(?:st|nd|rd|th) ((?:decimal )?(?:digit|decimal|place|figure|number))?(?: after the (?:decimal )?point)? ?of (?:the )?({_CONST})\b", t) \
        or re.search(rf"digit (?:number )?(\d+)( after the (?:decimal )?point)? of (?:the )?({_CONST})\b", t)
    if m:
        k, cname = int(m.group(1)), m.group(3)
        const = _constant(cname)
        if not const:
            return None
        value, label = const
        cap(k, MAX_CONST_DIGITS, "the digit position")
        dec = after_point(m.group(0)) or bool(re.search(r"\bdecimal\b", m.group(0)))
        d = _digits_of(value, k, dec)
        return Solution("constant_digits", f"digit {k:,} of {label}", d[k - 1],
                        [f"counting {'after the decimal point' if dec else 'from the leading digit'}",
                         f"…{d[max(0, k - 11):k - 1]}[{d[k - 1]}]", f"(the {k:,}{'th' if k % 10 > 3 or k % 100 in (11, 12, 13) else ['st', 'nd', 'rd'][k % 10 - 1] if k % 10 else 'th'} "
                         f"{'decimal' if not dec else 'digit counting the leading one'}: {_digits_of(value, k, not dec)[k - 1]})"])
    return None


def digits_of_number(t: str) -> Solution | None:
    """sum / product / count of the digits of any whole-number expression: 2^1000, 100!, 12345."""
    m = re.search(r"(sum|product|count|number) of (?:the |all )?digits (?:of|in) (?:the number )?(.+?)\??$", t) \
        or re.search(r"how many digits (?:are )?(?:in|does) (.+?)(?: have)?\??$", t)
    if not m:
        return None
    op, expr = (m.group(1), m.group(2)) if m.lastindex == 2 else ("count", m.group(1))
    if _constant(expr.strip()):
        raise MathError(f"{expr.strip()} has infinitely many digits: ask for e.g. 'the sum of the first 100 digits of {expr.strip()}'")
    v = arithmetic_value(expr)
    if not v.is_Integer:
        raise MathError("that isn't a whole number; I can only add up the digits of whole numbers")
    s = str(abs(int(v)))
    ds = [int(c) for c in s]
    if op in ("count", "number"):
        return Solution("digit_count", f"digits in {expr}", f"{len(s):,}", [f"{expr} = {_show_digits(s)}", f"it has {len(s):,} digits"])
    r = sum(ds) if op == "sum" else math.prod(ds)
    sign = " + " if op == "sum" else " × "
    shown = sign.join(s[:24]) + (sign + "…" if len(s) > 24 else "")
    return Solution("digits", f"{op} of the digits of {expr}", f"{r:,}",
                    [f"{expr} = {_show_digits(s)}" if not re.fullmatch(r"\d+", expr.strip()) else f"digits of {s}",
                     f"{shown} = {r:,}"], f"{len(s):,} digits, computed exactly ✓")


# ---------------------------------------------------------------- series and sums

SERIES_KIND = (r"(natural numbers|positive integers|positive whole numbers|counting numbers|whole numbers|integers|"
               r"numbers|digits|odd (?:natural |positive )?(?:numbers|integers)|even (?:natural |positive )?(?:numbers|integers)|"
               r"squares|square numbers|perfect squares|cubes|cube numbers|perfect cubes|primes|prime numbers|"
               r"fibonacci numbers|powers of \d+|multiples of \d+)")


def series(t: str) -> Solution | None:
    m = re.search(rf"sum of (?:all )?(?:the )?first (\d+|[a-z]) {SERIES_KIND}", t)
    if m:
        return _first_n(m.group(1), m.group(2))
    m = re.search(r"sum of (?:all )?(?:the )?(even |odd )?(?:natural |whole |positive )?(?:integers|numbers)"
                  rf" (?:from|between) {N} (?:to|and|through) {N}", t)
    if m:
        return _range_sum(m.group(1), int(num(m.group(2))), int(num(m.group(3))), "between" in m.group(0))
    m = re.search(r"(sum|how many|number|count) (?:of )?(?:all )?(?:the )?(?:natural numbers |numbers |positive integers |integers )?"
                  r"(?:that are |which are )?multiples of (\d+)((?: (?:or|and|,) \d+)*) (below|less than|under|up to|upto|"
                  r"not exceeding|to|till|until|from 1 to|between 1 and) (\d+)", t)
    if m:
        ks = [int(m.group(2))] + [int(k) for k in re.findall(r"\d+", m.group(3))]
        return _multiples(m.group(1), ks, m.group(4), int(m.group(5)))
    m = re.search(r"(sum|product) of (?:the |all )?digits (?:of|in) (?:the number )?(\d+)", t)
    if m:
        ds = [int(c) for c in m.group(2)]
        r = sum(ds) if m.group(1) == "sum" else math.prod(ds)
        op = " + " if m.group(1) == "sum" else " × "
        return Solution("digits", f"{m.group(1)} of the digits of {m.group(2)}", str(r), [op.join(map(str, ds)) + f" = {r}"])
    m = re.search(r"sum of (?:all )?(?:the )?digits(?: from 0 to 9| 0 to 9)?$", t)
    if m:
        return Solution("digits", "sum of the digits 0–9", "45", ["0 + 1 + 2 + … + 9 = 9 × 10 ÷ 2 = 45"])
    m = re.search(r"digital root of (\d+)", t)
    if m:
        n = int(m.group(1))
        steps, x = [], n
        while x >= 10:
            s = sum(int(c) for c in str(x))
            steps.append(f"{' + '.join(str(x))} = {s}")
            x = s
        return Solution("digital_root", f"digital root of {n}", str(x), steps or [f"{n} is already one digit"],
                        f"1 + ({n} − 1) mod 9 = {1 + (n - 1) % 9 if n else 0} ✓")
    m = re.search(r"how many digits (?:are )?(?:in|does) (.+?)(?: have)?\??$", t) or re.search(r"number of digits (?:in|of) (.+?)\??$", t)
    if m:
        v = arithmetic_value(m.group(1))
        if not v.is_Integer:
            raise MathError("count digits of a whole number")
        d = len(str(abs(int(v))))
        return Solution("digit_count", f"digits in {m.group(1)}", str(d), [f"{m.group(1)} = {fmt(v)}", f"⌊log₁₀ |n|⌋ + 1 = {d}"])
    m = (re.search(r"sum (?:of )?(.+?) (?:for|where|as) ([a-z]) (?:goes |runs |ranges |is )?(?:from |= ?)(\S+) (?:to|up to|through|till) (\S+?)\??$", t)
         or re.search(r"sum (?:from|for) ([a-z]) ?= ?(\S+) to (\S+?) of (.+?)\??$", t))
    if m:
        if m.re.pattern.startswith("sum (?:from"):
            var, lo, hi, body = m.group(1), m.group(2), m.group(3), m.group(4)
        else:
            body, var, lo, hi = m.group(1), m.group(2), m.group(3), m.group(4)
        k = sp.Symbol(var)
        f = to_expr(_words_to_symbols(body))
        a = sp.oo if lo in ("infinity", "inf") else arithmetic_value(lo)
        b = sp.oo if hi in ("infinity", "inf", "∞") else (sp.Symbol(hi) if re.fullmatch(r"[a-z]", hi) else arithmetic_value(hi))
        if (b == sp.oo or (b.is_number and a.is_number and b - a > 2000)) and not f.is_polynomial(k):
            # too many terms to add one by one: only allow it when there's a closed form
            top = sp.Symbol("N_top", integer=True, positive=True)
            closed = _timed(lambda: sp.summation(f, (k, a, top)))
            if closed.has(sp.Sum):
                if b != sp.oo:
                    raise MathError("that sum has no closed form and too many terms to add one by one")
            else:
                r = sp.factor(closed.subs(top, b)) if b != sp.oo else _timed(lambda: sp.limit(closed, top, sp.oo))
                steps = [f"Σ {fmt(f)} for {var} = {fmt(a)} … {fmt(b)}", f"closed form up to N: {fmt(closed)}"]
                return Solution("summation", steps[0], show(r), steps)
        if b.is_number and a.is_number and b != sp.oo and b - a > 10 ** 6 and not f.is_polynomial(k):
            raise MathError("that's more than a million terms")
        r = _timed(lambda: sp.factor(sp.summation(f, (k, a, b))))
        steps = [f"Σ {fmt(f)} for {var} = {fmt(a)} … {fmt(b)}"]
        if b.is_Integer and a.is_Integer and b - a < 8:
            steps.append(" + ".join(fmt(f.subs(k, i)) for i in range(int(a), int(b) + 1)) + f" = {show(r)}")
        return Solution("summation", steps[0], show(r), steps)
    return None


def _first_n(n_txt: str, kind: str) -> Solution:
    n = sp.Symbol("n") if n_txt.isalpha() else sp.Integer(n_txt)
    if n.is_Integer:
        cap(int(n), 10 ** 12, "n")
    k = sp.Symbol("k")
    notes = []
    if kind in ("digits", "numbers", "integers"):
        notes.append(f"reading '{kind}' as the counting numbers 1, 2, 3, …, n")
    if kind.startswith("whole numbers"):
        term, lo, label = k, 0, "0 + 1 + 2 + … + (n − 1)"
        formula, why = n * (n - 1) / 2, "whole numbers start at 0, so this is 0 + 1 + … + (n − 1) = (n − 1)·n ÷ 2"
    elif kind.startswith("odd"):
        term, lo, label = 2 * k - 1, 1, "1 + 3 + 5 + … + (2n − 1)"
        formula, why = n ** 2, "the k-th odd number is 2k − 1, so the sum is 2·(1 + … + n) − n = n(n + 1) − n = n²"
    elif kind.startswith("even"):
        term, lo, label = 2 * k, 1, "2 + 4 + 6 + … + 2n"
        formula, why = n * (n + 1), "each even number is 2k, so the sum is 2·(1 + … + n) = 2 · n(n + 1)/2 = n(n + 1)"
    elif kind in ("squares", "square numbers", "perfect squares"):
        term, lo, label = k ** 2, 1, "1² + 2² + … + n²"
        formula, why = n * (n + 1) * (2 * n + 1) / 6, "known identity Σk² = n(n + 1)(2n + 1)/6 (provable by induction)"
    elif kind in ("cubes", "cube numbers", "perfect cubes"):
        term, lo, label = k ** 3, 1, "1³ + 2³ + … + n³"
        formula, why = (n * (n + 1) / 2) ** 2, "Nicomachus: Σk³ = (1 + 2 + … + n)² = (n(n + 1)/2)²"
    elif kind.startswith("powers of"):
        b = int(kind.split()[-1])
        term, lo, label = sp.Integer(b) ** (k - 1), 1, f"1 + {b} + {b}² + … + {b}^(n−1)"
        formula = (sp.Integer(b) ** n - 1) / (b - 1) if b != 1 else n
        why = f"geometric series with ratio {b}: (rⁿ − 1)/(r − 1)"
    elif kind.startswith("multiples of"):
        mlt = int(kind.split()[-1])
        term, lo, label = mlt * k, 1, f"{mlt} + {2 * mlt} + … + {mlt}n"
        formula, why = mlt * n * (n + 1) / 2, f"{mlt} × (1 + 2 + … + n) = {mlt} · n(n + 1)/2"
    elif kind in ("primes", "prime numbers", "fibonacci numbers"):
        if not n.is_Integer:
            raise MathError(f"there's no closed formula for the sum of the first n {kind}; give a number")
        cap(int(n), 100000, "n")
        if kind.startswith("prime"):
            xs = [sp.prime(i) for i in range(1, int(n) + 1)]
        else:
            xs = [sp.fibonacci(i) for i in range(1, int(n) + 1)]
        s = sum(xs)
        shown = " + ".join(map(str, xs[:10])) + (" + …" if len(xs) > 10 else "")
        check = f"F(n + 2) − 1 = F({int(n) + 2}) − 1 = {sp.fibonacci(int(n) + 2) - 1} ✓" if kind.startswith("fib") else ""
        return Solution("series", f"sum of the first {n} {kind}", fmt(s), [shown + f" = {fmt(s)}"], check)
    else:  # natural numbers
        term, lo, label = k, 1, "1 + 2 + 3 + … + n"
        formula = n * (n + 1) / 2
        why = "pair the first and last terms: 1 + n, 2 + (n − 1), … each pair sums to n + 1, and there are n/2 pairs"
    formula = sp.factor(formula) if not n.is_Integer else formula
    steps = notes + [f"S = {label}", why, f"S = {fmt(sp.factor(formula.subs(n, sp.Symbol('n'))) if n.is_Integer else formula)}"]
    if n.is_Integer:
        steps.append(f"with n = {n}: S = {fmt(formula)}")
        if n <= 10 ** 6:
            direct = sum(term.subs(k, i) for i in range(lo, int(n) + lo)) if n <= 2000 else None
            check = f"adding all {n} terms directly also gives {fmt(direct)} ✓" if direct is not None else \
                f"Σ by sympy = {fmt(sp.summation(term, (k, lo, int(n) + lo - 1)))} ✓"
        else:
            check = ""
        return Solution("series", f"sum of the first {n} {kind}", fmt(formula), steps, check)
    sym = sp.summation(term, (k, lo, n + lo - 1))
    ok = sp.simplify(sym - formula) == 0
    small = {i: formula.subs(n, i) for i in (1, 2, 3)}
    return Solution("series", f"sum of the first n {kind}", fmt(formula), steps,
                    f"n = 1, 2, 3 → {', '.join(fmt(v) for v in small.values())}; symbolic Σ agrees {'✓' if ok else '✗'}")


def _range_sum(parity: str | None, a: int, b: int, between: bool) -> Solution:
    if a > b:
        a, b = b, a
    step = 2 if parity else 1
    if parity:
        want = 0 if parity.strip() == "even" else 1
        a = a if a % 2 == want else a + 1
        b = b if b % 2 == want else b - 1
    if a > b:
        return Solution("series", "empty range", "0", ["no numbers of that kind in the range"])
    count = (b - a) // step + 1
    s = (a + b) * count // 2
    what = f"{parity.strip()} numbers" if parity else "integers"
    steps = [f"first = {a}, last = {b}, step = {step}" + ("  (taking 'between' as inclusive)" if between else ""),
             f"number of terms = ({b} − {a}) ÷ {step} + 1 = {count}",
             f"sum = (first + last) × count ÷ 2 = ({a} + {b}) × {count} ÷ 2 = {s:,}"]
    check = f"adding them directly gives {sum(range(a, b + 1, step)):,} ✓" if count <= 10 ** 6 else ""
    return Solution("series", f"sum of {what} from {a} to {b}", f"{s:,}", steps, check)


def _multiples(op: str, ks: list[int], bound_word: str, limit: int) -> Solution:
    if any(k <= 0 for k in ks) or len(ks) > 4:
        raise MathError("give up to 4 positive numbers")
    top = limit - 1 if bound_word in ("below", "less than", "under") else limit
    cap(top, 10 ** 15, "the limit")
    from itertools import combinations
    total, count, steps = 0, 0, []
    for r in range(1, len(ks) + 1):
        for combo in combinations(ks, r):
            L = math.lcm(*combo)
            c = top // L
            s = L * c * (c + 1) // 2
            sign = 1 if r % 2 else -1
            total += sign * s
            count += sign * c
            steps.append(f"{'+' if sign > 0 else '−'} multiples of {L}{' (lcm of ' + ', '.join(map(str, combo)) + ')' if r > 1 else ''}: "
                         f"{c} of them, sum {L} × {c}·{c + 1}/2 = {s:,}")
    head = [f"largest allowed number: {top:,}"] + (["inclusion–exclusion so shared multiples count once:"] if len(ks) > 1 else [])
    label = f"multiples of {' or '.join(map(str, ks))} {bound_word} {limit:,}"
    if op == "sum":
        check = f"direct sum = {sum(i for i in range(1, top + 1) if any(i % k == 0 for k in ks)):,} ✓" if top <= 10 ** 6 else ""
        return Solution("series", f"sum of {label}", f"{total:,}", head + steps, check)
    check = f"direct count = {sum(1 for i in range(1, top + 1) if any(i % k == 0 for k in ks)):,} ✓" if top <= 10 ** 6 else ""
    return Solution("count", f"count of {label}", f"{count:,}", head + steps, check)


# ---------------------------------------------------------------- sequences

SEQ = r"((?:-?\d+(?:\.\d+)?\s*,\s*){2,}-?\d+(?:\.\d+)?)"


def _seq(txt: str) -> list:
    xs = [num(x) for x in re.split(r"\s*,\s*", txt.strip())]
    if len(xs) > 40:
        raise MathError("up to 40 terms")
    return xs


def analyse(xs: list):
    """→ (description, formula in n (1-indexed) or None, recurrence function or None, steps)."""
    n = sp.Symbol("n")
    steps = []
    diffs = [b - a for a, b in zip(xs, xs[1:])]
    steps.append(f"differences: {', '.join(fmt(d) for d in diffs)}")
    if len(set(diffs)) == 1:
        d = diffs[0]
        return f"arithmetic (add {fmt(d)} each time)", sp.expand(xs[0] + (n - 1) * d), None, steps
    if all(x != 0 for x in xs):
        ratios = [b / a for a, b in zip(xs, xs[1:])]
        if len(set(ratios)) == 1:
            r = ratios[0]
            steps.append(f"ratios: {', '.join(fmt(q) for q in ratios)}")
            return f"geometric (multiply by {fmt(r)} each time)", xs[0] * r ** (n - 1), None, steps
    if len(xs) >= 4 and all(xs[i] == xs[i - 1] + xs[i - 2] for i in range(2, len(xs))):
        steps.append("each term is the sum of the two before it")
        return "Fibonacci-style (add the previous two)", None, lambda s: s[-1] + s[-2], steps
    level, row = 1, diffs
    while len(row) > 1 and level < 4:
        nxt = [b - a for a, b in zip(row, row[1:])]
        steps.append(f"{level + 1}{'nd' if level == 1 else 'rd' if level == 2 else 'th'} differences: {', '.join(fmt(d) for d in nxt)}")
        if len(set(nxt)) == 1 and len(nxt) >= 2:
            poly = sp.expand(sp.interpolate(list(zip(range(1, len(xs) + 1), xs)), n))
            return f"polynomial of degree {level + 1} (constant {level + 1}{'nd' if level == 1 else 'rd' if level == 2 else 'th'} differences)", poly, None, steps
        row, level = nxt, level + 1
    if len(xs) >= 3 and all(x != 0 for x in xs[:-1]):
        ratios = [b / a for a, b in zip(xs, xs[1:])]
        rd = [b - a for a, b in zip(ratios, ratios[1:])]
        if len(set(rd)) == 1 and rd[0] != 0:
            steps.append(f"ratios: {', '.join(fmt(q) for q in ratios)} (they grow by {fmt(rd[0])})")
            return "ratio grows steadily", None, lambda s, r0=ratios[-1], g=rd[0]: s[-1] * (s[-1] / s[-2] + g), steps
    raise MathError("I couldn't find a pattern (tried arithmetic, geometric, Fibonacci-style and polynomial)")


def sequences(t: str) -> Solution | None:
    m = re.search(rf"(?:next (?:number|term|value)|what comes next|comes next|comes after|what is after|after|continue|missing number|follows)\D*?{SEQ}", t) \
        or re.search(rf"^{SEQ}\s*(?:,\s*)?(?:\.\.\.|…|\?|,\s*_+|what comes next|next)", t)
    if m:
        xs = _seq(m.group(1))
        kind, formula, rec, steps = analyse(xs)
        n = sp.Symbol("n")
        nxt = formula.subs(n, len(xs) + 1) if formula is not None else rec(xs)
        steps.append(f"pattern: {kind}")
        if formula is not None:
            steps.append(f"term n = {fmt(formula)}")
        return Solution("sequence", ", ".join(fmt(x) for x in xs) + ", ?", fmt(nxt), steps,
                        f"the rule reproduces all {len(xs)} given terms ✓" if formula is not None and
                        all(formula.subs(n, i + 1) == x for i, x in enumerate(xs)) else "")
    m = re.search(rf"(\d+|n)(?:st|nd|rd|th)? term of (?:the )?(?:sequence |series |progression |ap |gp )?{SEQ}", t)
    if m:
        xs = _seq(m.group(2))
        kind, formula, rec, steps = analyse(xs)
        n = sp.Symbol("n")
        steps.append(f"pattern: {kind}")
        if m.group(1) == "n":
            if formula is None:
                raise MathError("that pattern has no simple nth-term formula")
            return Solution("sequence", f"nth term of {', '.join(map(fmt, xs))}", fmt(formula), steps,
                            f"n = 1, 2, 3 → {', '.join(fmt(formula.subs(n, i)) for i in (1, 2, 3))} ✓")
        k = int(m.group(1))
        cap(k, 10 ** 6, "the term number")
        if formula is not None:
            steps.append(f"term n = {fmt(formula)} → n = {k}")
            val = formula.subs(n, k)
        else:
            cap(k, 5000, "the term number")
            s = list(xs)
            while len(s) < k:
                s.append(rec(s))
            val = s[k - 1]
        return Solution("sequence", f"term {k} of {', '.join(map(fmt, xs))}", fmt(val), steps)
    m = re.search(rf"sum of (?:the )?first (\d+) terms of (?:the )?(?:sequence |series |progression |ap |gp )?{SEQ}", t)
    if m:
        k, xs = int(m.group(1)), _seq(m.group(2))
        cap(k, 10 ** 6, "the number of terms")
        kind, formula, rec, steps = analyse(xs)
        n, i = sp.Symbol("n"), sp.Symbol("i")
        steps.append(f"pattern: {kind}")
        if formula is not None:
            total = sp.summation(formula.subs(n, i), (i, 1, k))
            steps.append(f"Σ term(i) for i = 1 … {k}")
        else:
            cap(k, 5000, "the number of terms")
            s = list(xs)
            while len(s) < k:
                s.append(rec(s))
            total = sum(s[:k])
        return Solution("series", f"sum of the first {k} terms of {', '.join(map(fmt, xs))}", fmt(total), steps)
    return None


# ---------------------------------------------------------------- number facts, bases, counting, probability

ROMAN = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"),
         (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def number_facts(t: str) -> Solution | None:
    m = re.search(r"(\d+)(?:st|nd|rd|th) prime(?: number)?", t)
    if m:
        k = int(m.group(1))
        cap(k, 200000, "the prime index")
        p = sp.prime(k)
        return Solution("prime", f"prime number {k}", str(p), [f"counting primes 2, 3, 5, 7, 11, … the {k}th is {p}"],
                        f"{p} is prime ✓ and there are {sp.primepi(p)} primes ≤ {p} ✓")
    m = re.search(r"(?:how many|number of|count(?: of)?) prime(?:s| numbers)? (?:are there )?(?:(below|less than|under|up to|upto|"
                  r"not exceeding|between 1 and|from 1 to|smaller than) (\d+)|between (\d+) and (\d+))", t)
    if m:
        if m.group(3):
            a, b = int(m.group(3)), int(m.group(4))
            cap(b, 10 ** 9, "the range")
            c = sp.primepi(b) - sp.primepi(a - 1 if a > 0 else 0)
            lst = list(sp.primerange(a, b + 1)) if c <= 30 else []
            return Solution("prime_count", f"primes between {a} and {b}", str(c),
                            [f"π({b}) − π({a - 1}) = {sp.primepi(b)} − {sp.primepi(max(a - 1, 0))} = {c}"] + ([f"they are {', '.join(map(str, lst))}"] if lst else []))
        lim = int(m.group(2))
        top = lim - 1 if m.group(1) in ("below", "less than", "under", "smaller than") else lim
        cap(top, 10 ** 9, "the limit")
        c = sp.primepi(top)
        lst = list(sp.primerange(2, top + 1)) if c <= 30 else []
        return Solution("prime_count", f"primes ≤ {top}", str(c), [f"π({top}) = {c}"] + ([f"they are {', '.join(map(str, lst))}"] if lst else []))
    m = re.search(r"(?:list |all |the |show )?prime(?:s| numbers) (?:(below|less than|under|up to|upto|smaller than) (\d+)|between (\d+) and (\d+))", t)
    if m:
        a, b = (2, int(m.group(2)) - (1 if m.group(1) in ("below", "less than", "under", "smaller than") else 0)) if m.group(2) else (int(m.group(3)), int(m.group(4)))
        cap(b, 10 ** 6, "the range")
        ps = list(sp.primerange(a, b + 1))
        cap(len(ps), 300, "the list")
        return Solution("primes", f"primes from {a} to {b}", ", ".join(map(str, ps)) or "none",
                        [f"{len(ps)} primes; each has no divisor other than 1 and itself"])
    m = re.search(r"(\d+)(?:st|nd|rd|th) fibonacci(?: number)?|fibonacci (?:number )?(\d+)", t)
    if m:
        k = int(m.group(1) or m.group(2))
        cap(k, 20000, "the index")
        f = sp.fibonacci(k)
        first = ", ".join(str(sp.fibonacci(i)) for i in range(1, min(k, 10) + 1))
        return Solution("fibonacci", f"Fibonacci number {k}", fmt(f), [f"F(1) = F(2) = 1, F(n) = F(n−1) + F(n−2): {first}{', …' if k > 10 else ''}"])
    m = re.search(r"(how many|number of|count of|sum of|list|all|the|show)?\s*(?:the )?(?:positive )?(?:divisors|factors) (?:of|does) (\d+)", t) \
        or re.search(r"how many (?:divisors|factors) does (\d+) have", t)
    if m:
        n = int(m.groups()[-1])
        cap(n, 10 ** 15, "the number")
        ds = sp.divisors(n)
        which = (m.group(1) or "") if m.lastindex and m.lastindex > 1 else "how many"
        f = sp.factorint(n)
        if which in ("how many", "number of", "count of"):
            formula = " × ".join(f"({e} + 1)" for e in f.values()) or "1"
            return Solution("divisors", f"number of divisors of {n}", str(len(ds)),
                            [f"{n} = " + " × ".join(f"{p}^{e}" if e > 1 else str(p) for p, e in f.items()),
                             f"divisor count = product of (exponent + 1) = {formula} = {len(ds)}"],
                            f"listing them gives {len(ds)} ✓" if len(ds) <= 200 else "")
        if which == "sum of":
            return Solution("divisors", f"sum of divisors of {n}", f"{sum(ds):,}", [" + ".join(map(str, ds[:20])) + (" + …" if len(ds) > 20 else "") + f" = {sum(ds):,}"])
        cap(len(ds), 300, "the list")
        return Solution("divisors", f"divisors of {n}", ", ".join(map(str, ds)), [f"pairs d × ({n} ÷ d) for d up to √{n}"])
    m = re.search(r"is (\d+) (?:a )?perfect(?: number)?\??$", t)
    if m:
        n = int(m.group(1))
        cap(n, 10 ** 15, "the number")
        s = sum(sp.divisors(n)) - n
        return Solution("perfect", f"is {n} perfect?", "yes" if s == n else "no",
                        [f"proper divisors sum to {s}", f"{s} {'=' if s == n else '≠'} {n}"])
    m = re.search(r"is (-?\d+) (?:an? )?(even|odd)(?: number)?\??$", t)
    if m:
        n, w = int(m.group(1)), m.group(2)
        ans = (n % 2 == 0) == (w == "even")
        return Solution("parity", f"is {n} {w}?", "yes" if ans else "no", [f"{n} ÷ 2 leaves remainder {n % 2}"])
    m = re.search(r"is (\d+) (?:a )?perfect (square|cube)\??$", t)
    if m:
        n, w = int(m.group(1)), m.group(2)
        r = math.isqrt(n) if w == "square" else round(n ** (1 / 3))
        ok = r ** (2 if w == "square" else 3) == n
        return Solution("perfect_power", f"is {n} a perfect {w}?", "yes" if ok else "no",
                        [f"{'√' if w == 'square' else '∛'}{n} ≈ {r}", f"{r}^{2 if w == 'square' else 3} = {r ** (2 if w == 'square' else 3)} {'=' if ok else '≠'} {n}"])
    m = re.search(r"is (-?\d+) divisible by (-?\d+)\??$", t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if b == 0:
            raise MathError("nothing is divisible by 0")
        return Solution("divisible", f"is {a} divisible by {b}?", "yes" if a % b == 0 else "no", [f"{a} ÷ {b} = {a // b} remainder {a % b}"])
    m = re.search(r"(?:convert )?(\d+) (?:to|in|into|as) (binary|hex(?:adecimal)?|octal|base (\d+))", t)
    if m:
        n = int(m.group(1))
        cap(n, 10 ** 30, "the number")
        base = {"binary": 2, "octal": 8}.get(m.group(2), 16 if m.group(2).startswith("hex") else int(m.group(3) or 10))
        if not 2 <= base <= 36:
            raise MathError("bases 2 to 36 only")
        digits, x, steps = "", n, []
        while x:
            steps.append(f"{x} ÷ {base} = {x // base} remainder {x % base}")
            digits = "0123456789abcdefghijklmnopqrstuvwxyz"[x % base] + digits
            x //= base
        digits = digits or "0"
        return Solution("base", f"{n} in base {base}", digits, steps[:12] + ["read the remainders from bottom to top"],
                        f"int('{digits}', {base}) = {int(digits, base)} ✓")
    m = re.search(r"(?:convert )?(?:the )?(binary|hex(?:adecimal)?|octal) (?:number )?([0-9a-f]+) (?:to|in|into) decimal", t) \
        or re.search(r"0([bxo])([0-9a-f]+) (?:in|to) decimal", t)
    if m:
        base = {"binary": 2, "b": 2, "octal": 8, "o": 8}.get(m.group(1), 16)
        try:
            v = int(m.group(2), base)
        except ValueError as e:
            raise MathError(f"'{m.group(2)}' isn't a valid base-{base} number") from e
        terms = [f"{int(c, base)}×{base}^{i}" for i, c in enumerate(reversed(m.group(2))) if c != "0"][::-1]
        return Solution("base", f"{m.group(2)} (base {base}) in decimal", str(v), [" + ".join(terms[:10]) + f" = {v}"])
    m = re.search(r"(\d+) (?:in|to|as|into) roman(?: numerals?)?|roman numerals? (?:for|of) (\d+)", t)
    if m:
        n = int(m.group(1) or m.group(2))
        if not 1 <= n <= 3999:
            raise MathError("Roman numerals cover 1 to 3999")
        out, x, steps = "", n, []
        for v, s in ROMAN:
            while x >= v:
                out += s
                x -= v
                steps.append(f"{s} ({v})")
        return Solution("roman", f"{n} in Roman numerals", out, [" + ".join(steps)])
    m = re.search(r"(?:convert )?(?:the )?roman(?: numerals?)? ([mdclxvi]+)(?: to (?:decimal|a number|arabic))?$|^([mdclxvi]+) in (?:decimal|numbers|arabic)", t)
    if m:
        s = (m.group(1) or m.group(2)).upper()
        val = {"M": 1000, "D": 500, "C": 100, "L": 50, "X": 10, "V": 5, "I": 1}
        total = 0
        for i, c in enumerate(s):
            v = val[c]
            total += -v if i + 1 < len(s) and val[s[i + 1]] > v else v
        return Solution("roman", f"{s} in decimal", str(total), ["a smaller numeral before a larger one is subtracted"])
    m = re.search(r"(?:the )?(square|cube|reciprocal|square root|cube root) of (-?\d+(?:\.\d+)?)", t)
    if m:
        x = num(m.group(2))
        r = {"square": x ** 2, "cube": x ** 3, "reciprocal": 1 / x if x else None, "square root": sp.sqrt(x),
             "cube root": sp.cbrt(x) if x >= 0 else -sp.cbrt(-x)}[m.group(1)]
        if r is None:
            raise MathError("0 has no reciprocal")
        how = {"square": f"{fmt(x)} × {fmt(x)}", "cube": f"{fmt(x)} × {fmt(x)} × {fmt(x)}", "reciprocal": f"1 ÷ {fmt(x)}",
               "square root": f"√{fmt(x)}", "cube root": f"∛{fmt(x)}"}[m.group(1)]
        return Solution("number", f"{m.group(1)} of {fmt(x)}", show(r), [f"{how} = {show(r)}"])
    m = re.search(rf"^(?:what is |what's )?(half|a third|one third|a quarter|one quarter|a fifth|double|2 times|3 times) (?:of )?{N}\??$", t)
    if m:
        f = {"half": sp.Rational(1, 2), "a third": sp.Rational(1, 3), "one third": sp.Rational(1, 3), "a quarter": sp.Rational(1, 4),
             "one quarter": sp.Rational(1, 4), "a fifth": sp.Rational(1, 5), "double": 2, "2 times": 2, "3 times": 3}[m.group(1)]
        x = num(m.group(2))
        return Solution("number", f"{m.group(1)} of {fmt(x)}", show(f * x), [f"{fmt(f)} × {fmt(x)} = {show(f * x)}"])
    return None


def counting(t: str) -> Solution | None:
    m = (re.search(r"(\d+) choose (\d+)", t) or re.search(r"\bc\((\d+),\s*(\d+)\)", t) or re.search(r"(\d+)c(\d+)\b", t))
    pick = None
    if m:
        pick = int(m.group(1)), int(m.group(2))
    else:
        m = re.search(r"(?:ways (?:to|can (?:you|we|i)) (?:choose|select|pick)|combinations of|choose|select|pick) (\d+) (?:\w+ ){0,3}(?:from|out of|among) (?:a group of |a set of )?(\d+)", t)
        if m:
            pick = int(m.group(2)), int(m.group(1))
    if pick:
        n, k = pick
        cap(n, 10000, "n")
        if k > n:
            return Solution("combinations", f"C({n}, {k})", "0", [f"can't choose {k} from only {n}"])
        r = sp.binomial(n, k)
        return Solution("combinations", f"C({n}, {k})", fmt(r),
                        [f"order doesn't matter: C(n, k) = n! ÷ (k! (n − k)!)", f"= {n}! ÷ ({k}! × {n - k}!) = {fmt(r)}"],
                        f"C({n}, {n - k}) is the same: {fmt(sp.binomial(n, n - k))} ✓")
    m = re.search(r"\bp\((\d+),\s*(\d+)\)", t) or re.search(r"(\d+)p(\d+)\b", t)
    perm = (int(m.group(1)), int(m.group(2))) if m else None
    if not perm:
        m = re.search(r"(?:ways (?:to|can (?:you|we|i)) )?(?:arrange|order|line up|seat|rank) (\d+) (?:\w+ ){0,3}(?:from|out of|among) (\d+)", t)
        if m:
            perm = (int(m.group(2)), int(m.group(1)))
    if perm:
        n, k = perm
        cap(n, 10000, "n")
        r = sp.ff(n, k) if k <= n else 0
        return Solution("permutations", f"P({n}, {k})", fmt(r),
                        [f"order matters: P(n, k) = n! ÷ (n − k)!", f"= {' × '.join(str(n - i) for i in range(min(k, 8)))}{' × …' if k > 8 else ''} = {fmt(r)}"])
    m = re.search(r"(?:arrangements|permutations|ways to arrange|ways can (?:you|we|i) arrange|rearrange) (?:of )?(?:all )?(?:the )?letters (?:in|of) (?:the word )?\"?'?([a-z]+)", t)
    if m:
        w = m.group(1)
        cap(len(w), 60, "the word length")
        counts = {c: w.count(c) for c in dict.fromkeys(w)}
        r = sp.factorial(len(w))
        for c in counts.values():
            r /= sp.factorial(c)
        rep = {c: k for c, k in counts.items() if k > 1}
        steps = [f"{len(w)} letters → {len(w)}! orderings"]
        if rep:
            steps.append("divide by the repeats: " + " × ".join(f"{k}! ({c.upper()})" for c, k in rep.items()))
        return Solution("permutations", f"arrangements of {w.upper()}", fmt(r), steps)
    m = re.search(r"(?:how many ways|in how many ways|number of ways)(?: can| to)? (?:you |we |i |they )?(?:arrange|order|line up|seat|sit|stack|rank) (\d+) ", t) \
        or re.search(r"(?:how many ways|in how many ways)(?: can)? (\d+) (?:\w+ )?(?:be arranged|line up|sit|stand)", t)
    if m:
        n = int(m.group(1))
        cap(n, 2000, "n")
        r = sp.factorial(n)
        return Solution("permutations", f"arrangements of {n} items", fmt(r),
                        [f"{n} choices for the first place, {n - 1} for the second, …", f"{n}! = {fmt(r)}"])
    m = re.search(r"handshakes? (?:among|between|with|for|if) (\d+) (?:people|persons|guests|players)", t) \
        or re.search(r"(\d+) (?:people|persons|guests|players) (?:\w+ ){0,5}(?:each )?shake hands", t)
    if m:
        n = int(m.group(1))
        r = n * (n - 1) // 2
        return Solution("combinations", f"handshakes among {n} people", f"{r:,}",
                        ["each handshake is a pair of people: C(n, 2) = n(n − 1)/2", f"{n} × {n - 1} ÷ 2 = {r:,}"])
    return None


CARDS = {"ace": 4, "king": 4, "queen": 4, "jack": 4, "heart": 13, "spade": 13, "club": 13, "diamond": 13,
         "red card": 26, "black card": 26, "face card": 12, "red": 26, "black": 26}


def probability(t: str) -> Solution | None:
    if "probab" not in t and "chance" not in t and "odds" not in t:
        return None
    m = re.search(r"(?:sum|total) of (\d+) (?:with|on|when rolling|rolling) (?:two|2|a pair of) (?:fair )?dice|"
                  r"(?:rolling|getting|roll|throwing) (?:a )?(?:sum of |total of )?(\d+) (?:with|on) (?:two|2|a pair of) (?:fair )?dice", t)
    if m:
        s = int(m.group(1) or m.group(2))
        ways = [(a, b) for a in range(1, 7) for b in range(1, 7) if a + b == s]
        p = sp.Rational(len(ways), 36)
        return Solution("probability", f"P(sum = {s} with two dice)", show(p),
                        ["two dice have 6 × 6 = 36 equally likely outcomes",
                         f"outcomes that sum to {s}: {', '.join(f'({a},{b})' for a, b in ways) or 'none'} → {len(ways)}",
                         f"P = {len(ways)}/36 = {show(p)}"])
    m = re.search(r"(?:rolling|getting|roll|throwing) (?:a |an )?(\d+) (?:on|with) (?:a |one )?(?:fair )?(?:die|dice|six-sided die)", t)
    if m:
        k = int(m.group(1))
        p = sp.Rational(1, 6) if 1 <= k <= 6 else sp.Integer(0)
        return Solution("probability", f"P(roll {k})", show(p), ["a die has 6 equally likely faces", f"{'one face shows ' + str(k) if p else 'no face shows ' + str(k)} → {show(p)}"])
    m = re.search(r"(exactly |at least |at most )?(\d+) (heads|tails) (?:in|when|with|from|out of) (?:flipping |tossing )?(?:a (?:fair )?coin )?(\d+) (?:times|flips|tosses|coin flips|coin tosses|coins)", t)
    if m:
        mode, k, n = (m.group(1) or "exactly ").strip(), int(m.group(2)), int(m.group(4))
        cap(n, 1000, "the number of tosses")
        ks = {"exactly": [k], "at least": range(k, n + 1), "at most": range(0, k + 1)}[mode]
        ways = int(sum(sp.binomial(n, i) for i in ks))
        p = ways / sp.Integer(2) ** n
        return Solution("probability", f"P({mode} {k} {m.group(3)} in {n} tosses)", show(p),
                        [f"{n} tosses → 2^{n} = {2 ** n:,} equally likely outcomes",
                         f"favourable: {' + '.join(f'C({n},{i})' for i in list(ks)[:6])}{' + …' if len(ks) > 6 else ''} = {ways:,}",
                         f"P = {ways:,}/{2 ** n:,} = {show(p)}"])
    m = re.search(r"(?:drawing|draw|picking|pick|getting) (?:a |an )?(ace|king|queen|jack|heart|spade|club|diamond|red card|black card|face card|red|black)s?", t)
    if m and ("card" in t or "deck" in t):
        c = CARDS[m.group(1)]
        p = sp.Rational(c, 52)
        return Solution("probability", f"P(draw a {m.group(1)})", show(p), ["a standard deck has 52 cards", f"{c} of them are {m.group(1)}s → {c}/52 = {show(p)}"])
    return None


# ---------------------------------------------------------------- units

U = {  # alias → (dimension, factor to the base unit)
    "mm": ("len", "0.001"), "millimeter": ("len", "0.001"), "millimetre": ("len", "0.001"), "cm": ("len", "0.01"),
    "centimeter": ("len", "0.01"), "centimetre": ("len", "0.01"), "m": ("len", "1"), "meter": ("len", "1"), "metre": ("len", "1"),
    "km": ("len", "1000"), "kilometer": ("len", "1000"), "kilometre": ("len", "1000"), "in": ("len", "0.0254"),
    "inch": ("len", "0.0254"), "inches": ("len", "0.0254"), "ft": ("len", "0.3048"), "foot": ("len", "0.3048"),
    "feet": ("len", "0.3048"), "yd": ("len", "0.9144"), "yard": ("len", "0.9144"), "mi": ("len", "1609.344"), "mile": ("len", "1609.344"),
    "mg": ("mass", "0.000001"), "milligram": ("mass", "0.000001"), "g": ("mass", "0.001"), "gram": ("mass", "0.001"),
    "kg": ("mass", "1"), "kilogram": ("mass", "1"), "tonne": ("mass", "1000"), "ton": ("mass", "1000"), "lb": ("mass", "0.45359237"),
    "lbs": ("mass", "0.45359237"), "pound": ("mass", "0.45359237"), "oz": ("mass", "0.028349523125"), "ounce": ("mass", "0.028349523125"),
    "ms": ("time", "0.001"), "millisecond": ("time", "0.001"), "s": ("time", "1"), "sec": ("time", "1"), "second": ("time", "1"),
    "min": ("time", "60"), "minute": ("time", "60"), "h": ("time", "3600"), "hr": ("time", "3600"), "hour": ("time", "3600"),
    "day": ("time", "86400"), "week": ("time", "604800"), "year": ("time", "31536000"), "decade": ("time", "315360000"),
    "ml": ("vol", "0.001"), "milliliter": ("vol", "0.001"), "millilitre": ("vol", "0.001"), "l": ("vol", "1"), "liter": ("vol", "1"),
    "litre": ("vol", "1"), "gallon": ("vol", "3.785411784"), "gal": ("vol", "3.785411784"),
    "bit": ("data", "0.125"), "byte": ("data", "1"), "kb": ("data", "1000"), "kilobyte": ("data", "1000"), "mb": ("data", "1000000"),
    "megabyte": ("data", "1000000"), "gb": ("data", "1000000000"), "gigabyte": ("data", "1000000000"), "tb": ("data", "1000000000000"),
    "terabyte": ("data", "1000000000000"), "kib": ("data", "1024"), "mib": ("data", "1048576"), "gib": ("data", "1073741824"),
    "km/h": ("speed", "5/18"), "kmph": ("speed", "5/18"), "kph": ("speed", "5/18"), "mph": ("speed", "0.44704"), "m/s": ("speed", "1"),
    "knot": ("speed", "0.514444"),
    "km2": ("area", "1000000"), "square kilometer": ("area", "1000000"), "square kilometre": ("area", "1000000"),
    "sq km": ("area", "1000000"), "square mile": ("area", "2589988.110336"), "sq mi": ("area", "2589988.110336"),
    "acre": ("area", "4046.8564224"), "hectare": ("area", "10000"), "m2": ("area", "1"), "square meter": ("area", "1"),
    "square metre": ("area", "1"), "square feet": ("area", "0.09290304"), "square foot": ("area", "0.09290304"),
    "c": ("temp", None), "celsius": ("temp", None), "°c": ("temp", None), "f": ("temp", None), "fahrenheit": ("temp", None),
    "°f": ("temp", None), "k": ("temp", None), "kelvin": ("temp", None),
}
_UNIT = "|".join(re.escape(u) + "s?" for u in sorted(U, key=len, reverse=True))


def _unit(u: str):
    u = u.strip().rstrip(".")
    if u in U:
        return u
    if u.endswith("es") and u[:-2] in U:
        return u[:-2]
    if u.endswith("s") and u[:-1] in U:
        return u[:-1]
    return None


def _temp(x, a, b):
    to_c = {"c": lambda v: v, "f": lambda v: (v - 32) * sp.Rational(5, 9), "k": lambda v: v - sp.Rational(27315, 100)}
    from_c = {"c": lambda v: v, "f": lambda v: v * sp.Rational(9, 5) + 32, "k": lambda v: v + sp.Rational(27315, 100)}
    return from_c[b](to_c[a](x))


def units(t: str) -> Solution | None:
    m = re.search(rf"(?:convert )?{N} ?({_UNIT}) (?:to|in|into|as|=) ({_UNIT})\??$", t)
    amount = None
    if m:
        amount, a, b = num(m.group(1)), _unit(m.group(2)), _unit(m.group(3))
    else:
        m = re.search(rf"how many ({_UNIT}) (?:are )?(?:there )?in (?:a |an |one |{N} )?({_UNIT})\??$", t)
        if m:
            amount, a, b = (num(m.group(2)) if m.group(2) else sp.Integer(1)), _unit(m.group(3)), _unit(m.group(1))
    if amount is None or not a or not b:
        return None
    da, fa = U[a]
    db, fb = U[b]
    if da != db:
        raise MathError(f"can't convert {a} ({da}) to {b} ({db})")
    if da == "temp":
        key = {"celsius": "c", "°c": "c", "fahrenheit": "f", "°f": "f", "kelvin": "k"}
        ka, kb = key.get(a, a), key.get(b, b)
        r = _temp(amount, ka, kb)
        formula = {("c", "f"): "°F = °C × 9/5 + 32", ("f", "c"): "°C = (°F − 32) × 5/9", ("c", "k"): "K = °C + 273.15",
                   ("k", "c"): "°C = K − 273.15"}.get((ka, kb), "via Celsius")
        return Solution("units", f"{fmt(amount)} °{ka.upper()} in °{kb.upper()}", f"{nice(r)} {'K' if kb == 'k' else '°' + kb.upper()}", [formula])
    ra, rb = sp.Rational(fa), sp.Rational(fb)
    r = amount * ra / rb
    notes = ["(a 365-day year)"] if "year" in (a, b) or "decade" in (a, b) else []
    notes += ["(decimal units: 1 kB = 1000 bytes; use KiB/MiB for 1024)"] if da == "data" and not {a, b} & {"kib", "mib", "gib", "bit", "byte"} else []
    label = b + ("es" if b == "inch" else "" if b in ("feet", "sheep") else "s") if len(b) > 3 and "/" not in b and r != 1 else b
    return Solution("units", f"{fmt(amount)} {a} in {b}", f"{nice(r)} {label}",
                    [f"1 {a} = {nice(ra / rb)} {b}", f"{fmt(amount)} × {nice(ra / rb)} = {nice(r)}"] + notes)


# ---------------------------------------------------------------- algebra with conditions

def _defs(parts: list[str]):
    funcs, eqs = {}, []
    for p in parts:
        p = p.strip(" .")
        if not p:
            continue
        m = re.fullmatch(r"([a-z])\(([a-z])\)\s*=\s*(.+)", p)
        if m:
            v = sp.Symbol(m.group(2))
            funcs[m.group(1)] = sp.Lambda(v, to_expr(_words_to_symbols(m.group(3))))
            continue
        if "=" not in p:
            raise MathError(f"I can't read the condition '{p}'")
        left, right = p.split("=", 1)
        eqs.append(sp.Eq(_expr_with(left, funcs), _expr_with(right, funcs)))
    return funcs, eqs


def _expr_with(s: str, funcs: dict):
    s = _words_to_symbols(s.strip())
    for name, lam in funcs.items():
        def call(m, lam=lam):
            return f"({sp.sstr(lam(to_expr(m.group(1))))})"
        for _ in range(3):
            s = re.sub(rf"\b{name}\s*\(([^()]*)\)", call, s)
    return to_expr(s)


def algebra(t: str) -> Solution | None:
    t = t.rstrip("?. ")
    m = re.search(r"(?:^|\b)(?:if|given(?: that)?|suppose|let|when)\s+(.+?),?\s+(?:then\s+)?(?:what is|what's|find|evaluate|compute|calculate|determine|work out)\s+(?:the value of\s+)?(.+)$", t) \
        or re.search(r"^([a-z]\([a-z]\)\s*=\s*[^,;]+)[,;.]\s*(?:what is|what's|find|evaluate|compute|calculate)\s+(?:the value of\s+)?(.+)$", t)
    target_first = False
    if not m:
        m = re.search(r"^(?:find|what is|what's|solve for|determine)\s+([a-z](?:\s*(?:,|and)\s*[a-z])*)\s+(?:if|when|given(?: that)?|such that|where)\s+(.+)$", t)
        target_first = bool(m)
    if not m:
        return None
    cond, target = (m.group(2), m.group(1)) if target_first else (m.group(1), m.group(2))
    if "=" not in cond:
        return None
    parts = [p for p in re.split(r"\s*(?:,|;|\band\b)\s*", cond) if p]
    funcs, eqs = _defs(parts)
    targets = [x.strip() for x in re.split(r"\s*(?:,|\band\b)\s*", target) if x.strip()]
    texprs = [_expr_with(x, funcs) for x in targets]
    steps = [f"given: {fmt(e.lhs)} = {fmt(e.rhs)}" for e in eqs] + [f"{n}({lam.variables[0]}) = {fmt(lam.expr)}" for n, lam in funcs.items()]
    if eqs:
        unknowns = sorted(set().union(*(e.free_symbols for e in eqs)), key=lambda s: s.name)
        sol = _timed(lambda: sp.solve(eqs, unknowns, dict=True))
        if not sol:
            return Solution("algebra", "; ".join(parts), "no solution: the conditions contradict each other", steps)
        s0 = sol[0]
        steps.append("solve the conditions: " + ", ".join(f"{k} = {show(v)}" for k, v in s0.items()))
        if len(sol) > 1:
            steps.append(f"({len(sol)} solutions; using the first)")
    else:
        s0 = {}
    answers = []
    for name, e in zip(targets, texprs):
        v = sp.simplify(e.subs(s0))
        steps.append(f"{name} = {fmt(e)} → {show(v)}" if str(e) != name else f"{name} = {show(v)}")
        answers.append(f"{name} = {show(v)}" if len(targets) > 1 or v.free_symbols else show(v))
    check = ""
    if eqs and s0:
        ok = all(sp.simplify(e.lhs.subs(s0) - e.rhs.subs(s0)) == 0 for e in eqs)
        check = f"the values satisfy every condition {'✓' if ok else '✗'}"
    return Solution("algebra", "; ".join(parts) + " → " + ", ".join(targets), ", ".join(answers), steps, check)


# ---------------------------------------------------------------- "a number" problems

THE_NUMBER = r"(?:(?:a|the|some|a certain|what|an unknown|that|this|my|your) )?(?:number|integer|value)"
X = sp.Symbol("x")


def _split_try(p: str, sep: str, combine):
    for m in re.finditer(re.escape(sep), p):
        a, b = p[:m.start()], p[m.end():]
        try:
            return combine(phrase(a), phrase(b))
        except MathError:
            continue
    return None


def phrase(p: str):
    """English arithmetic phrase about 'a number' → sympy expression in x."""
    p = p.strip(" ,.?").removeprefix("then ")
    p = re.sub(r"^(?:the result of|the value of|the answer to)\s+", "", p)
    if not p:
        raise MathError("empty phrase")
    if re.fullmatch(rf"{THE_NUMBER}|it|x|the result|the answer|the original number", p):
        return X
    if re.fullmatch(N, p):
        return num(p)
    m = re.fullmatch(r"(?:the )?(sum|difference|product|quotient|ratio) (?:of|between) (.+)", p)
    if m:
        op = m.group(1)
        sep = " to " if op == "ratio" else " and "
        r = _split_try(m.group(2), sep, {"sum": lambda a, b: a + b, "difference": lambda a, b: a - b,
                                          "product": lambda a, b: a * b, "quotient": lambda a, b: a / b,
                                          "ratio": lambda a, b: a / b}[op])
        if r is not None:
            return r
    for sep, comb in ((" more than ", lambda a, b: b + a), (" greater than ", lambda a, b: b + a),
                      (" less than ", lambda a, b: b - a), (" fewer than ", lambda a, b: b - a),
                      (" added to ", lambda a, b: b + a), (" subtracted from ", lambda a, b: b - a),
                      (" increased by ", lambda a, b: a + b), (" decreased by ", lambda a, b: a - b),
                      (" reduced by ", lambda a, b: a - b), (" plus ", lambda a, b: a + b), (" minus ", lambda a, b: a - b),
                      (" + ", lambda a, b: a + b), (" - ", lambda a, b: a - b),
                      (" divided by ", lambda a, b: a / b), (" over ", lambda a, b: a / b),
                      (" multiplied by ", lambda a, b: a * b), (" times ", lambda a, b: a * b), (" * ", lambda a, b: a * b)):
        if sep in f" {p} ":
            r = _split_try(p, sep.strip(" ") if sep.strip() in "+-*" else sep, comb) if sep.strip() not in "+-*" else _split_try(p, sep, comb)
            if r is not None:
                return r
    m = re.fullmatch(rf"{P} (?:%|percent) of (.+)", p)
    if m:
        return num(m.group(1)) / 100 * phrase(m.group(2))
    for pat, f in ((r"(?:the )?square of (.+)|(.+) squared", lambda a: a ** 2), (r"(?:the )?cube of (.+)|(.+) cubed", lambda a: a ** 3),
                   (r"(?:the )?square root of (.+)", sp.sqrt), (r"(?:the )?reciprocal of (.+)", lambda a: 1 / a),
                   (r"half (?:of )?(.+)", lambda a: a / 2), (r"(?:a |one )?third of (.+)", lambda a: a / 3),
                   (r"(?:a |one )?quarter of (.+)|(?:a |one )?fourth of (.+)", lambda a: a / 4),
                   (r"double (.+)", lambda a: 2 * a), (r"(?:the )?(?:opposite|negative) of (.+)", lambda a: -a),
                   (r"(?:the )?(?:number|value) (.+)", lambda a: a)):
        m = re.fullmatch(pat, p)
        if m:
            inner = next(g for g in m.groups() if g)
            return f(phrase(inner))
    raise MathError(f"I can't read '{p}'")


EQ_WORDS = (" is equal to ", " equals ", " is the same as ", " gives ", " results in ", " will be ", " makes ", " is ", " = ", " was ")
ASK = re.compile(r"[.?!,;]?\s*(?:so |then )?(?:what|find|which|determine|calculate|work out)\b[^.?!]*(?:number|it|x|value)[^.?!]*[.?!]?\s*$")


def a_number(t: str, original: str) -> Solution | None:
    if not re.search(rf"{THE_NUMBER}|\bthink of\b", t):
        return None
    body = ASK.sub("", t).strip(" .?")
    body = re.sub(r"^(?:if |when |suppose )", "", body)
    sol = _chain(body)
    if sol:
        return sol
    for sep in EQ_WORDS:
        for m in re.finditer(re.escape(sep), body):
            left, right = body[:m.start()], body[m.end():]
            try:
                lhs, rhs = phrase(left), phrase(right)
            except MathError:
                continue
            if not (lhs.has(X) or rhs.has(X)):
                continue
            return _finish_number(f"'{left.strip()}' → {fmt(lhs)}", f"'{right.strip()}' → {fmt(rhs)}", lhs, rhs)
    return None


def _finish_number(s1: str, s2: str, lhs, rhs, extra: list | None = None) -> Solution:
    steps = (extra or []) + ["let the number be x", f"translate: {s1}", f"translate: {s2}", f"equation: {fmt(lhs)} = {fmt(rhs)}"]
    sols = _timed(lambda: sp.solve(sp.Eq(lhs, rhs), X))
    if not sols:
        return Solution("word_problem", f"{fmt(lhs)} = {fmt(rhs)}", "no number works", steps)
    real = [s for s in sols if s.is_real] or sols
    checks = "; ".join(f"x = {fmt(s)}: {fmt(lhs.subs(X, s))} = {fmt(rhs.subs(X, s))} {'✓' if sp.simplify(lhs.subs(X, s) - rhs.subs(X, s)) == 0 else '✗'}" for s in real[:2])
    ans = " or ".join(show(s) for s in real)
    return Solution("word_problem", f"{fmt(lhs)} = {fmt(rhs)}", f"the number is {ans}", steps, checks)


CHAIN_OPS = [
    (rf"(?:it is |is |was )?doubled|double it|multiply it by 2", lambda e, n: 2 * e, "×2"),
    (rf"(?:it is |is |was )?tripled|triple it", lambda e, n: 3 * e, "×3"),
    (rf"(?:it is |is |was )?halved|halve it", lambda e, n: e / 2, "÷2"),
    (rf"(?:it is |is |was )?squared|square it", lambda e, n: e ** 2, "²"),
    (rf"(?:it is |is |was )?(?:increased by|added to) {N}|(?:add|plus|adding) {N}(?: to it)?|{N} (?:is |was )?added(?: to it)?",
     lambda e, n: e + n, "+"),
    (rf"(?:it is |is |was )?(?:decreased|reduced) by {N}|(?:subtract|subtracting|minus|take away|taking away) {N}(?: from it)?|{N} (?:is |was )?(?:subtracted|taken away)(?: from it)?",
     lambda e, n: e - n, "−"),
    (rf"(?:it is |is |was )?multiplied by {N}|(?:multiply|multiplying) (?:it |that |the result )?by {N}|times {N}", lambda e, n: e * n, "×"),
    (rf"(?:it is |is |was )?divided by {N}|(?:divide|dividing) (?:it |that |the result )?by {N}", lambda e, n: e / n, "÷"),
]
RESULT = re.compile(rf"(?:the (?:result|answer|total|final number|final result) (?:is|was|will be)|(?:(?:i|you|we|and) )?(?:get|got|end up with|obtain)|"
                    rf"(?:it |this |that )?(?:gives|equals|becomes|makes|results in)|to get|is equal to|=|the result is|you'll get|you will get) {N}")


def _chain(body: str) -> Solution | None:
    m = re.search(rf"(?:^|\b)(?:i |you )?(?:think of|take|start with|pick|choose|have)?\s*{THE_NUMBER}[, ]*(?:when |is |,)?", body)
    if not m:
        return None
    rest = body[m.end():]
    rm = RESULT.search(rest)
    if not rm:
        return None
    ops_text, target = rest[:rm.start()], num(rm.group(1))
    e, steps = X, []
    pieces = [p for p in re.split(r"\s*(?:,|\band then\b|\bthen\b|\band\b|\.)\s*", ops_text) if p.strip()]
    if not pieces:
        return None
    for piece in pieces:
        piece = piece.strip()
        for pat, f, sym in CHAIN_OPS:
            pm = re.fullmatch(pat, piece)
            if pm:
                n = next((num(g) for g in pm.groups() if g), None)
                before = e
                e = f(e, n)
                steps.append(f"'{piece}': {fmt(before)} → {fmt(e)}")
                break
        else:
            return None
    return _finish_number("start with x", f"after the steps: {fmt(e)} = {fmt(target)}", e, target, ["follow each step in order:"] + steps)


# ---------------------------------------------------------------- classic word problems

def two_numbers(t: str) -> Solution | None:
    if not re.search(r"\b(?:two|2) (?:positive |whole |natural |real )?(?:numbers|integers)\b|\bthe other\b", t):
        return None
    x, y = sp.symbols("x y")
    eqs, steps = [], []
    rules = [
        (rf"(?:their |the )?sum(?: of (?:the |these )?(?:2 )?(?:numbers|integers))? is {N}|(?:add up to|sum to|total) {N}|(?:have|has) a sum of {N}", lambda a: sp.Eq(x + y, a)),
        (rf"(?:their |the )?difference(?: (?:of|between) (?:the |these )?(?:2 )?(?:numbers|integers))? is {N}|differ by {N}|(?:have|has) a difference of {N}", lambda a: sp.Eq(x - y, a)),
        (rf"(?:their |the )?product(?: of (?:the |these )?(?:2 )?(?:numbers|integers))? is {N}|multiply to {N}|(?:have|has) a product of {N}", lambda a: sp.Eq(x * y, a)),
        (rf"(?:their |the )?quotient is {N}", lambda a: sp.Eq(x, a * y)),
        (rf"(?:one|the (?:first|larger|bigger|greater)(?: number)?|one of them) is {N} times (?:the other|the second|the smaller|the first)", lambda a: sp.Eq(x, a * y)),
        (rf"(?:one|the (?:first|larger|bigger|greater)(?: number)?|one of them) is {N} more than (?:the other|the second|the smaller)", lambda a: sp.Eq(x, y + a)),
        (rf"(?:one|the (?:first|smaller)(?: number)?|one of them) is {N} less than (?:the other|the second|the larger)", lambda a: sp.Eq(y, x - a)),
        (rf"(?:in the |their )?ratio (?:is |of )?{P} ?: ?{P}", None),
    ]
    for pat, mk in rules:
        for m in re.finditer(pat, t):
            vals = [num(g) for g in m.groups() if g]
            if mk is None:
                a, b = vals
                eq = sp.Eq(b * x, a * y)
            else:
                eq = mk(vals[0])
            eqs.append(eq)
            steps.append(f"'{m.group(0)}' → {fmt(eq.lhs)} = {fmt(eq.rhs)}")
    if len(eqs) < 2:
        return None
    sols = _timed(lambda: sp.solve(eqs[:2], [x, y], dict=True))
    sols = [s for s in sols if all(v.is_real for v in s.values())]
    if not sols:
        return Solution("word_problem", "two numbers", "no real numbers satisfy that", steps)
    s0 = max(sols, key=lambda s: (bool(s[x] >= s[y]), float(s[x])))
    a, b = sorted([s0[x], s0[y]], reverse=True)
    ok = all(sp.simplify(e.lhs.subs(s0) - e.rhs.subs(s0)) == 0 for e in eqs)
    return Solution("word_problem", "two numbers", f"{show(a)} and {show(b)}",
                    ["let the numbers be x and y (x the larger)"] + steps + [f"solve: x = {show(s0[x])}, y = {show(s0[y])}"],
                    f"both conditions hold {'✓' if ok else '✗'}")


def consecutive(t: str) -> Solution | None:
    m = re.search(rf"product of (\d+) consecutive (even |odd )?(?:positive )?(?:integers|numbers|whole numbers|natural numbers)? ?(?:is|equals|=) {N}", t)
    kind = "product"
    if not m:
        kind = "sum"
        m = re.search(rf"(?:sum|total) of (\d+) consecutive (even |odd )?(?:positive )?(?:integers|numbers|whole numbers|natural numbers)? ?(?:is|equals|=) {N}", t) \
            or re.search(rf"(\d+) consecutive (even |odd )?(?:positive )?(?:integers|numbers|whole numbers|natural numbers)?\s*(?:whose sum is|with a sum of|that add up to|add up to|sum to|have a sum of|total)\s*{N}", t)
    if not m:
        return None
    k, par, target = int(m.group(1)), (m.group(2) or "").strip(), num(m.group(3))
    cap(k, 50, "the count")
    step = 2 if par else 1
    terms = [X + step * i for i in range(k)]
    expr = sum(terms) if kind == "sum" else sp.Mul(*terms)
    sols = _timed(lambda: sp.solve(sp.Eq(expr, target), X))
    good = [s for s in sols if s.is_integer and (not par or (s % 2 == (0 if par == "even" else 1)))]
    steps = [f"let them be {', '.join(fmt(e) for e in terms)}", f"{kind}: {fmt(sp.expand(expr))} = {fmt(target)}"]
    if not good:
        return Solution("word_problem", f"{k} consecutive {par} integers", "no such integers exist",
                        steps + [f"x = {', '.join(show(s) for s in sols) or 'none'} isn't a valid {par or 'whole'} number"])
    s = max(good)
    vals = [e.subs(X, s) for e in terms]
    return Solution("word_problem", f"{k} consecutive {par + ' ' if par else ''}integers with {kind} {fmt(target)}",
                    ", ".join(map(fmt, vals)), steps + [f"x = {fmt(s)}"],
                    f"{(' + ' if kind == 'sum' else ' × ').join(map(fmt, vals))} = {fmt(sum(vals) if kind == 'sum' else sp.Mul(*vals))} ✓")


NAME = r"((?:his |her |their )?[a-z]+)"
_SKIP = {"it", "they", "who", "what", "how", "which", "the", "a", "and", "is", "will", "was", "in", "ago", "years", "year",
         "there", "this", "that", "one"}
PRONOUNS = {"he", "she", "him", "her"}


def ages(t: str) -> Solution | None:
    if not re.search(r"\b(?:old|older|younger|age|ages|years ago|in \d+ years)\b", t):
        return None
    syms: dict[str, sp.Symbol] = {}
    state = {"last": None}

    def v(name, subject=False):
        name = re.sub(r"^(?:his|her|their) ", "", name)
        if name in PRONOUNS:
            if not state["last"]:
                raise MathError("can't tell who 'he/she' is")
            return syms[state["last"]]
        if name in _SKIP:
            raise MathError("can't tell who that is")
        if subject:
            state["last"] = name
        return syms.setdefault(name, sp.Symbol(name))

    t2 = re.sub(r"\bhalf as old as\b", "0.5 times as old as", t)
    t2 = re.sub(r"\b2 times as old\b", "2 times as old", t2)
    pats = [
        (rf"in {P} years?,? {NAME} will be {P} times (?:as old as|the age of) {NAME}", lambda n, a, k, b: sp.Eq(v(a, True) + num(n), num(k) * (v(b) + num(n)))),
        (rf"{P} years? ago,? {NAME} was {P} times (?:as old as|the age of) {NAME}", lambda n, a, k, b: sp.Eq(v(a, True) - num(n), num(k) * (v(b) - num(n)))),
        (rf"{NAME} is {P} times (?:as old as|the age of|older than) {NAME}", lambda a, k, b: sp.Eq(v(a, True), num(k) * v(b))),
        (rf"{NAME} is {P} years? older than {NAME}", lambda a, n, b: sp.Eq(v(a, True), v(b) + num(n))),
        (rf"{NAME} is {P} years? younger than {NAME}", lambda a, n, b: sp.Eq(v(a, True), v(b) - num(n))),
        (rf"in {P} years?,? the sum of their ages will be {P}", lambda n, s: sp.Eq(sum(syms.values()) + len(syms) * num(n), num(s))),
        (rf"(?:the )?sum of their (?:present |current )?ages is {P}|their (?:present |current )?ages (?:add up to|sum to|total) {P}|together they are {P}",
         lambda *g: sp.Eq(sum(syms.values()), num(next(x for x in g if x)))),
        (rf"{NAME} is {P}(?: years old)?(?=[ ,.;]|$)(?! times| years? (?:older|younger))", lambda a, n: sp.Eq(v(a, True), num(n))),
    ]
    found = []
    for i, (pat, mk) in enumerate(pats):
        for m in re.finditer(pat, t2):
            found.append((m.start(), i, m, mk))
    found.sort(key=lambda f: (f[0], f[1]))
    eqs, steps, used = [], [], []
    for _, _, m, mk in found:
        if any(m.start() < e and m.end() > s for s, e in used):
            continue
        try:
            eq = mk(*m.groups())
        except MathError:
            continue
        if eq is sp.true or eq is sp.false:
            continue
        used.append(m.span())
        eqs.append(eq)
        steps.append(f"'{m.group(0)}' → {fmt(eq.lhs)} = {fmt(eq.rhs)}")
    if not eqs:
        return None
    if len(eqs) < len(syms):
        return Solution("word_problem", "ages", "not enough information: I need one fact per person", steps, ok=False)
    sol = _timed(lambda: sp.solve(eqs, list(syms.values()), dict=True))
    if not sol:
        return Solution("word_problem", "ages", "the facts contradict each other", steps)
    s0 = sol[0]
    who = re.search(r"how old (?:is|was|will be|are) (?:the |his |her |their )?([a-z]+)", t)
    names = [who.group(1)] if who and who.group(1) in syms else list(syms)
    ans = ", ".join(f"{n.title()} is {show(s0[syms[n]])}" for n in names)
    steps.append("solve together: " + ", ".join(f"{n} = {show(s0[sy])}" for n, sy in syms.items() if sy in s0))
    return Solution("word_problem", "ages", ans, ["one unknown per person: " + ", ".join(syms)] + steps,
                    f"every statement holds {'✓' if all(sp.simplify(e.lhs.subs(s0) - e.rhs.subs(s0)) == 0 for e in eqs) else '✗'}")


TWO_LEGS = r"chickens?|hens?|ducks?|birds?|geese|goose|people|persons?|humans?|chicks?|roosters?|turkeys?|ostriches?"
FOUR_LEGS = r"cows?|pigs?|goats?|rabbits?|dogs?|cats?|horses?|sheep|lambs?|cattle|deer|donkeys?|camels?|bulls?"


def heads_legs(t: str) -> Solution | None:
    m = re.search(rf"{P} (?:heads?|animals|birds and animals)\b.*?{P} (?:legs|feet)\b", t) or re.search(rf"{P} (?:legs|feet)\b.*?{P} heads?\b", t)
    two = re.search(rf"\b({TWO_LEGS})\b", t)
    four = re.search(rf"\b({FOUR_LEGS})\b", t)
    wheels = re.search(rf"{P} (?:vehicles|cars and (?:bikes|bicycles|motorcycles)|(?:bikes|bicycles|motorcycles) and cars)\b.*?{P} wheels", t)
    if wheels:
        h, l = num(wheels.group(1)), num(wheels.group(2))
        a_name, b_name, a_legs, b_legs, unit = "bikes", "cars", 2, 4, "wheels"
        a_name = re.search(r"bicycles|motorcycles|bikes", t).group(0)
    elif m and two and four:
        h, l = (num(m.group(1)), num(m.group(2))) if "head" in t[:m.end()].split("leg")[0] or m.re.pattern.startswith(P + " (?:heads") else (num(m.group(2)), num(m.group(1)))
        if m.re.pattern.startswith(P + " (?:legs"):
            l, h = num(m.group(1)), num(m.group(2))
        a_name, b_name, a_legs, b_legs, unit = two.group(1), four.group(1), 2, 4, "legs"
    else:
        return None
    a, b = sp.symbols("a b")
    s = sp.solve([sp.Eq(a + b, h), sp.Eq(a_legs * a + b_legs * b, l)], [a, b], dict=True)[0]
    steps = [f"let a = {a_name}, b = {b_name}", f"heads: a + b = {fmt(h)}", f"{unit}: {a_legs}a + {b_legs}b = {fmt(l)}",
             f"if all {fmt(h)} were {a_name}: {a_legs * h} {unit}; the extra {fmt(l - a_legs * h)} come from {b_name}, {b_legs - a_legs} extra each → b = {fmt(s[b])}"]
    if not (s[a].is_integer and s[b].is_integer and s[a] >= 0 and s[b] >= 0):
        return Solution("word_problem", "heads and legs", "no whole-number answer fits those totals", steps)
    return Solution("word_problem", f"{fmt(h)} heads, {fmt(l)} {unit}", f"{fmt(s[a])} {a_name} and {fmt(s[b])} {b_name}", steps,
                    f"{fmt(s[a])} + {fmt(s[b])} = {fmt(h)} and {a_legs}×{fmt(s[a])} + {b_legs}×{fmt(s[b])} = {fmt(l)} ✓")


SPEED_U = {"km/h": ("km", "h"), "kmph": ("km", "h"), "kph": ("km", "h"), "km per hour": ("km", "h"), "kilometers per hour": ("km", "h"),
           "kilometres per hour": ("km", "h"), "km an hour": ("km", "h"), "mph": ("mile", "h"), "miles per hour": ("mile", "h"),
           "miles an hour": ("mile", "h"), "m/s": ("m", "s"), "meters per second": ("m", "s"), "metres per second": ("m", "s")}
DIST_U = {"km": "km", "kms": "km", "kilometers": "km", "kilometres": "km", "kilometer": "km", "kilometre": "km", "miles": "mile",
          "mile": "mile", "m": "m", "meters": "m", "metres": "m", "meter": "m", "metre": "m"}
TIME_U = {"hours": "h", "hour": "h", "hrs": "h", "hr": "h", "h": "h", "minutes": "min", "minute": "min", "mins": "min",
          "min": "min", "seconds": "s", "second": "s", "secs": "s", "sec": "s", "s": "s"}
TO_BASE = {"km": 1000, "mile": sp.Rational("1609.344"), "m": 1, "h": 3600, "min": 60, "s": 1}


def motion(t: str) -> Solution | None:
    if not re.search(r"speed|how fast|how long|how far|how much time|distance|travel|drive|drives|ride|walks?|runs?|trip|journey|train|car", t):
        return None
    m = re.search(rf"(?:at|with|averag\w*) {P} ?(?:km/h|kmph|kph|mph|km per hour|km an hour|miles per hour|miles an hour)?\b.*?(?:return\w*|back|comes back|home)\b.*?(?:at|with) {P}", t)
    if m and "average speed" in t:
        a, b = num(m.group(1)), num(m.group(2))
        r = 2 * a * b / (a + b)
        return Solution("word_problem", "round-trip average speed", f"{nice(r)}", [
            "same distance d each way, so average speed = total distance ÷ total time",
            f"= 2d ÷ (d/{fmt(a)} + d/{fmt(b)}) = 2·{fmt(a)}·{fmt(b)} ÷ ({fmt(a)} + {fmt(b)}) = {nice(r)}",
            "(not the simple mean of the two speeds: more time is spent at the slower speed)"],
            f"try d = {fmt(a * b)}: time {fmt(b)} + {fmt(a)} = {fmt(a + b)}, total {fmt(2 * a * b)} ÷ {fmt(a + b)} = {nice(r)} ✓")
    spd_alt = "|".join(re.escape(k) for k in sorted(SPEED_U, key=len, reverse=True))
    sp_m = re.search(rf"{P} ?({spd_alt})\b", t)
    rest = t[:sp_m.start()] + " " + t[sp_m.end():] if sp_m else t
    d_m = re.search(rf"{P} ?({'|'.join(sorted(DIST_U, key=len, reverse=True))})\b", rest)
    t_m = re.search(rf"{P} ?({'|'.join(sorted(TIME_U, key=len, reverse=True))})\b", rest)
    speed = (num(sp_m.group(1)), SPEED_U[sp_m.group(2)]) if sp_m else None
    dist = (num(d_m.group(1)), DIST_U[d_m.group(2)]) if d_m else None
    tm = (num(t_m.group(1)), TIME_U[t_m.group(2)]) if t_m else None
    if sum(v is not None for v in (speed, dist, tm)) != 2:
        return None
    if re.search(r"how fast|what (?:is|was) (?:its|his|her|their|the)? ?(?:average )?speed|find (?:the )?speed|speed\?", t) and dist and tm:
        du, tu = dist[1], ("h" if tm[1] in ("h", "min") and dist[1] != "m" else tm[1])
        tv = tm[0] * TO_BASE[tm[1]] / TO_BASE[tu]
        r = dist[0] / tv
        unit = {"km": "km/h", "mile": "mph", "m": "m/s" if tu == "s" else f"m/{tu}"}[du] if tu == "h" or du == "m" else f"{du}/{tu}"
        steps = ["speed = distance ÷ time"] + ([f"{fmt(tm[0])} {tm[1]} = {nice(tv)} {tu}"] if tm[1] != tu else []) + [f"{fmt(dist[0])} {du} ÷ {nice(tv)} {tu} = {nice(r)} {unit}"]
        return Solution("word_problem", "speed", f"{nice(r)} {unit}", steps, f"{nice(r)} × {nice(tv)} = {fmt(dist[0])} {du} ✓")
    if re.search(r"how long|how much time|how many (?:hours|minutes|seconds)|time (?:taken|needed|required)|take\?", t) and dist and speed:
        sd, st = speed[1]
        dv = dist[0] * TO_BASE[dist[1]] / TO_BASE[sd]
        r = dv / speed[0]
        steps = ["time = distance ÷ speed"] + ([f"{fmt(dist[0])} {dist[1]} = {nice(dv)} {sd}"] if dist[1] != sd else []) + [f"{nice(dv)} ÷ {fmt(speed[0])} = {nice(r)} {st}"]
        ans = f"{nice(r)} {'hours' if st == 'h' else 'seconds'}"
        if st == "h" and not r.is_integer:
            hrs = int(r)
            mins = (r - hrs) * 60
            ans += f" ({hrs} h {nice(mins)} min)"
        return Solution("word_problem", "travel time", ans, steps, f"{fmt(speed[0])} × {nice(r)} = {nice(dv)} ✓")
    if re.search(r"how far|distance|how many (?:km|kilomet|miles|meters|metres)", t) and speed and tm:
        sd, st = speed[1]
        tv = tm[0] * TO_BASE[tm[1]] / TO_BASE[st]
        r = speed[0] * tv
        steps = ["distance = speed × time"] + ([f"{fmt(tm[0])} {tm[1]} = {nice(tv)} {st}"] if tm[1] != st else []) + [f"{fmt(speed[0])} × {nice(tv)} = {nice(r)} {sd}"]
        return Solution("word_problem", "distance", f"{nice(r)} {sd if sd != 'mile' else 'miles'}", steps, f"{nice(r)} ÷ {nice(tv)} = {fmt(speed[0])} ✓")
    return None


def shopping(t: str, cur: str) -> Solution | None:
    m = re.search(rf"(?:bought|buys|purchased|cost price (?:is|was|of)?|cp (?:is|of)?)\D*?{P}.*?(?:sold|sells|selling price (?:is|was|of)?|sp (?:is|of)?)\D*?{P}", t)
    if m:
        a, b = num(m.group(1)), num(m.group(2))
        if a == 0:
            raise MathError("cost price can't be 0")
        diff = b - a
        pct = diff / a * 100
        word = "profit" if diff > 0 else "loss" if diff < 0 else "no profit or loss"
        return Solution("word_problem", f"bought {money(a, cur)}, sold {money(b, cur)}",
                        f"{word} of {money(abs(diff), cur)} ({nice(abs(pct))}%)" if diff else word,
                        [f"{word} = selling − cost = {money(b, cur)} − {money(a, cur)} = {money(diff, cur)}",
                         f"{word} % = {money(abs(diff), cur)} ÷ {money(a, cur)} × 100 = {nice(abs(pct))}%"])
    pm = re.search(rf"(?:costs?|priced at|price (?:is|of)|marked (?:at )?|sells? for|is|was|worth|for|of) {P}\b", t)
    if not pm:
        return None
    price = num(pm.group(1))
    m = re.search(rf"{P} ?(?:%|percent) (?:off|discount)|discount of {P} ?(?:%|percent)|{P} ?(?:%|percent) (?:sale|reduction)", t)
    if m:
        r = num(next(g for g in m.groups() if g))
        save = price * r / 100
        final = price - save
        asks_saving = re.search(r"how much (?:do|will|did|would) (?:you|i|we|she|he|they) save|discount amount|how much is the discount", t)
        return Solution("word_problem", f"{money(price, cur)} with {fmt(r)}% off",
                        money(save, cur) + " saved" if asks_saving else money(final, cur),
                        [f"discount = {fmt(r)}% of {money(price, cur)} = {money(save, cur)}",
                         f"price after discount = {money(price, cur)} − {money(save, cur)} = {money(final, cur)}"],
                        f"{money(price, cur)} × {nice(1 - r / 100)} = {money(final, cur)} ✓")
    m = re.search(rf"{P} ?(?:%|percent) (sales tax|tax|tip|vat|gst|markup|mark-up|service charge|surcharge)|(tax|tip|vat|gst|markup) (?:of|is|at) {P} ?(?:%|percent)", t)
    if m:
        r = num(m.group(1) or m.group(4))
        what = m.group(2) or m.group(3)
        add = price * r / 100
        return Solution("word_problem", f"{money(price, cur)} plus {fmt(r)}% {what}", money(price + add, cur),
                        [f"{what} = {fmt(r)}% of {money(price, cur)} = {money(add, cur)}", f"total = {money(price, cur)} + {money(add, cur)} = {money(price + add, cur)}"],
                        f"{money(price, cur)} × {nice(1 + r / 100)} = {money(price + add, cur)} ✓")
    return None


FREQ = {"annually": 1, "yearly": 1, "semi-annually": 2, "semiannually": 2, "half-yearly": 2, "quarterly": 4, "monthly": 12, "daily": 365, "weekly": 52}


def interest(t: str, cur: str) -> Solution | None:
    if "interest" not in t and "compounded" not in t:
        return None
    r_m = re.search(rf"{P} ?(?:%|percent)", t)
    y_m = re.search(rf"{P} (years?|months?)", t)
    nums = [num(x) for x in re.findall(r"\d+(?:\.\d+)?", t)]
    if not (r_m and y_m):
        return None
    rate, years = num(r_m.group(1)), num(y_m.group(1)) / (12 if y_m.group(2).startswith("month") else 1)
    used = {r_m.group(1), y_m.group(1)}
    principal = next((x for x in sorted(nums, reverse=True) if str(fmt(x)) not in used and x != rate), None)
    if principal is None:
        return None
    if "compound" in t:
        freq_w = next((w for w in FREQ if w in t), "annually")
        n = FREQ[freq_w]
        amount = principal * (1 + rate / 100 / n) ** (n * years)
        intr = amount - principal
        return Solution("word_problem", f"compound interest on {money(principal, cur)} at {fmt(rate)}% for {fmt(years)} years, {freq_w}",
                        f"interest {money(intr, cur)} (amount {money(amount, cur)})",
                        [f"A = P (1 + r/n)^(n·t), with P = {money(principal, cur)}, r = {fmt(rate / 100)}, n = {n}, t = {fmt(years)}",
                         f"A = {money(principal, cur)} × (1 + {nice(rate / 100 / n)})^{fmt(n * years)} = {money(amount, cur)}",
                         f"interest = A − P = {money(intr, cur)}"])
    intr = principal * rate * years / 100
    return Solution("word_problem", f"simple interest on {money(principal, cur)} at {fmt(rate)}% for {fmt(years)} years",
                    f"interest {money(intr, cur)} (amount {money(principal + intr, cur)})",
                    [f"I = P × R × T ÷ 100 = {money(principal, cur)} × {fmt(rate)} × {fmt(years)} ÷ 100 = {money(intr, cur)}",
                     f"amount = P + I = {money(principal + intr, cur)}"],
                    f"{money(intr / years, cur)} per year × {fmt(years)} years = {money(intr, cur)} ✓")


AGENTS = r"workers?|men|women|people|persons?|machines?|pumps?|pipes?|taps?|painters?|builders?|labou?rers?|robots?|printers?|cooks?|employees?|students?|girls?|boys?"
DURATIONS = r"days?|hours?|hrs?|minutes?|mins?|weeks?|months?"


def work(t: str) -> Solution | None:
    if re.search(r"\btogether\b|\bboth\b|at the same time|working together|simultaneously|combined", t):
        ds = re.findall(rf"in {P} ({DURATIONS})", t)
        if len(ds) == 2:
            a, b = num(ds[0][0]), num(ds[1][0])
            unit = ds[0][1] if ds[0][1].endswith("s") else ds[0][1] + "s"
            drain = re.search(r"empt|drain|leak", t)
            rate = 1 / a - 1 / b if drain else 1 / a + 1 / b
            if rate <= 0:
                return Solution("word_problem", "combined work", "it never fills (it drains at least as fast)", [f"net rate = 1/{fmt(a)} − 1/{fmt(b)} ≤ 0"])
            r = 1 / rate
            return Solution("word_problem", "working together", f"{nice(r)} {unit}",
                            [f"rates: 1/{fmt(a)} and 1/{fmt(b)} of the job per {unit[:-1]}",
                             f"combined: 1/{fmt(a)} {'−' if drain else '+'} 1/{fmt(b)} = {fmt(rate)}", f"time = 1 ÷ {fmt(rate)} = {nice(r)} {unit}"],
                            f"in {nice(r)} {unit}: {nice(r / a)} {'−' if drain else '+'} {nice(r / b)} = 1 job ✓")
    m = re.search(rf"{P} ({AGENTS})\b.*?\bin {P} ({DURATIONS}).*?\b{P} (?:\2|{AGENTS})\b", t) or \
        re.search(rf"{P} ({AGENTS})\b.*?\b(?:take|takes|took|need|needs) {P} ({DURATIONS}).*?\b{P} (?:\2|{AGENTS})\b", t)
    if m and re.search(r"how (?:long|many (?:days|hours|minutes|weeks))", t):
        a, d, unit, c = num(m.group(1)), num(m.group(3)), m.group(4), num(m.group(5))
        r = a * d / c
        return Solution("word_problem", f"{fmt(a)} {m.group(2)} take {fmt(d)} {unit}; {fmt(c)} {m.group(2)}?", f"{nice(r)} {unit if unit.endswith('s') else unit + 's'}",
                        ["more workers → less time (inverse proportion): workers × time stays the same",
                         f"total work = {fmt(a)} × {fmt(d)} = {fmt(a * d)} worker-{unit if unit.endswith('s') else unit + 's'}",
                         f"time = {fmt(a * d)} ÷ {fmt(c)} = {nice(r)}"],
                        f"{fmt(c)} × {nice(r)} = {fmt(a * d)} ✓")
    return None


def proportion(t: str, cur: str) -> Solution | None:
    m = re.search(rf"(?:if |when )?{P} ([a-z]+(?: [a-z]+)?) (?:cost|costs|weigh|weighs|make|makes|produce|produces|need|needs|use|uses|hold|holds|contain|contains|give|gives|fill|fills|feed|feeds|can make|can produce|are worth|is worth|sell for) {P}(?: ([a-z]+))?.*?\b{P} ([a-z]+)", t)
    if not m or not re.search(r"how (?:much|many)|what (?:will|would|do|does)|cost\?|find", t):
        return None
    a, item, b, bunit, c, item2 = num(m.group(1)), m.group(2), num(m.group(3)), m.group(4), num(m.group(5)), m.group(6)
    if plural(item.split()[-1]) != plural(item2) or a == 0:
        return None
    per = b / a
    r = per * c
    is_money = cur or "cost" in m.group(0) or "worth" in m.group(0) or "sell" in m.group(0)
    show_v = (lambda v: money(v, cur)) if is_money else (lambda v: f"{nice(v)}{' ' + bunit if bunit else ''}")
    return Solution("word_problem", f"{fmt(a)} {item} → {show_v(b)}; {fmt(c)} {item2}?", show_v(r),
                    ["unitary method: find the value for one, then scale",
                     f"1 {plural(item2)} → {show_v(b)} ÷ {fmt(a)} = {show_v(per)}", f"{fmt(c)} {item2} → {show_v(per)} × {fmt(c)} = {show_v(r)}"],
                    f"ratio check: {fmt(c)}/{fmt(a)} = {nice(c / a)} and {nice(r)}/{nice(b)} = {nice(r / b)} ✓")


def averages(t: str) -> Solution | None:
    m = re.search(rf"average (?:of|on|for) (?:the |her |his |their |my )?(?:first )?{P} (?:\w+ ){{0,2}}(?:is|was|=) {P}", t)
    if not m:
        return None
    n, avg = num(m.group(1)), num(m.group(2))
    want = re.search(rf"(?:to (?:get|have|make|raise|bring|reach)|for) (?:an? |the |her |his |their |my )?(?:overall |new )?average (?:of |to )?{P}", t)
    if want:
        target = num(want.group(1))
        need = (n + 1) * target - n * avg
        return Solution("word_problem", f"average {fmt(avg)} over {fmt(n)}; want {fmt(target)} over {fmt(n + 1)}", nice(need),
                        [f"current total = {fmt(n)} × {fmt(avg)} = {fmt(n * avg)}", f"needed total = {fmt(n + 1)} × {fmt(target)} = {fmt((n + 1) * target)}",
                         f"next value = {fmt((n + 1) * target)} − {fmt(n * avg)} = {nice(need)}"],
                        f"({fmt(n * avg)} + {nice(need)}) ÷ {fmt(n + 1)} = {nice((n * avg + need) / (n + 1))} ✓")
    tail = re.sub(r"\b\d+ of (?:them|these|the numbers|the values)\b", "", t[m.end():])
    known = [num(x) for x in re.findall(r"-?\d+(?:\.\d+)?", tail)]
    if len(known) == n - 1:
        missing = n * avg - sum(known)
        return Solution("word_problem", f"average of {fmt(n)} values is {fmt(avg)}", nice(missing),
                        [f"total = {fmt(n)} × {fmt(avg)} = {fmt(n * avg)}", f"known values add to {' + '.join(map(fmt, known))} = {fmt(sum(known))}",
                         f"missing = {fmt(n * avg)} − {fmt(sum(known))} = {nice(missing)}"],
                        f"({' + '.join(map(fmt, known))} + {nice(missing)}) ÷ {fmt(n)} = {fmt(avg)} ✓")
    return None


def ratios(t: str, cur: str) -> Solution | None:
    m = re.search(rf"(?:divide|split|share|distribute|shared|divided|split up) {P} (?:\w+ ){{0,4}}?(?:in|into|in the|by) (?:the |a )?ratio (?:of )?(\d+(?:\s*:\s*\d+)+)", t) \
        or re.search(rf"{P} (?:\w+ ){{0,4}}?(?:is |are )?(?:divided|split|shared|distributed) (?:\w+ ){{0,3}}?in (?:the |a )?ratio (?:of )?(\d+(?:\s*:\s*\d+)+)", t)
    if m:
        total, parts = num(m.group(1)), [num(x) for x in re.split(r"\s*:\s*", m.group(2))]
        whole = sum(parts)
        shares = [total * p / whole for p in parts]
        fmt_v = (lambda v: money(v, cur)) if cur else nice
        return Solution("word_problem", f"divide {fmt_v(total)} in the ratio {':'.join(map(fmt, parts))}", " and ".join(fmt_v(s) for s in shares),
                        [f"total parts = {' + '.join(map(fmt, parts))} = {fmt(whole)}", f"one part = {fmt_v(total)} ÷ {fmt(whole)} = {fmt_v(total / whole)}"]
                        + [f"{fmt(p)} parts = {fmt_v(s)}" for p, s in zip(parts, shares)],
                        f"{' + '.join(fmt_v(s) for s in shares)} = {fmt_v(total)} ✓")
    m = re.search(rf"ratio of ([a-z]+) to ([a-z]+) is {P} ?: ?{P}", t)
    if m:
        a_n, b_n, a, b = m.group(1), m.group(2), num(m.group(3)), num(m.group(4))
        tot = re.search(rf"{P} (?:\w+ )?(?:in total|total|altogether|in all)|(?:total of|there are|has|have) {P} (?!{a_n}|{b_n})(?:\w+)", t)
        ask_a = re.search(rf"how many {a_n}", t)
        ask_b = re.search(rf"how many {b_n}", t)
        known_a = re.search(rf"{P} {a_n}", t[m.end():])
        known_b = re.search(rf"{P} {b_n}", t[m.end():])
        if known_a and ask_b:
            k = num(known_a.group(1))
            r = k * b / a
            return Solution("word_problem", f"{a_n}:{b_n} = {fmt(a)}:{fmt(b)}, {fmt(k)} {a_n}", f"{nice(r)} {b_n}",
                            [f"{b_n} = {a_n} × {fmt(b)}/{fmt(a)} = {fmt(k)} × {nice(b / a)} = {nice(r)}"])
        if known_b and ask_a:
            k = num(known_b.group(1))
            r = k * a / b
            return Solution("word_problem", f"{a_n}:{b_n} = {fmt(a)}:{fmt(b)}, {fmt(k)} {b_n}", f"{nice(r)} {a_n}",
                            [f"{a_n} = {b_n} × {fmt(a)}/{fmt(b)} = {fmt(k)} × {nice(a / b)} = {nice(r)}"])
        if tot and (ask_a or ask_b):
            T = num(tot.group(1) or tot.group(2))
            name, part = (a_n, a) if ask_a else (b_n, b)
            r = T * part / (a + b)
            return Solution("word_problem", f"{a_n}:{b_n} = {fmt(a)}:{fmt(b)} out of {fmt(T)}", f"{nice(r)} {name}",
                            [f"total parts = {fmt(a)} + {fmt(b)} = {fmt(a + b)}", f"{name} = {fmt(part)}/{fmt(a + b)} × {fmt(T)} = {nice(r)}"],
                            f"the other group: {nice(T - r)}; {nice(r)}:{nice(T - r)} = {fmt(a)}:{fmt(b)} ✓")
    return None


# ---------------------------------------------------------------- entry point

GATE = re.compile(r"\d|\bnumbers?\b|consecutive|prime|fibonacci|digits?\b|ratio|average|ways|choose|arrange|probab|chance|heads|"
                  r"\blegs\b|\bold\b|older|younger|convert|how many|how much|how long|how far|twice|thrice|triple|half|double|"
                  r"square|cube|binary|hex|octal|roman|sequence|series|next|term|interest|percent|discount|profit|speed|"
                  r"\bsum\b|\bproduct\b|handshake|together|letters|\bf\(", re.I)


def solve(text: str) -> Solution | None:
    if len(text) > 600 or not GATE.search(text):
        return None
    t, cur = prepare(text)
    readers = [
        lambda: constant_digits(t), lambda: digits_of_number(t), lambda: series(t), lambda: sequences(t), lambda: number_facts(t), lambda: counting(t), lambda: probability(t),
        lambda: units(t), lambda: consecutive(t), lambda: two_numbers(t), lambda: heads_legs(t), lambda: ages(t),
        lambda: averages(t), lambda: ratios(t, cur), lambda: interest(t, cur), lambda: work(t), lambda: motion(t),
        lambda: shopping(t, cur), lambda: proportion(t, cur), lambda: algebra(t), lambda: a_number(t, text),
    ]
    for read in readers:
        sol = read()
        if sol:
            if sol.kind == "word_problem":
                sol.confidence = 0.95
            return sol
    return None

