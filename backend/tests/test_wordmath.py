"""Word problems, series, sequences and textual maths: right answers, checks, and no hijacking of Kepler commands."""
import random
import time

import pytest

from kepler.bot.reasoning import solve_text
from kepler.bot.wordmath import words_to_numbers

ANSWERS = {
    # series and sums
    "sum of first n natural numbers": "n·(n + 1)/2",
    "sum of the first n digits": "n·(n + 1)/2",
    "sum of first 100 natural numbers": "5050",
    "what is the sum of the first ten odd numbers?": "100",
    "sum of first n odd numbers": "n^2",
    "sum of first n even numbers": "n·(n + 1)",
    "sum of the first n squares": "n·(n + 1)·(2·n + 1)/6",
    "sum of first 10 cubes": "3025",
    "sum of the first 5 primes": "28",
    "sum of first 10 fibonacci numbers": "143",
    "sum of all integers from 1 to 100": "5,050",
    "sum of even numbers between 1 and 100": "2,550",
    "sum of all multiples of 3 or 5 below 1000": "233,168",
    "how many multiples of 7 below 100": "14",
    "sum of the digits of 98765": "35",
    "how many digits are in 2^100": "31",
    "digital root of 987654": "3",
    "sum of k^2 for k from 1 to 10": "385",
    # sequences
    "what comes next 2, 4, 8, 16": "32",
    "next number in the sequence 2, 6, 12, 20, 30": "42",
    "what is the next number 1, 1, 2, 3, 5, 8": "13",
    "20th term of 3, 7, 11, 15": "79",
    "nth term of 5, 8, 11, 14": "3·n + 2",
    "sum of first 10 terms of 2, 4, 6, 8": "110",
    # number facts
    "the 10th prime": "29",
    "how many primes below 100": "25",
    "30th fibonacci number": "832,040",
    "divisors of 36": "1, 2, 3, 4, 6, 9, 12, 18, 36",
    "how many divisors does 360 have": "24",
    "is 28 a perfect number": "yes",
    "is 91 divisible by 7": "yes",
    "255 in binary": "11111111",
    "convert 255 to hex": "ff",
    "binary 1011 to decimal": "11",
    "1994 in roman numerals": "MCMXCIV",
    "roman mcmxciv": "1994",
    "square of 12": "144",
    "half of 90": "45",
    # counting and probability
    "10 choose 3": "120",
    "how many ways to choose 3 people from 10": "120",
    "how many ways can you arrange 5 books": "120",
    "arrangements of the letters in banana": "60",
    "handshakes among 10 people": "45",
    "probability of rolling a sum of 7 with two dice": "1/6 ≈ 0.1666666667",
    "probability of exactly 3 heads in 5 tosses": "0.3125",
    # units
    "convert 5 km to miles": "3.107 miles",
    "100 f to c": "37.78 °C",
    "how many seconds in a day": "86,400 seconds",
    "2 gb in mb": "2000 mb",
    # algebra with conditions
    "if a + b = 10 and a - b = 4, what is a*b": "21",
    "if x = 3, what is 2x^2 + 1": "19",
    "f(x) = 2x + 3, find f(5)": "13",
    "if f(x) = x^2 + 1, what is f(2) + f(3)": "15",
    "find x if 3x - 7 = 11": "6",
    "if 2x + y = 7 and x - y = 2, find x and y": "x = 3, y = 1",
    # "a number"
    "5 more than twice a number is 17": "the number is 6",
    "twice a number plus 5 is 17. what is the number?": "the number is 6",
    "three times a number minus 4 equals 11": "the number is 15",
    "the sum of a number and 9 is 25": "the number is 16",
    "a number divided by 4 is 6": "the number is 24",
    "half of a number is 21": "the number is 42",
    "a number is doubled and then increased by 7, the result is 31. find the number": "the number is 12",
    "i think of a number, multiply it by 3, subtract 5 and get 16": "the number is 7",
    # classic word problems
    "the sum of two numbers is 30 and their difference is 4": "17 and 13",
    "two numbers have a sum of 40 and one is 3 times the other": "30 and 10",
    "the sum of two numbers is 13 and their product is 40": "8 and 5",
    "the sum of three consecutive integers is 51": "16, 17, 18",
    "two consecutive even numbers add up to 46": "22, 24",
    "the product of two consecutive integers is 72": "8, 9",
    "tom is twice as old as jerry. the sum of their ages is 36. how old is jerry?": "Jerry is 12",
    "anna is 5 years older than ben. in 3 years the sum of their ages will be 31. how old is ben?": "Ben is 10",
    "a father is 4 times as old as his son. in 20 years, he will be twice as old as his son. how old is the son?": "Son is 10",
    "a farm has chickens and cows. there are 30 heads and 74 legs. how many of each?": "23 chickens and 7 cows",
    "a car travels 120 km in 2 hours. what is its speed?": "60 km/h",
    "how long does it take to travel 300 km at 60 km/h?": "5 hours",
    "how far can you go in 3 hours at 50 mph?": "150 miles",
    "a train covers 90 km in 45 minutes. what is its speed?": "120 km/h",
    "a car goes to a city at 60 km/h and returns at 40 km/h. what is the average speed?": "48",
    "a shirt costs $40 and is 25% off. what is the sale price?": "$30",
    "a meal costs 50 plus 8% tax": "54",
    "bought a bike for 2000 and sold it for 2500, what is the profit percent?": "profit of 500 (25%)",
    "simple interest on 1000 at 5% for 3 years": "interest 150 (amount 1,150)",
    "compound interest on 1000 at 10% for 2 years compounded annually": "interest 210 (amount 1,210)",
    "if 3 pencils cost 1.50, how much do 10 pencils cost?": "5",
    "if 5 workers can build a wall in 12 days, how long will 6 workers take?": "10 days",
    "a can do a job in 6 hours and b can do it in 3 hours. how long working together?": "2 hours",
    "a pipe fills a tank in 4 hours and another empties it in 6 hours. how long to fill it with both open?": "12 hours",
    "the average of 5 numbers is 20. four of them are 10, 15, 25 and 30. what is the fifth?": "20",
    "the average of 4 tests is 85. what score on the 5th test to get an average of 88?": "100",
    "divide 120 in the ratio 3:5": "45 and 75",
    "share $500 between two people in the ratio 2:3": "$200 and $300",
    "the ratio of boys to girls is 3:2 and there are 30 students in total. how many boys?": "18 boys",
}

KEPLER = ["show the last 5 incidents", "how many incidents are open", "how many incidents in the last 24 hours",
          "what's the average latency", "why did signups drop in the last 2 hours", "compare the three models",
          "is signups ok", "switch to time", "show me the next incident", "explain #40", "label 40 real",
          "set sensitivity to 70%", "break down api_errors by region", "what happened in the last 3 days",
          "plot signups for 6 hours", "how long has api_errors been high", "show p95_latency_ms last 6h",
          "how much did signups drop", "hello", "copy decision 40", "inject the ios release bug",
          "what's the status of job_failures", "open incident 12", "which segment of signups is off",
          "connect datadog", "train the models", "how do i connect prometheus", "show two incidents"]


@pytest.mark.parametrize("q", list(ANSWERS))
def test_word_answers(q):
    s = solve_text(q)
    assert s is not None and s.ok, q
    assert s.answer == ANSWERS[q]
    assert s.steps
    assert "✗" not in s.check


@pytest.mark.parametrize("q", KEPLER)
def test_kepler_commands_are_not_maths(q):
    assert solve_text(q) is None


def test_number_words():
    assert words_to_numbers("three hundred and forty-two apples") == "342 apples"
    assert words_to_numbers("twenty five and a dozen") == "25 and 12"
    assert words_to_numbers("one is 3 times the other") == "one is 3 times the other"


@pytest.mark.parametrize("q", ["sum of first 10^20 natural numbers", "sum of first 999999999999999 primes",
                               "the 99999999th prime", "99999999999 choose 5000", "10000000th fibonacci number",
                               "probability of exactly 3 heads in 100000 tosses", "primes below 99999999999",
                               "sum of k^k for k from 1 to 10^9"])
def test_huge_word_questions_are_refused_fast(q):
    t = time.time()
    s = solve_text(q)
    assert time.time() - t < 5
    assert s is None or not s.ok or len(s.answer) < 200


def test_random_sentences_never_crash():
    words = ("sum of first a number is twice the other more than less than heads legs years old ago in will be km "
             "hours at speed cost % off ratio : divide average of consecutive integers product probability dice "
             "choose arrange letters convert to binary prime next 2, 4, 8 if = what find f(x) x y 3 7 12 0 -5 1.5").split()
    rng = random.Random(1)
    for _ in range(400):
        q = " ".join(rng.choice(words) for _ in range(rng.randint(2, 14)))
        t = time.time()
        solve_text(q)  # may answer, refuse or pass to the bot, but never raise or hang
        assert time.time() - t < 5, q


def _pi_digits(n):
    import mpmath
    with mpmath.workdps(n + 20):  # local precision: never leak into other code
        return mpmath.nstr(mpmath.pi, n + 15, strip_zeros=False).replace(".", "")[:n]


@pytest.mark.parametrize("q,expect", [
    ("What are the sum of \"x\" digits of PI", "no formula: π is irrational and its digits follow no known pattern"),
    ("what is the sum of the first 10 digits of pi", str(sum(map(int, _pi_digits(10))))),
    ("sum of the first \"10\" digits of pi", "39"),
    ("sum of the first 100 decimal digits of pi", str(sum(map(int, _pi_digits(101)[1:])))),
    ("sum of the first 144 decimal digits of pi", "666"),
    ("first 20 digits of pi", _pi_digits(20)),
    ("the 762nd decimal of pi", "9"),
    ("how many 7s in the first 1000 digits of pi", str(_pi_digits(1000).count("7"))),
    ("sum of digits of 100!", "648"),
    ("sum of the digits of 2^1000", "1,366"),
    ("how many digits does 2^1000 have", "302"),
    ("first 10 digits of the square root of 2", "1414213562"),
])
def test_digits_of_constants_and_numbers(q, expect):
    s = solve_text(q)
    assert s is not None and s.ok, q
    assert s.answer == expect, (q, s.answer)


def test_digits_are_fast_and_capped():
    t = time.time()
    s = solve_text("sum of the first 100000 digits of pi")
    assert s.ok and time.time() - t < 5
    s = solve_text("sum of the first 10000000 digits of pi")
    assert not s.ok and "capped" in s.answer
