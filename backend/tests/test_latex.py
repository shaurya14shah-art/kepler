"""Formal write-ups: plain-text maths → LaTeX, documents for every kind of answer, PDF compilation."""
import shutil

import pytest

from kepler.bot import latex
from kepler.bot.mind import Mind


@pytest.mark.parametrize("plain,tex", [
    ("Base case n = 1: left side = 1, right side = 1 ✓", r"Base case $n = 1$: left side $= 1$, right side $= 1$ $\checkmark$"),
    ("x = (−b ± √disc) ÷ 2a", r"$x = (-b \pm \sqrt{disc}) \div 2a$"),
    ("Σ_{k=1}^{n} (2·k - 1) = n^2", r"$\sum _{k=1}^{n} (2\cdot k - 1) = n^{2}$"),
    ("y(x) = C1·sin(x) + C2·cos(x)", r"$y(x) = C_{1}\cdot \sin(x) + C_{2}\cdot \cos(x)$"),
    ("discount = 25% of $40 = $10", r"discount $= 25\%$ of $\$40 = \$10$"),
    ("the 762nd digit is 9", "the 762nd digit is $9$"),
    ("A = [1  2; 3  4]", r"$A = \begin{bmatrix}1 & 2 \\ 3 & 4\end{bmatrix}$"),
])
def test_plain_maths_to_latex(plain, tex):
    assert latex.to_tex(plain) == tex


@pytest.mark.parametrize("text,question,pdf", [
    ("write a formal proof that 1 + 2 + ... + n = n(n+1)/2 as a pdf", "prove that 1 + 2 + ... + n = n(n+1)/2", True),
    ("make a pdf of the solution to x^2 - 5x + 6 = 0", "x^2 - 5x + 6 = 0", True),
    ("prove x + 1/x >= 2 for positive x as pdf", "prove x + 1/x >= 2 for positive x", True),
    ("give me the latex source for solve y'' + y = 0", "solve y'' + y = 0", False),
    ("y''+y'=x^2 /pdf", "y''+y'=x^2", True),
    ("solve y'' + y = 0 /pdf", "solve y'' + y = 0", True),
    ("x^2 - 1 = 0 /tex", "x^2 - 1 = 0", False),
])
def test_requests(text, question, pdf):
    assert latex.request(text) == (question, pdf)


@pytest.mark.parametrize("text", ["show signups as pdf", "what is 2+2", "is api_errors ok", "write"])
def test_not_requests(text):
    assert latex.request(text) is None


QUESTIONS = ["prove that 1 + 2 + ... + n = n(n+1)/2", "prove x + 1/x >= 2 for positive x",
             "prove there are infinitely many primes", "solve x^2 - 5x + 6 = 0", "integrate x^2 from 0 to 3",
             "determinant of [[1, 2], [3, 4]]", "solve y'' + y = 0", "sum of the first 10 digits of pi",
             "a car travels 120 km in 2 hours. what is its speed?", "what is a prime number", "is signups ok"]


def test_document_has_every_part():
    m = Mind()
    items = [latex.from_thought(q, m.think(q)) for q in QUESTIONS]
    tex = latex.document(items, "test")
    assert tex.count(r"\section*{Problem") == len(QUESTIONS)
    assert r"\begin{theorem}" in tex and r"\begin{proof}" in tex          # formal proofs
    assert r"\sum_{k=1}^{n} k = \frac{n \left(n + 1\right)}{2}" in tex      # from the maths engine's exact LaTeX
    assert r"\begin{bmatrix}" in tex and r"\begin{tcolorbox}[answerbox]" in tex
    assert "no language model" in tex
    assert tex.count("{") == tex.count("}") + tex.count(r"\{") - tex.count(r"\}")  # balanced braces


@pytest.mark.skipif(not (shutil.which("tectonic") or shutil.which("pdflatex")), reason="no LaTeX engine installed")
def test_compiles_to_pdf(tmp_path, monkeypatch):
    monkeypatch.setenv("KEPLER_DOCS", str(tmp_path))
    w, items = latex.write_answers(QUESTIONS[:6], Mind(), title="Kepler test")
    assert w.pdf and w.pdf.exists() and w.pdf.read_bytes()[:4] == b"%PDF"
    assert not w.note  # the formal layout compiled (no fallback)
    assert w.tex.read_text().startswith(r"\documentclass")


@pytest.mark.skipif(not (shutil.which("tectonic") or shutil.which("pdflatex")), reason="no LaTeX engine installed")
def test_broken_latex_still_gives_a_pdf(tmp_path):
    item = latex.Item("bad", "math", "bad", statement=r"\undefinedcommand{x}", answer="42")
    w = latex.write([item], "bad", out=tmp_path / "bad.pdf")
    assert w.pdf and w.pdf.exists() and "plain PDF" in w.note


def test_no_engine_means_tex_only(tmp_path, monkeypatch):
    monkeypatch.setattr(latex, "engine", lambda: None)
    w = latex.write([latex.Item("q", "math", "q", answer="1")], "q", out=tmp_path / "q.pdf")
    assert w.pdf is None and w.tex.exists() and "no LaTeX engine" in w.note
