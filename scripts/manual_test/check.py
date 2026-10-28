"""Manual test kit: did Kepler catch the real labelled anomalies? Compares its incidents with schedule.json.

    backend/.venv/bin/python -I scripts/manual_test/check.py

An anomaly counts as caught when Kepler opened an incident on that metric inside the anomaly's labelled window, and
for tweets on that company's slice (or naming it in "where"). The labels come from the Numenta Anomaly Benchmark.
Incidents near no label are listed too: they're false alarms, or real events the benchmark didn't label.
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from kepler.cli.client import Client, KeplerError

SCHEDULE = Path(__file__).resolve().parents[2] / "backend" / "data" / "manual-test" / "schedule.json"


def matches(inc: dict, a: dict) -> bool:
    if inc["metric"] != a["metric"] or not a["window"][0] <= inc["started_at"] <= a["window"][1]:
        return False
    if not a["slice"]:
        return True
    dim, val = a["slice"].split("=", 1)
    return inc.get("slice") == a["slice"] or any(w["dimension"] == dim and w["value"] == val for w in inc.get("where") or [])


def when(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%a %d %b %H:%M")


def main() -> int:
    if not SCHEDULE.exists():
        sys.exit("no schedule yet: run scripts/manual_test/setup.py first")
    plan = json.loads(SCHEDULE.read_text())
    try:
        incs = Client(plan["url"]).get("/api/incidents", limit=500)
    except KeplerError as e:
        sys.exit(f"can't reach the Kepler test server: {e}")
    now = int(time.time())
    live = [a for a in plan["anomalies"] if a["at"] > plan["created"]]  # the ones that happen after setup
    used = set()
    print("labelled real anomalies since setup:")
    caught = 0
    for a in live:
        name = a["metric"] + (f" · {a['slice']}" if a["slice"] else "")
        hit = [i for i in incs if matches(i, a)]  # a real event often starts before NAB's label: early catches count
        used |= {i["incident_id"] for i in hit}
        if not hit and a["at"] > now:
            print(f"  …  {when(a['at'])}  {name}  (in {(a['at'] - now) // 60} min)")
            continue
        if hit:
            caught += 1
            first = min(hit, key=lambda i: i["started_at"])
            lag = (first["started_at"] - a["at"]) // 60
            print(f"  ✓  {when(a['at'])}  {name}  → incident #{first['incident_id']} "
                  f"({first['severity']}, {first['confidence']:.0%}, {lag:+d} min vs the label)")
        elif now < a["window"][1]:
            print(f"  ·  {when(a['at'])}  {name}  (not yet; its window runs until {when(a['window'][1])})")
        else:
            print(f"  ✗  {when(a['at'])}  {name}  (missed)")
    due = [a for a in live if a["at"] <= now or any(matches(i, a) for i in incs)]
    print(f"\ncaught {caught} of {len(due)} so far")
    other = [i for i in incs if i["incident_id"] not in used and i["started_at"] >= plan["created"]]
    if other:
        print(f"\n{len(other)} other incident(s) since setup (false alarms, or real events NAB didn't label):")
        for i in other[:15]:
            print(f"  #{i['incident_id']}  {when(i['started_at'])}  {i['metric']}{' · ' + i['slice'] if i.get('slice') else ''}"
                  f"  {i['direction']} {i['change_pct']:+.0f}%  ({i['status']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
