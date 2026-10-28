"""Chemistry solver: positive cases (answers computed independently from IUPAC-style atomic masses) and negatives."""
import time

import pytest

from kepler.bot.solvers.chemistry import solve

POSITIVE = [
    # molar mass, hydrates in three notations, parentheses, names
    ("quick one: molar mass of CuSO4·5H2O pls", "249.68 g/mol"),
    ("molar mass of CuSO4.5H2O", "249.68 g/mol"),
    ("what's the molar mass of CuSO4*5H2O", "249.68 g/mol"),
    ("molar mass of Ca3(PO4)2 for my homework", "310.17 g/mol"),
    ("molar mass of caffeine", "194.19 g/mol"),
    ("molar mass of aspirin 4 sig figs", "180.2 g/mol"),
    ("molar mass of aluminum sulfate", "342.13 g/mol"),
    ("what is the molar mass of aluminium sulphate", "342.13 g/mol"),
    ("molar mass of potassium bromide", "119.00 g/mol"),
    ("molar mass of ammonium nitrate, show me the steps", "80.04 g/mol"),
    ("molar mass of calcium chloride", "110.98 g/mol"),
    ("molar mass of iron(III) oxide", "159.69 g/mol"),
    ("molar mass of iron(III) oxide Fe2O3", "159.69 g/mol"),
    # grams <-> moles <-> particles
    ("how many moles in 36 g of water", "1.998 mol"),
    ("how many grams is 2.5 mol of NaCl", "146.1 g"),
    ("how many molecules in 2 moles of CO2", "1.204 × 10^24 molecules"),
    ("how many moles is 3.011e23 molecules of water", "0.5 mol"),
    ("18 g of water, how many molecules?", "6.017 × 10^23 molecules"),
    ("convert 5 g of caffeine to moles pls", "0.02575 mol"),
    ("how many moles of KBr in 238 g", "2 mol"),
    # molarity
    ("molarity of 0.5 mol NaCl in 250 mL", "2 M"),
    ("molarity when 58.44 g NaCl dissolved in 2 L", "0.5 M"),
    ("how many grams of NaOH do I need for 500 mL of 0.2 M solution", "4 g"),
    ("grams of CuSO4·5H2O to make 250 mL of 0.1 M", "6.242 g"),
    # dilution
    ("dilute 50 mL of 2 M to 0.5 M, final volume?", "200 mL"),
    ("what volume of 12 M HCl is needed to make 1 L of 1 M", "0.08333 L"),
    ("how much water to add to 100 mL of 6 M HCl to get 1 M", "500 mL of water"),
    # percent composition
    ("percent composition of H2O", "H 11.19 %, O 88.81 %"),
    ("percent by mass of oxygen in CO2", "72.71 %"),
    ("mass percent of iron in iron(III) oxide", "69.94 %"),
    ("% N in ammonium nitrate", "35 %"),
    ("percent water in CuSO4·5H2O", "36.08 %"),
    ("how many grams of oxygen are in 88 g of CO2", "63.98 g"),
    # ideal gas
    ("volume of 1 mol of gas at 273 K and 1 atm", "22.4 L"),
    ("pressure of 2 mol gas in 10 L at 25 °C", "4.893 atm"),
    ("moles of gas at 101.3 kPa, 22.4 L and 0 °C", "0.9991 mol"),
    ("760 mmHg 500 mL 25 C how many moles of gas", "0.02044 mol"),
    ("density of CO2 at STP", "1.963 g/L"),
    # pH / pOH
    ("pH of 0.01 M HCl", "2"),
    ("pH of a 0.01 M HCl solution", "2"),
    ("pH of 0.001 M NaOH", "11"),
    ("pH of 0.05 M H2SO4", "1"),
    ("whats the pH of a 0.0025 M HNO3 solution, 3 sig figs", "2.60"),
    ("[H+] = 1e-3 M, what is the pH", "3"),
    ("pOH of solution with [OH-] = 1e-5", "5"),
    ("what is the pH when pOH is 3", "11"),
    ("pH is 7.4, what's the pOH", "6.6"),
    ("pH is 4.5, find [H+]", "10^-4.5 ≈ 3.162 × 10^-5 M"),
    ("the pH of a solution is 3.25. what is [OH-]?", "10^-10.75 ≈ 1.778 × 10^-11 M"),
    ("The hydrogen ion concentration of a solution is 3.2 × 10^-4 M. What is the pH?", "3.495"),
    ("The hydroxide ion concentration of a solution is 2.5 × 10^-3 M. What is the pOH?", "2.602"),
    ("i have 6 M HCl stock and want 500 mL of 0.5 M. how much stock do i use (C1V1=C2V2)", "41.67 mL"),
    ("Using M1V1 = M2V2, what volume of 12 M HCl is needed to make 250 mL of 1.0 M HCl?", "20.83 mL"),
]

NEGATIVE = [
    "is signups ok", "why did checkout_errors spike 40% at 3pm", "show incidents from the last 6 hours",
    "set sensitivity to 80%", "switch payments to area", "explain incident 42", "mark #12 as a false alarm",
    "connect datadog", "break down signups by region", "chart latency for 24h", "hi kepler", "thanks!",
    "what is a derivative", "what's the difference between mean and median", "who invented the telephone",
    "how are you", "what is molarity", "what is a mole", "what is pH",
]


@pytest.mark.parametrize("text,expected", POSITIVE)
def test_positive(text, expected):
    sol = solve(text)
    assert sol is not None, text
    assert sol.answer == expected, (text, sol.answer)
    assert sol.steps


@pytest.mark.parametrize("text", NEGATIVE)
def test_negative(text):
    assert solve(text) is None


def test_roman_numeral_not_iodine():
    sol = solve("molar mass of iron(III) oxide")
    assert "I" not in [s.split()[0] for s in sol.steps if s.startswith("I ")]
    assert sol.answer == "159.69 g/mol"


def test_fast():
    t0 = time.perf_counter()
    for text, _ in POSITIVE:
        solve(text)
    assert (time.perf_counter() - t0) / len(POSITIVE) < 0.5
