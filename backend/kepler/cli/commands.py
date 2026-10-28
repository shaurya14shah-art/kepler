"""kepler: every dashboard feature from the terminal.

    kepler                      full-screen app (welcome screen, tabs, chat with Kepler)
    kepler ask "why did signups drop?"     one question to the Kepler bot
    kepler chat                 conversation in the terminal (no full screen)
    kepler write "prove …" "solve …" [--open] [--tex] [--out FILE.pdf]   formal LaTeX/PDF write-ups
    kepler learn wikipedia | wordnet | PATH · --web on|off · --status · --ask "who was einstein"
    kepler bot [--live]         full-screen chat with the bot: test it and train it
    kepler teach [--live]       chat box for testing and training the bot (/y, /n INTENT, /new NAME REPLY)
    kepler status | decide M | metric M | incidents | explain ID | watch | analyze FILE.csv
    kepler label ID real|false|clear · train · models · settings · key · alerts · demo
    kepler integrations · connect TYPE k=v… · pulls · destinations · import FILE.csv
    kepler open [incident ID | metric M] · copy key|decision ID
    kepler agent install|uninstall|status|run · completion zsh|bash · config
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from rich.console import Console

from .. import device
from . import render as R
from .client import Client, KeplerError, load_config, save_config

from .. import __version__ as VERSION
EXIT = {"normal": 0, "watch": 1, "anomaly": 2}
console = Console(highlight=False)
err = Console(stderr=True, highlight=False)


def out(obj):
    console.print(obj)


def emit_json(obj):
    console.print_json(json.dumps(obj, default=str))


def client(args) -> Client:
    return Client(getattr(args, "url", None), getattr(args, "key", None))


def status_rows(c: Client) -> list[dict]:
    rows = []
    for m in c.get("/api/overview")["metrics"]:
        d = c.get_auth(f"/api/v1/decision/{m['name']}")
        if d["decision"] == "anomaly":
            top = d["incidents"][0]
            rows.append({"metric": m["name"], "decision": "anomaly", "p": top["confidence"], "observed": top["observed"],
                         "expected": top["expected"], "change_pct": top["change_pct"], "where": top["where"]})
        else:
            rows.append({"metric": m["name"], "decision": d["decision"], "p": d.get("anomaly_probability"),
                         "observed": d.get("observed"), "expected": d.get("expected"), "change_pct": d.get("change_pct")})
    return rows


# ---------------------------------------------------------------- app / chat

def cmd_serve(args):
    """Run the Kepler server (API + dashboard + background worker)."""
    if args.db:
        os.environ["KEPLER_DB"] = str(Path(args.db).expanduser().resolve())
    if args.demo is not None:
        os.environ["KEPLER_DEMO"] = "1" if args.demo == "on" else "0"
    import uvicorn

    from .. import config as kconfig
    from .. import db as kdb
    kdb.init_db()
    data = _remember_server(args.port)
    out(f"[bold]Kepler {VERSION}[/] · http://{args.host}:{args.port} · data: {data}")
    if kconfig.AUTH_REQUIRED:
        out(f"Dashboard sign-in key: [bold]{kdb.get_settings()['api_key']}[/]  [grey50](also: `kepler key`; rotate it in Settings)[/]")
    else:
        out("[yellow]Access gate is off (KEPLER_AUTH=off): only do this on a machine and network you trust.[/]")
    uvicorn.run("kepler.api:app", host=args.host, port=args.port, timeout_keep_alive=75, log_level=args.log_level)
    return 0


def _remember_server(port: int) -> str:
    """Note this server's database in ~/.kepler/servers.json, so the kepler CLI on this machine can find its access key
    (it reads it from the database, as you). Returns the database path."""
    from .. import db as kdb
    from .client import SERVER_INFO
    data = str(kdb.DB_PATH)
    try:
        known = json.loads(SERVER_INFO.read_text()) if SERVER_INFO.exists() else {}
        known = known if isinstance(known, dict) else {}
        known[str(port)] = data
        SERVER_INFO.parent.mkdir(parents=True, exist_ok=True)
        SERVER_INFO.write_text(json.dumps(known, indent=1))
    except (OSError, ValueError):
        pass
    return data


def _start_local_server(c: Client):
    """No server answers at a localhost URL: run one inside this process for as long as the app is open (`kepler serve`
    keeps one running on its own). Returns (server, thread), or None when the URL isn't local or the port is taken."""
    import logging
    import socket
    import threading
    from urllib.parse import urlparse

    import uvicorn

    from .. import db as kdb
    from .client import LOCAL_HOSTS, SERVER_INFO
    u = urlparse(c.url)
    if (u.hostname or "") not in LOCAL_HOSTS or u.scheme != "http":
        return None
    port = u.port or 80
    with socket.socket() as s:  # something else (not Kepler) on that port: leave it alone
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return None
    kdb.init_db()
    _remember_server(port)
    # the server's log goes to a file: anything written to the terminal would break the full-screen app
    SERVER_INFO.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=SERVER_INFO.parent / "server.log", level=logging.WARNING,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    server = uvicorn.Server(uvicorn.Config("kepler.api:app", host="127.0.0.1", port=port, log_config=None,
                                           access_log=False, timeout_keep_alive=75))
    thread = threading.Thread(target=server.run, daemon=True, name="kepler-server")
    thread.start()
    for _ in range(300):  # up to 15 s
        if server.started or not thread.is_alive():
            break
        time.sleep(0.05)
    if not server.started:
        server.should_exit = True
        return None
    return server, thread


def cmd_ui(args):
    """The full-screen app: dashboard tabs + the Kepler AI tab. With no server running on this machine it starts one for
    as long as the app is open. Only when no server can be reached or started does it open Kepler AI alone."""
    c = client(args)
    local = None
    note = ""
    try:
        c.get("/api/health")
    except KeplerError:
        local = _start_local_server(c)
        if local is None:
            from ..bot import chat_app
            return chat_app.run(None, note=f"no Kepler server at {c.url}: start one with `kepler serve` for the dashboard tabs")
        note = (f"Started Kepler at {c.url}: it stops when you quit. "
                "For one that keeps running (dashboard, alerts), use `kepler serve`.")
    from ..tui.app import run
    try:
        return run(c, skip_welcome=args.no_welcome, note=note)
    finally:
        if local:
            server, thread = local
            server.should_exit = True  # a clean shutdown: the worker and the compare helper stop too
            thread.join(timeout=10)


def cmd_ask(args):
    from ..bot.brain import Bot
    bot = Bot(client(args))
    with console.status("thinking…", spinner="dots"):
        reply = bot.handle(" ".join(args.text))
    if args.json:
        emit_json(reply.decision)
    else:
        out(reply.renderable())
    return 0


def cmd_chat(args):
    from ..bot.brain import Bot
    c = client(args)
    bot = Bot(c)
    out(R.welcome(c.url, True, {"mode": "chat · type 'help', 'exit' to leave"}))
    while True:
        try:
            text = console.input(f"[bold {R.ACCENT}]you ›[/] ")
        except (EOFError, KeyboardInterrupt):
            out("")
            return 0
        if text.strip().lower() in ("exit", "quit", ":q", "bye"):
            return 0
        reply = bot.handle(text)
        out(reply.renderable())
        out("")


def cmd_billing(args):
    """Plan and billing status. Billing (Razorpay) is disabled: Kepler is free and nothing can be charged."""
    from .. import billing
    try:
        st = client(args).get("/api/billing")  # the server's view: its environment holds the billing settings
        where = "from the server"
    except KeplerError:
        st, where = billing.status(), "from this machine (no server reachable)"
    if args.json:
        emit_json(st)
        return 0
    out(f"[bold]Plan:[/] {st['plan']}   [bold]Billing:[/] {'[green]on' if st['enabled'] else '[green]off'}[/] "
        f"({st['provider']}, {st['mode']})  [grey50]· {where}[/]")
    out(st["message"])
    rows = [[p["id"], p["name"], p["tagline"],
             "your plan" if p["id"] == st["plan"] else "for sale" if p["for_sale"] else "not for sale"] for p in st["plans"]]
    out(R.table(["plan", "name", "", "status"], rows))
    if st["blockers"]:
        out("[grey50]Charging stays off while any of these is true:[/]")
        for b in st["blockers"]:
            out(f"[grey50]  · {b}[/]")
        out("[grey50]How to enable it later: docs/billing.md[/]")
    return 0


def cmd_write(args):
    """Formal write-ups: each question answered by Kepler's engines, typeset in LaTeX, compiled to PDF."""
    from pathlib import Path

    from ..bot import latex
    from ..bot.mind import Mind
    if not args.questions:
        err.print("[red]give at least one question, e.g.[/] kepler write \"prove that 1 + 2 + ... + n = n(n+1)/2\"")
        return 2
    with console.status("thinking and typesetting…", spinner="dots"):
        w, items = latex.write_answers(args.questions, Mind(), pdf=not args.tex, title=args.title or "",
                                       out=Path(args.out).expanduser() if args.out else None)
    if args.json:
        emit_json({"pdf": str(w.pdf) if w.pdf else None, "tex": str(w.tex), "engine": w.engine, "note": w.note,
                   "sections": [{"question": i.question, "kind": i.kind, "answer": i.answer} for i in items]})
    else:
        for i in items:
            out(f"[bold]{i.question}[/] → {i.answer[:100]}")
        out(latex.summary(w))
    if args.open and (w.pdf or w.tex):
        latex.open_file(w.pdf or w.tex)
    return 0 if (w.pdf or args.tex) else 1


def cmd_learn(args):
    """Feed the library: datasets, your files, the live Wikipedia switch."""
    from pathlib import Path

    from ..library import index, ingest

    def say(msg):
        err.print(f"[grey50]{msg}[/]")

    if args.web:
        index.set_setting("web", args.web)
        out(f"Wikipedia lookup is now {args.web}." + ("  (only the search words of a question are sent to en.wikipedia.org)" if args.web == "on" else ""))
    if args.forget:
        n = index.forget(args.forget)
        out(f"Forgot {n:,} item(s) from {args.forget}.")
    for target in args.what or []:
        if target in ("wikipedia", "wordnet"):
            path = ingest.dataset_path(target)
            if not path.exists():
                say(f"downloading {target} (once) …")
                ingest.download(target, progress=say)
            if target == "wikipedia":
                n = ingest.import_wikipedia(path, limit=args.limit, progress=say)
                out(f"Learned {n:,} Simple English Wikipedia articles.")
            else:
                n = ingest.import_wordnet(path, progress=say)
                out(f"Learned {n:,} word meanings from Open English WordNet.")
        else:
            p = Path(target).expanduser()
            if not p.exists():
                err.print(f"[red]no such file or folder:[/] {target}")
                return 2
            n, problems = ingest.import_files(p, progress=say)
            out(f"Learned {n:,} file(s) from {p}.")
            for msg in problems[:10]:
                err.print(f"[yellow]skipped[/] {msg}")
    if args.ask:
        from ..library import answer
        a = answer.ask(args.ask)
        if args.json:
            emit_json(a.as_dict())
        else:
            out(answer.render(a.as_dict()))
        return 0
    if args.status or not (args.what or args.web or args.forget):
        st = index.stats()
        if args.json:
            emit_json(st)
            return 0
        rows = [[k, f"{v:,}"] for k, v in sorted(st["docs"].items())] + [["dictionary words", f"{st['words']:,}"],
                                                                           ["passages", f"{st['passages']:,}"],
                                                                           ["size", f"{st['size_mb']} MB"],
                                                                           ["live Wikipedia lookup", st["web"]]]
        out(R.table(["library", ""], rows))
        out("[grey50]feed it: kepler learn wikipedia · kepler learn wordnet · kepler learn ~/notes · kepler learn --web on|off[/]")
    return 0


def cmd_bot(args):
    from ..bot import chat_app
    bot = None
    if args.live:
        from ..bot.brain import Bot
        bot = Bot(client(args))
        bot.context()  # fail fast with a clear message if the server isn't reachable
    return chat_app.run(bot)


def cmd_teach(args):
    from ..bot import teach
    bot = None
    if args.live:
        from ..bot.brain import Bot
        bot = Bot(client(args))
        bot.context()  # fail fast with a clear message if the server isn't reachable
    return teach.run(console, bot)


# ---------------------------------------------------------------- reading

def diagnose(c) -> list[tuple[str, str, str]]:
    """Health checks for `kepler doctor`: (level, check, detail), level ok | warn | error | info."""
    now = time.time()
    try:
        health = c.get("/api/health")
    except KeplerError as e:
        return [("error", "server", str(e))]  # (the client's message says how to start one)
    out = [("ok", "server", f"reachable at {c.url}")]
    try:
        c.get("/api/settings")
        out.append(("ok", "access key", "accepted"))
    except KeplerError as e:
        return out + [("error", "access key", str(e))]
    if health.get("seeding"):
        out.append(("info", "worker", "seeding demo data (about 15 s)"))
    elif not health.get("last_tick") or now - health["last_tick"] > 60:
        out.append(("error", "worker", "the background worker hasn't run for over a minute: restart the server"))
    else:
        out.append(("ok", "worker", f"last ran {int(now - health['last_tick'])} s ago"))
    if health.get("last_error"):
        out.append(("error", "worker", f"last run failed: {health['last_error']}"))

    metrics = c.get("/api/overview")["metrics"]
    if not metrics:
        out.append(("warn", "data", "no metrics yet: connect a source (`kepler integrations`) or send one (`kepler send`)"))
    else:
        stale = [m["name"] for m in metrics if m["status"] == "stale"]
        out.append(("warn", "data", f"no recent data for {', '.join(stale)}") if stale
                   else ("ok", "data", f"{len(metrics)} metric{'s' if len(metrics) != 1 else ''}, all receiving data"))
        custom = sum(1 for m in metrics if m["model"] == "custom")
        trained = [m["trained_at"] for m in c.get("/api/models").get("metrics", []) if m.get("trained_at")]
        age = f", last trained {int((now - max(trained)) // 86400)} d ago" if trained else ""
        auto = health.get("auto_train", True)
        if custom and trained and not auto and now - max(trained) > 14 * 86400:
            out.append(("warn", "models", f"{custom} of {len(metrics)} custom-trained{age}, and automatic retraining is off "
                                          "(KEPLER_AUTO_TRAIN): run `kepler train`"))
        elif custom:
            out.append(("ok", "models", f"{custom} of {len(metrics)} on custom-trained models{age}"
                                        + (" (retrained weekly)" if auto else "")))
        else:
            out.append(("info", "models", "all on the shared model: custom models train once a metric has 7 days of data"
                                          + ("" if auto else " (`kepler train`)")))
        opened = sum(len(m["open_incidents"]) for m in metrics)
        if opened:
            out.append(("info", "incidents", f"{opened} open: `kepler incidents`"))
        if c.get("/api/settings").get("muted_until"):
            out.append(("warn", "maintenance", "maintenance mode is on: no alerts go out (`kepler maintenance off`)"))
        muted = [m["name"] for m in metrics if m.get("muted_until")]
        if muted:
            out.append(("info", "muted", f"alerts paused for {', '.join(muted)}"))

    for p in c.get("/api/connectors"):
        status = p.get("last_status") or ""
        if status.startswith("error"):
            out.append(("error", f"pull #{p['id']}", f"{p['name']}: {status}"))
        elif p.get("last_run") and now - p["last_run"] > 3 * p["interval_s"] + 120:
            out.append(("warn", f"pull #{p['id']}", f"{p['name']}: hasn't run for {int((now - p['last_run']) // 60)} min"))
        else:
            out.append(("ok", f"pull #{p['id']}", f"{p['name']}: {status or 'not run yet'}"))

    dests = c.get("/api/destinations")
    slack = bool(c.get("/api/settings").get("slack_webhook_url"))
    for d in dests:
        status = d.get("last_status") or ""
        out.append(("error" if status.startswith("error") else "ok", f"alerts: {d['label']}",
                    f"{d['name']}: {status or 'nothing sent yet'}"))
    if slack:
        out.append(("ok", "alerts: Slack", "webhook configured"))
    if not dests and not slack:
        out.append(("warn", "alerts", "alerts go nowhere: add Slack (Settings) or a destination (Integrations)"))

    billing = c.get("/api/billing")
    out.append(("info", "billing", "on: " + billing.get("mode", "") if billing.get("enabled")
                else "off: Kepler is free and nothing can be charged"))
    return out


def cmd_maintenance(args):
    """Maintenance mode: pause every alert for a while (planned work); detection and incidents go on."""
    c = client(args)
    if args.duration:
        c.put("/api/settings", {"muted_until": mute_until(args.duration)})
    until = c.get("/api/settings").get("muted_until") or 0
    if until:
        out(f"[yellow]maintenance mode: every alert paused until {time.strftime('%a %d %b %H:%M', time.localtime(until))}[/] "
            "(incidents are still detected and recorded; `kepler maintenance off` ends it)")
    else:
        out("maintenance mode is off: alerts go out as usual")
    return 0


def cmd_report(args):
    """What Kepler saw over the last days; --send posts it to Slack and email (cron it for a weekly digest)."""
    c = client(args)
    if args.send:
        res = c.post(f"/api/report/send?days={args.days}")
        out(res["text"])
        for s in res["sent"]:
            out(("[green]✓ " if s["ok"] else "[red]✗ ") + f"{s['channel']}: {s['detail']}[/]")
        if not res["sent"]:
            out("[yellow]nowhere to send it: add Slack (Settings) or an email destination (Integrations)[/]")
        return 0 if res["sent"] and all(s["ok"] for s in res["sent"]) else 1
    r = c.get("/api/report", days=args.days)
    if args.json:
        emit_json(r)
        return 0
    from rich.markup import escape
    out(escape(r["text"]))
    return 0


def cmd_doctor(args):
    checks = diagnose(client(args))
    bad = sum(1 for level, _, _ in checks if level == "error")
    if args.json:
        emit_json([{"level": lv, "check": ck, "detail": dt} for lv, ck, dt in checks])
        return 1 if bad else 0
    mark = {"ok": "[green]✓[/]", "warn": "[yellow]![/]", "error": "[red]✗[/]", "info": "[grey50]·[/]"}
    for level, check, detail in checks:
        out(f"{mark[level]} {check:<18} {detail}")
    warn = sum(1 for level, _, _ in checks if level == "warn")
    out(f"\n[red]{bad} problem(s)[/]" if bad else "\n[yellow]looks fine, with warnings[/]" if warn else "\n[green]all good[/]")
    return 1 if bad else 0


def cmd_status(args):
    c = client(args)
    ov = c.get("/api/overview")
    if ov.get("seeding"):
        out("Kepler is still generating demo data; try again in a few seconds.")
        return 0
    rows = status_rows(c)
    if args.json:
        emit_json(rows)
    else:
        out(f"\n[grey50]Kepler · {c.url} · {len(rows)} metrics · {ov['stats']['open']} open incident(s)[/]")
        out(R.status_table(rows))
    return max((EXIT[r["decision"]] for r in rows), default=0) if args.exit_code else 0


def cmd_decide(args):
    d = client(args).get_auth(f"/api/v1/decision/{args.metric}")
    emit_json(d) if args.json else out(R.decision_panel(d))
    return EXIT[d["decision"]] if args.exit_code else 0


def cmd_metrics(args):
    c = client(args)
    ms = c.metrics()
    if args.json:
        emit_json([{k: m[k] for k in ("id", "name", "unit", "agg", "source", "status", "model", "bad_direction")} for m in ms])
        return 0
    out(R.table(["metric", "status", "source", "agg", "alerts when", "model", "last 6 h"],
                [[m["name"], m["status"], m["source"], m["agg"], m["bad_direction"], m["model"],
                  R.spark([p["value"] for p in m["sparkline"]], 30)] for m in ms]))
    return 0


def mute_until(text: str, now: float | None = None) -> int:
    """'30m' / '2h' / '1d' → when the mute ends (epoch seconds); 'off' → 0."""
    import re
    if text.strip().lower() in ("off", "0", "no", "unmute"):
        return 0
    m = re.fullmatch(r"\s*(\d+)\s*([mhd])\s*", text.lower())
    if not m:
        raise KeplerError(f"--mute takes a duration like 30m, 2h or 1d, or 'off' (got '{text}')")
    return int((time.time() if now is None else now) + int(m.group(1)) * {"m": 60, "h": 3600, "d": 86400}[m.group(2)])


def cmd_metric(args):
    c = client(args)
    m = c.metric_by_name(args.name)
    if args.delete:
        if not args.yes and console.input(f"Delete [bold]{m['name']}[/] and all its data? [y/N] ").lower() != "y":
            return 0
        c.delete(f"/api/metrics/{m['id']}")
        out(f"deleted {m['name']}")
        return 0
    patch = {k: v for k, v in (("unit", args.unit), ("description", args.description), ("bad_direction", args.alert_when),
                               ("agg", args.agg), ("tier", args.tier)) if v is not None}
    if args.mute:
        until = mute_until(args.mute)
        patch["muted_until"] = until
    if patch:
        c.patch(f"/api/metrics/{m['id']}", patch)
        if args.mute:
            out(f"alerts for {m['name']} muted until {time.strftime('%a %d %b %H:%M', time.localtime(until))}: "
                "incidents are still detected and recorded" if until else f"alerts for {m['name']} are on again")
        if set(patch) - {"muted_until"}:
            out(f"updated {m['name']}: { {k: v for k, v in patch.items() if k != 'muted_until'} }")
    data = c.get(f"/api/metrics/{m['id']}/series", hours=args.hours, slice=args.slice or "")
    if args.json:
        emit_json(data)
        return 0
    w = min(console.width, 110)
    out(R.metric_chart(data["points"], w - 4, 16, f"{m['name']}{' · ' + args.slice if args.slice else ''} · last {args.hours} h"))
    out(f"[grey50]{data['model']} · alerts when it goes {m['bad_direction']} · slices: {', '.join(data['slices']) or 'none'}[/]")
    br = c.get(f"/api/metrics/{m['id']}/breakdown")["slices"]
    if br:
        out(R.table(["slice", "now", "expected", "change", "z"],
                    [[s["slice"], R.num(s["observed"]), R.num(s["expected"]), R.pct(s["change_pct"]),
                      "–" if s["z"] is None else f"{s['z']:.1f}"] for s in sorted(br, key=lambda s: -abs(s["z"] or 0))]))
    if data["incidents"]:
        out(R.incidents_table(list(reversed(data["incidents"]))))
    return 0


def cmd_incidents(args):
    incs = client(args).get("/api/incidents", limit=args.limit, status="open" if args.open else None)
    if args.json:
        emit_json(incs)
    elif not incs:
        out("no incidents" + (" open" if args.open else ""))
    else:
        out(R.incidents_table(incs))
    return 0


def cmd_explain(args):
    res = client(args).get(f"/api/incidents/{args.id}")
    if args.json:
        emit_json(res["decision"])
        return 0
    out(R.incident_panel(res["decision"], res["points"], min(console.width, 110)))
    if res.get("notifications"):
        out("[grey50]alerts: " + ", ".join(f"{n['kind']} {'✓' if n['delivered'] else '(' + (n['error'] or '') + ')'}"
                                         for n in res["notifications"]) + "[/]")
    related = res["decision"].get("related") or []
    if related:
        out("[grey50]at the same time: " + ", ".join(f"#{r['incident_id']} {r['metric']} {R.change_text(r)}" for r in related) + "[/]")
    _print_notes(res.get("notes") or [])
    return 0


def _print_notes(notes: list[dict]):
    from rich.markup import escape  # notes are the team's text: never markup
    for n in notes:
        out(f"[grey50]{time.strftime('%a %d %b %H:%M', time.localtime(n['created_at']))} · #{n['id']}[/]  {escape(n['text'])}")


def cmd_note(args):
    """Add a note to an incident (what you found or did), or list its notes."""
    c = client(args)
    if args.delete:
        res = c.delete(f"/api/incidents/{args.id}/notes/{args.delete}")
    elif args.text:
        res = c.post(f"/api/incidents/{args.id}/notes", {"text": " ".join(args.text)})
    else:
        res = c.get(f"/api/incidents/{args.id}")
    notes = res.get("notes") or []
    if args.json:
        emit_json(notes)
        return 0
    if not notes:
        out(f"[grey50]no notes on incident #{args.id} yet: kepler note {args.id} \"what you found\"[/]")
    _print_notes(notes)
    return 0


def _watch_loop(c: Client, interval: int, min_severity: str, desktop: bool, quiet: bool = False, once: bool = False,
                state_name: str | None = None):
    rank = {"medium": 0, "high": 1, "critical": 2}
    state = device.load_state(state_name) if state_name else {}
    seen: dict[str, list] = state.get("seen", {})
    first = not seen
    while True:
        try:
            incs = c.get("/api/incidents", limit=50)
        except KeplerError as e:
            if not quiet:
                err.print(f"[red]{e}[/]")
            if once:
                return
            time.sleep(interval)
            continue
        for d in reversed(incs):
            if rank[d["severity"]] < rank[min_severity]:
                continue
            key = str(d["incident_id"])
            sig = [d["status"], d["severity"]]
            prev = seen.get(key)
            seen[key] = sig
            if first and d["status"] != "open":
                continue
            where = R.where_text(d["where"])
            if prev is None:
                if not quiet:
                    out(f"[bold red]{time.strftime('%H:%M:%S')} NEW[/]")
                    out(R.incident_panel(d))
                if desktop:
                    device.notify(f"Kepler · {d['severity'].upper()}", f"{d['metric']} {R.pct(d['change_pct'])} · {where}",
                                  f"{d['confidence']:.0%} confidence · #{d['incident_id']}")
            elif prev[0] == "open" and d["status"] == "resolved":
                if not quiet:
                    out(f"[bold green]{time.strftime('%H:%M:%S')} RESOLVED[/]  #{d['incident_id']} {d['metric']}")
                if desktop:
                    device.notify("Kepler · resolved", f"{d['metric']} is back to normal", f"#{d['incident_id']} · {where}",
                                  sound=False)
            elif prev != sig and d["status"] == "open" and prev[1] != d["severity"] and not quiet:
                out(f"[bold yellow]{time.strftime('%H:%M:%S')} ESCALATED[/]  #{d['incident_id']} {prev[1]} → {d['severity']}")
        first = False
        if state_name:
            device.save_state(state_name, {"seen": dict(list(seen.items())[-500:])})
        if once:
            return
        time.sleep(interval)


def cmd_watch(args):
    c = client(args)
    out(f"[grey50]watching {c.url} every {args.interval}s{' · desktop notifications on' if args.notify else ''} · Ctrl-C to stop[/]")
    try:
        _watch_loop(c, args.interval, args.min_severity, args.notify, once=args.once)
    except KeyboardInterrupt:
        pass
    return 0


# ---------------------------------------------------------------- acting

def cmd_send(args):
    dims = dict(d.split("=", 1) for d in args.dim or [])
    r = client(args).post_auth("/api/v1/ingest", {"metrics": [{"name": args.metric, "value": args.value, "dims": dims or None,
                                                               "agg": "mean" if args.mean else "sum"}]})
    out(f"accepted {r['accepted']} point(s) for {', '.join(r['metrics'])}")
    return 0


def cmd_label(args):
    r = client(args).post(f"/api/incidents/{args.id}/feedback", {"label": {"real": 1, "false": 0, "clear": None}[args.label]})
    out(f"#{args.id} labelled {args.label} · {r['labels']} labels in this workspace (run `kepler train` to learn from them)")
    return 0


def cmd_train(args):
    with console.status("training…"):
        r = client(args).post("/api/models/train")
    if args.json:
        emit_json(r)
        return 0
    for m in r["metrics"]:
        ok = m["status"] == "trained"
        out(f"{'[green]✓[/]' if ok else '[grey50]·[/]'} {m['metric']:<24} {m['status']}"
            + (f"[grey50]  ({m['slices_trained']} series, {m['model']})[/]" if ok else ""))
    fb = r["feedback"]
    acc = f", cross-validated accuracy {fb['cv_accuracy']:.0%}" if fb.get("cv_accuracy") is not None else ""
    out(f"[green]✓[/] feedback filter          {fb.get('status')} ({fb.get('n_labels', 0)} labels{acc})")
    return 0


def cmd_models(args):
    mm = client(args).get("/api/models")
    if args.json:
        emit_json(mm)
        return 0
    fb = mm["feedback"]
    out(f"feedback filter: [bold]{'active' if fb.get('active') else 'prior only'}[/] · {mm['labels']['pos']} 👍 "
        f"{mm['labels']['neg']} 👎 {mm['labels']['unl']} unlabelled · weight {fb.get('weight', 0):.0%}"
        + (f" · cv accuracy {fb['cv_accuracy']:.0%}" if fb.get("cv_accuracy") is not None else ""))
    out(R.table(["metric", "baseline", "slices trained", "trained on", "updated"],
                [[x["metric"], f"custom · {x['period']}" if x["kind"] == "custom" else "base (shared)",
                  str(max(0, x["slices_trained"] - 1)) if x["slices_trained"] else "–",
                  f"{x['trained_days']} d" if x["trained_days"] else "–", R.ago(x["trained_at"]) if x["trained_at"] else "never"]
                 for x in mm["metrics"]]))
    return 0


def cmd_tiers(args):
    data = client(args).get("/api/tiers")
    if args.json:
        emit_json(data)
        return 0
    out(R.tiers_table(data))
    bill = data.get("monthly_preview")
    out(f"[grey50]{data['paywall']['note']}" + (f"  Estimated bill: ${bill['amount']:.0f}/month → $0 charged." if bill else "") + "[/]")
    out("[grey50]kepler tier orbit|area|time · kepler metric <name> --tier … · kepler compare <metric>[/]")
    return 0


def cmd_tier(args):
    c = client(args)
    st = c.put("/api/settings", {"model_tier": args.tier})
    out(f"default model → [bold]{st['model_tier'].title()}[/] (metrics with their own model keep it)")
    return 0


def cmd_compare(args):
    c = client(args)
    m = c.metric_by_name(args.metric)
    with console.status("running Orbit, Area and Time…"):
        res = c.get(f"/api/metrics/{m['id']}/compare")
    if args.json:
        emit_json(res)
        return 0
    out(R.compare_table(res))
    out(f"[grey50]{res['paywall']['note']}[/]")
    return 0


def cmd_settings(args):
    c = client(args)
    patch = {}
    if args.sensitivity is not None:
        patch["sensitivity"] = args.sensitivity / 100 if args.sensitivity > 1 else args.sensitivity
    if args.min_change is not None:
        patch["min_change_pct"] = args.min_change
    if args.slack is not None:
        patch["slack_webhook_url"] = args.slack
    if args.demo is not None:
        patch["demo_mode"] = args.demo == "on"
    st = c.put("/api/settings", patch) if patch else c.get("/api/settings")
    if args.test_slack:
        r = c.post("/api/settings/test-slack")
        out(("[green]✓ " if r["ok"] else "[red]✗ ") + r["message"] + "[/]")
    if args.json:
        emit_json({k: v for k, v in st.items() if k != "api_key"})
        return 0
    ag = device.agent_status()
    out(R.table(["setting", "value"], [
        ["sensitivity", f"{st['sensitivity']:.0%} minimum confidence to alert"],
        ["ignore changes under", f"{st['min_change_pct']:.0f}%"],
        ["slack webhook", "set" if st["slack_webhook_url"] else "not set"],
        ["demo mode", "on" if st["demo_mode"] else "off"],
        ["background agent", ("running" if ag["running"] else "installed, not running") if ag["installed"] else "not installed"],
        ["server", c.url]]))
    return 0


def cmd_key(args):
    c = client(args)
    st = c.post("/api/settings/rotate-key") if args.rotate else c.get("/api/settings")
    if args.copy:
        out("copied to clipboard" if device.copy(st["api_key"]) else "no clipboard available")
    out(st["api_key"])
    if args.rotate:
        cfg = load_config()
        if cfg.get("key"):
            cfg["key"] = st["api_key"]
            save_config(cfg)
    return 0


def cmd_alerts(args):
    log = client(args).get("/api/notifications")
    if args.json:
        emit_json(log)
        return 0
    out(R.table(["kind", "message", "slack", "when"], [[n["kind"], n["payload"]["text"], "✓" if n["delivered"] else (n["error"] or ""),
                                                      R.ago(n["created_at"])] for n in log[:args.limit]]) if log else "no alerts sent yet")
    return 0


def cmd_demo(args):
    c = client(args)
    if args.scenario == "reset":
        c.post("/api/demo/reset")
        out("regenerating demo data (about 15 s)…")
        return 0
    if not args.scenario:
        out(R.table(["scenario", "what breaks"], [[s["id"], s["label"]] for s in c.get("/api/demo/scenarios")]))
        out("[grey50]kepler demo <scenario> · kepler demo reset[/]")
        return 0
    r = c.post("/api/demo/inject", {"scenario": args.scenario})
    if r.get("incident_id"):
        res = c.get(f"/api/incidents/{r['incident_id']}")
        out(R.incident_panel(res["decision"], res["points"], min(console.width, 110)))
    else:
        out("injected; not confident enough to alert yet. Try `kepler watch`.")
    return 0


# ---------------------------------------------------------------- integrations

def cmd_integrations(args):
    items = client(args).get("/api/integrations")
    if args.json:
        emit_json(items)
        return 0
    for direction, title in (("pull", "Pull metrics from"), ("push", "Send data to Kepler"), ("destination", "Send incidents to")):
        out(R.table(["tool", "type", "category", "summary"],
                    [[i["label"], i["type"], i["category"], i["summary"][:72]] for i in items if i["direction"] == direction], title))
    out("[grey50]kepler connect <type> --help-fields · kepler connect <type> field=value … [--test][/]")
    return 0


def _parse_kv(pairs: list[str]) -> dict:
    out_ = {}
    for p in pairs:
        if "=" not in p:
            raise KeplerError(f"expected field=value, got '{p}'")
        k, v = p.split("=", 1)
        out_[k.strip()] = v
    return out_


def cmd_connect(args):
    c = client(args)
    integ = next((i for i in c.get("/api/integrations") if i["type"] == args.type), None)
    if not integ:
        raise KeplerError(f"unknown integration '{args.type}'. See `kepler integrations`.")
    if args.help_fields or not args.fields:
        out(f"[bold]{integ['label']}[/] ({integ['direction']}): {integ['summary']}")
        out(R.table(["field", "label", "", "default"], [[f["name"], f["label"], "required" if f["required"] else "optional",
                                                        f["default"][:60]] for f in integ["fields"]]))
        if integ["docs"]:
            out(f"[grey50]docs: {integ['docs']}[/]")
        return 0
    cfg = {f["name"]: f["default"] for f in integ["fields"]}
    cfg.update(_parse_kv(args.fields))
    if integ["direction"] == "pull":
        body = {"type": integ["type"], "name": args.name or f"{integ['label']}: {cfg.get('metric', '')}",
                "interval_s": args.every * 60, "config": {**cfg, "agg": args.agg or integ["default_agg"],
                                                          "bad_direction": args.alert_when or integ["default_bad"]}}
        r = c.post("/api/connectors/test", body)
        out(("[green]✓ " if r["ok"] else "[red]✗ ") + r["message"] + "[/]")
        if args.test or not r["ok"] and not args.force:
            return 0 if r["ok"] else 1
        cid = c.post("/api/connectors", body)["id"]
        out(f"saved pull #{cid}; it runs every {args.every} min")
    elif integ["direction"] == "destination":
        body = {"type": integ["type"], "name": args.name or integ["label"], "config": cfg, "min_severity": args.min_severity}
        r = c.post("/api/destinations/test", body)
        out(("[green]✓ " if r["ok"] else "[red]✗ ") + r["message"] + "[/]")
        if args.test or not r["ok"] and not args.force:
            return 0 if r["ok"] else 1
        out(f"saved destination #{c.post('/api/destinations', body)['id']}")
    else:
        out(f"{integ['label']} pushes to Kepler; nothing to save here. See `kepler connect {integ['type']}` for the URL.")
    return 0


def cmd_pulls(args):
    c = client(args)
    if args.action == "run":
        r = c.post(f"/api/connectors/{args.id}/run")
        out(("[green]✓ " if r["ok"] else "[red]✗ ") + r["message"] + "[/]")
        return 0
    if args.action == "rm":
        c.delete(f"/api/connectors/{args.id}")
        out(f"removed pull #{args.id}")
        return 0
    rows = c.get("/api/connectors")
    emit_json(rows) if args.json else out(R.table(["#", "name", "type", "metric", "every", "last run", "status"], [
        [r["id"], r["name"], r["type"], r["config"].get("metric", ""), f"{r['interval_s'] // 60} min",
         R.ago(r["last_run"]) if r["last_run"] else "never", r["last_status"] or "–"] for r in rows]) if rows else "no scheduled pulls")
    return 0


def cmd_destinations(args):
    c = client(args)
    if args.action == "rm":
        c.delete(f"/api/destinations/{args.id}")
        out(f"removed destination #{args.id}")
        return 0
    rows = c.get("/api/destinations")
    emit_json(rows) if args.json else out(R.table(["#", "name", "type", "sends", "status"], [
        [r["id"], r["name"], r["type"], f"{r['min_severity']}+", r["last_status"] or "waiting"] for r in rows]) if rows else "no destinations")
    return 0


def cmd_import(args):
    r = client(args).upload_csv(Path(args.file), args.metric or "", args.agg, args.bad)
    out(f"imported {r['rows']:,} rows into {', '.join(r['metrics'])}" + (f" (dimensions: {', '.join(r['dimensions'])})" if r["dimensions"] else ""))
    out("[grey50]run `kepler train` to learn from it[/]")
    return 0


# ---------------------------------------------------------------- device

def cmd_open(args):
    c = client(args)
    path = ""
    if args.what == "incident" and args.target:
        path = f"incident/{args.target}"
    elif args.what == "metric" and args.target:
        path = f"metric/{c.metric_by_name(args.target)['id']}"
    elif args.what:
        path = args.what
    url = c.dashboard_url(path)
    device.open_url(url)
    out(f"opened {url}")
    return 0


def cmd_copy(args):
    c = client(args)
    if args.what == "key":
        text = c.get("/api/settings")["api_key"]
    elif args.what == "decision":
        if not args.target:
            raise KeplerError("which incident? `kepler copy decision 40`")
        text = json.dumps(c.get(f"/api/incidents/{args.target}")["decision"], indent=2)
    else:
        text = json.dumps(c.get_auth(f"/api/v1/decision/{args.target or args.what}"), indent=2)
    out("copied to clipboard" if device.copy(text) else text)
    return 0


def cmd_agent(args):
    if args.action == "run":
        c = client(args)
        print(f"{time.strftime('%F %T')} kepler agent watching {c.url} (min severity {args.min_severity})", flush=True)
        _watch_loop(c, args.interval, args.min_severity, desktop=True, quiet=True, state_name="agent")
        return 0
    if args.action == "install":
        url = client(args).url
        if args.print:
            print(device.agent_plist(url, args.min_severity) if device.IS_MAC else device.systemd_unit(url, args.min_severity))
            return 0
        out(device.agent_install(url, args.min_severity))
        out("[grey50]You'll get a desktop notification for every new incident, even with no terminal open.[/]")
        return 0
    if args.action == "uninstall":
        out(device.agent_uninstall())
        return 0
    st = device.agent_status()
    out(R.table(["", ""], [["installed", "yes" if st["installed"] else "no"], ["running", "yes" if st["running"] else "no"],
                           ["definition", st["path"]], ["log", st["log"]]]))
    if args.test_notification:
        out("sent" if device.notify("Kepler", "Desktop notifications work.", "test") else "no notifier available")
    return 0


def cmd_config(args):
    cfg = load_config()
    if args.set_url:
        cfg["url"] = args.set_url
    if args.set_key:
        cfg["key"] = args.set_key
    if args.set_url or args.set_key:
        save_config(cfg)
        out("saved")
    shown = {**cfg, **({"key": cfg["key"][:6] + "…"} if cfg.get("key") else {})}
    out(json.dumps(shown, indent=2) if shown else "no config saved (defaults: http://localhost:8000, key read from the server)")
    return 0


# ---------------------------------------------------------------- offline analysis (no server)

def cmd_analyze(args):
    path = Path(args.file)
    if not path.is_file():
        raise KeplerError(f"no such file: {path}")
    tmp = tempfile.mkdtemp(prefix="kepler-")
    os.environ["KEPLER_DB"] = str(Path(tmp) / "analyze.db")
    from .. import connectors, db
    from ..db import BUCKET, DAY
    from ..engine import detector

    db.DB_PATH = Path(os.environ["KEPLER_DB"])
    db.init_db()
    db.set_setting("demo_mode", "0")
    t0 = time.time()
    with console.status(f"analyzing {path.name}…"):
        summary = connectors.import_csv(path.read_bytes(), args.metric, args.agg, args.bad)
        result = {"file": str(path), "metrics": []}
        with db.session(write=True) as c:
            for name, info in summary["metrics"].items():
                m = c.execute("SELECT * FROM metrics WHERE name = ?", (name,)).fetchone()
                start, end = db.bucket_of(info["from"]), db.bucket_of(info["to"])
                days = (end - start) / 86400
                entry = {"metric": name, "points": info["points"], "days": round(days, 1)}
                if days < 1.5:
                    entry["error"] = "needs at least 2 days of data"
                    result["metrics"].append(entry)
                    continue
                c.execute("UPDATE metrics SET last_scored_ts = 0 WHERE id = ?", (m["id"],))
                m = c.execute("SELECT * FROM metrics WHERE id = ?", (m["id"],)).fetchone()
                first = start + DAY * BUCKET
                detector.backfill(c, m, first, end)
                model = "shared base model"
                if days >= 8:  # second pass with a model trained on this very file
                    detector.train_all(c, now=end)
                    c.execute("DELETE FROM incidents WHERE metric_id = ?", (m["id"],))
                    c.execute("UPDATE metrics SET last_scored_ts = 0 WHERE id = ?", (m["id"],))
                    detector.backfill(c, m, first, end)
                    model = detector.get_model(c, m).label
                entry["model"] = model
                entry["slices"] = detector.slices(c, m, end)[1:]
                incs = c.execute("SELECT * FROM incidents WHERE metric_id = ? ORDER BY confidence DESC", (m["id"],)).fetchall()
                entry["incidents"] = [detector.decision(i, m) for i in incs]
                result["metrics"].append(entry)
    result["seconds"] = round(time.time() - t0, 2)
    shutil.rmtree(tmp, ignore_errors=True)
    found = any(e.get("incidents") for e in result["metrics"])
    if args.json:
        emit_json(result)
        return 2 if args.exit_code and found else 0
    out(f"\n[grey50]kepler analyze · {path.name} · {summary['rows']:,} rows · {result['seconds']}s[/]\n")
    for e in result["metrics"]:
        out(f"[bold]{e['metric']}[/]  {e['days']} days · {e['points']:,} points"
            + (f" · slices: {', '.join(e['slices'])}" if e.get("slices") else ""))
        if "error" in e:
            out(f"[yellow]skipped: {e['error']}[/]\n")
            continue
        sev = {k: sum(1 for d in e["incidents"] if d["severity"] == k) for k in ("critical", "high", "medium")}
        out(f"[grey50]model[/]  {e['model']}")
        out("[grey50]found[/]  " + (", ".join(f"[{R.SEV[k]}]{v} {k}[/]" for k, v in sev.items() if v) if e["incidents"]
                                     else "[green]nothing unusual[/]"))
        for d in e["incidents"][: args.top]:
            out(R.incident_panel(d))
        if len(e["incidents"]) > args.top:
            out(f"[grey50]… {len(e['incidents']) - args.top} more (use --top or --json)[/]\n")
    return 2 if args.exit_code and found else 0


# ---------------------------------------------------------------- completions

def cmd_complete(args):
    """Hidden helper used by the shell completion scripts."""
    try:
        c = Client(timeout=1.5)
        if args.kind == "metrics":
            print("\n".join(m["name"] for m in c.metrics()))
        elif args.kind == "incidents":
            print("\n".join(str(i["incident_id"]) for i in c.get("/api/incidents", limit=30)))
        elif args.kind == "integrations":
            print("\n".join(i["type"] for i in c.get("/api/integrations")))
        elif args.kind == "scenarios":
            print("\n".join(["reset"] + [s["id"] for s in c.get("/api/demo/scenarios")]))
    except Exception:
        pass
    return 0


DYNAMIC = {"decide": "metrics", "metric": "metrics", "compare": "metrics", "explain": "incidents", "label": "incidents", "connect": "integrations",
           "demo": "scenarios"}


def cmd_completion(args):
    parser = build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    cmds = [n for n in sub.choices if not n.startswith("_")]
    opts = {n: sorted({o for a in p._actions for o in a.option_strings if o.startswith("--")}) for n, p in sub.choices.items()}
    if args.shell == "zsh":
        cases = "\n".join(f"      {n}) opts=({' '.join(opts[n])}); dyn={DYNAMIC.get(n, '')};;" for n in cmds)
        print(f"""#compdef kepler
# kepler zsh completion. Install: kepler completion zsh > "${{fpath[1]}}/_kepler"  (then restart your shell)
_kepler() {{
  local -a cmds opts; local dyn
  cmds=({' '.join(cmds)})
  if (( CURRENT == 2 )); then compadd -- $cmds; return; fi
  case $words[2] in
{cases}
  esac
  if [[ -n $dyn && $words[CURRENT] != -* ]]; then compadd -- ${{(f)"$(kepler __complete $dyn 2>/dev/null)"}}; fi
  compadd -- $opts
}}
compdef _kepler kepler
""")
    else:
        cases = "\n".join(f"    {n}) opts='{' '.join(opts[n])}'; dyn='{DYNAMIC.get(n, '')}';;" for n in cmds)
        print(f"""# kepler bash completion. Install: kepler completion bash > ~/.kepler-completion.bash && echo 'source ~/.kepler-completion.bash' >> ~/.bashrc
_kepler() {{
  local cur=${{COMP_WORDS[COMP_CWORD]}} opts='' dyn=''
  if [[ $COMP_CWORD -eq 1 ]]; then COMPREPLY=($(compgen -W "{' '.join(cmds)}" -- "$cur")); return; fi
  case ${{COMP_WORDS[1]}} in
{cases}
  esac
  if [[ -n $dyn && $cur != -* ]]; then COMPREPLY=($(compgen -W "$(kepler __complete $dyn 2>/dev/null)" -- "$cur")); fi
  COMPREPLY+=($(compgen -W "$opts" -- "$cur"))
}}
complete -F _kepler kepler
""")
    return 0


# ---------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    def flags(suppress: bool) -> argparse.ArgumentParser:
        # global flags work before or after the command; sub-commands must not reset values given before it
        d = {"default": argparse.SUPPRESS} if suppress else {}
        f = argparse.ArgumentParser(add_help=False)
        f.add_argument("--url", help="Kepler server (default: KEPLER_URL, saved config, or http://localhost:8000)", **d)
        f.add_argument("--key", help="API key (default: KEPLER_KEY, saved config, or read from a local server)", **d)
        f.add_argument("--json", action="store_true", help="machine-readable output", **d)
        f.add_argument("--no-color", action="store_true", **d)
        f.add_argument("--exit-code", action="store_true", help="exit 0 normal / 1 watch / 2 anomaly (for CI gates)", **d)
        return f

    common = flags(True)
    p = argparse.ArgumentParser(prog="kepler", description="Kepler metric watchdog. Run `kepler` alone for the full-screen app.",
                                parents=[flags(False)], formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--version", action="version", version=f"kepler {VERSION}")
    sub = p.add_subparsers(dest="cmd", metavar="command")

    def add(name, fn, help_, **kw):
        s = sub.add_parser(name, parents=[common], help=help_, **kw)
        s.set_defaults(fn=fn)
        return s

    s = add("serve", cmd_serve, "run the Kepler server: API, dashboard and background worker")
    s.add_argument("--host", default="127.0.0.1", help="interface to listen on (default: this machine only)")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--db", help="database file (default: KEPLER_DB or ~/.kepler/kepler.db)")
    s.add_argument("--demo", choices=["on", "off"], help="stream a simulated startup's metrics (first start only)")
    s.add_argument("--log-level", default="info", choices=["critical", "error", "warning", "info", "debug"])
    s = add("ui", cmd_ui, "full-screen app (default when run with no command)")
    s.add_argument("--no-welcome", action="store_true")
    s = add("ask", cmd_ask, "ask the Kepler bot one question")
    s.add_argument("text", nargs="+")
    add("chat", cmd_chat, "chat with Kepler in the terminal")
    s = add("maintenance", cmd_maintenance, "pause every alert for planned work: kepler maintenance 2h | off")
    s.add_argument("duration", nargs="?", help="30m, 2h, 1d … (at most 30d), or 'off'")
    s = add("report", cmd_report, "what Kepler saw over the last days; --send posts it to Slack and email (weekly cron)")
    s.add_argument("--days", type=int, default=7)
    s.add_argument("--send", action="store_true")
    add("doctor", cmd_doctor, "check this setup: server, key, worker, data, pulls, alerts (exit code 1 on a problem)")
    add("billing", cmd_billing, "plan and billing status (Razorpay; disabled: Kepler is free)")
    s = add("write", cmd_write, "formal LaTeX write-up of questions/proofs, compiled to PDF (~/Documents/Kepler)")
    s.add_argument("questions", nargs="*", help='e.g. "prove that 1 + 2 + ... + n = n(n+1)/2" "solve x^2 - 5x + 6 = 0"')
    s.add_argument("--title", help="document title")
    s.add_argument("--out", help="output path (…/name.pdf); default ~/Documents/Kepler/")
    s.add_argument("--tex", action="store_true", help="LaTeX source only, don't compile")
    s.add_argument("--open", action="store_true", help="open the PDF when done")
    s = add("learn", cmd_learn, "feed Kepler's library: wikipedia, wordnet, your files (PATH), --web on|off, --status")
    s.add_argument("what", nargs="*", help="wikipedia | wordnet | a file or folder")
    s.add_argument("--limit", type=int, help="import at most N Wikipedia articles")
    s.add_argument("--web", choices=["on", "off"], help="live Wikipedia lookup when the library doesn't know")
    s.add_argument("--forget", metavar="SOURCE", help="remove a source: wikipedia, wordnet, web-wikipedia, files")
    s.add_argument("--status", action="store_true", help="what the library holds")
    s.add_argument("--ask", metavar="QUESTION", help="ask the library directly")
    s = add("bot", cmd_bot, "full-screen chat with the Kepler bot; test and train it (offline by default)")
    s.add_argument("--live", action="store_true", help="also give real answers from a running Kepler server")
    s = add("teach", cmd_teach, "chat box for testing and training the Kepler bot (offline by default)")
    s.add_argument("--live", action="store_true", help="also give real answers from a running Kepler server")
    add("status", cmd_status, "every metric, one line each")
    s = add("decide", cmd_decide, "typed decision for one metric right now")
    s.add_argument("metric")
    add("metrics", cmd_metrics, "list metrics")
    s = add("metric", cmd_metric, "chart, slices and incidents for one metric (and edit it)")
    s.add_argument("name")
    s.add_argument("--hours", type=int, default=24)
    s.add_argument("--slice")
    s.add_argument("--unit")
    s.add_argument("--description")
    s.add_argument("--alert-when", choices=["up", "down", "both"])
    s.add_argument("--agg", choices=["sum", "mean"])
    s.add_argument("--tier", choices=["orbit", "area", "time", "default"], help="model for this metric")
    s.add_argument("--mute", metavar="DURATION", help="pause its alerts for 30m, 2h, 1d … (at most 30d), or 'off'")
    s.add_argument("--delete", action="store_true")
    s.add_argument("-y", "--yes", action="store_true")
    s = add("incidents", cmd_incidents, "list incidents")
    s.add_argument("--open", action="store_true")
    s.add_argument("--limit", type=int, default=15)
    s = add("explain", cmd_explain, "full reasoning behind one incident")
    s.add_argument("id", type=int)
    s = add("note", cmd_note, 'add a note to an incident (kepler note 40 "rolled back deploy 4.2"), or list its notes')
    s.add_argument("id", type=int)
    s.add_argument("text", nargs="*")
    s.add_argument("--delete", type=int, metavar="NOTE_ID")
    s = add("watch", cmd_watch, "live tail of incidents")
    s.add_argument("--interval", type=int, default=15)
    s.add_argument("--min-severity", choices=["medium", "high", "critical"], default="medium")
    s.add_argument("--notify", action="store_true", help="also send desktop notifications")
    s.add_argument("--once", action="store_true", help=argparse.SUPPRESS)
    s = add("analyze", cmd_analyze, "run the engine offline on a CSV (no server needed)")
    s.add_argument("file")
    s.add_argument("--metric")
    s.add_argument("--agg", choices=["sum", "mean"], default="sum")
    s.add_argument("--bad", choices=["up", "down", "both"], default="both")
    s.add_argument("--top", type=int, default=5)
    s = add("send", cmd_send, "send one data point")
    s.add_argument("metric")
    s.add_argument("value", type=float)
    s.add_argument("--dim", action="append", metavar="KEY=VALUE")
    s.add_argument("--mean", action="store_true")
    s = add("label", cmd_label, "label an incident to train the alert filter")
    s.add_argument("id", type=int)
    s.add_argument("label", choices=["real", "false", "clear"])
    add("train", cmd_train, "retrain models now")
    add("models", cmd_models, "model status")
    add("tiers", cmd_tiers, "the three models (Orbit, Area, Time): cost, speed, accuracy")
    s = add("tier", cmd_tier, "set the workspace default model")
    s.add_argument("tier", choices=["orbit", "area", "time"])
    s = add("compare", cmd_compare, "run Orbit, Area and Time on one metric right now")
    s.add_argument("metric")
    s = add("settings", cmd_settings, "show or change settings")
    s.add_argument("--sensitivity", type=float, help="0.2-0.95 or a percentage")
    s.add_argument("--min-change", type=float, help="ignore changes smaller than this %%")
    s.add_argument("--slack", help="Slack incoming webhook URL ('' to clear)")
    s.add_argument("--demo", choices=["on", "off"])
    s.add_argument("--test-slack", action="store_true")
    s = add("key", cmd_key, "show, copy or rotate the API key")
    s.add_argument("--rotate", action="store_true")
    s.add_argument("--copy", action="store_true")
    s = add("alerts", cmd_alerts, "alerts sent to Slack")
    s.add_argument("--limit", type=int, default=20)
    s = add("demo", cmd_demo, "list / inject demo incidents, or reset")
    s.add_argument("scenario", nargs="?")
    add("integrations", cmd_integrations, "list supported tools")
    s = add("connect", cmd_connect, "connect a tool: kepler connect datadog api_key=… app_key=… query=… metric=…")
    s.add_argument("type")
    s.add_argument("fields", nargs="*", metavar="FIELD=VALUE")
    s.add_argument("--name")
    s.add_argument("--every", type=int, default=5, help="minutes between pulls")
    s.add_argument("--agg", choices=["sum", "mean"])
    s.add_argument("--alert-when", choices=["up", "down", "both"])
    s.add_argument("--min-severity", choices=["medium", "high", "critical"], default="high")
    s.add_argument("--test", action="store_true", help="only test, don't save")
    s.add_argument("--force", action="store_true", help="save even if the test fails")
    s.add_argument("--help-fields", action="store_true")
    s = add("pulls", cmd_pulls, "scheduled pulls: list | run ID | rm ID")
    s.add_argument("action", nargs="?", choices=["list", "run", "rm"], default="list")
    s.add_argument("id", nargs="?", type=int)
    s = add("destinations", cmd_destinations, "incident destinations: list | rm ID")
    s.add_argument("action", nargs="?", choices=["list", "rm"], default="list")
    s.add_argument("id", nargs="?", type=int)
    s = add("import", cmd_import, "upload a CSV of history to the server")
    s.add_argument("file")
    s.add_argument("--metric")
    s.add_argument("--agg", choices=["sum", "mean"], default="sum")
    s.add_argument("--bad", choices=["up", "down", "both"], default="both")
    s = add("open", cmd_open, "open the dashboard: kepler open [incident 40 | metric signups | incidents | models …]")
    s.add_argument("what", nargs="?")
    s.add_argument("target", nargs="?")
    s = add("copy", cmd_copy, "copy to clipboard: key | decision ID | <metric>")
    s.add_argument("what")
    s.add_argument("target", nargs="?")
    s = add("agent", cmd_agent, "background watcher with desktop notifications: install | uninstall | status | run")
    s.add_argument("action", choices=["install", "uninstall", "status", "run"])
    s.add_argument("--min-severity", choices=["medium", "high", "critical"], default="high")
    s.add_argument("--interval", type=int, default=30)
    s.add_argument("--print", action="store_true", help="print the service definition instead of installing")
    s.add_argument("--test-notification", action="store_true")
    s = add("completion", cmd_completion, "shell completion script: kepler completion zsh|bash")
    s.add_argument("shell", choices=["zsh", "bash"])
    s = add("config", cmd_config, "show or save server URL / key")
    s.add_argument("--set-url")
    s.add_argument("--set-key")
    s = sub.add_parser("__complete")
    s.add_argument("kind")
    s.set_defaults(fn=cmd_complete)
    return p


def main(argv=None) -> int:
    global console
    args = build_parser().parse_args(argv)
    if getattr(args, "no_color", False) or "NO_COLOR" in os.environ:
        console = Console(no_color=True, highlight=False)
    if not getattr(args, "fn", None):  # bare `kepler` → full-screen app
        args.fn, args.no_welcome = cmd_ui, False
        if not sys.stdout.isatty():
            build_parser().print_help()
            return 0
    try:
        return args.fn(args) or 0
    except KeplerError as e:
        err.print(f"[bold red]error:[/] {e}")
        return 3
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
