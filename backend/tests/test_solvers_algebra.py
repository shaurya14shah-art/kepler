"""Algebra solver: chatty phrasings in, exact answers out; Kepler commands and definitions pass (None)."""
import time

import pytest

from kepler.bot.solvers.algebra import solve

POSITIVE = [
    # equations
    ("what are the roots of x^2 - 5x + 6 = 0", "x = 2 or x = 3"),
    ("can u run the quadratic formula on 2x^2 + 3x - 9 = 0", "x = -3 or x = 3/2 = 1.5"),
    ("x^2 + 4x - 12 = 0, solve it", "x = -6 or x = 2"),
    ("solve 3/(x - 1) = 2", "x = 5/2 = 2.5"),
    ("quick one: solve 5x - 7 = 3x + 9 pls", "x = 8"),
    ("for my homework, solve 2(x + 3) = 14 and show me the steps", "x = 4"),
    ("solve x^2 = 2, exact form if you can", "x = -√2 ≈ -1.414 or x = √2 ≈ 1.414"),
    ("x^2 + 2x + 5 = 0", "no real roots; complex roots x = -1 - 2i and x = -1 + 2i"),
    ("find x: x/3 + 1 = 5", "x = 12"),
    ("solve 7 - 3x = 1 - x give it as a fraction", "x = 3"),
    ("solve 4x + 1 = 2, give it as a fraction", "x = 1/4 = 0.25"),
    ("x^2 - 6x + 9 = 0", "x = 3"),
    # systems
    ("x + y = 10 and x - y = 4", "x = 7, y = 3"),
    ("2x + 3y = 12, 4x - y = 5", "x = 27/14 ≈ 1.929, y = 19/7 ≈ 2.714"),
    ("solve the system x + y + z = 6, x - y + z = 2, 2x + y - z = 1", "x = 1, y = 2, z = 3"),
    ("3a + 2b = 7 and a - b = 4 pls", "a = 3, b = -1"),
    # inequalities
    ("what x values make 4 - 2x > 10 true", "x < -3"),
    ("solve 3x + 2 <= 11", "x ≤ 3"),
    ("for which x is 5 - x >= 2x - 4", "x ≤ 3"),
    ("2x - 7 < 3x + 1", "x > -8"),
    # absolute value
    ("|2x - 5| = 9", "x = -2 or x = 7"),
    ("solve |x - 3| < 4 pls", "-1 < x < 7"),
    ("|x + 1| > 2, find x", "x < -3 or x > 1"),
    ("solve |3x| = -2", "no solution"),
    # factor / expand
    ("factor 6x^2 + x - 2", "(2x - 1)(3x + 2)"),
    ("factorise x^2 - 9y^2", "(x - 3y)(x + 3y)"),
    ("can you factor x^2 + 5x + 6", "(x + 2)(x + 3)"),
    ("expand (x + 3)(2x - 5)", "2x^2 + x - 15"),
    ("expand (a - b)^2", "a^2 - 2ab + b^2"),
    # vertex / discriminant
    ("vertex of y = x^2 - 4x + 7", "vertex (2, 3), a minimum"),
    ("what's the vertex of the parabola y = -2x^2 + 8x - 3", "vertex (2, 5), a maximum"),
    ("find the discriminant of 2x^2 + 3x + 5 = 0 and the nature of the roots",
     "D = -31: no real roots (two complex conjugate roots)"),
    ("discriminant of x^2 - 4x + 4", "D = 0: one repeated real root"),
    ("how many real roots does x^2 - 3x - 10 = 0 have", "D = 49: two distinct real roots (rational)"),
    # evaluate
    ("3x^2 - 2xy + y at x = 2, y = -1", "15"),
    ("(2a + b)/(a - b) when a = 5 and b = -3", "7/8 = 0.875"),
    ("evaluate x^2 + 1 for x = 1/3", "10/9 ≈ 1.111"),
    # word problems
    ("a phone plan costs $25 a month plus $0.10 per text. with a $40 budget how many texts can she send?",
     "at most 150 texts"),
    ("a rectangle's length is 3 more than twice its width. the perimeter is 36 cm. find the dimensions",
     "width 5 cm, length 13 cm"),
    ("A phone plan costs $25 a month plus $0.10 per text message. With a $40 monthly budget, how many texts can I send?",
     "at most 150 texts"),
    ("The length of a rectangle is 3 more than twice its width. If the perimeter is 36, find the length and width.",
     "width 5, length 13"),
    ("A rectangle has a perimeter of 50 m and its length is 5 m more than its width", "width 10 m, length 15 m"),
]

NEGATIVE = [
    "is signups ok", "why did checkout_errors spike 40% at 3pm", "show incidents from the last 6 hours",
    "set sensitivity to 80%", "switch payments to area", "explain incident 42", "mark #12 as a false alarm",
    "connect datadog", "break down signups by region", "chart latency for 24h", "hi kepler", "thanks!",
    "what is a derivative", "what's the difference between mean and median", "who invented the telephone",
    "how are you",
]


@pytest.mark.parametrize("q,expected", POSITIVE)
def test_exact(q, expected):
    sol = solve(q)
    assert sol is not None and sol.ok and sol.steps
    assert sol.answer == expected


@pytest.mark.parametrize("q", NEGATIVE)
def test_none(q):
    assert solve(q) is None


def test_fast():
    t0 = time.perf_counter()
    for q, _ in POSITIVE:
        solve(q)
    assert (time.perf_counter() - t0) / len(POSITIVE) < 0.5
