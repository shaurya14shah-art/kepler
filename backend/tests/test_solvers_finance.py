"""The finance solver: personal finance and business maths in chatty English, with exact answers; None for the rest."""
import time

import pytest

from kepler.bot.solvers.finance import solve

# (question, a substring the answer must contain) - expected values computed independently and checked by hand
POSITIVE = [
    # tester round: compounding wording, lump sum vs plan, payment caps, payment counts, tip after tax, changes over years
    ("I invest $5,000 at 6% per year compounded monthly for 10 years. What is the balance at the end?", "$9,096.98"),
    ("What is the future value of 250k invested at 4% per year compounded semi-annually for 5 years?", "304,748.60"),
    ("How much should I invest today at 5% per year compounded annually to have $20,000 in 8 years?", "$13,536.79"),
    ("What is the largest loan I can afford if my monthly payment can be no more than $1,500, at 4.8% APR over 30 years?", "$285,896.52"),
    ("I deposit $200 at the end of each month for 20 years into an account paying 5% APR compounded monthly, what is the future value?", "$82,206.73"),
    ("A dinner bill is $84.50 before tax. Sales tax is 7%, then an 18% tip is calculated on the bill after tax. The total is split evenly among 4 people. How much does each person pay?", "$26.67 per person"),
    ("A $15,000 car loan has 5% APR and 60 monthly payments. What is the total interest paid over the life of the loan?", "$1,984.20 total interest"),
    ("A stock rises 20% one year and then falls 20% the next year. What is the net percentage change over the two years?", "-4%"),
    ("$2,000 lump sum, 12% APR compounded monthly, 4 years. what's it worth at the end", "$3,224.45"),
    ("how much do i need to invest today at 5% annual to have 50k in 8 years", "33,841.97"),
    ("put 500 a month in for 10 years at 8% compounded monthly, what's the balance at the end", "91,473.02"),
    ("bill is 120 before tax, 8% tax, then 18% tip on the total, split 4 ways, per person?", "38.23 per person"),
    # compound interest, every compounding, amounts written many ways
    ("10k at 5% compounded quarterly for 3 years, how much?", "11,607.55"),
    ("250k invested at 4% compounded daily for 2 years pls", "270,820.58"),
    ("$1,000 at 5% compounded continuously for 10 years, exact form if you can", "$1,648.72"),
    ("for my homework: $8,000 invested at 3.5% compounded annually for 6 years, show me the steps", "$9,834.04"),
    ("what will 2,500 dollars grow to at 6% interest compounded monthly over 3 years?", "$2,991.70"),
    ("Quick one: I put 5000 in a savings account paying 3% compounded semiannually. How much after 7 years?", "6,158.78"),
    ("pls help, 1.2m at 2% compounded annually for 3 years?", "1,273,449.60"),
    ("10 thousand dollars at 3% compounded semi-annually for 4 years", "$11,264.93"),
    ("ten thousand at 5% compounded annually for 2 years", "11,025.00"),
    ("$5,000 at 6% compounded monthly for 3 years, exact form if you can", "$5,983.40"),
    ("$1,000 at 4% compounded annually for 5 years, 4 sig figs", "$1,217"),
    # present value
    ("how much should I invest today to have $20,000 in 5 years at 6% compounded annually", "$14,945.16"),
    ("present value of $50,000 due in 8 years at 5% compounded quarterly", "$33,599.20"),
    ("how much do i need today to have 100k in 10 years if i earn 8% a year", "46,319.35"),
    ("how much to invest now at 7% compounded continuously to have 1 million in 30 years", "122,456.43"),
    # doubling time
    ("how long to double my money at 8% compounded annually? also rule of 72", "9.006 years"),
    ("rule of 72: how long to double at 6%", "12 years"),
    ("at 9% interest how many years until my investment doubles", "8.043 years"),
    ("how long to double money at 5% compounded continuously", "13.86 years"),
    # loans and mortgages
    ("monthly payment on a $300,000 mortgage at 6.5% for 30 years", "$1,896.20 a month"),
    ("what's the monthly payment on a 200k loan at 4% over 15 years", "1,479.38 a month"),
    ("car loan 25,000 at 3.9% for 60 months, monthly payment?", "459.29 a month"),
    ("what's the EMI on a 10 lakh loan at 9% for 5 years", "20,758.36 a month"),
    ("30 year mortgage, $450,000, 7% interest, how much is the monthly payment and total interest",
     "$2,993.86 a month; $627,789.60 total interest"),
    ("total interest paid on a $20,000 car loan at 5% for 5 years", "$2,645.20 total interest"),
    ("how much interest will i pay in total on a $15,000 loan at 6% for 3 years", "$1,427.88 total interest"),
    # affordability
    ("i can afford $1,500 a month, at 7% for 30 years how big a loan can i get", "$225,461.35"),
    ("max loan if i can pay $800 a month for 5 years at 6%", "$41,380.45"),
    ("how much house can i afford with $2,000 a month at 6% for 30 years", "$333,583.23"),
    # savings plans
    ("how much do i need to deposit monthly to reach $100,000 in 10 years at 6%", "$610.21 a month"),
    ("need $50,000 in 5 years, earning 4% compounded monthly, how much per month should I save", "$754.16 a month"),
    ("if i save $200 a month at 5% for 20 years how much will i have", "$82,206.73"),
    ("put away $500 every month at 7% for 30 years, future value?", "$609,985.50"),
    # simple interest
    ("simple interest on $5,000 at 4% for 90 days", "$49.32"),
    ("simple interest on 1.2m at 3% for 8 months", "24,000.00"),
    ("simple interest: $2,000 at 6% for 18 months", "$180.00"),
    ("$1,500 borrowed at 8% simple interest for 120 days, interest?", "$39.45"),
    ("$5,000 at 6% simple interest for 3 years, total amount", "$5,900.00"),
    # effective annual rate
    ("what's the effective annual rate of a 12% APR compounded monthly", "12.68%"),
    ("effective annual rate for 6% compounded quarterly", "6.136%"),
    ("6% apr compounded daily, what's the apy", "6.183%"),
    # inflation
    ("$10,000 today, inflation 3% for 10 years, what is it worth in real terms", "$7,440.94"),
    ("if inflation is 2.5% a year, what will $1,000 be worth in real terms in 20 years", "$610.27"),
    ("real return if nominal return is 8% and inflation is 3%", "4.854%"),
    # profit, loss, markup
    ("bought for $80 sold for $100, percentage profit?", "25% profit"),
    ("I bought a bike for $250 and sold it for $200, what's my percentage loss", "20% loss"),
    ("cost $40, markup 25%, selling price?", "$50.00"),
    ("marked up a $60 item by 40%, what is the price", "$84.00"),
    # discount and tax chains, successive changes
    ("a $120 jacket is 25% off then 8% sales tax, final price", "$97.20"),
    ("a $80 shirt with 30% off and then 6% tax", "$59.36"),
    ("a $250 tv is 20% off, then another 10% off, sales tax 7%, final price?", "$192.60"),
    ("price goes up 20% then down 20%, net change?", "-4%"),
    ("stock goes up 50% then down 50%, overall change?", "-25%"),
    ("a price increases by 10% then by 10% again, total percentage change", "+21%"),
    ("a 15% decrease followed by a 15% increase, net?", "-2.25%"),
    # tips, tax and splitting
    ("dinner bill $84, 18% tip and 8% tax, split between 4 people", "$26.46 per person"),
    ("bill is $120, tip 20%, split 3 ways", "$48.00 per person"),
    ("$45 lunch, 20% tip, split 3 ways", "$18.00 per person"),
    ("$65 meal plus 15% tip, how much in total?", "$74.75"),
    # break-even
    ("fixed costs $12,000, price $50 per unit, variable cost $30 per unit, break-even units", "600 units"),
    ("break even: fixed costs 5000, selling price 25 each, variable cost 15 each", "500 units"),
    ("we sell mugs at $12 each, cost $4 each to make, fixed costs $2,400 a month. how many mugs to break even?",
     "300 units"),
    # margins
    ("revenue $500,000, cogs $300,000, net income $50,000, gross and net margin", "gross margin 40%, net margin 10%"),
    ("revenue 200k, cost of goods sold 120k, gross margin?", "40%"),
    ("net profit margin with revenue 1.2m and net profit 150k", "12.5%"),
    # progressive tax
    ("tax on $50,000 income: 10% on first $10,000, 20% on next $30,000, 30% above $40,000", "$10,000.00"),
    ("income $85,000, brackets: 10% up to $11,000, 12% from $11,000 to $44,725, 22% above $44,725. tax owed?",
     "$14,007.50"),
    # geometric average return
    ("returns of 10%, -5%, 20% over three years, geometric average annual return", "7.837%"),
    ("yearly returns 5%, 10%, -3%, 8%, what's the geometric mean return", "4.88%"),
    ("my returns were 20%, -10%, 15%, 5% - average annual return (geometric)?", "6.863%"),
    # ROI
    ("invested $2,000, now worth $2,600, roi?", "30%"),
    ("I invested 1000 and got back 1250, what's my return on investment", "25%"),
    ("bought shares for $1,200, sold for $1,500, plus $60 dividends, ROI?", "30%"),
    # salary
    ("$25 an hour, 40 hours a week, annual salary", "$52,000.00 a year"),
    ("$78,000 a year salary to hourly", "$37.50 an hour"),
    ("$20/hr full time, what's that annually", "$41,600.00 a year"),
    ("$35/hour, 37.5 hours a week, 52 weeks, annual?", "$68,250.00 a year"),
    ("$60,000 salary, 2080 hours, hourly rate?", "$28.85 an hour"),
    ("40k a year is how much per hour", "19.23 an hour"),
]

NEGATIVE = [
    "is signups ok", "why did checkout_errors spike 40% at 3pm", "show incidents from the last 6 hours",
    "set sensitivity to 80%", "switch payments to area", "explain incident 42", "mark #12 as a false alarm",
    "connect datadog", "break down signups by region", "chart latency for 24h", "hi kepler", "thanks!",
    "what is a derivative", "what's the difference between mean and median", "who invented the telephone",
    "how are you", "what is compound interest", "what is APR", "what is the rule of 72",
    "why is revenue down 5% this week", "show me revenue for the last 30 days", "alert me if signups drop 20%",
    "compare signups and revenue", "forecast revenue for next 3 months",
]


@pytest.mark.parametrize("q,want", POSITIVE)
def test_solves(q, want):
    sol = solve(q)
    assert sol is not None, q
    assert want in sol.answer, (q, sol.answer)
    assert sol.steps and sol.kind == "finance"


@pytest.mark.parametrize("q", NEGATIVE)
def test_passes(q):
    assert solve(q) is None


def test_steps_have_formula_and_substitution():
    sol = solve("monthly payment on a $300,000 mortgage at 6.5% for 30 years")
    text = "\n".join(sol.steps)
    assert "formula:" in text and "substitute:" in text and "result:" in text


def test_fast():
    t0 = time.perf_counter()
    for q, _ in POSITIVE:
        solve(q)
    for q in NEGATIVE:
        solve(q)
    assert (time.perf_counter() - t0) / (len(POSITIVE) + len(NEGATIVE)) < 0.25
