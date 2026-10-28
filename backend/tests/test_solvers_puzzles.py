"""Classic word problems and puzzles: positives with independently computed answers, and Kepler chatter (None)."""
import time

import pytest

from kepler.bot.solvers.puzzles import solve

# (question, substrings that must all appear in the answer)
POSITIVE = [
    # ages: d = 4m, d + 12 = 2(m + 12) -> m = 6, d = 24
    ("quick one: my dad is 4 times my age. in 12 years he will be twice my age. how old am i?", ["6"]),
    # a = 3b, a + 5 = 2(b + 5) -> b = 5
    ("Anna is three times as old as Ben. In 5 years Anna will be twice as old as Ben. How old is Ben? pls", ["5"]),
    # m = 30 + k... mom 36, son 6: 36 = 6*6; 36+9=45 vs 15*3=45
    ("mom is 30 years older than her son. in 9 years she will be 3 times as old as him. how old is the son?", ["6"]),
    # sum 50 diff 10 -> 30, 20
    ("the sum of two ages is 50 and the difference is 10, how old is the older one", ["30"]),
    ("ann and bob ages sum to 50, ann is 10 years older than bob. how old is bob?", ["20"]),
    # mixtures: 10*0.4 = 0.25(10 + w) -> w = 6
    ("how much water must be added to 10 liters of 40% acid to make it 25%?", ["6 L"]),
    # x + y = 30, .2x + .5y = 9 -> y = 10, x = 20
    ("how many liters of 20% solution and 50% solution to make 30 liters of 30% solution", ["20 L of the 20%", "10 L of the 50%"]),
    # work: 1/6 + 1/3 = 1/2 -> 2 h
    ("A can paint a house in 6 hours, B in 3 hours. together how long?", ["2 hours"]),
    # 1/4 - 1/6 = 1/12 -> 12 h
    ("a pipe fills a tank in 4 hours and another drains it in 6 hours, how long to fill with both open", ["12 hours"]),
    # 1/12 + 1/6... 1/4 + 1/12 = 1/3 -> 3 h
    ("for my homework: tom can mow a lawn in 4 hours and jerry in 12 hours. how long working together?", ["3 hours"]),
    # pairs
    ("10 people each shake hands once, how many handshakes", ["45"]),
    ("at a party of 25 people everyone shakes hands with everyone else once. how many handshakes?", ["300"]),
    ("how many diagonals does a 12-sided polygon have", ["54"]),
    ("how many diagonals in a decagon? show me the steps", ["35"]),
    ("round robin with 8 teams, how many games", ["28"]),
    # coins: n + d = 20, 5n + 10d = 140 -> d = 8, n = 12
    ("I have 20 coins, nickels and dimes, worth $1.40 total. how many of each?", ["12 nickels", "8 dimes"]),
    # d + q = 15, 10d + 25q = 270 -> 15q = 120, q = 8, d = 7
    ("there are 15 coins in a jar, all dimes and quarters, totaling $2.70. how many quarters?", ["8 quarters"]),
    # two-digit: a + b = 9, b - a = 3 -> 36
    ("a two-digit number's digits sum to 9. reversing digits increases the number by 27. find it", ["36"]),
    # a + b = 11, a - b = 5 (number decreases by 45) -> 83
    ("the digits of a two digit number add up to 11. when the digits are reversed the new number is 45 less than the original. what is the number?", ["83"]),
    # doubling
    ("lily pads double every day and cover the lake on day 48. when is it half covered?", ["47"]),
    ("bacteria double every minute and fill the jar in 60 minutes. when is the jar a quarter full?", ["58"]),
    # trains: 300 / 150 = 2 h, 120 km
    ("two trains 300 km apart travel toward each other at 60 km/h and 90 km/h. when do they meet?", ["2 hours", "120 km"]),
    # head start 120 miles, gap closes at 20 mph -> 6 h after 4pm = 10pm, 480 miles
    ("a train leaves at 2pm at 60 mph, a second train leaves the same station at 4pm at 80 mph on the same track. when does the second catch the first?", ["10:00 pm", "480"]),
    # averages: .2*90 + .5*80 + .3*70 = 18 + 40 + 21 = 79
    ("homework is 20% of grade, tests 50%, final 30%. I got 90 on homework, 80 on tests, 70 on the final. grade?", ["79"]),
    # clock: |30*3 - 5.5*15| = 7.5
    ("what is the angle between the hands of a clock at 3:15", ["7.5"]),
    # |30*9 - 0| = 270 -> 90
    ("angle between hour and minute hand at 9:00?", ["90"]),
    # |30*2 - 5.5*30| = |60 - 165| = 105
    ("clock angle at 2:30 pls", ["105"]),
    # digit counts: 7 in 1..100: 10 units + 10 tens = 20
    ("how many times is the digit 7 written from 1 to 100", ["20"]),
    # 1..1000 digit 1: 300 + 1 (from 1000) = 301
    ("how many times do you write the digit 1 when writing the numbers from 1 to 1000?", ["301"]),
    # tickets: a + c = 500, 8a + 5c = 3100 -> 3a = 600, a = 200
    ("500 tickets sold, adults $8 children $5, total $3100. how many adult tickets?", ["200"]),
    # a + c = 100, 12a + 7c = 1000 -> 5a = 300, a = 60, c = 40
    ("a play sold 100 tickets. adult tickets cost $12 and child tickets $7. they made $1000. how many child tickets were sold?", ["40"]),
    # consecutive
    ("three consecutive integers sum to 72, find them", ["23, 24, 25"]),
    # 2n + 2n+2 + 2n+4 ... x + x+2 + x+4 = 78 -> x = 24
    ("find three consecutive even integers whose sum is 78", ["24, 26, 28"]),
    # odd: x + x+2 = 56 -> 27, 29
    ("two consecutive odd numbers add up to 56. what are they?", ["27, 29"]),
    # 12 * 13 = 156
    ("two consecutive integers multiply to 156", ["12, 13"]),
    # 9*.3 + x = .5(9 + x) -> x = 3.6
    ("a 9 litre jug of 30% juice, how much pure juice to add to get 50%?", ["3.6 L"]),
    # 450 / 90 = 5 h, 200 miles
    ("pls help: two cars leave towns 450 miles apart heading toward each other at 40 mph and 50 mph, where do they meet?", ["5 hours", "200 miles"]),
    # boats: down 12, up 8 -> boat 10, current 2
    ("a boat goes 24 km downstream in 2 hours and back upstream in 3 hours. speed of the current?", ["2 km/h"]),
    # 30 / (12 - 3) = 10/3 h
    ("a boat goes 12 mph in still water, current 3 mph, how long to go 30 miles upstream", ["3 h 20 min"]),
    # 4 sig figs chatter: 1/5 + 1/7 = 12/35 -> 35/12 = 2.917
    ("A fills a pool in 5 hours, B fills it in 7 hours. how long together? 4 sig figs", ["2.917"]),
    # tester round: ages with "exactly twice", "as she will be then", "rn", sum of "X and me ages"
    ("Tom is 3 times as old as his son. In 10 years, Tom will be exactly twice as old as his son. How old is Tom now?", ["30"]),
    ("A father is 4 times as old as his daughter. In 12 years, he will be exactly twice as old as she will be then. How old is the daughter now?", ["6"]),
    ("my dad is 4 times my age. in 12 years dad will be exactly twice my age. how old am i rn", ["6"]),
    ("sum of my brother and me ages is 35. he is 3 years older than me. how old is he", ["19"]),
    # two-digit: both conditions must hold
    ("The sum of the digits of a two-digit number is 9. When the digits are reversed, the new number is 27 greater than the original. Find the original number.", ["36"]),
    ("A two-digit number is 4 times the sum of its digits. When its digits are reversed, the new number is 18 greater than the original number. Find the original number.", ["24"]),
    ("two digit number, digits add to 9. swap the digits and you get a number 27 more than the original. whats the number", ["36"]),
    # weighted grades with "30% homework" / "75 midterm" phrasing
    ("A student's course grade is computed as 30% homework, 30% midterm, and 40% final exam. Her homework average is 88 and her midterm score is 74. What final exam score does she need for an overall grade of 80?", ["78.5"]),
    ("hw is 30%, midterm 30%, final 40%. i got 88 on hw, 75 midterm, 90 final. what's my grade", ["84.9"]),
    ("need 4 liters of a 50% alcohol mix. got 30% and 70% stuff. how many liters of the 70% do i use", ["2 L of the 70%"]),
    ("tickets were 25 total, adult tix $12 and child $8, total collected $260. how many adults", ["15 adult"]),
]

NEGATIVE = [
    "is signups ok", "why did checkout_errors spike 40% at 3pm", "show incidents from the last 6 hours",
    "set sensitivity to 80%", "switch payments to area", "explain incident 42", "mark #12 as a false alarm",
    "connect datadog", "break down signups by region", "chart latency for 24h", "hi kepler", "thanks!",
    "what is a derivative", "what's the difference between mean and median", "who invented the telephone",
    "how are you",
]


@pytest.mark.parametrize("question,parts", POSITIVE)
def test_positive(question, parts):
    sol = solve(question)
    assert sol is not None, question
    for p in parts:
        assert p in sol.answer, (question, sol.answer)
    assert sol.steps


@pytest.mark.parametrize("question", NEGATIVE)
def test_negative(question):
    assert solve(question) is None


def test_fast():
    t0 = time.perf_counter()
    for qn, _ in POSITIVE:
        solve(qn)
    for qn in NEGATIVE:
        solve(qn)
    assert (time.perf_counter() - t0) / (len(POSITIVE) + len(NEGATIVE)) < 0.5
