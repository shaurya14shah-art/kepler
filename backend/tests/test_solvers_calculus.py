"""Calculus solver: chatty phrasings in, exact answers out; Kepler commands and definitions pass (None)."""
import time

import pytest

from kepler.bot.solvers.calculus import solve

POSITIVE = [
    ("derivative of x^2 * sin(x)? i keep mixing up the product rule", "x^2·cos(x) + 2x·sin(x)"),
    ("Differentiate (3x+1)^5 for me", "15(3x + 1)^4"),
    ("if y = e^(x^2), what is dy/dx", "2x·e^(x^2)"),
    ("d/dx of x ln x", "ln(x) + 1"),
    ("d/dx of sqrt(4x+9)", "2/√(4x + 9)"),
    ("quick one: integrate 4x^3 - 2x + 5 wrt x pls", "x^4 - x^2 + 5x + C"),
    ("indefinite integral of e^(3x) dx", "e^(3x)/3 + C"),
    ("integral of 1/(2x) dx", "ln|x|/2 + C"),
    ("from 0 to 2 of 3x^2 dx", "8"),
    ("integrate 1/x between 1 and e", "1"),
    ("area under sin x from 0 to pi", "2 square units"),
    ("between 1 and 4 of sqrt(x) dx", "14/3 ≈ 4.667"),
    ("integral from 0 to 1 of 2x dx", "1"),
    ("lim x->3 (x^2-9)/(x-3)", "6"),
    ("limit of sin(x)/x as x goes to 0", "1"),
    ("limit of (3x^2+1)/(x^2-5) as x -> infinity", "3"),
    ("(1 - cos x)/x^2 as x approaches 0", "1/2 = 0.5"),
    ("lim x->2 of x^2 + 1", "5"),
    ("slope of the tangent to y = x^3 at x = 2", "12"),
    ("equation of the tangent line to y = x^2 + 1 at x = 1", "y = 2x"),
    ("find the stationary points of x^3 - 3x", "local maximum at (-1, 2); local minimum at (1, -2)"),
    ("max value of -x^2 + 6x and where it happens", "maximum 9 at x = 3"),
    ("global min of x^3 - 3x on [0, 2]", "minimum -2 at x = 1"),
    ("max area with 40 m of fencing", "100 m² (10 m by 10 m)"),
    ("open box from a 12 cm by 12 cm sheet, cut squares from corners, max volume", "128 cm³ (cut 2 cm squares)"),
    ("position s(t) = t^3 - 6t^2 + 9t, velocity at t = 2", "-3"),
    ("velocity v(t) = 3t^2 - 2t, distance travelled from t=0 to t=3", "494/27 ≈ 18.3"),
    ("revenue R(q) = 50q - 0.5q^2, marginal revenue at q = 20", "30.00 per unit"),
    ("cost C(x) = 0.01x^3 - 0.6x^2 + 13x + 1000, marginal cost at x = 30", "4.00 per unit"),
]

# answers whose exact display may vary: check the value is present
CONTAINS = [
    ("for my homework: differentiate x^3 + 2x", "3x^2 + 2"),
    ("whats the derivative of cos(2x)", "sin(2x)"),
    ("d/dx e^x sin x, show me the steps", "e^x"),
    ("integrate x e^x dx", "e^x"),
    ("evaluate the integral of x^2 from 0 to 3", "9"),
    ("limit as x approaches 1 of (x^2 - 1)/(x - 1)", "2"),
    ("find dy/dx if y = x^4", "4x^3"),
    ("min value of x^2 - 4x + 7", "3"),
]


@pytest.mark.parametrize("q,expected", POSITIVE)
def test_exact(q, expected):
    sol = solve(q)
    assert sol is not None and sol.ok and sol.steps
    assert sol.answer == expected


@pytest.mark.parametrize("q,expected", CONTAINS)
def test_contains(q, expected):
    sol = solve(q)
    assert sol is not None and sol.ok
    assert expected in sol.answer


NEGATIVE = [
    "is signups ok", "why did checkout_errors spike 40% at 3pm", "show incidents from the last 6 hours",
    "set sensitivity to 80%", "switch payments to area", "explain incident 42", "mark #12 as a false alarm",
    "connect datadog", "break down signups by region", "chart latency for 24h", "hi kepler", "thanks!",
    "what is a derivative", "what's the difference between mean and median", "who invented the telephone",
    "how are you",
]


@pytest.mark.parametrize("q", NEGATIVE)
def test_none(q):
    assert solve(q) is None


def test_fast():
    t0 = time.perf_counter()
    for q, _ in POSITIVE:
        solve(q)
    assert (time.perf_counter() - t0) / len(POSITIVE) < 1.0
