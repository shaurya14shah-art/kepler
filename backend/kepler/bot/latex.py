"""Formal write-ups: Kepler's answers as LaTeX documents, compiled to PDF.

  document(items) → .tex source     (title page block, one section per question: theorem + proof for proofs,
                                      numbered steps for solutions, a boxed answer, verification, sources)
  write(items)    → .pdf (and .tex) (compiled with Tectonic, else pdflatex / xelatex / lualatex)

Answers that carry LaTeX from the maths engine (tex_statement / tex_steps / tex_answer) are typeset from it
directly; everything else goes through `to_tex`, which turns Kepler's plain-text maths (√, Σ, ≥, π, x^2, C1, …)
into LaTeX. Compilation is sandboxed: no shell escape (Tectonic --untrusted, -no-shell-escape for the others),
a time limit, and a plain fallback document if the formal one ever fails to compile, so you always get a PDF.
"""
import datetime
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

TIMEOUT = 240  # seconds; the very first Tectonic run downloads the LaTeX packages it needs


def docs_dir() -> Path:
    return Path(os.environ.get("KEPLER_DOCS") or Path.home() / "Documents" / "Kepler")


@dataclass
class Item:
    """One question in a document."""
    question: str
    kind: str                      # math | knowledge | lookup | text
    title: str = ""
    statement: str = ""            # LaTeX (math mode) or ""
    steps: list[str] = field(default_factory=list)       # plain text
    tex_steps: list[str] = field(default_factory=list)   # LaTeX paragraphs
    answer: str = ""
    tex_answer: str = ""
    check: str = ""
    sources: list[dict] = field(default_factory=list)    # {title, url, licence, origin}
    proof: bool = False


# ---------------------------------------------------------------- plain text → LaTeX

TEXT_ESC = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{",
            "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
SYMBOLS = [("·", r"\cdot "), ("×", r"\times "), ("÷", r"\div "), ("−", "-"), ("–", "-"), ("±", r"\pm "), ("∓", r"\mp "),
           ("≤", r"\le "), ("≥", r"\ge "), ("≠", r"\ne "), ("≈", r"\approx "), ("≡", r"\equiv "), ("∞", r"\infty "),
           ("→", r"\to "), ("⇒", r"\Rightarrow "), ("⇔", r"\Leftrightarrow "), ("∈", r"\in "), ("∑", r"\sum "),
           ("Σ", r"\sum "), ("∫", r"\int "), ("∏", r"\prod "), ("∂", r"\partial "), ("′", "'"), ("∎", r"\blacksquare "),
           ("π", r"\pi "), ("θ", r"\theta "), ("λ", r"\lambda "), ("ζ", r"\zeta "), ("φ", r"\varphi "), ("γ", r"\gamma "),
           ("τ", r"\tau "), ("α", r"\alpha "), ("β", r"\beta "), ("δ", r"\delta "), ("ε", r"\varepsilon "), ("μ", r"\mu "),
           ("σ", r"\sigma "), ("ω", r"\omega "), ("Δ", r"\Delta "), ("Ω", r"\Omega "), ("°", r"^\circ "),
           ("²", "^{2}"), ("³", "^{3}"), ("⁻¹", "^{-1}"), ("ⁿ", "^{n}"), ("₀", "_0"), ("₁", "_1"), ("₂", "_2"),
           ("₃", "_3"), ("₁₀", "_{10}"), ("ᵢ", "_i"), ("ₖ", "_k"), ("ᵀ", "^{T}"), ("✓", r"\checkmark "),
           ("✗", r"\times "), ("…", r"\ldots "), ("|", r"\mid ")]
FUNCS = ["arcsin", "arccos", "arctan", "sinh", "cosh", "tanh", "sin", "cos", "tan", "exp", "log", "ln", "det", "gcd",
         "lim", "max", "min"]
MATHY = re.compile(r"[=<>+*/^_√∑Σ∫πθλζφγτ·×÷≤≥≠≈≡∞±²³⁻ⁿ′()\[\]]|\d|^[-−]$|^[a-zA-Z]$|^[a-z]\(|^(?:%s)\b" % "|".join(FUNCS))
WORD = re.compile(r"^[A-Za-z][a-z]+[.,:;!?]?$")


def _escape_text(s: str) -> str:
    out = "".join(TEXT_ESC.get(c, c) for c in s).replace("''", "\\textquotesingle\\textquotesingle{}")
    out = out.replace("✓", r"$\checkmark$").replace("✗", r"$\times$").replace("∎", r"$\blacksquare$")
    out = out.replace("—", "---").replace("–", "--")
    out = out.replace("“", "``").replace("”", "''").replace("’", "'").replace("…", r"\ldots{}").replace("→", r"$\to$")
    return re.sub(r"([≤≥≠≈≡±×÷·−√πΣ∞⇒²³°])", lambda m: f"${_math(m.group(1))}$", out)


def _math(s: str) -> str:
    """One run of plain-text maths → LaTeX math-mode source."""
    m = s.strip()
    m = m.replace("%", r"\%").replace("#", r"\#").replace("&", r"\&").replace("$", r"\$").replace("...", "…")
    m = re.sub(r"√\(([^()]*)\)", lambda g: "\x00sqrt{" + g.group(1) + "}", m)
    m = re.sub(r"√(\w+)", lambda g: "\x00sqrt{" + g.group(1) + "}", m)
    m = re.sub(r"∛\(([^()]*)\)|∛(\w+)", lambda g: "\x00sqrt[3]{" + (g.group(1) or g.group(2)) + "}", m)
    m = re.sub(r"\[([^\[\]]*;[^\[\]]*)\]", lambda g: "\x00begin{bmatrix}" + " \x00\x00 ".join(
        " & ".join(row.split()) for row in g.group(1).split(";")) + "\x00end{bmatrix}", m)  # [1 2; 3 4]
    m = re.sub(r"\^\(([^()]*)\)", r"^{\1}", m)                     # x^(n+1) → x^{n+1}
    m = re.sub(r"\^(-?[\w.]+)", r"^{\1}", m)                      # x^10, e^-x
    m = re.sub(r"\bC(\d+)\b", r"C_{\1}", m)                        # C1 → C_{1}
    # words of 3+ letters stay upright text, function names become operators (before any macros exist)
    def word(g):
        w = g.group(0)
        return "\x00" + w if w in FUNCS else (r"\text{" + w + "}" if w != "mod" else "\x00bmod")
    m = re.sub(r"(?<![\x00\\{])\b[A-Za-z]{3,}\b", word, m)
    for sym, tex in SYMBOLS:
        m = m.replace(sym, tex)
    return m.replace("\x00", "\\")


ORDINAL = re.compile(r"^\(?\d[\d,]*(?:st|nd|rd|th)\b")


def to_tex(line: str) -> str:
    """A step written for the terminal → LaTeX (text with inline $maths$)."""
    if not line.strip():
        return ""
    label = ""
    lm = re.match(r"^\[(library|maths|web)\]\s*", line)
    if lm:
        label, line = f"\\textsc{{{lm.group(1)}}}: ", line[lm.end():]
    out: list[str] = []
    run: list[str] = []

    def flush():
        if not run:
            return
        expr = "".join(run)
        lead = expr[: len(expr) - len(expr.lstrip())]
        tail_ws = expr[len(expr.rstrip()):]
        expr = expr.strip()
        trail = ""
        while expr and expr[-1] in ",.;:" and not re.search(r"\d\.$", expr[-2:] + "x"):
            trail = expr[-1] + trail
            expr = expr[:-1]
        out.append(lead + (f"${_math(expr)}$" if expr else "") + _escape_text(trail) + tail_ws)
        run.clear()

    for tok in re.split(r"(\s+)", line.strip()):
        if not tok:
            continue
        if tok.isspace():
            (run if run else out).append(" ")
            continue
        mathy = (MATHY.search(tok) and not WORD.match(tok) and not ORDINAL.match(tok)
                 and not re.search(r"[“”‘’\"]", tok) and not re.fullmatch(r"\(?[A-Za-z]{2,}\)?[,.]?", tok))
        if mathy:
            run.append(tok)
        else:
            flush()
            out.append(_escape_text(tok))
    flush()
    return label + re.sub(r" {2,}", " ", "".join(out)).strip()


# ---------------------------------------------------------------- building items from Kepler's answers

def from_thought(question: str, th) -> Item:
    """A Mind thought (math / knowledge / lookup / intent) → a document item."""
    if th.kind in ("math", "steps") and th.solution is not None:
        s = th.solution
        sources = []
        for step in s.steps:
            m = re.search(r"\(“?.*?”?,? ?([^·(]+?) · ([^)]+)\)\s*$", step)
            if step.startswith("[library]") and m:
                sources.append({"title": m.group(1).strip(), "origin": m.group(2).strip(), "url": "", "licence": ""})
        title = re.sub(r"^(?:prove(?: that)?|show(?: that)?|solve|find|compute|calculate|verify|check)\s+", "", s.problem).strip()
        return Item(question, "math", title or question, s.tex_statement, list(s.steps), list(s.tex_steps), s.answer,
                    s.tex_answer, s.check, sources, proof=s.kind == "proof")
    if th.kind == "knowledge" and th.knowledge:
        k = th.knowledge
        steps = [k["text"]] + ([f"Example: {k['example']}"] if k.get("example") else [])
        steps += [f"Also ({o['origin']}): {o['text']}" for o in k.get("supporting", [])]
        from .knowledge import SPELLED
        title = k.get("title", question)
        return Item(question, "knowledge", SPELLED.get(title, title[:1].upper() + title[1:]), steps=steps,
                    answer=k["text"],
                    sources=[{"title": "Kepler knowledge base", "origin": "built in", "url": "", "licence": ""}])
    if th.kind == "lookup" and th.lookup:
        a = th.lookup
        src = [{"title": a["title"], "origin": a["origin"], "url": a.get("url", ""), "licence": a.get("licence", "")}] if a.get("title") else []
        steps = [a["text"]] + [f"Also ({o['origin']}): {o['text']}" for o in a.get("supporting", [])]
        return Item(question, "lookup", a.get("title") or question, steps=steps,
                    answer=a["text"] if a["decision"] == "answer" else f"({a['decision']}) {a['text']}",
                    check=f"confidence {a['confidence']:.2f}", sources=src)
    return Item(question, "text", question, steps=["This question is about Kepler itself (metrics, incidents, settings); "
                                                   "ask it in the chat to get the live answer."])


# ---------------------------------------------------------------- the document

PREAMBLE = r"""\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage{amsmath,amssymb,amsthm,mathtools}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{microtype}
\usepackage{enumitem}
\usepackage{xcolor}
\usepackage[most]{tcolorbox}
\usepackage{fancyhdr}
\usepackage[hidelinks]{hyperref}
\definecolor{kepler}{HTML}{6B5CE7}
\newtheorem*{claim}{Claim}
\newtheorem*{theorem}{Theorem}
\theoremstyle{definition}
\newtheorem*{problem}{Problem}
\tcbset{answerbox/.style={colback=kepler!6,colframe=kepler!70,boxrule=0.6pt,arc=2pt,left=6pt,right=6pt,top=4pt,bottom=4pt}}
\pagestyle{fancy}\fancyhf{}
\fancyhead[L]{\small\textcolor{kepler}{Kepler}}\fancyhead[R]{\small \today}
\fancyfoot[C]{\footnotesize Generated by Kepler: deterministic reasoning (rules and exact computer algebra), no language model. \quad \thepage}
\setlength{\parskip}{4pt}\setlength{\parindent}{0pt}
\allowdisplaybreaks
"""


def _title_tex(t: str) -> str:
    if not t:
        return ""
    starts_with_words = re.match(r"[a-z]{3,}\b", t) and not re.match(r"(?:%s)\b" % "|".join(FUNCS), t)
    return to_tex(t[:1].upper() + t[1:] if starts_with_words else t)


def _section(i: int, it: Item, total: int) -> str:
    head = f"Problem {i}" if total > 1 else "Problem"
    shown = f"${it.statement}$" if it.statement and len(it.statement) < 160 else _title_tex(it.title)[:180]
    plain = _escape_text(re.sub(r"\s+", " ", it.question))[:70]
    lines = [f"\\section*{{{head}: {shown}}}", f"\\addcontentsline{{toc}}{{section}}{{{head}: {plain}}}"]
    lines.append(f"\\begin{{problem}}{to_tex(it.question)}\\end{{problem}}")
    if it.proof:
        env = "theorem" if it.tex_statement_ok() else "claim"
        lines.append(f"\\begin{{{env}}}" + (f"${it.statement}$" if it.statement else to_tex(it.title)) + f"\\end{{{env}}}")
        lines.append("\\begin{proof}")
        if it.tex_steps:
            lines += [s + "\n" for s in it.tex_steps]
        else:
            body = [s for s in it.steps if not s.startswith("Claim")]
            lines.append("\\begin{enumerate}[label=(\\arabic*),leftmargin=2em]")
            lines += [f"\\item {to_tex(s.replace('∎', '').strip())}" for s in body if s.strip(" ∎")]
            lines.append("\\end{enumerate}")
        lines.append("\\end{proof}")
    else:
        if it.statement and len(it.statement) >= 160:
            lines.append(f"\\[ {it.statement} \\]")  # short statements are already in the heading
        if it.tex_steps:
            lines.append("\\subsection*{Solution}")
            lines += [f"\\[ {s} \\]" for s in it.tex_steps]
        elif it.steps:
            lines.append("\\subsection*{Solution}" if it.kind == "math" else "\\subsection*{Answer in detail}")
            lines.append("\\begin{enumerate}[label=\\textbf{Step \\arabic*.},leftmargin=4.2em]")
            lines += [f"\\item {to_tex(s)}" for s in it.steps if s.strip()]
            lines.append("\\end{enumerate}")
    ans = f"\\[ {it.tex_answer} \\]" if it.tex_answer else to_tex(it.answer)
    lines.append(f"\\begin{{tcolorbox}}[answerbox]\\textbf{{Answer.}} {ans}\\end{{tcolorbox}}")
    if it.check:
        lines.append(f"\\paragraph{{Verification.}} {to_tex(it.check)}")
    if it.sources:
        lines.append("\\paragraph{Sources.}\\begin{itemize}[leftmargin=1.5em,itemsep=0pt]")
        for s in it.sources:
            url = f" \\url{{{s['url']}}}" if s.get("url") else ""
            lic = f" ({_escape_text(s['licence'])})" if s.get("licence") else ""
            lines.append(f"\\item {_escape_text(s['title'])}, {_escape_text(s.get('origin', ''))}{url}{lic}")
        lines.append("\\end{itemize}")
    return "\n".join(lines)


def _ok_statement(self) -> bool:
    return bool(self.statement)


Item.tex_statement_ok = _ok_statement


def document(items: list[Item], title: str = "") -> str:
    title = title or (items[0].title if len(items) == 1 else f"{len(items)} problems")
    body = [PREAMBLE, f"\\title{{\\textbf{{{_title_tex(title)[:200]}}}}}",
            "\\author{Kepler}", f"\\date{{{datetime.date.today():%d %B %Y}}}", "\\begin{document}", "\\maketitle",
            "\\thispagestyle{fancy}"]
    if len(items) > 2:
        body.append("\\tableofcontents\\bigskip")
    body += [_section(i, it, len(items)) for i, it in enumerate(items, 1)]
    body.append("\\end{document}\n")
    return "\n".join(body)


def plain_document(items: list[Item], title: str = "") -> str:
    """A fallback that always compiles: everything as escaped text."""
    body = [r"\documentclass[11pt]{article}\usepackage[margin=1in]{geometry}\usepackage[T1]{fontenc}\usepackage{lmodern}",
            r"\usepackage{amssymb}\setlength{\parindent}{0pt}\begin{document}",
            f"\\section*{{{_escape_text(title or items[0].title)}}}"]
    for i, it in enumerate(items, 1):
        body.append(f"\\subsection*{{{i}. {_escape_text(it.question)}}}")
        body += [f"{_escape_text(s)}\\par" for s in it.steps]
        body.append(f"\\textbf{{Answer:}} {_escape_text(it.answer)}\\par")
        if it.check:
            body.append(f"\\textit{{{_escape_text(it.check)}}}\\par")
    body.append(r"\vfill{\footnotesize Generated by Kepler (plain layout).}\end{document}")
    return "\n".join(body)


# ---------------------------------------------------------------- compiling

def engine() -> list[str] | None:
    if shutil.which("tectonic"):
        return ["tectonic", "-X", "compile", "--untrusted", "--outdir", "{out}", "{tex}"]
    for e in ("pdflatex", "xelatex", "lualatex"):
        if shutil.which(e):
            return [e, "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", "-output-directory", "{out}", "{tex}"]
    return None


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:50] or "kepler"


@dataclass
class Written:
    tex: Path
    pdf: Path | None
    engine: str
    note: str = ""


def compile_tex(source: str, out_dir: Path, name: str) -> tuple[Path | None, str]:
    cmd = engine()
    if not cmd:
        return None, "no LaTeX engine found (install one with `brew install tectonic`)"
    with tempfile.TemporaryDirectory(prefix="kepler-tex-") as tmp:
        tex = Path(tmp) / f"{name}.tex"
        tex.write_text(source)
        args = [a.replace("{out}", tmp).replace("{tex}", str(tex)) for a in cmd]
        try:
            r = subprocess.run(args, cwd=tmp, capture_output=True, text=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            return None, f"LaTeX took longer than {TIMEOUT}s"
        pdf = Path(tmp) / f"{name}.pdf"
        if r.returncode != 0 or not pdf.exists():
            err = "\n".join(line for line in (r.stdout + r.stderr).splitlines() if line.startswith(("!", "error")))[:400]
            return None, err or "LaTeX failed"
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"{name}.pdf"
        shutil.copyfile(pdf, dest)
        return dest, ""


def write(items: list[Item], title: str = "", out: Path | None = None, pdf: bool = True) -> Written:
    """Write the .tex (and compile the .pdf) into ~/Documents/Kepler (or `out`)."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    name = (out.stem if out else f"{_slug(title or items[0].title)}-{stamp}")
    out_dir = (out.parent if out else docs_dir())
    out_dir.mkdir(parents=True, exist_ok=True)
    source = document(items, title)
    tex_path = out_dir / f"{name}.tex"
    tex_path.write_text(source)
    if not pdf:
        return Written(tex_path, None, "", "LaTeX source only")
    path, err = compile_tex(source, out_dir, name)
    if path:
        return Written(tex_path, path, (engine() or ["?"])[0])
    if "no LaTeX engine" in err:
        return Written(tex_path, None, "", err)
    # the formal layout failed: keep its .tex for debugging, and still give a PDF in the plain layout
    path2, err2 = compile_tex(plain_document(items, title), out_dir, name)
    return Written(tex_path, path2, (engine() or ["?"])[0],
                   f"the formal layout didn't compile ({err.splitlines()[0] if err else 'unknown error'}); wrote a plain PDF instead"
                   if path2 else f"LaTeX failed: {err2 or err}")


def write_answers(questions: list[str], mind, protect=None, classify=None, pdf: bool = True, title: str = "",
                  out: Path | None = None) -> tuple[Written, list[Item]]:
    """Answer each question with Kepler's engines and typeset all of them in one document."""
    items = [from_thought(q, mind.think(q, protect, classify)) for q in questions]
    return write(items, title, out, pdf), items


def summary(w: Written) -> str:
    if w.pdf:
        return f"PDF: {w.pdf}\nLaTeX source: {w.tex}" + (f"\n({w.note})" if w.note else "")
    return f"LaTeX source: {w.tex}\n({w.note})" if w.note else f"LaTeX source: {w.tex}"


def open_file(path: Path) -> None:
    import sys
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    if shutil.which(opener):
        subprocess.Popen([opener, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------- recognising a request for a write-up

WRITE_REQ = re.compile(
    r"^(?:please |can you |could you |kepler,? )*(?:write|make|create|generate|produce|export|give me|typeset|draft|prepare)"
    r"(?: me)?(?: up)?(?: an?| the)?(?: formal| full| rigorous| detailed| complete| proper| latex| pdf| tex)*"
    r" (?:proof|solution|answer|write-?up|document|pdf|report|latex|derivation)s?(?: document| file| pdf)?"
    r"(?: (?:of|for|that|to|showing|on|about))? (.+?)(?:\s+(?:as|in|into|to) (?:an? )?(?:pdf|latex|tex|document|file))?[.?!]?$", re.I)
WRITE_SUFFIX = re.compile(r"^(.+?)[,;]?\s+(?:as|in|into) (?:an? )?(?:pdf|latex|tex)(?: document| file)?[.?!]?$", re.I)


def request(text: str) -> tuple[str, bool] | None:
    """'write a formal proof that 1 + 2 + ... + n = n(n+1)/2 as a pdf' → ('prove that 1 + 2 + ... + n = …', wants_pdf)."""
    t = text.strip()
    tail = re.match(r"^(.+?)\s*/(pdf|tex|latex)\s*$", t, re.I)  # "solve y'' + y = 0 /pdf"
    if tail:
        return tail.group(1).strip(), tail.group(2).lower() == "pdf"
    m = WRITE_REQ.match(t)
    q = None
    if m:
        q = m.group(1)
        if re.match(r"(?:a )?proof\b", t.split(None, 3)[-1] if False else "", re.I):
            pass
        if re.search(r"\bproof\b", t[:m.start(1)], re.I) and not re.match(r"(?:prove|show)\b", q, re.I):
            q = f"prove {'that ' if not q.lower().startswith('that') else ''}{q}"
    else:
        m = WRITE_SUFFIX.match(t)
        if m and not re.match(r"(?:show|open|copy)\b", m.group(1), re.I):
            q = m.group(1)
    if not q:
        return None
    for _ in range(3):
        q = re.sub(r"^(?:the |a |an )?(?:formal |full |complete |detailed |latex |tex )?(?:solution|proof|answer|working|"
                   r"latex|tex|source|code|write-?up)s?(?: source| code)?(?: (?:to|of|for|that|showing))?\s+", "", q.strip(), flags=re.I)
    if not q:
        return None
    wants_pdf = not re.search(r"\b(?:latex|tex) (?:source|code|only)\b|\bas (?:latex|tex)\b", t, re.I)
    return q.strip(), wants_pdf
