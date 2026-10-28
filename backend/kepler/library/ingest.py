"""Feeding the library: Simple English Wikipedia dumps, Open English WordNet, and your own files.

All importers stream (constant memory), commit in batches, report progress through a callback, and can be re-run:
a document is replaced, never duplicated.
"""
import bz2
import csv
import gzip
import html
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from .. import __version__
from . import index

DATASETS = {
    "wikipedia": ("https://dumps.wikimedia.org/simplewiki/latest/simplewiki-latest-pages-articles.xml.bz2",
                  "simplewiki-latest-pages-articles.xml.bz2"),
    "wordnet": ("https://github.com/globalwordnet/english-wordnet/releases/download/2024-edition/english-wordnet-2024.xml.gz",
                "english-wordnet-2024.xml.gz"),
}
WIKI_LICENCE = "CC BY-SA 4.0 (Wikipedia contributors)"
WORDNET_LICENCE = "CC BY 4.0 (Open English WordNet)"
MAX_WORDS = 110   # passage size: about one paragraph


def dataset_path(name: str) -> Path:
    from .. import device
    return device.HOME / "datasets" / DATASETS[name][1]


def download(name: str, progress=None) -> Path:
    """Download a dataset into ~/.kepler/datasets (resumable)."""
    import httpx
    url, fname = DATASETS[name]
    dest = dataset_path(name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    headers = {"User-Agent": f"Kepler/{__version__} (self-hosted metric watchdog; library import)"}
    if have:
        headers["Range"] = f"bytes={have}-"
    with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=60) as r:
        if r.status_code == 416:  # already complete
            part.rename(dest)
            return dest
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0)) + have
        with open(part, "ab" if have and r.status_code == 206 else "wb") as f:
            done = have if r.status_code == 206 else 0
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(f"downloading {fname}: {done / 1e6:,.0f} / {total / 1e6:,.0f} MB")
    part.rename(dest)
    return dest


# ---------------------------------------------------------------- wikipedia

SKIP_TITLE = re.compile(r"^(?:list of|lists of|index of|timeline of|glossary of)\b|\(disambiguation\)$", re.I)
SKIP_SECTION = re.compile(r"^(?:references|notes|other websites|external links|see also|sources|further reading|related pages|bibliography|gallery)$", re.I)


def _strip_nested(text: str, open_: str, close: str) -> str:
    """Remove nested {{ … }} / {| … |} blocks (templates and tables)."""
    out, depth, i = [], 0, 0
    lo, lc = len(open_), len(close)
    while i < len(text):
        if text.startswith(open_, i):
            depth += 1
            i += lo
        elif depth and text.startswith(close, i):
            depth -= 1
            i += lc
        else:
            if not depth:
                out.append(text[i])
            i += 1
    return "".join(out)


CONVERT_UNIT = {"C": "°C", "F": "°F", "K": "K", "sqmi": "square miles", "sqkm": "km2", "km2": "km2", "mi2": "square miles",
                "ha": "hectares", "kmh": "km/h", "km/h": "km/h", "mph": "mph", "m/s": "m/s", "ftm": "fathoms"}


def _measurements(t: str) -> str:
    """Keep the numbers inside measurement templates: {{convert|8848|m|ft}} → '8848 m', {{formatnum:123}} → '123'."""
    def conv(m):
        args = [a.strip() for a in m.group(1).split("|")]
        if not args or not re.fullmatch(r"-?[\d.,]+", args[0]):
            return ""
        if len(args) >= 4 and args[1] in ("-", "to", "and", "–", "or", "x", "by") and re.fullmatch(r"-?[\d.,]+", args[2]):
            num, unit = f"{args[0]}–{args[2]}", args[3]
        else:
            num, unit = args[0], args[1] if len(args) > 1 else ""
        unit = CONVERT_UNIT.get(unit, unit)
        return f"{num} {unit}".strip() if re.fullmatch(r"[A-Za-z°/²0-9 ]{0,20}", unit) else num
    t = re.sub(r"\{\{\s*(?:convert|cvt)\s*\|([^{}]*)\}\}", conv, t, flags=re.I)
    t = re.sub(r"\{\{\s*formatnum\s*:\s*([\d.,]+)\s*\}\}", r"\1", t, flags=re.I)
    t = re.sub(r"\{\{\s*val\s*\|\s*([^{}|]+)(?:\|[^{}]*)?\}\}", r"\1", t, flags=re.I)
    t = re.sub(r"\{\{\s*nowrap\s*\|((?:[^{}]|\{\{[^{}]*\}\})*)\}\}", r"\1", t, flags=re.I)  # may hold links with "|"
    return t


MONTHS = "January February March April May June July August September October November December".split()
INFOBOX_FIELDS = [
    (r"population_(?:estimate|census|total)|population|pop", "population", ""),
    (r"area_(?:total_)?km2|area_km2", "area", "km2"),
    (r"area_(?:total_)?sq_mi", "area", "square miles"),
    (r"elevation_m|height_m|peak_elevation_m|elevation|height", "height", "m"),
    (r"length_km|length", "length", "km"),
    (r"depth_m|max_depth", "depth", "m"),
    (r"capital", "capital", ""), (r"largest_city", "largest city", ""), (r"currency", "currency", ""),
    (r"official_languages|languages|common_languages", "language", ""),
    (r"birth_date", "birth date", ""), (r"death_date", "death date", ""), (r"birth_place", "birthplace", ""),
    (r"founded|established|establishment|formation|established_date1|foundation", "founding date", ""),
    (r"author", "author", ""), (r"director", "director", ""), (r"genre", "genre", ""),
    (r"discoverer|discovered_by|inventor", "discoverer", ""), (r"mass", "mass", ""), (r"mean_diameter|diameter", "diameter", ""),
]


def _infobox_block(wt: str) -> str:
    i = wt.find("{{Infobox")
    if i < 0:
        i = wt.find("{{infobox")
    if i < 0:
        return ""
    depth, j = 0, i
    while j < len(wt) - 1:
        if wt.startswith("{{", j):
            depth += 1
            j += 2
        elif wt.startswith("}}", j):
            depth -= 1
            j += 2
            if depth == 0:
                return wt[i + 2:j - 2]
        else:
            j += 1
    return ""


def _params(block: str) -> dict:
    out, depth, cur = {}, 0, []
    fields = []
    k = 0
    while k < len(block):
        two = block[k:k + 2]
        if two in ("{{", "[["):
            depth += 1
            cur.append(two)
            k += 2
            continue
        if two in ("}}", "]]"):
            depth -= 1
            cur.append(two)
            k += 2
            continue
        if block[k] == "|" and depth == 0:
            fields.append("".join(cur))
            cur = []
        else:
            cur.append(block[k])
        k += 1
    fields.append("".join(cur))
    for f in fields[1:]:
        if "=" in f:
            key, val = f.split("=", 1)
            out[key.strip().lower()] = val.strip()
    return out


def _date_template(m) -> str:
    nums = [a.strip() for a in m.group(1).split("|") if re.fullmatch(r"\s*\d{1,4}\s*", a)]
    if len(nums) >= 3 and 1 <= int(nums[1]) <= 12:
        return f"{int(nums[2])} {MONTHS[int(nums[1]) - 1]} {nums[0]}"
    return nums[0] if nums else ""


def _clean_value(v: str) -> str:
    v = re.sub(r"<!--.*?-->", "", v, flags=re.S)
    v = re.sub(r"<ref[^>/]*/>|<ref[^>]*>.*?</ref>", "", v, flags=re.S)
    v = re.sub(r"\{\{\s*(?:birth|death|start|end|film)[ _]date(?: and age)?\s*\|([^{}]*)\}\}", _date_template, v, flags=re.I)
    v = _measurements(v)
    v = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", v)   # links first, so their "|" can't confuse templates
    v = re.sub(r"\[\[([^\]]*)\]\]", r"\1", v)
    v = re.sub(r"\{\{\s*(?:plainlist|plain list|ubl|unbulleted list|hlist|flatlist|nowrap)\s*\|", "{{§", v, flags=re.I)
    while True:  # unwrap list templates (marked §), drop every other template
        new = re.sub(r"\{\{§([^{}]*)\}\}", lambda m: m.group(1).replace("|", ", "), v)
        if new == v:
            new = _strip_nested(v, "{{", "}}")
        if new == v:
            break
        v = new
    v = re.sub(r"<br\s*/?>|\n\s*\*\s*", ", ", v)
    v = html.unescape(re.sub(r"<[^>]+>|'{2,}", "", v))
    v = re.sub(r"\s+", " ", v).strip(" ,;*\\")
    return "" if v.lower() in ("capital", "none", "n/a", "unknown", "-") else v[:120]


def infobox_facts(title: str, wt: str) -> str:
    """The infobox as plain sentences, one fact each: "Australia's capital is Canberra." """
    block = _infobox_block(wt)
    if not block:
        return ""
    params = _params(block)
    said, sentences = set(), []
    for pat, label, unit in INFOBOX_FIELDS:
        if label in said:
            continue
        for key, raw in params.items():
            if not re.fullmatch(pat, key):
                continue
            v = _clean_value(raw)
            if not v or len(v) < 1 or re.fullmatch(r"[\W_]+", v):
                continue
            if unit and re.fullmatch(r"[\d.,]+", v):
                v = f"{v} {unit}"
            owner = f"{title}'" if title.endswith("s") else f"{title}'s"
            sentences.append(f"{owner} {label} is {v}.")
            said.add(label)
            break
    return (" ".join(sentences)) if sentences else ""


def clean_wikitext(wt: str) -> list[str]:
    """Wiki markup → plain paragraphs (sections like References dropped)."""
    t = re.sub(r"<!--.*?-->", "", wt, flags=re.S)
    t = _measurements(t)
    t = re.sub(r"<ref[^>/]*/>", "", t)
    t = re.sub(r"<ref[^>]*>.*?</ref>", "", t, flags=re.S)
    t = _strip_nested(t, "{{", "}}")
    t = _strip_nested(t, "{|", "|}")
    t = re.sub(r"\[\[(?:File|Image|Category|Media|Datei|Fichier):(?:[^\[\]]|\[\[[^\]]*\]\])*\]\]", "", t, flags=re.I)
    t = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"\[\[([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"\[https?://\S+ ([^\]]*)\]", r"\1", t)
    t = re.sub(r"\[https?://\S+\]", "", t)
    t = re.sub(r"'{2,}", "", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t)
    paras, skipping = [], False
    for block in re.split(r"\n\s*\n", t):
        lines = []
        for line in block.split("\n"):
            line = line.strip()
            h = re.fullmatch(r"=+\s*(.*?)\s*=+", line)
            if h:
                skipping = bool(SKIP_SECTION.match(h.group(1)))
                continue
            if skipping or not line or line[0] in "*#:;|!" or line.startswith("__"):
                continue
            lines.append(line)
        p = re.sub(r"\s+", " ", " ".join(lines)).strip()
        p = re.sub(r"\(\s*(?:(?:or|and|;|,|:|-|–|/)\s*)*\)", "", p)  # "( or ; )" left by removed pronunciation templates
        p = re.sub(r"\s+([,.;:])", r"\1", re.sub(r"\s{2,}", " ", p))
        if len(p) >= 40 and not p.lower().startswith(("redirect", "#redirect")):
            paras.extend(_chunk(p))
    return paras


def _chunk(p: str) -> list[str]:
    words = p.split()
    if len(words) <= MAX_WORDS * 1.4:
        return [p]
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", p)
    out, cur = [], []
    for s in sents:
        if cur and len(" ".join(cur + [s]).split()) > MAX_WORDS:
            out.append(" ".join(cur))
            cur = []
        cur.append(s)
    if cur:
        out.append(" ".join(cur))
    return out


def import_wikipedia(dump: Path, limit: int | None = None, progress=None) -> int:
    """Stream a pages-articles .xml.bz2 dump into the library. Returns the number of articles imported."""
    opener = bz2.open if str(dump).endswith(".bz2") else open
    n, seen, t0 = 0, 0, time.time()
    batch = 0
    conn = index.connect(write=True)
    try:
        with opener(dump, "rb") as f:
            ns = ""
            for event, el in ET.iterparse(f, events=("start", "end")):
                if event == "start" and not ns and el.tag.startswith("{"):
                    ns = el.tag.split("}")[0] + "}"
                if event != "end" or el.tag != f"{ns}page":
                    continue
                seen += 1
                title = el.findtext(f"{ns}title") or ""
                pns = el.findtext(f"{ns}ns")
                redirect = el.find(f"{ns}redirect") is not None
                text = el.findtext(f"{ns}revision/{ns}text") or ""
                el.clear()
                if pns != "0" or redirect or not text or SKIP_TITLE.search(title):
                    continue
                paras = clean_wikitext(text)
                if not paras:
                    continue
                facts = infobox_facts(title, text)
                if facts:
                    paras.insert(1, facts)  # right after the lead, so lookups and "tell me more" see it early
                url = "https://simple.wikipedia.org/wiki/" + title.replace(" ", "_")
                if index.add_doc(conn, "wikipedia", title, title, paras, url, WIKI_LICENCE):
                    n += 1
                    batch += 1
                if batch >= 2000:
                    conn.commit()
                    batch = 0
                    if progress:
                        rate = n / max(time.time() - t0, 1e-6)
                        progress(f"wikipedia: {n:,} articles ({seen:,} pages read, {rate:,.0f}/s)")
                if limit and n >= limit:
                    break
        conn.commit()
        conn.execute("INSERT INTO passages_fts(passages_fts) VALUES ('optimize')")
        conn.commit()
    finally:
        conn.close()
    if progress:
        progress(f"wikipedia: {n:,} articles imported in {time.time() - t0:,.0f}s")
    return n


# ---------------------------------------------------------------- wordnet

POS = {"n": "noun", "v": "verb", "a": "adjective", "s": "adjective", "r": "adverb"}


def import_wordnet(xml_gz: Path, progress=None) -> int:
    """Open English WordNet (LMF XML) → the words table: one row per word sense."""
    entries: list[tuple[str, str, list[str]]] = []   # (lemma, pos, [synset ids])
    synsets: dict[str, tuple[str, list[str], list[str]]] = {}  # id → (definition, examples, member entry ids)
    entry_lemma: dict[str, str] = {}
    cur_lemma, cur_pos, cur_senses, cur_id = None, None, [], None
    with gzip.open(xml_gz, "rb") as f:
        for event, el in ET.iterparse(f, events=("end",)):
            tag = el.tag
            if tag == "Lemma":
                cur_lemma, cur_pos = el.get("writtenForm"), el.get("partOfSpeech")
            elif tag == "Sense":
                cur_senses.append(el.get("synset"))
            elif tag == "LexicalEntry":
                cur_id = el.get("id")
                if cur_lemma:
                    entries.append((cur_lemma, cur_pos, cur_senses))
                    entry_lemma[cur_id] = cur_lemma
                cur_lemma, cur_pos, cur_senses = None, None, []
                el.clear()
            elif tag == "Synset":
                d = el.findtext("Definition") or ""
                ex = [e.text or "" for e in el.findall("Example")][:2]
                synsets[el.get("id")] = (d, ex, (el.get("members") or "").split())
                el.clear()
    conn = index.connect(write=True)
    n = 0
    try:
        conn.execute("DELETE FROM words WHERE source = 'wordnet'")
        rows = []
        for lemma, pos, sids in entries:
            for sid in sids:
                if sid not in synsets:
                    continue
                d, ex, members = synsets[sid]
                syn = [entry_lemma[m] for m in members if m in entry_lemma and entry_lemma[m] != lemma][:8]
                rows.append((lemma.lower(), POS.get(pos, pos), d, " | ".join(ex), ", ".join(syn)))
            if len(rows) >= 20000:
                conn.executemany("INSERT INTO words(lemma, pos, definition, examples, synonyms) VALUES (?, ?, ?, ?, ?)", rows)
                n += len(rows)
                rows = []
                if progress:
                    progress(f"wordnet: {n:,} word senses")
        if rows:
            conn.executemany("INSERT INTO words(lemma, pos, definition, examples, synonyms) VALUES (?, ?, ?, ?, ?)", rows)
            n += len(rows)
        conn.commit()
    finally:
        conn.close()
    if progress:
        progress(f"wordnet: {n:,} word senses from {len(entries):,} words")
    return n


# ---------------------------------------------------------------- your files

TEXT_EXT = {".txt", ".md", ".markdown", ".rst", ".text", ".log", ".org"}
MAX_FILE_MB = 25


def _file_paragraphs(p: Path) -> list[str]:
    ext = p.suffix.lower()
    if ext in TEXT_EXT:
        raw = p.read_text(errors="ignore")
        raw = re.sub(r"^#+\s*", "", raw, flags=re.M)  # markdown headings become plain lines
        return [x for b in re.split(r"\n\s*\n", raw) for x in _chunk(re.sub(r"\s+", " ", b).strip()) if len(x) >= 20]
    if ext in (".html", ".htm"):
        raw = re.sub(r"(?is)<(script|style).*?</\1>", "", p.read_text(errors="ignore"))
        raw = html.unescape(re.sub(r"<[^>]+>", "\n", raw))
        return [x for b in re.split(r"\n\s*\n", raw) for x in _chunk(re.sub(r"\s+", " ", b).strip()) if len(x) >= 20]
    if ext == ".csv":
        out = []
        with open(p, newline="", errors="ignore") as f:
            reader = csv.reader(f)
            header = next(reader, [])
            for i, row in enumerate(reader):
                if i >= 20000:
                    break
                out.append("; ".join(f"{h}: {v}" for h, v in zip(header, row) if v))
        return [r for r in out if r]
    if ext == ".json":
        data = json.loads(p.read_text(errors="ignore"))
        items = data if isinstance(data, list) else [data]
        return [json.dumps(x, ensure_ascii=False)[:2000] for x in items[:20000]]
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise RuntimeError("reading PDFs needs pypdf: pip install pypdf") from None
        text = "\n\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages[:500])
        return [x for b in re.split(r"\n\s*\n", text) for x in _chunk(re.sub(r"\s+", " ", b).strip()) if len(x) >= 20]
    if ext == ".docx":
        import zipfile
        with zipfile.ZipFile(p) as z:
            xml = z.read("word/document.xml").decode(errors="ignore")
        paras = [re.sub(r"<[^>]+>", "", m) for m in re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S)]
        return [x for b in paras for x in _chunk(html.unescape(b).strip()) if len(x) >= 20]
    return []


SUPPORTED = TEXT_EXT | {".html", ".htm", ".csv", ".json", ".pdf", ".docx"}


def import_files(root: Path, progress=None) -> tuple[int, list[str]]:
    """Import a file or every supported file under a folder. Returns (files imported, problems)."""
    root = root.expanduser().resolve()
    files = [root] if root.is_file() else [p for p in sorted(root.rglob("*"))
                                           if p.is_file() and p.suffix.lower() in SUPPORTED
                                           and not any(part.startswith(".") for part in p.relative_to(root).parts)]
    n, problems = 0, []
    conn = index.connect(write=True)
    try:
        for i, p in enumerate(files):
            try:
                if p.stat().st_size > MAX_FILE_MB * 1e6:
                    problems.append(f"{p.name}: larger than {MAX_FILE_MB} MB, skipped")
                    continue
                paras = _file_paragraphs(p)
            except (OSError, UnicodeError, ValueError, RuntimeError, KeyError) as e:
                problems.append(f"{p.name}: {e}")
                continue
            title = p.stem.replace("_", " ").replace("-", " ")
            if index.add_doc(conn, f"files:{root}", str(p), title, paras, p.as_uri()):
                n += 1
            if progress and i % 25 == 0:
                progress(f"files: {i + 1:,} / {len(files):,}")
        conn.commit()
    finally:
        conn.close()
    return n, problems

