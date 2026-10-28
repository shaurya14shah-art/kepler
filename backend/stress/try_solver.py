"""Run questions through one subject solver, or through the whole chat, and print what Kepler answers.

    echo '["a 2 kg ball at 3 m/s, kinetic energy?", "is signups ok"]' | .venv/bin/python -I stress/try_solver.py physics
    echo '[...]' | .venv/bin/python -I stress/try_solver.py all      # the whole chat (Mind), as a user would see it

Prints one JSON object per question: {"question", "answer" (null when the solver passed), "ok", "kind", "steps"}.
"""
import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["KEPLER_WEB"] = "off"


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    questions = json.load(sys.stdin)
    if which == "all":
        import kepler.device as device
        device.HOME = Path(tempfile.mkdtemp(prefix="kepler-try-"))
        from kepler.bot.mind import Mind
    else:
        mod = importlib.import_module(f"kepler.bot.solvers.{which}")
    for q in questions:
        if which == "all":
            th = Mind().think(q)
            sol = th.solution if th.kind in ("math", "steps") else None
            if sol is None:
                print(json.dumps({"question": q, "answer": None, "routed_to": th.kind, "ok": False}, ensure_ascii=False))
                continue
        else:
            try:
                sol = mod.solve(q)
            except Exception as e:  # a crash is a bug to report, not a reason to stop
                print(json.dumps({"question": q, "answer": None, "ok": False, "error": repr(e)}, ensure_ascii=False))
                continue
        out = {"question": q, "answer": sol.answer if sol else None, "ok": bool(sol and sol.ok),
               "kind": sol.kind if sol else None, "steps": sol.steps if sol else []}
        print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
