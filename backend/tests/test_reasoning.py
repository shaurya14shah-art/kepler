"""The maths reasoning engine: right answers, worked steps, checks, safety, and no hijacking of Kepler commands."""
import io
import time

import pytest
from rich.console import Console

from kepler import device
from kepler.bot import model, store
from kepler.bot.reasoning import solve_text
from kepler.bot.teach import Trainer

ANSWERS = {
    "what is 2+2": "4",
    "12 * (3 + 4)^2 / 7": "84",
    "how much is 12 times 7?": "84",
    "what is 3 + 4 * 2 - (6 / 3)^2": "7",
    "1/4 + 1/4": "0.5",
    "7/3": "7/3 ≈ 2.333333333",
    "2^10": "1024",
    "17 mod 5": "2",
    "5!": "120",
    "the square root of 144": "12",
    "sin 30 degrees": "0.5",
    "log 1000": "3",
    "ln(e^2)": "2",
    "what's 15% of 200": "30",
    "what's 2.5% of 1,200?": "30",
    "30 is what percent of 120": "25%",
    "percent change from 120 to 150": "+25% (increase)",
    "increase 80 by 25%": "100",
    "average of 4, 8 and 15": "9",
    "median of 3 1 4 1 5": "3",
    "std of 2,4,4,4,5,5,7,9": "2",
    "gcd of 12 and 18": "6",
    "lcm of 4, 6, 10": "60",
    "is 97 prime": "yes",
    "is 91 prime": "no",
    "prime factors of 360": "2^3 × 3^2 × 5",
    "solve 2x + 3 = 7": "x = 2",
    "x^2 - 5x + 6 = 0": "x = 2, x = 3",
    "x^2 + 4x + 13 = 0": "x = -2 - 3·i, x = -2 + 3·i",
    "solve x + y = 10, x - y = 2": "x = 6, y = 4",
    "derivative of x^3 + 2x": "3·x^2 + 2",
    "derivative of x^2 sin(x)": "x^2·cos(x) + 2·x·sin(x)",
    "integrate x^2 from 0 to 3": "9",
    "integral of 1/x": "ln(x) + C",
    "limit of sin(x)/x as x approaches 0": "1",
    "factor x^2 - 1": "(x - 1)·(x + 1)",
    "expand (x+1)^3": "x^3 + 3·x^2 + 3·x + 1",
    "simplify (x^2-1)/(x-1)": "x + 1",
}


@pytest.mark.parametrize("q", list(ANSWERS))
def test_answers(q):
    s = solve_text(q)
    assert s is not None and s.ok, q
    assert s.answer == ANSWERS[q]
    assert s.steps, "every answer comes with its reasoning"
    assert "✗" not in s.check


@pytest.mark.parametrize("q", ["1/0", "9^9^9", "2^100000", "3000!", "10^10^10^10", "2^(2^(2^(2^2)))", "(0)^(-1)",
                               "log(0)", "x = x + 1", "solve 2x = 4, 2x = 5"])
def test_undefined_or_huge_is_refused_fast(q):
    t = time.time()
    s = solve_text(q)
    assert time.time() - t < 2
    assert s is not None
    assert not s.ok or s.answer == "no solution"


@pytest.mark.parametrize("q", ["pow(9, 9**9)", "__import__('os').system('ls')", "().__class__", "eval(1)",
                               "exec 1+1", "var('x') + 1", "open(1)", "lambda: 1", "[1,2][0] + 1", "x.__class__ + 1",
                               "'a' * 10**9", "1e999999"])
def test_code_and_tricks_never_run(q):
    t = time.time()
    s = solve_text(q)
    assert time.time() - t < 2
    assert s is None or not s.ok or s.kind in ("arithmetic", "simplify")


@pytest.mark.parametrize("q", ["!5", "! 3", "!!", "5 + !2", "solve !x = 2", "simplify !"])
def test_broken_factorial_notation_is_refused_not_crashed(q):
    """sympy raises tokenize.TokenError (not a SyntaxError) on a leading '!': found by the stress test."""
    from kepler.bot.reasoning import MathError, to_expr
    with pytest.raises(MathError):
        to_expr(q.removeprefix("solve ").removeprefix("simplify ").replace("= 2", ""))
    s = solve_text(q)
    assert s is None or not s.ok


@pytest.mark.parametrize("q", ["show the last 5 incidents", "set sensitivity to 70%", "explain #40", "is signups ok",
                               "what's the average of signups", "how do i solve the latency issue",
                               "what factor caused the spike", "show api_errors last 6h", "1", "2", "label 40 real",
                               "hello!", "plot signups for 3 days", "status", "switch to time", "copy decision 40",
                               "break down p95_latency_ms by region", "inject the ios release bug"])
def test_kepler_commands_stay_with_the_bot(q):
    assert solve_text(q) is None


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(device, "HOME", tmp_path)
    monkeypatch.setattr(model, "_cache", None)
    return tmp_path


def test_teach_box_answers_maths_and_lessons_override_it(home):
    buf = io.StringIO()
    t = Trainer(Console(file=buf, width=120, color_system=None))
    t.handle("solve 2x + 3 = 7")
    out = buf.getvalue()
    assert "◆ math" in out and "x = 2" in out and "Reasoning" in out and "✓" in out
    t.handle("/y")
    assert store.load()["examples"] == []  # maths isn't learned, it's worked out
    # a sentence you label as something else is no longer treated as maths
    t.handle("p95 is 300")
    t.handle("/n status")
    assert store.taught_intent("p95 is 300") == "status"
    buf.truncate(0)
    t.handle("p95 is 300")
    assert "◆ status" in buf.getvalue()
