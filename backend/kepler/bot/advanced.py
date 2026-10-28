"""Kepler's advanced reasoning: proofs, research-level computation, a conjecture lab, and the open problems.

Honest by design. Kepler proves what can be proved mechanically, computes exactly, finds counterexamples, and
tests famous conjectures on huge ranges. It never claims to have solved an open problem: verifying a conjecture for
many cases is labelled evidence, not proof.

  proofs        prove 1 + 2 + … + n = n(n + 1)/2 (induction) · prove (a + b)^2 = a^2 + 2ab + b^2 (identity)
                prove x^2 + 1 >= 2x (inequality: squares) · prove there are infinitely many primes (classic proofs)
                false claims get a counterexample
  linear alg.   determinant / inverse / eigenvalues / rank / transpose / trace / rref of [[1, 2], [3, 4]], products
  ODEs          solve y'' + y = 0 · solve y' = 2y · solve dy/dx = x*y (each solution checked by substitution)
  number theory 7^222 mod 13 · is 2^127 - 1 prime · factor 2^64 + 1 · totient of 360 · solve 3x + 5y = 7 in integers
                x ≡ 2 mod 3 and x ≡ 3 mod 5 (Chinese remainder theorem)
  series        does the sum of 1/n^2 converge (with the test that decides it, and the value when known)
  lab           check goldbach up to 100000 · check collatz up to 1000000 · twin primes below 100000
                verify the riemann hypothesis up to height 100 / for the first 50 zeros
  open problems what is the riemann hypothesis · solve p vs np · millennium prize problems
"""
import math
import random
import re
import time

import sympy as sp

from .reasoning import MathError, Solution, _timed, fmt, show, to_expr, _words_to_symbols

LAB_LIMIT = 2_000_000


def _expr(s: str):
    return to_expr(_words_to_symbols(s.strip()))


# ================================================================ proofs

def _sum_spec(lhs: str):
    """'1 + 2 + ... + n' / '1 + 3 + 5 + ... + (2n - 1)' / 'sum of k^2 for k from 1 to n' → (term f(k), k, start, upper n)."""
    k = sp.Symbol("k")
    m = re.fullmatch(r"(?:the )?sum of (.+?) for ([a-z]) (?:from|=) ?(\d+) to ([a-z])", lhs)
    if m:
        var = sp.Symbol(m.group(2))
        return _expr(m.group(1)).subs(var, k), k, int(m.group(3)), sp.Symbol(m.group(4))
    m = re.fullmatch(r"(.+?)\s*\+\s*(?:\.\.\.|…|\. \. \.)\s*\+\s*(.+)", lhs)
    if not m:
        return None
    first_terms = [t.strip() for t in m.group(1).split("+") if t.strip()]
    last = _expr(m.group(2))
    syms = sorted(last.free_symbols, key=lambda s: s.name)
    if len(syms) != 1:
        return None
    upper = syms[0]
    f = last.subs(upper, k)
    # the listed first terms must match f(1), f(2), … (so we know the sum starts at k = 1)
    try:
        vals = [sp.sympify(_expr(t)) for t in first_terms]
    except MathError:
        return None
    if [f.subs(k, i + 1) for i in range(len(vals))] != vals:
        raise MathError(f"the first terms {', '.join(map(fmt, vals))} don't follow the pattern {fmt(f)} for k = 1, 2, …")
    return f, k, 1, upper


def prove_sum(statement: str) -> Solution | None:
    m = re.fullmatch(r"(?:prove|show|verify)(?: that)?(?: by induction)?(?: that)? (.+?) = (.+?)(?: for all (?:positive integers |natural numbers |integers )?[a-z](?: ?>= ?1)?)?(?: by induction)?", statement)
    if not m or not re.search(r"\+\s*(?:\.\.\.|…)|\bsum of\b", m.group(1)):
        return None
    spec = _sum_spec(m.group(1).strip())
    if not spec:
        return None
    f, k, start, n = spec
    rhs = _expr(m.group(2)).subs(sp.Symbol("n"), n)
    mm = sp.Symbol("m")
    ft = f"({fmt(f)})" if f.is_Add else fmt(f)
    steps = [f"Claim P({n}): Σ_{{k={start}}}^{{{n}}} {ft} = {fmt(rhs)} for every integer {n} ≥ {start}."]
    base_l, base_r = f.subs(k, start), rhs.subs(n, start)
    steps.append(f"Base case {n} = {start}: left side = {fmt(base_l)}, right side = {fmt(base_r)} {'✓' if sp.simplify(base_l - base_r) == 0 else '✗'}")
    if sp.simplify(base_l - base_r) != 0:
        return Solution("proof", m.group(0), f"false: it already fails at {n} = {start} ({fmt(base_l)} ≠ {fmt(base_r)})", steps,
                        confidence=0.97)
    steps.append(f"Inductive hypothesis: assume P(m) holds, i.e. Σ_{{k={start}}}^{{m}} {ft} = {fmt(rhs.subs(n, mm))}.")
    step_lhs = rhs.subs(n, mm) + f.subs(k, mm + 1)
    target = rhs.subs(n, mm + 1)
    steps.append(f"Inductive step: Σ_{{k={start}}}^{{m+1}} = (Σ up to m) + term(m + 1) = {fmt(rhs.subs(n, mm))} + {fmt(f.subs(k, mm + 1))}")
    steps.append(f"  = {fmt(sp.factor(step_lhs))}")
    steps.append(f"Right side of P(m + 1): {fmt(target)} = {fmt(sp.factor(target))}")
    ok = sp.simplify(step_lhs - target) == 0
    if not ok:
        bad = next((i for i in range(start, start + 60) if sp.summation(f, (k, start, i)) != rhs.subs(n, i)), None)
        return Solution("proof", m.group(0), f"false" + (f": counterexample {n} = {bad} (left {fmt(sp.summation(f, (k, start, bad)))}, "
                                                         f"right {fmt(rhs.subs(n, bad))})" if bad is not None else ": the inductive step fails"),
                        steps + ["the two sides differ, so the step P(m) ⇒ P(m + 1) does not hold"], confidence=0.97)
    steps.append("The two agree, so P(m) ⇒ P(m + 1).")
    steps.append(f"By induction P({n}) holds for all {n} ≥ {start}. ∎")
    check = sp.simplify(sp.summation(f, (k, start, n)) - rhs) == 0
    L = sp.latex
    tex_claim = f"\\sum_{{k={start}}}^{{{L(n)}}} {L(f)} = {L(rhs)} \\quad \\text{{for every integer }} {L(n)} \\ge {start}."
    tex_steps = [
        f"\\textbf{{Base case}} (${L(n)} = {start}$): the left side is ${L(base_l)}$ and the right side is ${L(base_r)}$, so the claim holds.",
        f"\\textbf{{Inductive hypothesis.}} Assume that for some $m \\ge {start}$, $\\displaystyle\\sum_{{k={start}}}^{{m}} {L(f)} = {L(rhs.subs(n, mm))}$.",
        "\\textbf{Inductive step.} Then\\begin{align*}"
        f"\\sum_{{k={start}}}^{{m+1}} {L(f)} &= \\sum_{{k={start}}}^{{m}} {L(f)} + {L(f.subs(k, mm + 1))} \\\\"
        f" &= {L(rhs.subs(n, mm))} + {L(f.subs(k, mm + 1))} \\\\ &= {L(sp.factor(step_lhs))} = {L(target)},"
        "\\end{align*}which is the claim for $m + 1$.",
        f"\\textbf{{Conclusion.}} By the principle of mathematical induction, the identity holds for every integer ${L(n)} \\ge {start}$.",
    ]
    return Solution("proof", m.group(0), f"proved by induction: Σ {ft} = {fmt(sp.factor(rhs))}", steps, tex_statement=tex_claim,
                    tex_steps=tex_steps, tex_answer=f"\\sum_{{k={start}}}^{{{L(n)}}} {L(f)} = {L(sp.factor(rhs))}",
                    check=f"independent check: sympy's closed-form sum agrees {'✓' if check else '✗'}; spot check n = 1…10 "
                    f"{'✓' if all(sp.summation(f, (k, start, i)) == rhs.subs(n, i) for i in range(start, start + 10)) else '✗'}",
                    confidence=0.99)


def prove_identity(statement: str) -> Solution | None:
    m = re.fullmatch(r"(?:prove|show|verify|is it true|check|is it always true)(?: that)? (.+?) = (.+?)(?: for all [a-z, ]+)?\??", statement)
    if not m or "..." in statement or "…" in statement:
        return None
    lhs, rhs = _expr(m.group(1)), _expr(m.group(2))
    d = sp.simplify(sp.expand(lhs - rhs))
    if d != 0:
        d = sp.simplify(sp.trigsimp(sp.expand_trig(lhs - rhs)))
    steps = [f"Claim: {fmt(lhs)} = {fmt(rhs)}"]
    if lhs.free_symbols | rhs.free_symbols:
        steps.append(f"expand the left side: {fmt(sp.expand(lhs))}")
        steps.append(f"expand the right side: {fmt(sp.expand(rhs))}")
    if d == 0:
        steps.append("left − right simplifies to 0 for every value of the variables")
        return Solution("proof", m.group(0), "true: it's an identity", steps + ["∎"],
                        "random numeric spot checks agree ✓" if _spot(lhs, rhs) else "", confidence=0.99,
                        tex_statement=f"{sp.latex(lhs)} = {sp.latex(rhs)}",
                        tex_steps=[f"Expanding the left-hand side gives ${sp.latex(sp.expand(lhs))}$.",
                                   f"Expanding the right-hand side gives ${sp.latex(sp.expand(rhs))}$.",
                                   f"Hence ${sp.latex(lhs)} - \\left({sp.latex(rhs)}\\right)$ simplifies to $0$ for all values of the variables."],
                        tex_answer=f"{sp.latex(lhs)} = {sp.latex(rhs)}")
    syms = sorted(d.free_symbols, key=lambda s: s.name)
    if not syms:
        return Solution("proof", m.group(0), f"false: the two sides differ by {show(d)}", steps, confidence=0.98)
    rng = random.Random(1)
    for _ in range(200):
        vals = {s: sp.Rational(rng.randint(-9, 9), rng.choice([1, 1, 2, 3])) for s in syms}
        try:
            lv, rv = lhs.subs(vals), rhs.subs(vals)
        except (ZeroDivisionError, TypeError):
            continue
        if lv.is_finite and rv.is_finite and sp.simplify(lv - rv) != 0:
            where = ", ".join(f"{s} = {fmt(v)}" for s, v in vals.items())
            return Solution("proof", m.group(0), f"false: counterexample {where}", steps +
                            [f"at {where}: left = {show(lv)}, right = {show(rv)}"], confidence=0.98)
    return Solution("proof", m.group(0), "not proved: no counterexample found, but the difference didn't simplify to 0",
                    steps + [f"left − right = {fmt(d)}"], ok=True, confidence=0.5)


def _spot(lhs, rhs) -> bool:
    syms = sorted((lhs - rhs).free_symbols, key=lambda s: s.name)
    rng = random.Random(7)
    for _ in range(8):
        vals = {s: rng.uniform(-3, 3) for s in syms}
        try:
            if abs(complex(sp.N((lhs - rhs).subs(vals)))) > 1e-9:
                return False
        except (TypeError, ValueError, ZeroDivisionError):
            continue
    return True


def prove_inequality(statement: str) -> Solution | None:
    m = re.fullmatch(r"(?:prove|show|verify|is it true)(?: that)? (.+?) (>=|≥|<=|≤|>|<) (.+?)(?: (?:for all|for every|for|whenever|when|if|where) (.+))?\??", statement)
    if not m:
        return None
    a, op, b, cond = _expr(m.group(1)), m.group(2), _expr(m.group(3)), (m.group(4) or "")
    flip = op in ("<=", "≤", "<")
    strict = op in (">", "<")
    d = sp.together(b - a if flip else a - b)
    positive = bool(re.search(r"positive|> ?0|>= ?0|real", cond)) or "positive" in statement
    syms = sorted(d.free_symbols, key=lambda s: s.name)
    if positive:
        reps = {s: sp.Symbol(s.name, positive=True) for s in syms}
        d = d.subs(reps)
        syms = list(reps.values())
    sym = ">" if strict else "≥"
    steps = [f"Claim: {fmt(a)} {op} {fmt(b)}" + (f" ({cond})" if cond else ""),
             f"equivalently D = {fmt(sp.factor(d))} {sym} 0"]
    num, den = sp.fraction(sp.factor(d))
    proof = None
    const, factors = sp.factor_list(num) if num.is_polynomial() else (None, [])
    if const is not None and const > 0 and factors and all(e % 2 == 0 for _, e in factors):
        root = sp.Mul(*[f**(e // 2) for f, e in factors]) * sp.sqrt(const)
        proof = f"the numerator is a perfect square: {fmt(num)} = ({fmt(root)})² ≥ 0"
    elif len(syms) == 1 and num.is_polynomial(syms[0]) and sp.degree(num, syms[0]) == 2:
        x = syms[0]
        A, B, C = sp.Poly(num, x).all_coeffs()
        h, kk = -B / (2 * A), C - B**2 / (4 * A)
        if A > 0 and kk >= 0:
            proof = f"complete the square: {fmt(num)} = {fmt(A)}·({fmt(x - h)})² + {fmt(kk)} ≥ {fmt(kk)} ≥ 0"
    elif num.is_Add and all(t.is_Pow and t.exp % 2 == 0 or (t.is_Mul and all(f.is_Pow and f.exp % 2 == 0 or f.is_positive for f in t.args)) for t in num.args):
        proof = f"the numerator {fmt(num)} is a sum of even powers, each ≥ 0"
    if proof:
        den_ok = den == 1 or den.is_positive or (den.is_Pow and den.exp % 2 == 0)
        if den_ok:
            steps.append(proof)
            if den != 1:
                steps.append(f"the denominator {fmt(den)} is positive" + (" (given)" if positive else ""))
            eq_case = sp.solve(num, syms[0]) if len(syms) == 1 else []
            if strict:
                if eq_case:
                    return Solution("proof", m.group(0), f"false as a strict inequality: equality holds at {syms[0]} = {fmt(eq_case[0])}",
                                    steps, confidence=0.95)
            steps.append(f"so D {sym} 0, which is the claim" + (f"; equality exactly when {syms[0]} = {', '.join(fmt(e) for e in eq_case)}" if eq_case and not strict else "") + ". ∎")
            rel = {"<=": "\\le", "≤": "\\le", ">=": "\\ge", "≥": "\\ge", "<": "<", ">": ">"}[op]
            ge = ">" if strict else "\\ge"
            tex = [f"It suffices to show $D = {sp.latex(sp.factor(d))} {ge} 0$.",
                   f"The numerator is a perfect square or a sum of squares: ${sp.latex(num)} \\ge 0$."]
            if den != 1:
                tex.append(f"The denominator ${sp.latex(den)}$ is positive" + (" by hypothesis." if positive else "."))
            if eq_case and not strict:
                tex.append(f"Equality holds exactly when ${sp.latex(syms[0])} = {sp.latex(eq_case[0])}$.")
            return Solution("proof", m.group(0), "true: proved", steps, confidence=0.97,
                            tex_statement=f"{sp.latex(a)} {rel} {sp.latex(b)}" + (f" \\quad \\text{{({cond})}}" if cond else ""),
                            tex_steps=tex, tex_answer=f"{sp.latex(a)} {rel} {sp.latex(b)}")
    # no proof found: hunt for a counterexample
    rng = random.Random(3)
    for _ in range(4000):
        vals = {s: (rng.uniform(0.001, 50) if positive else rng.uniform(-50, 50)) for s in syms}
        try:
            v = float(sp.N(d.subs(vals)))
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if v < -1e-9 or (strict and abs(v) < 1e-12):
            where = ", ".join(f"{s} = {val:.4g}" for s, val in vals.items())
            return Solution("proof", m.group(0), f"false: counterexample {where}", steps + [f"at {where}, D = {v:.4g} < 0"],
                            confidence=0.95)
    return Solution("proof", m.group(0), "not proved, but no counterexample in 4,000 random samples (evidence, not proof)",
                    steps + ["I couldn't write D as a square or sum of squares", "random search found D ≥ 0 every time"],
                    confidence=0.5)


CLASSIC = [
    (r"infinitely many primes|primes are infinite|no largest prime|infinite number of primes", "Euclid's theorem: there are infinitely many primes", [
        "Suppose there were only finitely many primes p₁, p₂, …, pₖ.",
        "Let N = p₁·p₂·…·pₖ + 1.",
        "N > 1, so N has a prime factor q.",
        "Dividing N by any pᵢ leaves remainder 1, so q is none of the pᵢ.",
        "That contradicts the list containing every prime. ∎"]),
    (r"(?:square root of|sqrt ?\(?|√ ?)2\)? is irrational|irrationality of (?:the square root of |√)2", "√2 is irrational", [
        "Suppose √2 = a/b with integers a, b in lowest terms (no common factor).",
        "Then a² = 2b², so a² is even, so a is even: a = 2c.",
        "Then 4c² = 2b², so b² = 2c²: b is even too.",
        "Both even contradicts lowest terms. So √2 is not a fraction. ∎"]),
    (r"(?:real numbers|the reals) are uncountable|uncountab|cantor'?s? diagonal", "The real numbers are uncountable (Cantor's diagonal argument)", [
        "Suppose the reals in (0, 1) could be listed r₁, r₂, r₃, … with decimal expansions.",
        "Build x whose n-th decimal differs from the n-th decimal of rₙ (and avoid 0 and 9 to dodge 0.0999… = 0.1).",
        "x differs from every rₙ in at least one place, so x is not on the list.",
        "No list contains every real: they are uncountable. ∎"]),
    (r"0\.9+(?:\.\.\.|…| recurring| repeating)? ?(?:=|equals|is equal to) ?1", "0.999… = 1", [
        "Let x = 0.999…",
        "Then 10x = 9.999…",
        "Subtract: 10x − x = 9.999… − 0.999… = 9, so 9x = 9 and x = 1.",
        "(Also: 1/3 = 0.333…, so 3 × 1/3 = 0.999… = 1.) ∎"]),
    (r"halting problem|halting is undecidable", "The halting problem is undecidable (Turing, 1936)", [
        "Suppose a program H(P, x) always correctly answers whether program P halts on input x.",
        "Build D(P): if H(P, P) says 'halts', loop forever; otherwise stop.",
        "Run D on itself: D(D) halts ⇔ H(D, D) says it doesn't halt ⇔ D(D) doesn't halt.",
        "Contradiction, so no such H can exist. ∎"]),
    (r"pythagor", "Pythagorean theorem: a² + b² = c² for a right triangle", [
        "Place four copies of the right triangle (legs a, b, hypotenuse c) inside a square of side a + b,",
        "arranged so they leave a tilted square of side c in the middle.",
        "Area of the big square two ways: (a + b)² = 4·(ab/2) + c².",
        "Expand: a² + 2ab + b² = 2ab + c², so a² + b² = c². ∎"]),
    (r"pigeonhole", "The pigeonhole principle", [
        "Put n + 1 objects into n boxes.",
        "If every box held at most one object, there would be at most n objects.",
        "That's fewer than n + 1, so some box holds at least two. ∎"]),
    (r"sum of (?:the )?angles (?:in|of) a triangle|angles of a triangle (?:add|sum)", "The angles of a triangle sum to 180° (Euclidean geometry)", [
        "Draw the line through one vertex parallel to the opposite side.",
        "The two angles it makes with the triangle's sides equal the other two angles (alternate angles).",
        "Together with the vertex angle they form a straight line: 180°. ∎"]),
    (r"(?:square root of|sqrt|√) ?(\d+) is irrational", None, None),  # √p, p not a perfect square: generated
]


def classic_proof(statement: str) -> Solution | None:
    if not re.match(r"(?:prove|show|why is|explain why|proof (?:of|that)|is it true that)\b", statement):
        return None
    for pat, title, steps in CLASSIC:
        m = re.search(pat, statement)
        if not m:
            continue
        if title is None:
            p = int(m.group(1))
            r = math.isqrt(p)
            if r * r == p:
                return Solution("proof", statement, f"false: √{p} = {r} is a whole number", [f"{r} × {r} = {p}"], confidence=0.99)
            q = min(sp.factorint(p))
            title = f"√{p} is irrational"
            steps = [f"Suppose √{p} = a/b in lowest terms. Then a² = {p}·b².",
                     f"The prime {q} divides {p} an odd number of times ({p} = {' × '.join(f'{x}^{e}' if e > 1 else str(x) for x, e in sp.factorint(p).items())}).",
                     f"In a², every prime appears an even number of times; in {p}·b², the prime {q} appears an odd number of times.",
                     "By unique factorisation they can't be equal: contradiction. ∎"]
        return Solution("proof", statement, f"proved: {title}", steps, "classic proof from Kepler's proof library", confidence=0.99)
    return None


# ================================================================ linear algebra

MATRIX = r"\[\s*\[[-\d\s.,/\[\]]+\]\s*\]"


def _matrix(s: str):
    rows = re.findall(r"\[([^\[\]]+)\]", s)
    data = [[sp.Rational(x) for x in re.split(r"[,\s]+", r.strip()) if x] for r in rows]
    if not data or any(len(r) != len(data[0]) for r in data):
        raise MathError("every row of the matrix needs the same number of entries")
    if len(data) > 12 or len(data[0]) > 12:
        raise MathError("matrices up to 12 × 12")
    return sp.Matrix(data)


def _mfmt(M) -> str:
    return "[" + "; ".join("  ".join(fmt(v) for v in M.row(i)) for i in range(M.rows)) + "]"


def linear_algebra(t: str) -> Solution | None:
    ms = re.findall(MATRIX, t)
    if not ms:
        return None
    if len(ms) == 2 and re.search(r"\b(?:times|multiply|product|\*|×)\b|\*", t):
        A, B = _matrix(ms[0]), _matrix(ms[1])
        if A.cols != B.rows:
            raise MathError(f"can't multiply a {A.rows}×{A.cols} by a {B.rows}×{B.cols} matrix (inner sizes must match)")
        C = A * B
        return Solution("matrix", "A × B", _mfmt(C), [f"A = {_mfmt(A)}", f"B = {_mfmt(B)}",
                        "entry (i, j) = row i of A · column j of B", f"A × B = {_mfmt(C)}"])
    A = _matrix(ms[0])
    op = re.search(r"determinant|\bdet\b|inverse|eigenvalues?|eigenvectors?|rank|transpose|trace|rref|row echelon|null ?space|characteristic polynomial", t)
    op = op.group(0) if op else "determinant"
    steps = [f"A = {_mfmt(A)}  ({A.rows}×{A.cols})"]
    square = A.rows == A.cols
    if op in ("determinant", "det"):
        if not square:
            raise MathError("only square matrices have a determinant")
        d = _timed(A.det)
        if A.rows == 2:
            a, b, c, e = A[0, 0], A[0, 1], A[1, 0], A[1, 1]
            steps.append(f"det = ad − bc = {fmt(a)}·{fmt(e)} − {fmt(b)}·{fmt(c)} = {fmt(d)}")
        else:
            steps.append("expand along the first row (cofactor expansion) / row-reduce")
        return Solution("matrix", "det(A)", fmt(d), steps, "nonzero, so A is invertible" if d != 0 else "zero, so A is singular (no inverse)",
                        tex_statement=f"\\det {sp.latex(A)}", tex_answer=f"\\det {sp.latex(A)} = {sp.latex(d)}")
    if op == "inverse":
        if not square:
            raise MathError("only square matrices can have an inverse")
        d = A.det()
        if d == 0:
            return Solution("matrix", "A⁻¹", "A has no inverse (determinant 0)", steps + ["det(A) = 0"])
        inv = _timed(A.inv)
        ok = (A * inv) == sp.eye(A.rows)
        return Solution("matrix", "A⁻¹", _mfmt(inv), steps + [f"det(A) = {fmt(d)} ≠ 0", "Gauss–Jordan: [A | I] → [I | A⁻¹]"],
                        f"A × A⁻¹ = I {'✓' if ok else '✗'}", tex_statement=f"A = {sp.latex(A)}",
                        tex_answer=f"A^{{-1}} = {sp.latex(inv)}")
    if op.startswith("eigenvalue") or op == "characteristic polynomial":
        if not square:
            raise MathError("eigenvalues need a square matrix")
        lam = sp.Symbol("λ")
        cp = _timed(lambda: sp.factor((A - lam * sp.eye(A.rows)).det()))
        if op == "characteristic polynomial":
            return Solution("matrix", "det(A − λI)", fmt(cp), steps)
        ev = _timed(A.eigenvals)
        ans = ", ".join(f"{show(v)}" + (f" (×{k})" if k > 1 else "") for v, k in ev.items())
        return Solution("matrix", "eigenvalues of A", ans, steps + [f"characteristic polynomial det(A − λI) = {fmt(cp)}", "set it to 0 and solve for λ"],
                        f"sum = trace = {fmt(A.trace())}, product = det = {fmt(A.det())} ✓"
                        if sp.simplify(sum(v * k for v, k in ev.items()) - A.trace()) == 0 else "")
    if op.startswith("eigenvector"):
        vecs = _timed(A.eigenvects)
        lines = [f"λ = {show(v)}: " + ", ".join("(" + ", ".join(fmt(c) for c in vec) + ")" for vec in vs) for v, _, vs in vecs]
        return Solution("matrix", "eigenvectors of A", "; ".join(lines), steps + ["for each eigenvalue λ, solve (A − λI)v = 0"])
    if op == "rank":
        return Solution("matrix", "rank(A)", str(A.rank()), steps + ["row-reduce and count the nonzero rows"])
    if op == "transpose":
        return Solution("matrix", "Aᵀ", _mfmt(A.T), steps + ["swap rows and columns"])
    if op == "trace":
        return Solution("matrix", "tr(A)", fmt(A.trace()), steps + ["add the diagonal entries"])
    if op.startswith("null"):
        ns = A.nullspace()
        return Solution("matrix", "null space of A", "; ".join("(" + ", ".join(fmt(c) for c in v) + ")" for v in ns) or "{0}", steps)
    R, piv = A.rref()
    return Solution("matrix", "rref(A)", _mfmt(R), steps + [f"pivot columns: {', '.join(str(p + 1) for p in piv)}"])


# ================================================================ differential equations

def _ode_fmt(e) -> str:
    """Derivative(y(x), (x, 2)) → y'' , y(x) → y: how people write ODEs."""
    s = fmt(e)
    s = re.sub(r"Derivative\(y\(x\), \(x, (\d+)\)\)", lambda g: "y" + "'" * int(g.group(1)), s)
    s = s.replace("Derivative(y(x), x)", "y'")
    return s.replace("y(x)", "y")


def ode(t: str) -> Solution | None:
    # "solve y'' + y = 0" or just "y'' + y' = x^2": any equation with y', y'', y''' or dy/dx
    t = re.sub(r"d\s*\^?\s*([23])?\s*y\s*/\s*d\s*x\s*(?:\^\s*([23]))?", lambda g: f"d^{g.group(1)}y/dx^{g.group(1)}" if g.group(1) else "dy/dx", t)
    m = re.search(r"^(?:(?:solve|find|what is|find the general solution (?:of|to))(?: the)?(?: differential equation| ode)?:?\s*)?(.+)$", t)
    if not m or not re.search(r"y'|dy/dx|d\^?[23]y/dx\^?[23]", m.group(1)):
        return None
    s = m.group(1).strip().rstrip("?.")
    s = re.sub(r"\s*for y(?:\(x\))?$", "", s)
    s = re.sub(r"d\^?3y/dx\^?3", "u", s)
    s = re.sub(r"d\^?2y/dx\^?2", "w", s)
    s = s.replace("y'''", "u").replace("y''", "w").replace("y'", "v").replace("dy/dx", "v")
    if "'" in s:
        raise MathError("I can read derivatives up to y''' (third order)")
    if "=" not in s:
        s += " = 0"
    left, right = s.split("=", 1)
    x = sp.Symbol("x")
    y = sp.Function("y")
    subs = {sp.Symbol("u"): y(x).diff(x, 3), sp.Symbol("w"): y(x).diff(x, 2), sp.Symbol("v"): y(x).diff(x),
            sp.Symbol("y"): y(x)}
    eq = sp.Eq(_expr(left).subs(subs), _expr(right).subs(subs))
    order = 3 if "u" in s else 2 if "w" in s else 1
    sol = _timed(lambda: sp.dsolve(eq, y(x)))
    sols = sol if isinstance(sol, list) else [sol]
    ok = all(sp.checkodesol(eq, so)[0] for so in sols)
    kind = sp.classify_ode(eq, y(x))[:2]
    steps = [f"equation: {_ode_fmt(eq.lhs)} = {_ode_fmt(eq.rhs)}  (order {order})",
             f"method: {(kind[0] if kind else 'general').replace('nth_linear_constant_coeff_', 'linear, constant coefficients, ').replace('_', ' ')}"]
    if order == 2 and "nth_linear_constant_coeff_homogeneous" in sp.classify_ode(eq, y(x)):
        r = sp.Symbol("r")
        char = sp.expand((eq.lhs - eq.rhs).subs({y(x).diff(x, 2): r**2, y(x).diff(x): r, y(x): 1}))
        steps.append(f"characteristic equation: {fmt(char)} = 0 → r = {', '.join(show(v) for v in sp.solve(char, r))}")
    asked = re.sub(r"\s*([=+*-])\s*", r" \1 ", m.group(1).strip().rstrip("?.")).replace(" / ", "/")
    return Solution("ode", asked, "; ".join(f"{fmt(so.lhs)} = {fmt(so.rhs)}" for so in sols), steps,
                    f"substituting back satisfies the equation {'✓' if ok else '✗'} "
                    f"({', '.join(f'C{i}' for i in range(1, order + 1))} {'is an arbitrary constant' if order == 1 else 'are arbitrary constants'})",
                    tex_statement=f"{sp.latex(eq.lhs)} = {sp.latex(eq.rhs)}",
                    tex_answer=",\\quad ".join(f"{sp.latex(so.lhs)} = {sp.latex(so.rhs)}" for so in sols))


# ================================================================ number theory

def number_theory_plus(t: str) -> Solution | None:
    m = re.search(r"(.+?) (?:mod|modulo|%) (\d+)$", t.removeprefix("what is ").removeprefix("compute ").strip())
    if m and re.fullmatch(r"\s*\d+\s*(?:\^|\*\*)\s*\d+\s*", m.group(1)):
        a, b = [int(v) for v in re.split(r"\^|\*\*", m.group(1))]
        mod = int(m.group(2))
        if mod == 0:
            raise MathError("mod 0 is undefined")
        r = pow(a, b, mod)
        steps = [f"compute {a}^{b} mod {mod} without the huge number: square-and-multiply",
                 f"{b} in binary = {bin(b)[2:]}"]
        e, sq = 1, a % mod
        for bit in bin(b)[2:][::-1][:6]:
            steps.append(f"  {a}^{e} ≡ {sq} (mod {mod})")
            sq, e = sq * sq % mod, e * 2
        if math.gcd(a, mod) == 1 and sp.isprime(mod):
            steps.append(f"(Fermat: {a}^{mod - 1} ≡ 1, so only {b} mod {mod - 1} = {b % (mod - 1)} matters: {a}^{b % (mod - 1)} mod {mod} = {pow(a, b % (mod - 1), mod)})")
        return Solution("modular", f"{a}^{b} mod {mod}", str(r), steps, f"pow({a}, {b}, {mod}) = {r} ✓")
    m = re.search(r"is (.+?) (?:a )?prime(?: number)?\??$", t)
    if m and re.search(r"[\^*+\-!]|\d{31,}", m.group(1)):
        v = sp.sympify(to_expr(_words_to_symbols(m.group(1))))
        if not v.is_Integer:
            raise MathError("primality is about whole numbers")
        if len(str(v)) > 2000:
            raise MathError("up to 2,000 digits")
        p = _timed(sp.isprime, v)
        mers = re.fullmatch(r"\s*2\s*\^\s*(\d+)\s*-\s*1\s*", m.group(1))
        steps = [f"{m.group(1)} = {fmt(v)} ({len(str(abs(v)))} digits)",
                 "Baillie–PSW test (strong Fermat to base 2 + strong Lucas): no known counterexample; exact below 2⁶⁴"]
        if mers:
            steps.append(f"this is a Mersenne number M{mers.group(1)}; it can only be prime if {mers.group(1)} is prime "
                         f"({'it is' if sp.isprime(int(mers.group(1))) else 'it is not'})")
        if not p and len(str(v)) <= 40:
            f = _timed(sp.factorint, v)
            steps.append("factors: " + " × ".join(f"{q}^{e}" if e > 1 else str(q) for q, e in f.items()))
        return Solution("prime", f"is {m.group(1)} prime?", "yes" if p else "no", steps)
    m = re.search(r"(?:factor|factori[sz]e|prime factors of|prime factori[sz]ation of) (.+?)\??$", t)
    if m and re.search(r"[\^*+\-!]|\d{31,}", m.group(1)) and not re.search(r"[a-z]", re.sub(r"factorial", "", m.group(1))):
        v = sp.sympify(to_expr(_words_to_symbols(m.group(1))))
        if not v.is_Integer or v < 2:
            raise MathError("factor a whole number ≥ 2")
        if len(str(v)) > 60:
            raise MathError("factoring is capped at 60 digits here (it gets exponentially harder)")
        t0 = time.time()
        f = _timed(sp.factorint, v)
        return Solution("prime_factors", f"factor {m.group(1)}", " × ".join(f"{q}^{e}" if e > 1 else str(q) for q, e in f.items()),
                        [f"{m.group(1)} = {fmt(v)}", f"trial division, Pollard rho and p−1 ({time.time() - t0:.2f}s)"],
                        f"multiplying back gives {m.group(1)} ✓" if math.prod(q**e for q, e in f.items()) == v else "")
    m = re.search(r"(?:euler'?s )?(?:totient|phi) (?:function )?(?:of )?(\d+)", t)
    if m:
        n = int(m.group(1))
        f = sp.factorint(n)
        r = sp.totient(n)
        return Solution("totient", f"φ({n})", str(r), [f"{n} = " + " × ".join(f"{q}^{e}" if e > 1 else str(q) for q, e in f.items()),
                        "φ(n) = n · Π (1 − 1/p) over the primes p dividing n",
                        f"= {n} · " + " · ".join(f"(1 − 1/{q})" for q in f) + f" = {r}"],
                        "counts the numbers 1…n that share no factor with n")
    m = re.search(r"solve (.+?) in (?:the )?(?:integers|whole numbers)|integer solutions (?:of|to) (.+)", t)
    if m:
        eq = (m.group(1) or m.group(2)).strip()
        if "=" not in eq:
            eq += " = 0"
        left, right = eq.split("=", 1)
        e = _expr(left) - _expr(right)
        syms = sorted(e.free_symbols, key=lambda s: s.name)
        ints = {s: sp.Symbol(s.name, integer=True) for s in syms}
        from sympy.solvers.diophantine import diophantine
        sols = _timed(lambda: diophantine(e.subs(ints), syms=list(ints.values())))
        if not sols:
            g = math.gcd(*[int(c) for c in sp.Poly(e, *syms).coeffs()[:-1]]) if e.is_polynomial() else None
            return Solution("diophantine", eq, "no integer solutions",
                            [f"gcd of the coefficients is {g}, which doesn't divide the constant"] if g else [])
        lines = ["(" + ", ".join(fmt(v) for v in s) + ")" for s in list(sols)[:6]]
        return Solution("diophantine", eq, "; ".join(lines), [f"solve {fmt(e)} = 0 over the integers",
                        "t₀ is any integer" if any("t_0" in str(s) for s in sols) else "finitely many solutions"])
    cs = re.findall(r"(?:x|n)\s*(?:≡|=|is congruent to|congruent to)\s*(-?\d+)\s*\(?\s*(?:mod|modulo)\s*(\d+)\s*\)?", t)
    if len(cs) >= 2:
        from sympy.ntheory.modular import crt
        rs, ms = [int(a) for a, _ in cs], [int(b) for _, b in cs]
        r = crt(ms, rs)
        if r is None:
            return Solution("crt", "system of congruences", "no solution (the moduli conflict)", [])
        x0, M = r
        return Solution("crt", " and ".join(f"x ≡ {a} (mod {b})" for a, b in zip(rs, ms)), f"x ≡ {x0} (mod {M})",
                        [f"moduli {', '.join(map(str, ms))}; combined modulus {M}", "Chinese remainder theorem: combine the congruences one by one"],
                        "check: " + ", ".join(f"{x0} mod {b} = {x0 % b}" for b in ms) + " ✓")
    return None


# ================================================================ series convergence

def series_convergence(t: str) -> Solution | None:
    m = re.search(r"(?:does|is) (?:the )?(?:series |sum |infinite sum )?(?:of )?(.+?) (?:converge|convergent|diverge|divergent|finite)", t)
    if not m:
        return None
    body = re.sub(r"^(?:sum of|the sum of|series)\s+", "", m.group(1)).strip()
    body = re.sub(r"\s+(?:for|from) [a-z] ?(?:=|from)? ?\d+ to (?:infinity|∞)$", "", body)
    term = _expr(body)
    syms = sorted(term.free_symbols, key=lambda s: s.name)
    if len(syms) != 1:
        return None
    n = syms[0]
    nn = sp.Symbol(n.name, integer=True, positive=True)
    term = term.subs(n, nn)
    conv = _timed(lambda: sp.Sum(term, (nn, 1, sp.oo)).is_convergent())
    steps = [f"series Σ_{{{nn}=1}}^∞ {fmt(term)}"]
    lim = _timed(lambda: sp.limit(term, nn, sp.oo))
    if lim != 0:
        steps.append(f"term test: the terms tend to {fmt(lim)} ≠ 0, so it diverges")
    else:
        p = None
        base, ex = (term.as_base_exp() if term.is_Pow else (None, None))
        if term.is_Pow and base == nn and ex.is_number:
            p = -ex
        elif term.is_Mul and len(term.args) == 2 and term.args[0].is_number and term.args[1].is_Pow and term.args[1].base == nn:
            p = -term.args[1].exp
        if p is not None:
            steps.append(f"p-series 1/n^p with p = {fmt(p)}: converges exactly when p > 1")
        elif term.is_Pow and base.is_number:
            steps.append(f"geometric series with ratio {fmt(base)}: converges exactly when |r| < 1")
        else:
            steps.append("terms → 0, which is necessary but not enough; sympy's tests (ratio, root, integral, comparison) decide it")
    ans = "converges" if conv else "diverges"
    if conv:
        v = _timed(lambda: sp.summation(term, (nn, 1, sp.oo)))
        if not v.has(sp.Sum):
            steps.append(f"its value is {show(v)}")
            ans += f" (to {show(v)})"
    return Solution("series", f"Σ {fmt(term)}", ans, steps)


# ================================================================ conjecture lab

def _sieve(n: int) -> bytearray:
    s = bytearray([1]) * (n + 1)
    s[0:2] = b"\x00\x00"
    for i in range(2, math.isqrt(n) + 1):
        if s[i]:
            s[i * i::i] = bytearray(len(s[i * i::i]))
    return s


def zero_count(T: float) -> int:
    """N(T): non-trivial zeros of ζ with 0 < Im(s) < T anywhere in the critical strip (Riemann–von Mangoldt:
    N(T) = θ(T)/π + 1 + S(T), with S(T) from Backlund's method). An integer unless T sits on a zero."""
    import mpmath
    for nudge in (0.0, 1e-3, -1e-3, 3e-3):
        v = mpmath.siegeltheta(T + nudge) / mpmath.pi + 1 + mpmath.backlunds(T + nudge)
        if abs(v - round(v)) < 1e-6:
            return int(round(v))
    return int(round(float(v)))


EVIDENCE = "This is evidence, not a proof: checking many cases can never cover all infinitely many."


def lab(t: str) -> Solution | None:
    m = re.search(r"(?:check|test|verify|try|explore)(?: the)? goldbach(?:'?s)?(?: conjecture)? (?:up to|below|for numbers up to|to|until) (\d+)", t)
    if m:
        N = int(m.group(1))
        if N > LAB_LIMIT:
            raise MathError(f"the lab checks up to {LAB_LIMIT:,} here")
        s = _sieve(N)
        primes = [p for p in range(2, N + 1) if s[p]]
        worst, worst_n, t0 = 0, 4, time.time()
        for even in range(4, N + 1, 2):
            for p in primes:
                if s[even - p]:
                    if p > worst:
                        worst, worst_n = p, even
                    break
            else:
                return Solution("lab", f"Goldbach up to {N:,}", f"counterexample: {even} is not a sum of two primes!",
                                ["(this would disprove Goldbach's conjecture: please double-check!)"], confidence=0.6)
        last = N - N % 2
        p = next(q for q in primes if s[last - q])
        return Solution("lab", f"Goldbach's conjecture for every even number 4 … {last:,}", f"holds for all {last // 2 - 1:,} even numbers checked",
                        ["Goldbach (1742): every even number > 2 is the sum of two primes. Still unproved.",
                         f"sieved {len(primes):,} primes, then for each even n found the smallest prime p with n − p prime",
                         f"e.g. {last:,} = {p} + {last - p:,}",
                         f"hardest case in this range: {worst_n:,} needs p = {worst} ({time.time() - t0:.2f}s)",
                         "(it has been checked by computers up to 4 × 10¹⁸)"], EVIDENCE, confidence=0.99)
    m = re.search(r"(?:check|test|verify|try|explore)(?: the)? (?:collatz|3n ?\+ ?1)(?: conjecture| problem)? (?:up to|below|for numbers up to|to|until) (\d+)", t)
    if m:
        N = int(m.group(1))
        if N > LAB_LIMIT:
            raise MathError(f"the lab checks up to {LAB_LIMIT:,} here")
        cache = {1: 0}
        best, best_n, peak, t0 = 0, 1, 1, time.time()
        for start in range(1, N + 1):
            x, path = start, []
            while x not in cache:
                path.append(x)
                x = x // 2 if x % 2 == 0 else 3 * x + 1
                peak = max(peak, x)
                if len(path) > 10000:
                    return Solution("lab", f"Collatz up to {N:,}", f"{start} hasn't reached 1 after 10,000 steps: investigate!", [], confidence=0.6)
            steps_ = cache[x]
            for y in reversed(path):
                steps_ += 1
                if y <= N * 4:
                    cache[y] = steps_
            if cache.get(start, steps_) > best:
                best, best_n = cache.get(start, steps_), start
        return Solution("lab", f"Collatz conjecture for 1 … {N:,}", f"every start reaches 1",
                        ["Collatz (1937): repeat n → n/2 (even) or 3n + 1 (odd); you always reach 1. Unproved.",
                         f"longest trajectory: {best_n:,} takes {best} steps", f"highest value reached: {peak:,}",
                         f"({time.time() - t0:.2f}s; verified by others up to about 2⁶⁸)"], EVIDENCE, confidence=0.99)
    m = re.search(r"(?:twin primes?)(?: pairs?)? (?:below|under|up to|less than) (\d+)|(?:how many|count) twin primes (?:are there )?(?:below|under|up to) (\d+)", t)
    if m:
        N = int(m.group(1) or m.group(2))
        if N > LAB_LIMIT * 5:
            raise MathError(f"up to {LAB_LIMIT * 5:,} here")
        s = _sieve(N)
        pairs = [(p, p + 2) for p in range(3, N - 1) if s[p] and s[p + 2]]
        return Solution("lab", f"twin primes below {N:,}", f"{len(pairs):,} pairs",
                        ["twin primes differ by 2; the twin prime conjecture says there are infinitely many (unproved;",
                         "Zhang 2013 and Maynard proved infinitely many prime pairs within 246 of each other)",
                         f"first: {', '.join(f'({a}, {b})' for a, b in pairs[:5])}" + (f"; largest: ({pairs[-1][0]:,}, {pairs[-1][1]:,})" if pairs else "")],
                        EVIDENCE if pairs else "")
    m = re.search(r"(?:check|test|verify|explore)(?: the)? riemann(?: hypothesis| zeta)?(?: (?:up to|to) height (\d+(?:\.\d+)?)| for the first (\d+) (?:non-?trivial )?zeros)?", t)
    if m:
        import mpmath
        with mpmath.workdps(15):  # double precision is plenty, whatever precision other code left set
            return _riemann(m, mpmath)
    return _fermat(t)


def _riemann(m, mpmath):
    if True:
        if m.group(1):
            T = float(m.group(1))
            if T > 1000:
                raise MathError("heights up to 1,000 here")
            total = _timed(zero_count, T)
            if total > 700:
                raise MathError("that range holds more than 700 zeros; try a smaller height")
            zs = [mpmath.zetazero(k) for k in range(1, total + 1)]
            on_line = sum(1 for z in zs if abs(z.real - 0.5) < 1e-12 and z.imag < T)
            return Solution("lab", f"Riemann hypothesis up to height {T:g}", f"all {total} zeros with 0 < Im(s) < {T:g} lie on Re(s) = 1/2",
                            ["Riemann (1859): every non-trivial zero of ζ(s) has real part 1/2. Unproved; a Millennium Prize Problem.",
                             f"N({T:g}) = {total}: zeros anywhere in the critical strip below height {T:g} (θ(T)/π + 1 + S(T), Backlund)",
                             f"{on_line} zeros found on the critical line by sign changes of Hardy's Z-function",
                             "every zero in the strip is accounted for on the line" if on_line == total else "MISMATCH: investigate",
                             f"first: {', '.join(f'1/2 + {float(z.imag):.4f}i' for z in zs[:3])}",
                             "(computers have verified the first 10¹³ zeros)"], EVIDENCE, confidence=0.98)
        k = int(m.group(2) or 20)
        if k > 200:
            raise MathError("up to 200 zeros here")
        zs = [mpmath.zetazero(j) for j in range(1, k + 1)]
        T = float(zs[-1].imag) + 0.01
        total = zero_count(T)
        return Solution("lab", f"Riemann hypothesis: the first {k} zeros", f"all {k} lie on the critical line Re(s) = 1/2" if total == k else "count mismatch: investigate",
                        ["Riemann (1859): every non-trivial zero of ζ(s) has real part 1/2. Unproved.",
                         f"zeros 1…{k}: imaginary parts {', '.join(f'{float(z.imag):.3f}' for z in zs[:5])}, …, {float(zs[-1].imag):.3f}",
                         f"|ζ| at the last one: {float(abs(mpmath.zeta(zs[-1]))):.1e} (≈ 0)",
                         f"N({T:.2f}) = {total} zeros in the whole strip below that height, the same {k}: none is off the line"],
                        EVIDENCE, confidence=0.98)
    return None


def _fermat(t: str):
    m = re.search(r"(?:check|test|verify) fermat'?s last theorem (?:for )?(?:n ?= ?|exponent )?(\d+)(?: (?:up to|below|with numbers up to) (\d+))?", t)
    if m:
        e, N = int(m.group(1)), int(m.group(2) or 200)
        if N > 2000:
            raise MathError("up to 2,000 here")
        powers = {i**e: i for i in range(1, int(((2 * N**e) ** (1 / e))) + 2)}
        hits = [(a, b, powers[a**e + b**e]) for a in range(1, N + 1) for b in range(a, N + 1) if (a**e + b**e) in powers]
        if e == 2:
            return Solution("lab", f"a² + b² = c² with a, b ≤ {N}", f"{len(hits)} Pythagorean triples",
                            [f"e.g. {', '.join(f'{a}²+{b}²={c}²' for a, b, c in hits[:4])}", "n = 2 has infinitely many solutions"])
        return Solution("lab", f"a^{e} + b^{e} = c^{e} with a, b ≤ {N}", "no solutions" if not hits else f"solutions found: {hits[:3]}",
                        [f"searched {N * (N + 1) // 2:,} pairs (a, b)",
                         "Fermat's Last Theorem (no solutions for n > 2) was proved by Andrew Wiles in 1994 — this is a check, the proof is his"],
                        confidence=0.99)
    return None


# ================================================================ the open problems

MILLENNIUM = {
    "riemann": ("The Riemann hypothesis", "open",
                "Every non-trivial zero of the Riemann zeta function ζ(s) has real part exactly 1/2.",
                "It controls how regularly the primes are spread out: true means the prime-counting error is as small as possible.",
                "verify the riemann hypothesis up to height 100"),
    "p vs np": ("P versus NP", "open",
                "If a solution can be checked quickly (in polynomial time), can it also be found quickly?",
                "Proving P ≠ NP needs to rule out every possible clever algorithm; known techniques (relativization, natural proofs, algebrization) provably can't do it.",
                "is 2^127 - 1 prime"),
    "navier": ("Navier–Stokes existence and smoothness", "open",
               "Do smooth, finite-energy solutions to the 3-D Navier–Stokes equations of fluid flow always exist for all time, or can they blow up?",
               "Turbulence transfers energy to ever smaller scales; current estimates can't rule out a singularity forming.",
               "solve y'' + y = 0"),
    "yang": ("Yang–Mills existence and mass gap", "open",
             "Construct quantum Yang–Mills theory rigorously in 4-D and prove its lightest particle has positive mass (the mass gap).",
             "Physicists use it daily; mathematicians can't yet even define the theory rigorously in four dimensions.",
             ""),
    "hodge": ("The Hodge conjecture", "open",
              "On a projective algebraic variety, certain topological 'Hodge classes' are combinations of classes of algebraic subvarieties.",
              "It links topology to algebraic geometry in a way no general method yet reaches.",
              ""),
    "birch": ("The Birch and Swinnerton-Dyer conjecture", "open",
              "The rank of an elliptic curve (how many independent rational points it has) equals the order of vanishing of its L-function at s = 1.",
              "Known only for ranks 0 and 1 (Gross–Zagier, Kolyvagin); higher ranks are out of reach.",
              ""),
    "poincare": ("The Poincaré conjecture", "solved (Grigori Perelman, 2003)",
                 "Every simply connected, closed 3-manifold is a 3-sphere.",
                 "Perelman proved it using Ricci flow with surgery (building on Hamilton); he declined the $1M prize in 2010.",
                 ""),
}
MILLENNIUM_ALIAS = [(r"riemann", "riemann"), (r"p ?(?:vs\.?|versus|=|!=|≠) ?np|p\s*=\s*np|p versus np", "p vs np"),
                    (r"navier|stokes", "navier"), (r"yang|mills|mass gap", "yang"), (r"hodge", "hodge"),
                    (r"birch|swinnerton|bsd conjecture", "birch"), (r"poincar", "poincare")]


def open_problems(t: str) -> Solution | None:
    if re.search(r"millennium (?:prize )?problems?|clay (?:institute )?problems", t):
        lines = [f"{v[0]}: {v[1]}" for v in MILLENNIUM.values()]
        return Solution("open_problem", "the Millennium Prize Problems", "7 problems (Clay Institute, 2000), $1M each; 6 are still open",
                        lines + ["Ask about any one (e.g. 'what is the riemann hypothesis'), or run an experiment: "
                                 "'verify the riemann hypothesis up to height 100', 'check goldbach up to 100000'."], confidence=0.99)
    key = next((k for pat, k in MILLENNIUM_ALIAS if re.search(pat, t)), None)
    if not key or not re.search(r"solve|prove|disprove|proof|answer|what is|what's|explain|tell me about|status|is .* (?:true|solved)|hypothesis|conjecture|problem", t):
        return None
    name, status, statement, why, try_ = MILLENNIUM[key]
    asks_solve = re.search(r"\b(?:solve|prove|disprove|proof of|answer to)\b", t)
    steps = [f"Statement: {statement}", f"Status: {status}", f"Why it's hard / what's known: {why}"]
    if asks_solve and status == "open":
        steps.insert(0, "I can't solve this, and neither can any program or person so far: it's an open problem with a $1,000,000 Clay prize.")
        steps.append("What I can do: check it on many cases, compute related quantities exactly, and explain the ideas.")
    if try_:
        steps.append(f"Try: {try_}")
    ans = (f"{name} is unsolved: no one has proved or disproved it" if asks_solve and status == "open"
           else f"{name}: {status}")
    return Solution("open_problem", name, ans, steps, confidence=0.99)


# ================================================================ entry point

def solve(text: str) -> Solution | None:
    t = re.sub(r"\s+", " ", text.lower().strip()).rstrip("?!. ")
    t = re.sub(r"^(?:please |can you |could you |kepler,? )+", "", t)
    if len(t) > 400:
        return None
    readers = (lab, open_problems, classic_proof, linear_algebra, ode, prove_sum, prove_identity, prove_inequality,
               number_theory_plus, series_convergence)
    try:
        for read in readers:
            sol = read(t)
            if sol:
                return sol
    except MathError as e:
        return Solution("error", t, str(e), ok=False, confidence=0.9)
    except (TypeError, ValueError, AttributeError, KeyError, IndexError, ZeroDivisionError, NotImplementedError,
            RecursionError, sp.SympifyError, sp.PolynomialError):
        return None
    return None
