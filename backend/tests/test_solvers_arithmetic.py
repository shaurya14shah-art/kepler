"""Everyday arithmetic, percentages and units solver: answers checked against hand-computed values, plus non-problems."""
import pytest

from kepler.bot.solvers.arithmetic import solve

# (question, substrings that must all appear in the answer). Expected values worked out by hand:
POSITIVE = [
    ("7 x 8 x 9 pls", ["504"]),
    ("348 divided by 12?", ["29"]),
    ("calc 1,284 + 3,917 - 606", ["4,595"]),                                   # 5201 - 606
    ("quick one: 15 times 12", ["180"]),
    ("(3 + 4) * 2^3", ["56"]),
    ("what is 6 + 4 / 2", ["8"]),                                              # order of operations
    ("what's 100/7? i keep mixing up the order", ["100/7", "14 2/7", "14.29"]),
    ("add 3/4 and 5/6 for my homework", ["19/12", "1 7/12"]),                 # 9/12 + 10/12
    ("multiply 7/8 by 4/21 and reduce", ["1/6"]),                             # 28/168
    ("1 3/5 ÷ 2/5", ["4"]),                                                   # 8/5 * 5/2
    ("what's 2/3 - 1/4 give it as a fraction", ["5/12"]),                     # 8/12 - 3/12
    ("2 1/4 + 1 2/3 show me the steps", ["47/12", "3 11/12"]),                # 27/12 + 20/12
    ("subtract 1/3 from 5/6", ["1/2"]),
    ("what percent is 45 of 180", ["25%"]),
    ("38 out of 50 as a percentage", ["76%"]),
    ("what percent of 80 is 12", ["15%"]),
    ("percent change from 80 to 100", ["25%", "increase"]),
    ("it went from 250 to 200, percent decrease?", ["20%", "decrease"]),
    ("price was $80 now $60 what percent off?", ["25%", "off"]),
    ("a jacket costs $68 after a 15% discount, what was the original price", ["$80.00"]),   # 68 / 0.85
    ("20% off then another 10% off a $50 shirt, final price?", ["$36.00", "28%"]),           # 50*.8*.9
    ("what is 15% of 80", ["12"]),
    ("what is 12.5% of $240", ["$30.00"]),
    ("increase 250 by 12%", ["280"]),
    ("split $600 in a 2:3 ratio", ["$240.00", "$360.00"]),
    ("reduce the ratio 18:48", ["3:8"]),
    ("convert 26.2 miles to km", ["42.16 km"]),                               # 26.2 * 1.609344 = 42.1648
    ("use 1 mile = 1.609344 km: how many km in 5 miles", ["8.047 km"]),       # 8.04672
    ("100 °F to °C", ["37.78 °C"]),                                           # 68 * 5/9
    ("98.6 F to C", ["37 °C"]),
    ("300 kelvin in celsius", ["26.85 °C"]),
    ("5 GB to MB", ["5,000 MB"]),
    ("8 GiB in MiB", ["8,192 MiB"]),
    ("how many seconds in 3 hours", ["10,800"]),
    ("2.5 kg in pounds", ["5.512"]),                                          # 2.5 / 0.45359237
    ("a backlog of 12,750 messages draining at 340 a minute, how long?", ["37.5 minutes", "37 min 30 s"]),
    ("45 requests a second over 6 hours, how many total", ["972,000"]),      # 45 * 21600
    ("99.9% uptime over 30 days in minutes", ["43.2 minutes"]),
    ("what is the downtime budget in minutes for 99.9% uptime over 30 days", ["43.2 minutes"]),               # 0.001 * 43200
    ("downtime budget for a 99.95% SLO per year", ["262.8 minutes"]),         # 0.0005 * 525600
    ("square root of 144", ["12"]),
    ("square root of 50", ["5√2", "7.071"]),
    ("cube root of 27", ["3"]),
    ("2 to the power of 10", ["1,024"]),
    ("5 cubed", ["125"]),
    ("round 3.14159 to 3 sig figs", ["3.14"]),
    ("round 2.675 to 2 decimal places", ["2.68"]),
    ("round 1234.5 to the nearest hundred", ["1,200"]),
    ("write 0.00045 in scientific notation", ["4.5 × 10^-4"]),
    ("3.2 x 10^5 in standard form", ["320,000"]),
    ("22/7 to 4 sig figs", ["3.143"]),
]

NEGATIVE = [
    "is signups ok", "why did checkout_errors spike 40% at 3pm", "show incidents from the last 6 hours",
    "set sensitivity to 80%", "switch payments to area", "explain incident 42", "mark #12 as a false alarm",
    "connect datadog", "break down signups by region", "chart latency for 24h", "hi kepler", "thanks!",
    "what is a derivative", "what's the difference between mean and median", "who invented the telephone",
    "how are you",
]


@pytest.mark.parametrize("question,expected", POSITIVE)
def test_solves(question, expected):
    sol = solve(question)
    assert sol is not None, question
    for e in expected:
        assert e in sol.answer, (question, sol.answer)
    assert sol.steps


@pytest.mark.parametrize("question", NEGATIVE)
def test_passes(question):
    assert solve(question) is None
