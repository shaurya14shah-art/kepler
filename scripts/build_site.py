"""Build the product website's legal pages: legal/*.md → site/legal/*.html (same look as site/index.html).

Run from the repo root: python3 scripts/build_site.py   (`make site`). The site has no build step otherwise: it's
plain HTML and CSS you can put on any static host. Placeholders like {{COMPANY}} are left as they are, so an
unfilled draft is obvious; set them in legal/*.md (and in site/index.html's footer) before publishing.
"""
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = {"EULA": "eula", "TERMS": "terms", "PRIVACY": "privacy", "REFUND": "refund", "SHIPPING": "shipping", "CONTACT": "contact"}

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} · Kepler</title>
  <link rel="stylesheet" href="../style.css">
</head>
<body>
<header class="top"><div class="wrap"><a class="brand" href="../index.html">← Kepler</a></div></header>
<main class="doc">
{body}
</main>
<footer><div class="wrap"><nav>{nav}</nav></div></footer>
</body>
</html>
"""


def inline(text: str) -> str:
    t = html.escape(text, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\*)", r"<em>\1</em>", t)

    def link(m):
        label, url = m.group(1), m.group(2)
        stem = Path(url).stem.upper()
        if url.endswith(".md") and stem in PAGES:
            url = f"{PAGES[stem]}.html"
        elif url.endswith(".md"):
            return label  # links to repo files that aren't on the site
        return f'<a href="{html.escape(url)}">{label}</a>'
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, t)


def to_html(md: str) -> tuple[str, str]:
    lines, out, title = md.splitlines(), [], "Kepler"
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("# "):
            title = line[2:].strip()
            out.append(f"<h1>{inline(title)}</h1>")
        elif line.startswith("## "):
            out.append(f"<h2>{inline(line[3:].strip())}</h2>")
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            head, *body = rows
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body) + "</tbody></table>")
            continue
        elif re.match(r"\s*[-*] ", line):
            items = []
            while i < len(lines) and (re.match(r"\s*[-*] ", lines[i]) or (lines[i].startswith("  ") and lines[i].strip())):
                if re.match(r"\s*[-*] ", lines[i]):
                    items.append(re.sub(r"^\s*[-*] ", "", lines[i]))
                else:
                    items[-1] += " " + lines[i].strip()
                i += 1
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
            continue
        else:
            para = []
            while i < len(lines) and lines[i].strip() and not re.match(r"(#|\||\s*[-*] )", lines[i]):
                para.append(lines[i].strip())
                i += 1
            out.append("<p>" + "<br>".join(inline(p) for p in para) + "</p>" if any(p.endswith("  ") for p in para)
                       else "<p>" + inline(" ".join(para)) + "</p>")
            continue
        i += 1
    return title, "\n".join(out)


def main() -> None:
    dest = ROOT / "site" / "legal"
    dest.mkdir(parents=True, exist_ok=True)
    nav = " ".join(f'<a href="{slug}.html">{name.title() if name != "EULA" else "Licence"}</a>' for name, slug in PAGES.items())
    for name, slug in PAGES.items():
        title, body = to_html((ROOT / "legal" / f"{name}.md").read_text())
        (dest / f"{slug}.html").write_text(TEMPLATE.format(title=html.escape(title), body=body, nav=nav))
    left = sorted(set(re.findall(r"\{\{[A-Z_]+\}\}", "".join(p.read_text() for p in dest.glob("*.html")))))
    print(f"built {len(PAGES)} legal pages in site/legal/" + (f"; placeholders to fill: {', '.join(left)}" if left else ""))


if __name__ == "__main__":
    main()
