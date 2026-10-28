"""Electrical solver: exact answers in varied phrasings, and None for everything that is not this kind of problem."""
import pytest

from kepler.bot.solvers.electrical import solve

POSITIVE = [
    # Ohm's law
    ("a 12 V battery is connected to a 4 ohm resistor, what's the current? pls show steps", "3 A"),
    ("what voltage is needed to push 20 mA through a 4.7 kΩ resistor", "94 V"),
    ("resistance if 9 V gives 3 mA", "3 kΩ"),
    ("quick one: 5 V across 1.5 MΩ, current? 3 sig figs", "≈ 3.33 µA"),
    ("find the current when 230V is applied across 46 ohms", "5 A"),
    ("voltage across a 2.2 kilohm resistor with 5 mA flowing", "11 V"),
    ("what resistance draws 50 µA from 1.5 V?", "30 kΩ"),
    ("I = 0.5 A and R = 24 ohm, what is the voltage", "12 V"),
    ("for my homework: a 3 kV supply drives 2 mA, find the resistance", "1.5 MΩ"),
    ("current through 1 kΩ with 250 mV across it", "250 µA"),
    # power
    ("quick one: how many amps does a 2300 W kettle draw on 230 V?", "10 A"),
    ("a 60W bulb runs on 240V, find its resistance", "960 Ω"),
    ("current through a 100 ohm resistor dissipating 4 W", "200 mA"),
    ("power dissipated in a 10 kilohm resistor carrying 2 mA", "40 mW"),
    ("12 V across 8 ohms, power?", "18 W"),
    ("a motor draws 5 A at 24 V, what is its power", "120 W"),
    ("what voltage gives 50 W in a 2 ohm resistor", "10 V"),
    ("current in a 2 ohm resistor dissipating 4 W? exact form if you can", "√2 A ≈ 1.414 A"),
    # networks
    ("100 ohm || 200 ohm", "200/3 Ω ≈ 66.67 Ω"),
    ("resistors of 2, 3 and 6 ohms all in parallel, equivalent resistance?", "1 Ω"),
    ("three 6 Ω resistors in series, total resistance", "18 Ω"),
    ("a 100 Ω resistor in series with a parallel pair of 200 Ω and 300 Ω, total?", "220 Ω"),
    ("200 Ω and 300 Ω in parallel, then in series with 100 Ω. total resistance", "220 Ω"),
    ("10 kΩ and 10 kΩ in parallel", "5 kΩ"),
    ("(100 Ω + 200 Ω) || 300 Ω", "150 Ω"),
    ("a 9 V battery with 100 Ω and 200 Ω in series, what current flows?", "30 mA"),
    ("12 V across 4 ohm and 12 ohm in parallel, total current?", "4 A"),
    ("a 12 V supply drives 2 Ω, 4 Ω and 6 Ω in series, voltage across the 4 Ω", "4 V"),
    # energy and cost
    ("a 2 kW heater runs for 3 hours, how much energy in kWh", "6 kWh"),
    ("energy used by a 100 W lamp in 10 minutes in joules", "60 kJ"),
    ("a 1500 W heater used 4 hours a day for 30 days at $0.15 per kWh, what does it cost?", "$27.00"),
    ("60 W bulb 5 hours a day for a week at 12 cents per kWh cost?", "$0.25"),
    ("how much does it cost to run a 2.5 kW oven for 90 minutes at 20c/kWh", "$0.75"),
    ("cost of 350 kWh at £0.28 per kWh", "£98.00"),
    ("a 40 W laptop on for 8 hours, energy in Wh", "320 Wh"),
    # battery
    ("a 3000 mAh battery powering a 250 mA load, how long will it last", "12 h"),
    ("how long will a 2000 mAh battery last at 300 mA", "20/3 h ≈ 6.667 h (6 h 40 min)"),
    ("a 3.7 V 2500 mAh battery, how many Wh", "9.25 Wh"),
    ("a 50 Wh power bank running a 10 W device, runtime?", "5 h"),
    # charge
    ("charge if 2 A flows for 5 minutes", "600 C"),
    ("how many electrons pass when 1 A flows for 1 s", "≈ 6.242×10^18 electrons"),
    ("30 C passes in 6 s, what current", "5 A"),
    # dividers
    ("voltage divider 12 V with R1 = 10k and R2 = 4.7k, output voltage?", "188/49 V ≈ 3.837 V"),
    ("voltage divider: 9 V in, R1 = 1 kΩ, R2 = 2 kΩ, Vout across R2?", "6 V"),
    ("voltage divider from 5 V to 3.3 V with R1 = 10 kΩ, what is R2", "19.41 kΩ"),
]

NEGATIVE = [
    "is signups ok", "why did checkout_errors spike 40% at 3pm", "show incidents from the last 6 hours",
    "set sensitivity to 80%", "switch payments to area", "explain incident 42", "mark #12 as a false alarm",
    "connect datadog", "break down signups by region", "chart latency for 24h", "hi kepler", "thanks!",
    "what is a derivative", "what's the difference between mean and median", "who invented the telephone",
    "how are you", "what is ohm's law", "a 2 kg ball at 3 m/s, kinetic energy?",
]


@pytest.mark.parametrize("q,expected", POSITIVE)
def test_positive(q, expected):
    sol = solve(q)
    assert sol is not None, q
    assert expected in sol.answer, (q, sol.answer)
    assert sol.steps and sol.steps[0].startswith("formula:")


@pytest.mark.parametrize("q", NEGATIVE)
def test_negative(q):
    assert solve(q) is None
