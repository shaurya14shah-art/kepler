"""Subject solvers: word problems in plain English, by field, each answered with worked steps and a check.

Every module has `solve(text) -> Solution | None` that reads the user's raw message (chatty phrasing included:
"quick one:", "pls", "for my homework", "4 sig figs") and returns None for anything that isn't its kind of problem,
so Kepler commands ("is signups ok", "set sensitivity to 80%") never land here. The most specific subjects go first.
"""
import importlib

from ..reasoning import Solution

ORDER = ["puzzles", "chemistry", "electrical", "physics", "finance", "stats", "geometry", "calculus", "algebra",
         "arithmetic"]


def solve(text: str) -> Solution | None:
    if len(text) > 600:
        return None
    for name in ORDER:
        try:
            mod = importlib.import_module(f"{__name__}.{name}")
        except ImportError:
            continue
        try:
            sol = mod.solve(text)
        except (ValueError, ZeroDivisionError, OverflowError, TypeError, AttributeError, KeyError, IndexError,
                RecursionError, NotImplementedError):
            continue
        if sol is not None:
            return sol
    return None
