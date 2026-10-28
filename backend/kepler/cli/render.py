"""Rich renderables for Kepler objects. Used by the one-shot CLI, the chat bot and the full-screen TUI."""
import math
from datetime import datetime

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

ACCENT = "#8b7fff"
TIER_GLYPH = {"orbit": "◯", "area": "◐", "time": "◉"}
SEV = {"critical": "bold red", "high": "bold dark_orange", "medium": "bold yellow"}
VERDICT = {"normal": ("NORMAL", "black on green"), "watch": ("WATCH", "black on yellow"),
           "anomaly": ("ANOMALY", "white on red")}
LOGO = r"""
   _  __          _
  | |/ /___ _ __ | | ___ _ __
  | ' // _ \ '_ \| |/ _ \ '__|
  | . \  __/ |_) | |  __/ |
  |_|\_\___| .__/|_|\___|_|
           |_|
"""


# ---------------------------------------------------------------- formatting

def num(x) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "–"
    a = abs(x)
    return f"{x:,.0f}" if a >= 100 else f"{x:.1f}" if a >= 10 else f"{x:.2f}".rstrip("0").rstrip(".")


def pct(x) -> str:
    if x is None or not math.isfinite(x):
        return "–"
    return f"{x / 100 + 1:.1f}×" if x >= 1000 else f"{x:+.0f}%"


def change_text(d: dict) -> str:
    """An incident's change, or 'no data since 14:05' for a metric that stopped reporting."""
    if d.get("kind") == "no_data":
        return f"no data since {hhmm(d.get('silent_since') or d['started_at'])}"
    return f"{'▲' if d['direction'] == 'spike' else '▼'} {pct(d.get('change_pct'))}"


def hhmm(ts) -> str:
    return datetime.fromtimestamp(ts).strftime("%a %H:%M")


def mins(a, b) -> str:
    m = int((b - a) / 60) + 5
    return f"{m} min" if m < 60 else f"{m // 60} h {m % 60} min"


def ago(ts) -> str:
    d = max(0, datetime.now().timestamp() - ts)
    return "just now" if d < 90 else f"{int(d / 60)} min ago" if d < 3600 else f"{int(d / 3600)} h ago" if d < 86400 else f"{int(d / 86400)} d ago"


def bar(p: float | None, n: int = 20, style: str = "cyan") -> Text:
    if p is None or not math.isfinite(p):
        return Text("·" * n, style="grey50")
    p = max(0.0, min(1.0, p))
    full = int(p * n)
    rem = p * n - full
    frac = "▏▎▍▌▋▊▉"[min(6, int(rem * 7))] if full < n and rem >= 1 / 7 else ""
    t = Text("█" * full + frac, style=style)
    t.append("░" * (n - full - len(frac)), style="grey30")
    return t


def spark(values: list, n: int = 48) -> str:
    vals = [v for v in values if v is not None and math.isfinite(v)]
    if not vals:
        return ""
    if len(values) > n:
        step = len(values) / n
        values = [values[int(i * step)] for i in range(n)]
    lo, hi = min(vals), max(vals)
    ticks = "▁▂▃▄▅▆▇█"
    return "".join(" " if v is None else ticks[0 if hi == lo else int((v - lo) / (hi - lo) * 7)] for v in values)


def where_text(where: list[dict]) -> str:
    w = [x for x in where if x["dimension"] != "*"]
    return ", ".join(f"{x['dimension']}={x['value']}" for x in w) or "all segments"


def _kv_table() -> Table:
    t = Table.grid(padding=(0, 2))
    t.add_column(style="grey62", no_wrap=True)
    t.add_column()
    return t


# ---------------------------------------------------------------- decisions

def incident_panel(d: dict, points: list | None = None, chart_width: int = 70) -> Panel:
    sev = SEV.get(d["severity"], "bold")
    t = _kv_table()
    t.add_row("metric", Text(d["metric"], style="bold") + (Text(f"  slice {d['slice']}", style="grey50") if d.get("slice") else ""))
    t.add_row("confidence", bar(d["confidence"]) + Text(f"  {d['confidence']:.2f}", style="bold"))
    t.add_row("observed", Text.assemble((num(d["observed"]), "bold"), f"   expected {num(d['expected'])}  ",
                                        (f"(normal {num(d['expected_range'][0])} – {num(d['expected_range'][1])})", "grey50"),
                                        "   ", (change_text(d), sev), f"   z {d['z_score']:.1f}"))
    for i, w in enumerate(d["where"]):
        label = "all segments" if w["dimension"] == "*" else f"{w['dimension']}={w['value']}"
        share = min(w.get("share_of_change") or 0, 1.0)
        t.add_row("where" if i == 0 else "", Text.assemble((label.ljust(20), f"bold {ACCENT}"), " ", bar(share, 14, ACCENT),
                                                          f" {share:>4.0%} of change  ", (pct(w.get("change_pct")), "bold")))
    t.add_row("when", f"{hhmm(d['started_at'])} → {hhmm(d['last_seen_at'])}  ({mins(d['started_at'], d['last_seen_at'])})")
    if points:
        t.add_row("shape", Text(spark([p.get("value") for p in points], chart_width - 14), style="cyan"))
    m = d.get("model") or {}
    t.add_row("baseline", Text(m.get("baseline", "–"), style="grey50"))
    if m.get("prior") is not None:
        learned = f" · learned {m['learned']:.2f} at weight {m.get('weight', 0):.2f}" if m.get("learned") is not None else ""
        t.add_row("filter", Text(f"prior {m['prior']:.2f}{learned}", style="grey50"))
    if d.get("feedback") is not None:
        t.add_row("label", "👍 real incident" if d["feedback"] == 1 else "👎 false alarm")
    rs = d.get("reasoning")
    if rs:
        if rs.get("impact_text"):
            t.add_row("impact", Text(rs["impact_text"], style="bold red"))
        for i, step in enumerate(rs.get("steps", []), 1):
            t.add_row("reasoning" if i == 1 else "", Text(f"{i}. {step}", style="grey70"))
    title = Text.assemble((" ANOMALY ", "white on red"), "  ", (d["severity"], sev), f" · {d['direction']} · ",
                          (d["status"], "red" if d["status"] == "open" else "green"),
                          (f"  {TIER_GLYPH.get(d.get('tier'), '')} {d['tier'].title()}" if d.get("tier") else "", ACCENT))
    return Panel(t, title=title, title_align="left", subtitle=Text(f"#{d['incident_id']}", style="grey50"),
                 subtitle_align="right", border_style="red" if d["status"] == "open" else "grey35", box=box.ROUNDED)


def simple_decision_panel(d: dict) -> Panel:
    word, style = VERDICT[d["decision"]]
    t = _kv_table()
    p = d.get("anomaly_probability")
    t.add_row("anomaly p", bar(p) + Text(f"  {'–' if p is None else f'{p:.2f}'}", style="bold"))
    rng = d.get("expected_range") or [None, None]
    t.add_row("observed", Text.assemble((num(d["observed"]), "bold"), f"   expected {num(d['expected'])}  ",
                                        (f"(normal {num(rng[0])} – {num(rng[1])})", "grey50"),
                                        f"   {pct(d.get('change_pct'))}   z {num(d['z_score'])}"))
    t.add_row("baseline", Text(str(d.get("model", "")), style="grey50"))
    if d["decision"] == "watch":
        t.add_row("note", Text("deviating, but not (yet) confident enough to alert", style="yellow"))
    title = Text.assemble((f" {word} ", style), "  ", (d["metric"], "bold"), (f"   at {hhmm(d['at'])}", "grey50"))
    return Panel(t, title=title, title_align="left", border_style="green" if word == "NORMAL" else "yellow", box=box.ROUNDED)


def decision_panel(res: dict) -> Group | Panel:
    """Render a /api/v1/decision response (normal / watch / anomaly)."""
    if res["decision"] == "anomaly":
        return Group(*[incident_panel(i) for i in res["incidents"]])
    return simple_decision_panel(res)


# ---------------------------------------------------------------- tables

def status_table(rows: list[dict], compact: bool = False) -> Table:
    """One line per metric. compact=True fits narrow panels (TUI panes, chat)."""
    t = Table(box=box.SIMPLE_HEAD, header_style="grey62", pad_edge=False, expand=True)
    has_where = any(r.get("where") for r in rows)
    t.add_column("metric", style="bold", no_wrap=True, overflow="ellipsis", ratio=3)
    t.add_column("state", no_wrap=True)
    t.add_column("p(anomaly)", no_wrap=True)
    t.add_column("now", justify="right", no_wrap=True)
    t.add_column("exp" if compact else "expected", justify="right", no_wrap=True)
    t.add_column("Δ" if compact else "change", justify="right", no_wrap=True)
    if has_where:
        t.add_column("where", style=ACCENT, no_wrap=True, overflow="ellipsis", ratio=2)
    short = {"normal": ("● ok", "green"), "watch": ("● watch", "yellow"), "anomaly": ("● ANOMALY", "bold red")}
    for r in rows:
        p = r.get("p")
        if compact:
            word, style = short[r["decision"]]
            state = Text(word, style=style)
        else:
            word, style = VERDICT[r["decision"]]
            state = Text(f" {word} ", style=style)
        cells = [r["metric"], state, bar(p, 6 if compact else 14) + Text(f" {'–' if p is None else f'{p:.2f}'}"),
                 num(r.get("observed")), num(r.get("expected")), pct(r.get("change_pct"))]
        if has_where:
            cells.append(where_text(r["where"]) if r.get("where") else "")
        t.add_row(*cells)
    return t


def incidents_table(incs: list[dict]) -> Table:
    t = Table(box=box.SIMPLE_HEAD, header_style="grey62", pad_edge=False, expand=True)
    for col, kw in (("#", {"justify": "right", "style": "grey62"}), ("", {}), ("severity", {}), ("metric", {"no_wrap": True}),
                    ("change", {"justify": "right"}), ("confidence", {"no_wrap": True}), ("started", {"no_wrap": True}),
                    ("for", {"no_wrap": True}), ("where", {"style": ACCENT}), ("label", {})):
        t.add_column(col, **kw)
    for d in incs:
        t.add_row(str(d["incident_id"]), Text("●", style="red") if d["status"] == "open" else Text("○", style="grey50"),
                  Text(d["severity"], style=SEV[d["severity"]]), d["metric"], change_text(d),
                  bar(d["confidence"], 10) + Text(f" {d['confidence']:.2f}"), hhmm(d["started_at"]),
                  mins(d["started_at"], d["last_seen_at"]), where_text(d["where"]),
                  {1: "👍", 0: "👎"}.get(d.get("feedback"), ""))
    return t


def metric_chart(points: list[dict], width: int = 80, height: int = 16, title: str = "") -> Text:
    """Actual vs expected with the normal band, drawn with braille characters (sparkline fallback)."""
    pts = [p for p in points if p.get("ts")]
    if not any(p.get("value") is not None for p in pts):
        return Text("no data in this range", style="grey50")
    try:
        return _plotext_chart(pts, width, height, title)
    except Exception:  # plotext can choke on degenerate series; never let a chart take down a reply
        return Text.assemble((title + "\n", "bold") if title else "", (spark([p.get("value") for p in pts], width), "cyan"))


def _finite(xs):
    return any(x == x and x not in (float("inf"), float("-inf")) for x in xs)


def _plotext_chart(pts: list[dict], width: int, height: int, title: str) -> Text:
    import plotext as plt
    xs = list(range(len(pts)))
    plt.clear_figure()
    plt.plotsize(max(30, width), max(8, height))
    plt.theme("clear")
    plt.frame(False)
    lower = [p["lower"] if p.get("lower") is not None else float("nan") for p in pts]
    upper = [p["upper"] if p.get("upper") is not None else float("nan") for p in pts]
    if _finite(upper):
        plt.plot(xs, upper, color="gray", marker="braille")
    if _finite(lower) and max((v for v in lower if v == v), default=0) > 0:  # a band clipped at zero is a flat line
        plt.plot(xs, lower, color="gray", marker="braille")
    expected = [p["expected"] if p.get("expected") is not None else float("nan") for p in pts]
    if _finite(expected):
        plt.plot(xs, expected, color="magenta", marker="braille", label="expected")
    plt.plot(xs, [p["value"] if p.get("value") is not None else float("nan") for p in pts], color="cyan",
             marker="braille", label="actual")
    n = min(6, len(pts))
    idx = [int(i * (len(pts) - 1) / max(1, n - 1)) for i in range(n)]
    span_h = (pts[-1]["ts"] - pts[0]["ts"]) / 3600
    fmt = "%a %H:%M" if span_h > 30 else "%H:%M"
    plt.xticks(idx, [datetime.fromtimestamp(pts[i]["ts"]).strftime(fmt) for i in idx])
    if title:
        plt.title(title)
    return Text.from_ansi(plt.build())


def table(columns: list[str], rows: list[list], title: str | None = None) -> Table:
    t = Table(box=box.SIMPLE_HEAD, header_style="grey62", title=title, title_justify="left", title_style="bold",
              pad_edge=False, expand=True)
    for c in columns:
        t.add_column(c)
    for r in rows:
        t.add_row(*[x if isinstance(x, Text) else Text(str(x)) for x in r])
    return t


def welcome(server: str, ok: bool, info: dict) -> Panel:
    left = Text(LOGO.strip("\n"), style=f"bold {ACCENT}")
    right = _kv_table()
    right.add_row("server", Text(server, style="bold") + Text("  ● connected" if ok else "  ● unreachable",
                                                               style="green" if ok else "red"))
    for k, v in info.items():
        right.add_row(k, v if isinstance(v, Text) else Text(str(v)))
    grid = Table.grid(padding=(0, 4))
    grid.add_row(left, right)
    return Panel(grid, title=Text(" Kepler · metric watchdog ", style=f"bold {ACCENT}"), border_style=ACCENT,
                 box=box.ROUNDED, padding=(1, 2))


def tiers_table(data: dict) -> Table:
    """Orbit / Area / Time with measured benchmark, worst → best."""
    t = Table(box=box.SIMPLE_HEAD, header_style="grey62", pad_edge=False, expand=True)
    priced = any("price_preview" in x for x in data["tiers"])
    for col, kw in (("model", {"no_wrap": True}), ("Kepler's", {"style": "grey62", "no_wrap": True}), ("caught", {"justify": "right"}),
                    ("hard cases", {"justify": "right"}), ("noise/wk", {"justify": "right"}), ("ms/check", {"justify": "right"}),
                    ("reasoning", {}), *([("price (preview)", {"no_wrap": True})] if priced else []), ("metrics", {"justify": "right"})):
        t.add_column(col, **kw)
    for x in sorted(data["tiers"], key=lambda x: -x["rank"]):
        b = x.get("benchmark") or {}
        name = Text(f"{TIER_GLYPH[x['id']]} {x['name']}", style=f"bold {ACCENT}" if x["id"] == data["default"] else "bold")
        if x["id"] == data["default"]:
            name.append("  default", style="grey50")
        t.add_row(name, x["law"].split(":")[0].replace("Kepler's ", ""), f"{b.get('caught', '–')}/{b.get('real', '–')}",
                  f"{b.get('hard_cases_caught', '–')}/{b.get('hard_cases', '–')}", str(b.get("noise_per_week", "–")),
                  f"{b['eval_ms_per_metric']:.0f}" if b else "–", ["", "deepest", "solid", "basic"][x["rank"]],
                  *([x.get("price_preview", "")] if priced else []), str(x["metrics"]))
    return t


def compare_table(res: dict) -> Table:
    t = Table(box=box.SIMPLE_HEAD, header_style="grey62", pad_edge=False, expand=True,
              title=f"{res['metric']}: all three models on the latest data", title_justify="left", title_style="bold")
    priced = any("price_preview" in x for x in res["tiers"])
    for col in ("model", "verdict", "most unusual series", "confidence", "series", "time", *(["price (preview)"] if priced else []), ""):
        t.add_column(col)
    for x in res["tiers"]:
        top = x.get("top") or {}
        t.add_row(Text(f"{TIER_GLYPH[x['tier']]} {x['name']}", style="bold"),
                  Text(x["verdict"].upper(), style="bold red" if x["verdict"] == "anomaly" else "green"),
                  top.get("series", "–"), f"{top['confidence']:.2f}" if top else "–", str(x["series_watched"]),
                  f"{x['ms']:.0f} ms", *([x.get("price_preview", "")] if priced else []),
                  Text("in use", style=ACCENT) if res["current"] == x["tier"] else "")
    return t
