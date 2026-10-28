"""Advanced reasoning: proofs (and refutations), research-level computation, the conjecture lab, open problems."""
import time

import pytest

from kepler.bot.reasoning import solve_text

CASES = {
    # proofs and refutations
    "prove that 1 + 2 + ... + n = n(n+1)/2": "proved by induction: Σ k = n·(n + 1)/2",
    "prove by induction that 1 + 3 + 5 + ... + (2n-1) = n^2": "proved by induction: Σ (2·k - 1) = n^2",
    "prove sum of k^3 for k from 1 to n = (n(n+1)/2)^2": "proved by induction: Σ k^3 = n^2·(n + 1)^2/4",
    "prove that 1 + 2 + ... + n = n^2": "false: counterexample n = 2 (left 3, right 4)",
    "prove (a+b)^2 = a^2 + 2ab + b^2": "true: it's an identity",
    "prove that sin(x)^2 + cos(x)^2 = 1": "true: it's an identity",
    "prove x^2 + 1 >= 2x": "true: proved",
    "prove a^2 + b^2 >= 2ab": "true: proved",
    "prove x + 1/x >= 2 for positive x": "true: proved",
    "prove there are infinitely many primes": "proved: Euclid's theorem: there are infinitely many primes",
    "prove that the square root of 2 is irrational": "proved: √2 is irrational",
    "prove sqrt 6 is irrational": "proved: √6 is irrational",
    "prove sqrt 9 is irrational": "false: √9 = 3 is a whole number",
    # linear algebra
    "determinant of [[1, 2], [3, 4]]": "-2",
    "inverse of [[2, 1], [1, 3]]": "[0.6  -0.2; -0.2  0.4]",
    "eigenvalues of [[4, 1], [2, 3]]": "5, 2",
    "rank of [[1, 2, 3], [2, 4, 6], [1, 1, 1]]": "2",
    "[[1, 2], [3, 4]] times [[5, 6], [7, 8]]": "[19  22; 43  50]",
    # differential equations
    "solve y'' + y = 0": "y(x) = C1·sin(x) + C2·cos(x)",
    "solve y' = 2y": "y(x) = C1·exp(2·x)",
    "solve dy/dx = x*y": "y(x) = C1·exp(x^2/2)",
    "y''+y'=x^2": "y(x) = C1 + C2·exp(-x) + x^3/3 - x^2 + 2·x",       # no "solve", no spaces
    "dy/dx = 3y": "y(x) = C1·exp(3·x)",
    "d^2y/dx^2 + y = 0": "y(x) = C1·sin(x) + C2·cos(x)",
    # number theory
    "7^222 mod 13": str(pow(7, 222, 13)),
    "is 2^127 - 1 prime": "yes",
    "is 2^67 - 1 prime": "no",
    "factor 2^64 + 1": "274177 × 67280421310721",
    "totient of 360": "96",
    "x ≡ 2 mod 3 and x ≡ 3 mod 5": "x ≡ 8 (mod 15)",
    # series
    "does the sum of 1/n^2 converge": "converges (to π^2/6 ≈ 1.644934067)",
    "does the series 1/n converge": "diverges",
    # lab
    "check goldbach up to 100000": "holds for all 49,999 even numbers checked",
    "check collatz up to 100000": "every start reaches 1",
    "twin primes below 100000": "1,224 pairs",
    "verify the riemann hypothesis up to height 100": "all 29 zeros with 0 < Im(s) < 100 lie on Re(s) = 1/2",
    "check fermat's last theorem for n=3 up to 100": "no solutions",
    # open problems: honest
    "solve the riemann hypothesis": "The Riemann hypothesis is unsolved: no one has proved or disproved it",
    "prove p = np": "P versus NP is unsolved: no one has proved or disproved it",
    "is the poincare conjecture solved": "The Poincaré conjecture: solved (Grigori Perelman, 2003)",
}


@pytest.mark.parametrize("q", list(CASES))
def test_advanced(q):
    s = solve_text(q)
    assert s is not None and s.ok, q
    assert s.answer == CASES[q], (q, s.answer)
    assert s.steps


def test_false_inequality_gets_a_counterexample():
    s = solve_text("prove x^2 >= x")
    assert s.answer.startswith("false: counterexample x = ")
    x = float(s.answer.rsplit("= ", 1)[1])
    assert x * x < x  # the counterexample really is one


def test_lab_is_labelled_evidence_not_proof():
    for q in ("check goldbach up to 1000", "verify the riemann hypothesis up to height 50", "check collatz up to 1000"):
        assert "evidence, not a proof" in solve_text(q).check


def test_open_problems_are_never_claimed_solved():
    for q in ("solve p vs np", "prove the riemann hypothesis", "solve navier stokes", "prove the hodge conjecture",
              "solve the birch and swinnerton-dyer conjecture", "solve yang mills mass gap"):
        s = solve_text(q)
        assert s and "unsolved" in s.answer, q


def test_lab_limits_are_fast():
    t = time.time()
    s = solve_text("check goldbach up to 999999999")
    assert not s.ok and time.time() - t < 1
