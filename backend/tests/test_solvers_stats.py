"""Statistics and probability solver: answers checked against independently computed values, plus non-problems."""
import pytest

from kepler.bot.solvers.stats import solve

# (question, substrings that must all appear in the answer). Expected values worked by hand:
POSITIVE = [
    ("quick one: find the mean of 3, 7, 7, 2, 9 pls", ["5.6"]),                     # 28 / 5
    ("average of 10, 20, 30, 40 show me the steps", ["25"]),
    ("median of 4, 1, 9, 6", ["5"]),                                                 # (4 + 6) / 2
    ("what's the mode of 2 3 3 5 5 7", ["3", "5"]),
    ("range of 12, 5, 30, 18", ["25"]),
    ("sample standard deviation of 2, 4, 4, 4, 5, 5, 7, 9", ["2.138"]),             # sqrt(32 / 7)
    ("population variance of 2,4,4,4,5,5,7,9", ["4"]),                              # 32 / 8
    ("sd of 1, 2, 3, 4", ["sample sd ≈ 1.291", "population sd ≈ 1.118"]),          # sqrt(5/3), sqrt(5/4)
    ("pls find the variance and standard deviation of 6, 8, 10 (population)", ["8/3", "1.633"]),
    ("ugh stats: data is 5, 1, 3, 3, 8 - median and mode?", ["median = 3", "mode = 3"]),
    ("weighted mean of 80, 90, 70 with weights 2, 3, 5", ["78"]),                   # 780 / 10
    ("weights 20%, 30%, 50% on scores 70, 80, 90 - weighted average?", ["83"]),     # 14 + 24 + 45
    ("probability that the sum of two dice is 7", ["1/6"]),                         # 6 / 36
    ("chance of rolling a sum of 8 with 2 dice", ["5/36"]),
    ("probability of rolling doubles with two dice", ["1/6"]),
    ("probability of at least one six in 4 rolls", ["671/1296"]),                   # 1 - (5/6)^4
    ("chance of getting at least one 6 when rolling a die 4 times", ["671/1296"]),
    ("probability of exactly 3 heads in 5 flips of a fair coin", ["5/16"]),         # C(5,3) / 32
    ("at least 2 heads in 4 coin tosses?", ["11/16"]),                              # 1 - 5/16
    ("chance of getting no heads in 3 coin flips", ["1/8"]),
    ("I flip a coin 10 times, probability of at least 8 heads?", ["7/128"]),        # (45 + 10 + 1) / 1024
    ("two aces in a row without replacement", ["1/221"]),                           # 4/52 * 3/51
    ("P of drawing 2 kings in a row from a deck, no replacement", ["1/221"]),
    ("probability all 5 cards are hearts in a 5-card hand", ["33/66640"]),          # C(13,5) / C(52,5)
    ("what's the probability of drawing a heart from a deck? give it as a fraction", ["1/4"]),
    ("P(king | face card)", ["1/3"]),                                                # 4 / 12
    ("how many 5-card hands are there from a standard deck", ["2,598,960"]),
    ("how many 5-card hands contain exactly 2 aces", ["103,776"]),                  # 6 * C(48,3)
    ("how many ways to choose a committee of 3 from 10 people", ["120"]),
    ("in how many ways can gold silver and bronze be awarded among 8 runners", ["336"]),
    ("how many ways can a president, vp and treasurer be chosen from 12 members", ["1,320"]),
    ("for my homework: 4 friends, how many ways to line them up", ["24"]),
    ("how many ways can you arrange the letters of MISSISSIPPI", ["34,650"]),       # 11! / (4! 4! 2!)
    ("how many arrangements of the letters in BOOK", ["12"]),                       # 4! / 2!
    ("a game costs $2 to play, you win $10 with probability 0.1, expected net gain per play?", ["-$1.00"]),
    ("raffle: 1000 tickets sold at $5 each, one prize of $2000, expected value of a ticket", ["-$3.00"]),
    ("1% have the disease, the test catches 99% and has a 5% false positive rate, P(disease | positive)?", ["1/6"]),
    ("a 2% base rate, test sensitivity 90%, false positive rate 10%, probability of having it given a positive test",
     ["9/58"]),                                                                      # .018 / .116
    ("X ~ N(100, 15), P(X > 130)?", ["0.02275"]),                                    # 1 - Φ(2)
    ("mean 50 sd 8, P(X < 60)", ["0.8944"]),                                         # Φ(1.25)
    ("N(170, 10) P(160 < X < 185)", ["0.7745"]),                                     # Φ(1.5) - Φ(-1)
    ("IQ ~N(100, 15), what is P(85 < X < 115)", ["0.6827"]),
    ("z-score of 85 if mean 70 and sd 10", ["1.5"]),
    ("height ~N(170, 10), what value is the 90th percentile", ["182.8"]),          # 170 + 1.2816 * 10
    ("scores are normally distributed with mean 70 and standard deviation 5, what score is at the 95th percentile",
     ["78.22"]),                                                                     # 70 + 1.6449 * 5
    ("binomial n=20 p=0.3 mean and variance", ["mean = 6", "variance = 4.2"]),
    ("expected number of heads in 50 flips", ["25"]),
    ("A student's course grade is weighted as follows: homework 20%, midterm 30%, final exam 50%. Her averages are 88 "
     "on homework, 75 on the midterm, and 92 on the final. What is her weighted mean grade?", ["86.1"]),
    ("grades: quiz 80 (weight 20%), midterm 70 (30%), final 90 (50%). weighted avg?", ["82"]),
    ("A committee of 4 is to be chosen from 12 people. Ann must be on the committee. How many different committees "
     "are possible?", ["165"]),
    ("A committee of 4 is to be chosen from 12 people. Bob must not be on the committee. How many committees?", ["330"]),
    ("variance and std dev of 2 4 4 4 5 5 7 9 pls, need sample and population both",
     ["sample variance = 32/7", "population variance = 4", "sample sd ≈ 2.138", "population sd = 2"]),
    ("if a card is a face card (J Q K), whats prob that its a king", ["1/3"]),
    ("how many ways can we pick a 3 person committee from 10 people", ["120"]),
]

NEGATIVE = [
    "is signups ok", "why did checkout_errors spike 40% at 3pm", "show incidents from the last 6 hours",
    "set sensitivity to 80%", "switch payments to area", "explain incident 42", "mark #12 as a false alarm",
    "connect datadog", "break down signups by region", "chart latency for 24h", "hi kepler", "thanks!",
    "what is a derivative", "what's the difference between mean and median", "who invented the telephone",
    "how are you",
]


@pytest.mark.parametrize("q,parts", POSITIVE)
def test_positive(q, parts):
    sol = solve(q)
    assert sol is not None, q
    assert sol.ok and sol.steps
    for p in parts:
        assert p in sol.answer, (q, sol.answer)


@pytest.mark.parametrize("q", NEGATIVE)
def test_negative(q):
    assert solve(q) is None


def test_sample_before_population():
    ans = solve("sd of 1, 2, 3, 4").answer
    assert ans.index("sample") < ans.index("population")
