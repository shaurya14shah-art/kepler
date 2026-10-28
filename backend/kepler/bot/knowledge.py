"""Kepler's knowledge base: what words mean (maths, statistics, monitoring, Kepler itself) and small talk.

Hand-written entries, looked up by rules (no language model). `answer()` recognises definition questions
("what is a prime number", "what does anomaly mean", "define median", "tell me about seasonality") and small
talk ("how are you", "are you an AI", "tell me a joke"), with spelling tolerance on the term.
"""
import difflib
import random
import re
from dataclasses import dataclass, field


@dataclass
class Entry:
    terms: list[str]
    text: str
    example: str = ""
    tries: list[str] = field(default_factory=list)
    topic: str = "maths"


E = Entry
ENTRIES = [
    # numbers
    E(["prime", "prime number", "primes"], "A prime is a whole number greater than 1 whose only divisors are 1 and itself.",
      "2, 3, 5, 7, 11, 13 are prime; 9 = 3 × 3 is not.", ["is 97 prime", "primes below 50", "the 10th prime"]),
    E(["composite", "composite number"], "A composite number is a whole number above 1 that is not prime: it has a divisor other than 1 and itself.",
      "12 = 2 × 6 is composite.", ["prime factors of 360"]),
    E(["integer", "integers", "whole number", "whole numbers"], "Integers are the whole numbers with no fractional part, including negatives and zero: …, −2, −1, 0, 1, 2, …",
      "7 and −3 are integers; 2.5 is not.", ["sum of all integers from 1 to 100"]),
    E(["natural number", "natural numbers", "counting numbers"], "Natural numbers are the counting numbers 1, 2, 3, … (some books include 0).",
      "The sum of the first n natural numbers is n(n + 1)/2.", ["sum of first n natural numbers"]),
    E(["even", "even number", "even numbers"], "An even number is divisible by 2 (remainder 0).", "…, −2, 0, 2, 4, 6, …", ["is 28 even", "sum of first n even numbers"]),
    E(["odd", "odd number", "odd numbers"], "An odd number leaves remainder 1 when divided by 2.", "1, 3, 5, 7, …; the first n odd numbers add up to n².", ["sum of first n odd numbers"]),
    E(["rational number", "rational", "rational numbers"], "A rational number can be written as a fraction p/q of integers with q ≠ 0.", "0.75 = 3/4 is rational; √2 and π are not.", ["7/3"]),
    E(["irrational number", "irrational"], "An irrational number cannot be written as a fraction of integers; its decimals never end or repeat.", "√2 ≈ 1.41421…, π ≈ 3.14159…", ["sqrt 2"]),
    E(["fraction", "fractions"], "A fraction a/b means a parts out of b equal parts; a is the numerator, b the denominator.", "3/4 = 0.75", ["1/4 + 1/4"]),
    E(["decimal", "decimals"], "A decimal writes a number in base 10 with a point separating whole and fractional parts.", "2.5 = 5/2", ["7/3"]),
    E(["percentage", "percent", "per cent"], "A percentage is a number out of 100: x% means x/100.", "15% of 200 = 0.15 × 200 = 30.", ["15% of 200", "30 is what percent of 120"]),
    E(["factorial"], "n! (n factorial) is the product 1 × 2 × … × n, with 0! = 1. It counts the ways to order n things.", "5! = 120", ["5!", "how many ways can you arrange 5 books"]),
    E(["fibonacci", "fibonacci sequence", "fibonacci numbers"], "The Fibonacci sequence starts 1, 1 and each next term is the sum of the previous two.", "1, 1, 2, 3, 5, 8, 13, 21, …", ["30th fibonacci number"]),
    E(["divisor", "factor", "divisors", "factors"], "A divisor (factor) of n is a whole number that divides n with no remainder.", "Divisors of 12: 1, 2, 3, 4, 6, 12.", ["divisors of 36"]),
    E(["multiple", "multiples"], "A multiple of n is n times a whole number.", "Multiples of 3: 3, 6, 9, 12, …", ["sum of all multiples of 3 or 5 below 1000"]),
    E(["gcd", "hcf", "greatest common divisor", "highest common factor"], "The GCD/HCF of numbers is the largest number that divides all of them.", "gcd(12, 18) = 6", ["gcd of 12 and 18"]),
    E(["lcm", "least common multiple", "lowest common multiple"], "The LCM of numbers is the smallest number that all of them divide.", "lcm(4, 6) = 12", ["lcm of 4, 6, 10"]),
    E(["perfect number"], "A perfect number equals the sum of its proper divisors.", "6 = 1 + 2 + 3; 28 = 1 + 2 + 4 + 7 + 14", ["is 28 a perfect number"]),
    E(["perfect square", "square number"], "A perfect square is a whole number squared.", "49 = 7²", ["is 49 a perfect square"]),
    E(["square root", "root"], "The square root of x is the number that, multiplied by itself, gives x.", "√144 = 12", ["square root of 144"]),
    E(["exponent", "power", "index", "powers"], "An exponent says how many times to multiply a number by itself: aⁿ = a × a × … (n times).", "2^10 = 1024", ["2^10"]),
    E(["logarithm", "log"], "log_b(x) is the power you raise b to in order to get x. 'log' here is base 10 and 'ln' is base e.", "log 1000 = 3 because 10³ = 1000", ["log 1000", "ln(e^2)"]),
    E(["pi", "π"], "π is the ratio of a circle's circumference to its diameter, about 3.14159.", "Circle area = πr².", ["sin(pi/2)"]),
    E(["e", "euler's number", "eulers number"], "e ≈ 2.71828 is the base of natural logarithms; it's the limit of (1 + 1/n)ⁿ.", "", ["ln(e^2)"]),
    E(["binary"], "Binary is base 2: numbers written with only 0 and 1, each place worth a power of 2.", "13 = 1101₂ (8 + 4 + 1)", ["255 in binary"]),
    E(["hexadecimal", "hex"], "Hexadecimal is base 16, using digits 0–9 and a–f.", "255 = ff₁₆", ["convert 255 to hex"]),
    E(["roman numerals", "roman numeral"], "Roman numerals use letters I V X L C D M; a smaller numeral before a larger one is subtracted.", "1994 = MCMXCIV", ["1994 in roman numerals"]),
    E(["modulo", "mod", "remainder"], "a mod b is the remainder after dividing a by b.", "17 mod 5 = 2", ["17 mod 5"]),
    # algebra & calculus
    E(["variable", "variables", "unknown"], "A variable is a letter standing for a number we don't know yet or that can change.", "In 2x + 3 = 7, x is the variable (x = 2).", ["solve 2x + 3 = 7"]),
    E(["equation", "equations"], "An equation says two expressions are equal; solving it finds the values that make it true.", "2x + 3 = 7 → x = 2", ["solve 2x + 3 = 7"]),
    E(["expression"], "An expression is a combination of numbers, variables and operations, with no equals sign.", "3x² + 2x − 1", ["expand (x+1)^3"]),
    E(["linear equation"], "A linear equation has variables only to the first power; its graph is a straight line.", "y = 3x + 2", ["solve 2x + 3 = 7"]),
    E(["quadratic", "quadratic equation"], "A quadratic equation has the form ax² + bx + c = 0; it has up to two roots, x = (−b ± √(b² − 4ac)) / 2a.", "x² − 5x + 6 = 0 → x = 2 or 3", ["x^2 - 5x + 6 = 0"]),
    E(["discriminant"], "For ax² + bx + c, the discriminant b² − 4ac tells how many real roots: >0 two, =0 one, <0 none.", "", ["x^2 + 1 = 0"]),
    E(["polynomial", "polynomials"], "A polynomial is a sum of terms like a·xⁿ with whole-number powers.", "x³ − 2x + 1", ["factor x^2 - 1"]),
    E(["function"], "A function maps each input to exactly one output, e.g. f(x) = 2x + 3.", "f(5) = 13", ["f(x) = 2x + 3, find f(5)"]),
    E(["derivative", "differentiation", "differentiate"], "The derivative measures how fast a function changes: the slope of its graph at each point.", "d/dx x³ = 3x²", ["derivative of x^3 + 2x"]),
    E(["integral", "integration", "antiderivative"], "An integral adds up a quantity continuously: the area under a curve, or the reverse of differentiation.", "∫ x² dx = x³/3 + C", ["integrate x^2 from 0 to 3"]),
    E(["limit"], "A limit is the value a function approaches as its input approaches some point.", "sin(x)/x → 1 as x → 0", ["limit of sin(x)/x as x approaches 0"]),
    E(["slope", "gradient"], "Slope is rise over run: how much y changes for each unit of x.", "y = 3x + 2 has slope 3.", ["derivative of 3x + 2"]),
    E(["sequence"], "A sequence is an ordered list of numbers following a rule.", "2, 4, 8, 16 doubles each time.", ["next number in 2, 6, 12, 20"]),
    E(["series", "summation", "sigma"], "A series is the sum of a sequence's terms; Σ is the summation sign.", "1 + 2 + … + n = n(n + 1)/2", ["sum of k^2 for k from 1 to 10"]),
    E(["arithmetic progression", "arithmetic sequence", "ap"], "An arithmetic progression adds the same number (the common difference) each time; term n = a + (n − 1)d.", "3, 7, 11, 15 (d = 4)", ["20th term of 3, 7, 11, 15"]),
    E(["geometric progression", "geometric sequence", "gp"], "A geometric progression multiplies by the same number (the common ratio) each time; term n = a·rⁿ⁻¹.", "2, 6, 18, 54 (r = 3)", ["next number in 2, 6, 18, 54"]),
    E(["ratio"], "A ratio a:b compares two quantities; it can be scaled like a fraction.", "Split 120 in 3:5 → 45 and 75.", ["divide 120 in the ratio 3:5"]),
    E(["proportion", "proportional"], "Two quantities are directly proportional if they grow at the same rate (y = kx); inversely if their product stays fixed.", "3 pencils cost 1.50 → 10 cost 5.", ["if 3 pencils cost 1.50, how much do 10 pencils cost?"]),
    # statistics & probability
    E(["mean", "average", "arithmetic mean"], "The mean (average) is the sum of the values divided by how many there are.", "mean of 4, 8, 15 = 27/3 = 9", ["average of 4, 8 and 15"], "stats"),
    E(["median"], "The median is the middle value after sorting (the average of the two middle ones if there's an even count). It ignores outliers.", "median of 3, 1, 4, 1, 5 = 3", ["median of 3 1 4 1 5"], "stats"),
    E(["mode"], "The mode is the value that appears most often.", "mode of 1, 2, 2, 3 = 2", ["mode of 1 2 2 3"], "stats"),
    E(["range"], "The range is the largest value minus the smallest.", "range of 3, 9, 4 = 6", ["range of 3, 9, 4"], "stats"),
    E(["variance"], "Variance is the average squared distance from the mean: how spread out data is.", "", ["variance of 2,4,4,4,5,5,7,9"], "stats"),
    E(["standard deviation", "std", "sd"], "Standard deviation is the square root of the variance, in the same units as the data.", "std of 2,4,4,4,5,5,7,9 = 2", ["std of 2,4,4,4,5,5,7,9"], "stats"),
    E(["probability"], "Probability measures how likely an event is, from 0 (impossible) to 1 (certain): favourable outcomes ÷ all equally likely outcomes.", "P(7 with two dice) = 6/36 = 1/6", ["probability of rolling a sum of 7 with two dice"], "stats"),
    E(["permutation", "permutations"], "A permutation is an ordered arrangement; P(n, k) = n!/(n − k)!.", "P(5, 2) = 20", ["how many ways can you arrange 5 books"], "stats"),
    E(["combination", "combinations"], "A combination is a selection where order doesn't matter; C(n, k) = n!/(k!(n − k)!).", "10 choose 3 = 120", ["10 choose 3"], "stats"),
    E(["percentile", "p95", "p99", "95th percentile"], "The p-th percentile is the value below which p% of observations fall. p95 latency: 95% of requests were faster.", "", [], "monitoring"),
    E(["outlier", "outliers"], "An outlier is a value far from the rest of the data.", "", [], "stats"),
    E(["z-score", "z score", "standard score"], "A z-score says how many standard deviations a value is from the expected value. |z| > 3 is unusual.", "", [], "stats"),
    E(["poisson", "poisson distribution"], "The Poisson distribution models counts of random events in a fixed interval (errors per 5 minutes). Kepler uses it to judge whether a count is surprising.", "", [], "stats"),
    E(["correlation"], "Correlation measures how strongly two quantities move together, from −1 to 1. It doesn't prove causation.", "", [], "stats"),
    # physics, electrical, chemistry, finance
    E(["speed"], "Speed is how fast something moves: distance ÷ time. It has no direction.", "150 km in 2.5 h = 60 km/h", ["how long does it take to drive 150 km at 60 km/h"], "physics"),
    E(["velocity"], "Velocity is speed in a given direction (a vector), in m/s.", "20 m/s north", ["how far does a car go at 20 m/s in 30 seconds"], "physics"),
    E(["acceleration"], "Acceleration is how quickly velocity changes: a = (v − u) / t, in m/s².", "0 → 27 m/s in 9 s is 3 m/s²", ["a car accelerates from 0 to 27 m/s in 9 seconds, what is its acceleration?"], "physics"),
    E(["force"], "A force is a push or a pull. Newton's second law: F = m · a, measured in newtons (N).", "a 5 kg box at 4 m/s² needs 20 N", ["a 5 kg box is pushed with 20 N, what's its acceleration"], "physics"),
    E(["mass"], "Mass is how much matter an object has, in kilograms. It is the same everywhere.", "", ["what is the weight of a 10 kg bag"], "physics"),
    E(["weight"], "Weight is the force gravity puts on a mass: W = m · g (g ≈ 9.81 m/s² on Earth), in newtons.", "a 10 kg bag weighs 98.1 N", ["what is the weight of a 10 kg bag"], "physics"),
    E(["kinetic energy"], "Kinetic energy is the energy of motion: KE = ½ · m · v², in joules.", "2 kg at 3 m/s has 9 J", ["what is the kinetic energy of a 2 kg ball moving at 3 m/s?"], "physics"),
    E(["potential energy", "gravitational potential energy"], "Gravitational potential energy is stored by height: PE = m · g · h, in joules.", "", ["potential energy of a 3 kg book on a 2 m shelf"], "physics"),
    E(["energy"], "Energy is the capacity to do work, measured in joules (J); electricity bills use kilowatt-hours (1 kWh = 3.6 MJ).", "", ["power used by a 60 W bulb in 5 hours in kWh"], "physics"),
    E(["power"], "Power is energy per unit time, in watts (1 W = 1 J/s). In circuits P = V · I.", "", ["power of a 12 V device drawing 2 A"], "physics"),
    E(["momentum"], "Momentum is mass times velocity: p = m · v. It is conserved in collisions.", "", ["momentum of a 1000 kg car at 20 m/s"], "physics"),
    E(["density"], "Density is mass per volume: ρ = m / V, in kg/m³. Water is about 1000 kg/m³.", "", ["density of 2 kg in 0.001 m^3"], "physics"),
    E(["pressure"], "Pressure is force per area: P = F / A, in pascals (1 Pa = 1 N/m²).", "", ["pressure of 100 N on 0.5 m^2"], "physics"),
    E(["voltage", "potential difference"], "Voltage is the push that drives current around a circuit, in volts (V).", "", ["what current flows through a 10 ohm resistor at 5 volts?"], "electrical"),
    E(["current", "electric current"], "Current is the rate charge flows, in amperes (A). Ohm's law: I = V / R.", "", ["what current flows through a 10 ohm resistor at 5 volts?"], "electrical"),
    E(["resistance"], "Resistance is how much a component opposes current, in ohms (Ω). R = V / I.", "", ["resistance if 12 V drives 3 A"], "electrical"),
    E(["ohm's law", "ohms law"], "Ohm's law: V = I · R. Voltage equals current times resistance.", "5 V across 10 Ω drives 0.5 A", ["what current flows through a 10 ohm resistor at 5 volts?"], "electrical"),
    E(["mole", "moles"], "A mole is 6.022 × 10²³ particles (Avogadro's number). n = mass / molar mass.", "36 g of water ≈ 2 mol", ["how many moles in 36 g of water"], "chemistry"),
    E(["molar mass"], "Molar mass is the mass of one mole of a substance, in g/mol: add up the atomic masses in its formula.", "H2O = 2 × 1.008 + 15.999 = 18.02 g/mol", ["molar mass of H2O"], "chemistry"),
    E(["ph"], "pH measures acidity: pH = −log₁₀[H⁺]. Below 7 is acidic, 7 neutral, above 7 basic.", "0.001 M HCl has pH 3", ["what is the pH of a 0.001 M HCl solution"], "chemistry"),
    E(["acid", "acids"], "An acid releases H⁺ ions in water and has pH below 7. Strong acids (HCl, HNO3, H2SO4) dissociate fully.", "", ["pH of 0.01 M HCl"], "chemistry"),
    E(["base", "bases", "alkali"], "A base takes up H⁺ (or releases OH⁻) and has pH above 7. NaOH and KOH are strong bases.", "", ["pH of 0.01 M NaOH"], "chemistry"),
    E(["compound interest"], "Compound interest earns interest on past interest: A = P · (1 + r)^n.", "1000 at 5% for 10 years ≈ 1628.89", ["compound interest on 1000 at 5% for 10 years"], "finance"),
    E(["simple interest"], "Simple interest is paid only on the original amount: I = P · r · t.", "1000 at 5% for 3 years = 150", ["simple interest on 1000 at 5% for 3 years"], "finance"),
    E(["loan", "mortgage", "emi"], "A fixed-rate loan is repaid in equal monthly payments: PMT = P · r / (1 − (1 + r)^−n), with r the monthly rate.", "", ["monthly payment on a 200000 loan at 6% for 30 years"], "finance"),
    E(["cagr", "compound annual growth rate"], "CAGR is the steady yearly growth that takes a start value to an end value: (end / start)^(1/years) − 1.", "100 → 200 in 5 years ≈ 14.87% a year", ["revenue grew from 100 to 200 in 5 years, what is the annual growth rate"], "finance"),
    E(["inflation"], "Inflation is the rise in prices over time, so money buys less; 3% inflation halves value in about 23 years.", "", [], "finance"),
    E(["hypotenuse"], "The hypotenuse is the longest side of a right triangle, opposite the right angle: c = √(a² + b²).", "legs 3 and 4 → 5", ["hypotenuse of a right triangle with sides 3 and 4"], "maths"),
    E(["sine", "sin", "cosine", "cos", "tangent", "tan", "trigonometry"], "In a right triangle, sin = opposite/hypotenuse, cos = adjacent/hypotenuse, tan = opposite/adjacent.", "sin 30° = 1/2", ["sin of 30 degrees", "cos 60°"], "maths"),
    # monitoring & Kepler
    E(["anomaly", "anomalies"], "An anomaly is a value that's far from what Kepler expected for that time of day and week, with enough evidence that it isn't noise.", "", ["is api_errors ok", "status"], "monitoring"),
    E(["incident", "incidents"], "An incident is an anomaly Kepler reported: it opens when a metric breaks and resolves when it recovers.", "", ["show incidents", "explain the latest incident"], "monitoring"),
    E(["metric", "metrics"], "A metric is a number measured over time, like signups, errors or latency.", "", ["status", "show signups"], "monitoring"),
    E(["baseline"], "The baseline is what Kepler expects a metric to be right now, learned from the same time of day on similar days.", "", ["show signups"], "monitoring"),
    E(["seasonality"], "Seasonality is a pattern that repeats on a schedule, like daily peaks or quieter weekends. Kepler's baselines learn it so normal peaks don't alert.", "", [], "monitoring"),
    E(["slice", "segment", "dimension", "slices"], "A slice is part of a metric filtered by one dimension value, like platform=ios. Kepler watches each slice, so a broken iOS release is caught even if the total barely moves.", "", ["break down signups by platform"], "monitoring"),
    E(["drilldown", "root cause", "attribution"], "Drilldown is how Kepler finds where a change happened: which dimension values explain most of the change.", "", ["why did api_errors spike"], "monitoring"),
    E(["latency"], "Latency is how long a request takes to answer, usually in milliseconds.", "", ["is p95_latency_ms ok"], "monitoring"),
    E(["error rate", "errors"], "Error rate is the share or count of failed requests (like HTTP 5xx) per interval.", "", ["is api_errors ok"], "monitoring"),
    E(["false positive", "false alarm"], "A false positive is an alert for something that wasn't a real problem. Label it 👎 and Kepler learns to filter similar ones.", "", ["label it false"], "monitoring"),
    E(["confidence", "anomaly probability"], "Confidence (p) is how sure Kepler is: 0 means surely normal and 1 means surely broken. Every decision shows it.", "", [], "monitoring"),
    E(["sensitivity"], "Sensitivity controls how easily Kepler alerts: higher catches more but risks more noise.", "", ["set sensitivity to 70%"], "monitoring"),
    E(["orbit", "orbit model", "area model", "time model", "kepler models", "detection models"], "Kepler has three detection models named after Kepler's laws: Orbit (fast, shared), Area (trained per metric and slice), Time (deepest reasoning, slow burns).", "", ["compare the models"], "kepler"),
    E(["intent", "typed decision", "decision"], "A typed decision is how Kepler shows what it understood: an intent (like status), a probability, and the details (slots) it extracted.", "◆ decide p=0.97 metric=signups", [], "kepler"),
    E(["kepler", "you", "this bot", "this app"], "I'm Kepler, a metric watchdog. I learn what normal looks like for your metrics, tell you what broke, how sure I am and where, and I can answer maths questions with worked steps. I don't use a language model: I run trained classifiers and rules.", "", ["help", "status", "sum of first n natural numbers"], "kepler"),
]

# "what's the difference between X and Y": the one-line contrast, keyed by the two entries' first terms
CONTRASTS = {
    frozenset({"mean", "median"}): "The mean uses every value, so one outlier drags it; the median only looks at the middle, so it doesn't. For incomes or latencies the median is usually the fairer \"typical\" value.",
    frozenset({"mean", "mode"}): "The mean balances all the values; the mode is just the most common one, and works for categories too.",
    frozenset({"median", "mode"}): "The median is the middle of the sorted values; the mode is the most frequent value.",
    frozenset({"variance", "standard deviation"}): "Standard deviation is the square root of the variance, so it is in the data's own units and easier to read.",
    frozenset({"permutation", "combination"}): "Order matters in a permutation (ABC ≠ CBA) and doesn't in a combination, so there are k! times more permutations.",
    frozenset({"speed", "velocity"}): "Speed is only how fast; velocity is how fast and in which direction. Running a lap at constant speed, your velocity keeps changing.",
    frozenset({"mass", "weight"}): "Mass is how much matter (kg) and never changes; weight is gravity's pull on it (N), so you'd weigh less on the Moon.",
    frozenset({"voltage", "current"}): "Voltage is the push, current is the flow. In a water pipe, voltage is the pressure and current is how much water passes per second.",
    frozenset({"acid", "base"}): "Acids release H⁺ and have pH below 7; bases take up H⁺ (release OH⁻) and have pH above 7.",
    frozenset({"compound interest", "simple interest"}): "Simple interest is paid on the original amount only; compound interest also earns on past interest, so it grows faster over time.",
    frozenset({"correlation", "z-score"}): "Correlation compares two quantities; a z-score places one value against its own distribution.",
    frozenset({"anomaly", "outlier"}): "An outlier is any value far from the rest; an anomaly is one that's far from what was expected for that moment, with enough evidence to matter.",
    frozenset({"prime", "composite"}): "A prime has exactly two divisors (1 and itself); a composite has more.",
    frozenset({"rational number", "irrational number"}): "A rational number is a fraction of integers and its decimals end or repeat; an irrational one's never do.",
    frozenset({"derivative", "integral"}): "A derivative measures how fast something changes; an integral adds it up. Each undoes the other.",
    frozenset({"kinetic energy", "potential energy"}): "Kinetic energy is from motion (½mv²); potential energy is stored by position (mgh). A falling ball turns one into the other.",
}
PAIRS = [re.compile(p) for p in (
    r"^(?:what is |what are )?(?:the )?differences? (?:between|of) (?:a |an |the )?(.+?) (?:and|&) (?:a |an |the )?(.+?)$",
    r"^how (?:is|are|does|do) (?:a |an |the )?(.+?) differ(?:ent)? (?:from|to) (?:a |an |the )?(.+?)$",
    r"^compare (?:a |an |the )?(.+?) (?:and|with|to|vs\.?) (?:a |an |the )?(.+?)$",
    r"^(?:a |an |the )?([a-z' -]+?) (?:vs\.?|versus) (?:a |an |the )?([a-z' -]+)$",
    r"^is (?:a |an |the )?(.+?) the same (?:thing )?as (?:a |an |the )?(.+?)$",
)]

# indirect ways of asking "what is X" → the direct question. Applied before matching, so everything below sees one form.
INDIRECT = [
    (r"^(?:hey|hi|hello|hiya|yo|heya|howdy|greetings|good (?:morning|afternoon|evening))(?: there| kepler| buddy| friend| mate)?[,!. ]+(?=\w)", ""),
    (r"^(?:please|pls|plz|kindly)\s+", ""),
    (r"^(?:(?:can|could|would|will) you(?: please)?|please|i want you to|i would like you to|i'd like you to)\s+(?:tell me|explain(?: to me)?|describe|say)\s+"
     r"(?:what|whats)\s+(?:(?:a|an|the)\s+)?(.+?)\s+(?:is|are|means?)$", r"what is \1"),
    (r"^(?:(?:can|could|would|will) you(?: please)?)\s+(?:tell me about|explain|describe|define)\s+(.+)$", r"what is \1"),
    (r"^(?:i (?:do not|don't|dont) (?:get|understand|know)|i (?:never )?(?:understood|got)|i am not sure|i'm not sure|help me understand|"
     r"i (?:want|would like|need) to (?:know|understand)|i wonder|i was wondering)\s+(?:what|whats)\s+(?:(?:a|an|the)\s+)?(.+?)\s+(?:is|are|means?)\b.*$", r"what is \1"),
    (r"^explain(?: it)? (?:to me )?like i(?:'m| am) (?:5|five|a (?:kid|child|beginner))[,:]?\s*(?:what\s+)?(?:(?:a|an|the)\s+)?(.+?)(?:\s+(?:is|are|means?))?$", r"what is \1"),
    (r"^(.+?)[,:]? (?:explain|in simple words|in simple terms|in plain english|simply|eli5)$", r"\1"),
    (r"^(?:what|whats) (?:(?:a|an|the)\s+)?(.+?) (?:is|are|means)$", r"what is \1"),  # embedded order: "what a median is"
    (r"^(?:what is|what's) (?:a |an |the )?(.+?) (?:again|exactly|actually|anyway)$", r"what is \1"),
]


def understand(t: str) -> str:
    """Rewrites indirect questions into the direct form: "can you tell me what a median is" → "what is median"."""
    for pat, rep in INDIRECT:
        t = re.sub(pat, rep, t).strip()
    return t


def compare(t: str) -> dict | None:
    """'what's the difference between mean and median', 'mean vs median', 'compare speed and velocity'."""
    m = next((m for p in PAIRS if (m := p.match(t))), None)
    if not m:
        return None
    ea, eb = _lookup(m.group(1)), _lookup(m.group(2))
    if not (ea and eb) or ea is eb:
        return None
    return _comparison(ea, eb)


def _comparison(ea: Entry, eb: Entry) -> dict:
    contrast = CONTRASTS.get(frozenset({ea.terms[0], eb.terms[0]}), "")
    text = f"{ea.terms[0].capitalize()}: {ea.text}\n{eb.terms[0].capitalize()}: {eb.text}"
    if contrast:
        text += f"\nThe difference: {contrast}"
    return {"kind": "comparison", "topic": ea.topic if ea.topic == eb.topic else f"{ea.topic}, {eb.topic}",
            "title": f"{ea.terms[0]} vs {eb.terms[0]}", "text": text, "example": "", "tries": (ea.tries + eb.tries)[:3]}


# Finding the concept anywhere in the question: "can you tell me what a standard deviation is measuring?",
# "z-score meaning??", "what's the point of variance", "covariance and correlation... the same idea?"
CUE = re.compile(r"\b(?:mean|means|meaning|define|definition|explain|describe|intuition|concept|idea (?:of|behind)|"
                 r"eli5|plain (?:english|words|terms)|simple (?:english|words|terms)|layman|tell me (?:about|what)|"
                 r"what (?:is|are|was|were|does|do)|what'?s|stand for|stands for|used for|good for|point of|purpose of|"
                 r"what makes?|understand|understood|get what|walk me through|what (?:are|is) (?:they|it) \w* ?for)\b")
STRONG = re.compile(r"\b(?:mean|means|meaning|define|definition|concept|intuition|eli5|plain (?:english|words|terms)|"
                    r"simple (?:english|words|terms)|layman|stand for|stands for)\b")
DIFF = re.compile(r"\b(?:difference|differences|differ|differs|different|vs\.?|versus|compare|comparison|"
                  r"same (?:thing|idea|as)|mix(?:ing)? up|mixed up|confuse|confused|confusing|better)\b")
# commands and questions about your own data, even when they name a concept ("why is latency so high")
NOT_A_DEFINITION = re.compile(r"#\d|\bincident \d|\b[a-z]+_[a-z0-9_]+\b|^(?:show|chart|plot|graph|mute|switch|set|"
                              r"mark|label|connect|copy|open|break down|split|list|retrain|train|use)\b|"
                              r"\b(?:my|our|your) (?:metrics?|dashboard|alerts?|incidents?|settings)\b")
# concepts that are also everyday words or Kepler features: only a clearly definitional question counts
LOOSE = {"latency", "anomaly", "incident", "metric", "baseline", "sensitivity", "slice", "seasonality", "orbit",
         "confidence", "error rate", "false positive", "kepler", "intent", "drilldown", "set", "base", "mode", "range",
         "power", "series", "function", "limit", "current", "force", "work", "mass", "weight", "energy", "constant",
         "domain", "sample", "population", "charge", "principal", "e", "multiple", "odd", "even", "expression",
         "variable", "sequence", "proportion", "ratio", "speed", "pressure", "area", "volume", "uptime", "volume"}
_SPOT: dict = {}


def _spotter() -> re.Pattern:
    if _SPOT.get("n") != len(INDEX):
        terms = sorted((t for t in INDEX if len(t) > 1), key=len, reverse=True)
        alts = "|".join(re.escape(t).replace(r"\-", r"\s*-\s*") for t in terms)  # "z-score" after the normaliser: "z - score"
        _SPOT["re"] = re.compile(r"(?<![a-z0-9])(" + alts + r")(?:e?s)?(?![a-z0-9])")
        _SPOT["n"] = len(INDEX)
    return _SPOT["re"]


def spot(t: str) -> list[tuple[Entry, int, int]]:
    """The concepts named in t, in order, as (entry, start, end); each entry once."""
    out, seen = [], set()
    for m in _spotter().finditer(t):
        e = INDEX[re.sub(r"\s*-\s*", "-", m.group(1))]
        if e.topic == "kepler":
            continue  # Kepler's own features ("orbit", "you", "time model"): only "what is …" asks about those
        if id(e) not in seen:
            seen.add(id(e))
            out.append((e, m.start(), m.end()))
    return out


def concept(t: str) -> dict | None:
    """A definition or comparison asked in any wording, found by naming known concepts plus a cue."""
    if NOT_A_DEFINITION.search(t):
        return None
    found = spot(t)
    if not found:
        return None
    rest = _spotter().sub(" ", t)
    if re.search(r"\d", rest):
        return None  # a calculation that mentions a concept ("standard deviation of 2, 4, 4")
    _, a, b = found[0]
    bare = len(found) == 1 and not re.sub(r"\b(?:the|a|an|meaning|definition|means|mean|please|pls)\b|[?!. ]", "",
                                           t[:a] + t[b:])  # just the term: "voltage?", "z-score meaning??"
    strong = bool(STRONG.search(t)) or (bare and found[0][0].terms[0] not in LOOSE)  # "latency" alone may be a metric
    if not (CUE.search(t) or strong or (len(found) >= 2 and DIFF.search(t))):
        return None
    usable = [f for f in found if strong or f[0].terms[0] not in LOOSE]
    if len(usable) >= 2 and DIFF.search(t):
        # the pair joined by "or", "and", "vs", ","; else the first two
        pairs = list(zip(usable, usable[1:]))
        pair = next(((a, b) for a, b in pairs
                     if re.fullmatch(r"\s*,?\s*(?:or|and|vs\.?|versus|&|/)\s*(?:the |a |an )?", t[a[2]:b[1]])), None) \
            or next(((a, b) for a, b in pairs if re.fullmatch(r"\s*(?:,|\.\.\.)\s*", t[a[2]:b[1]])), None) \
            or (usable[0], usable[1])
        return _comparison(pair[0][0], pair[1][0])
    if not usable:
        return None
    e = usable[0][0]
    return {"kind": "definition", "topic": e.topic, "title": e.terms[0], "text": e.text, "example": e.example,
            "tries": e.tries}


SMALL_TALK = [
    (r"^(?:how are you|how are you doing|how is it going|how do you do|how have you been|you ok|are you ok|how is everything with you)\b",
     ["Running smoothly, thanks. Watching your metrics and ready for questions.", "All systems normal on my side. What can I do for you?"]),
    (r"^(?:are you (?:an? )?(?:ai|robot|bot|human|person|llm|chatgpt|gpt|language model|real))\b",
     ["I'm a bot but not a language model. I understand you with a trained intent classifier plus rules, and I work out maths exactly with a reasoning engine, so the same question always gets the same answer."]),
    (r"^(?:who (?:made|built|created|wrote) you|who is your (?:creator|maker))",
     ["I'm part of Kepler, built by this workspace's team. You can teach me new things in `kepler teach` or `kepler bot`."]),
    (r"^(?:tell me a joke|joke|say something funny|make me laugh|another joke)\b",
     ["Why was 6 afraid of 7? Because 7, 8 (ate), 9.", "I'd tell you a joke about infinity, but it doesn't have an ending.",
      "Parallel lines have so much in common. It's a shame they'll never meet.", "Why do statisticians love the outdoors? So many data points.",
      "My p95 latency for jokes is high: this one took 300 ms.", "There are 10 kinds of people: those who understand binary and those who don't."]),
    (r"^(?:what is the meaning of life|meaning of life|what is the answer to everything)\b",
     ["42. (Also: monitor your metrics.)"]),
    (r"^(?:bye|goodbye|good night|see you|see ya|cya|later|i am done|that is all)\b", ["Bye! I'll keep watching."]),
    (r"^(?:sorry|my bad|oops)\b", ["No problem."]),
    (r"^(?:you are|you're|ur) (?:smart|great|awesome|amazing|good|cool|the best|helpful|clever)\b", ["Thank you! Teach me anything I get wrong with /n."]),
    (r"^(?:you are|you're|ur) (?:dumb|stupid|wrong|useless|bad|slow)\b",
     ["Sorry about that. If I misunderstood, tell me what you meant with /n INTENT, or rephrase and I'll learn from it."]),
    (r"^(?:i do not understand|i am confused|confused|what|huh|what do you mean)\??$",
     ["Let me help. Ask me about your metrics ('status', 'why did signups drop?') or maths ('sum of first n numbers', '15% of 200'). Say 'help' for everything I know."]),
    (r"^(?:yes|no|ok|sure|fine|cool|great|nice|alright|got it|okay)\.?$", ["👍"]),
    (r"^(?:what time is it|what is the time|what is the date|what day is it|today'?s date)\b", ["__time__"]),
    (r"^(?:what is up|what's up|whats up)(?: kepler| buddy| mate| man| dude)?\??$", ["Not much: watching metrics and waiting for questions. Try 'status'."]),
    (r"^(?:how(?: is|'s) your day|how (?:is|are) you(?:r)? (?:doing|holding up|feeling)|are you (?:having|doing|ok|okay|alright|"
     r"well|good)|having a (?:good|decent|nice|pleasant) day|do you (?:ever )?get (?:bored|tired|lonely)|i hope you(?: are|'re) "
     r"(?:having|doing|well|keeping))",
     ["Doing well, thanks: watching your metrics never gets old. How can I help?"]),
    (r"^(?:(?:ok|okay|right|alright),? )?(?:i'?m |i am )?(?:off to (?:lunch|bed|a meeting|sleep)|catch you later|ttyl|brb|gotta go|"
     r"heading (?:out|off)|signing off|logging off|talk (?:to you )?later|see you (?:later|tomorrow|soon))",
     ["See you! I'll keep watching."]),
    (r"^(?:never ?mind|nvm|forget (?:it|i asked|that)|scratch that|ignore (?:that|me))\b", ["No problem."]),
    (r"^(?:who (?:\w+ )?(?:came up with|made|built|created|invented|wrote|designed) (?:you|u)|who are your (?:makers|creators))",
     ["I'm part of Kepler, built by this workspace's team. You can teach me new things in `kepler teach` or `kepler bot`."]),
    (r"^(?:you(?: are|'re)|ur|u r) (?:really |pretty |so |very |quite )?(?:smart|clever|helpful|great|awesome|good|useful)\b",
     ["Thank you! Teach me anything I get wrong with /n."]),
    (r"^(?:wassup|whassup|wazzup|whaddup|sup)\b", ["Hey! Watching your metrics. What can I do for you?"]),
    (r"^(?:what is your name|your name|who am i talking to|do you have a name)\b", ["I'm Kepler."]),
    (r"^(?:how old are you|what is your age|when were you (?:born|made|built))\b",
     ["I'm as old as this install of Kepler 1.0. In metric years, a few million readings."]),
    (r"^(?:lol|lmao|rofl|haha+|hehe+)\b", ["😄"]),
    (r"^(?:tell me something (?:interesting|cool|fun|new)|tell me a (?:fun )?fact|fun fact|surprise me)\b",
     ["There are more ways to shuffle a deck of cards (52! ≈ 8 × 10⁶⁷) than atoms on Earth.",
      "A sheet of paper folded 42 times would be thick enough to reach the Moon: 0.1 mm × 2⁴² ≈ 440,000 km.",
      "In a room of 23 people, there's a better than even chance two share a birthday. Ask me: probability that 2 of 23 people share a birthday.",
      "Light from the Sun takes about 8 minutes 20 seconds to reach Earth: 1.496 × 10¹¹ m ÷ 3 × 10⁸ m/s.",
      "1 kWh lifts a 1000 kg car about 367 m: h = E / (m · g)."]),
    (r"^(?:i have an? (?:\w+ )?(?:question|problem)|can i ask (?:you )?(?:a question|something)|quick question)\b",
     ["Go ahead. I can solve maths, physics, electrical, chemistry, finance and statistics problems with worked steps, "
      "explain terms ('what is a mole'), compare them ('speed vs velocity'), and answer questions about your metrics."]),
    (r"^(?:go away|leave me alone|shut up|be quiet|stop talking)\b",
     ["Okay, I'll be quiet. Kepler keeps watching in the background; to silence one metric, use `kepler mute METRIC 1h`."]),
]

TOPICS = {"maths": "maths", "math": "maths", "mathematics": "maths", "statistics": "stats", "stats": "stats",
          "probability": "stats", "physics": "physics", "chemistry": "chemistry", "finance": "finance", "money": "finance",
          "electricity": "electrical", "electronics": "electrical", "circuits": "electrical", "monitoring": "monitoring"}
TOUR = re.compile(r"^(?:teach me|i want to learn|i'd like to learn|help me learn|tell me about|what do you know about)\s+"
                  r"(?:some |about )?(" + "|".join(TOPICS) + r")$")


def tour(t: str) -> dict | None:
    """'teach me physics' → the terms I know in that field and problems to try."""
    m = TOUR.match(t)
    if not m:
        return None
    topic = TOPICS[m.group(1)]
    entries = [e for e in ENTRIES if e.topic == topic]
    if not entries:
        return None
    tries = list(dict.fromkeys(t for e in entries for t in e.tries))[:4]
    terms = ", ".join(e.terms[0] for e in entries)
    return {"kind": "tour", "topic": topic, "title": m.group(1), "text": f"Terms I can explain ({len(entries)}): {terms}. "
            "Ask 'what is …', or 'difference between … and …'.", "example": "", "tries": tries}

DEF_PATTERN = re.compile(r"^(?:what(?: is| are)|what does|define|definition of|meaning of|what is meant by|explain(?: what)?|"
                         r"tell me (?:about|what)|describe|who is|who are|what do you mean by|do you know(?: what)?)\s+"
                         r"(?:(?:a|an|the)\s+)?(.+?)(?:\s+(?:means?|is|are|stand for|stands for))?(?:\s+in (?:maths|math|statistics|kepler))?\s*\??$")


def vocabulary() -> set:
    out = set()
    for e in ENTRIES:
        for t in e.terms:
            out.update(re.findall(r"[a-z]+", t))
    return out


def _corpus() -> None:
    """Adds corpus/knowledge.json (entries and contrasts written in bulk and fact-checked) to the hand-written ones.
    A corpus entry never replaces a hand-written term."""
    import json
    from pathlib import Path
    try:
        data = json.loads((Path(__file__).with_name("corpus") / "knowledge.json").read_text())
    except (OSError, ValueError):
        return
    known = {t for e in ENTRIES for t in e.terms}
    for d in data.get("entries", []):
        terms = [t for t in d["terms"] if t not in known]
        if terms and terms[0] == d["terms"][0]:
            ENTRIES.append(Entry(terms, d["text"], d.get("example", ""), d.get("tries", []), d.get("topic", "maths")))
            known.update(terms)
    for c in data.get("contrasts", []):
        CONTRASTS.setdefault(frozenset({c["a"], c["b"]}), c["text"])


_corpus()


def _index() -> dict:
    idx = {}
    for e in ENTRIES:
        for t in e.terms:
            idx[t] = e
    return idx


INDEX = _index()


def _lookup(term: str):
    term = re.sub(r"\s+", " ", term.strip(" ?.!").lower())
    term = re.sub(r"^(?:a|an|the|this|that)\s+", "", term)
    for cand in (term, term.rstrip("s"), term + "s", re.sub(r"\s+(?:number|numbers)$", " number", term)):
        if cand in INDEX:
            return INDEX[cand]
    if len(term) >= 5 and " " not in term:
        close = difflib.get_close_matches(term, list(INDEX), n=1, cutoff=0.86)
        if close:
            return INDEX[close[0]]
    return None


def answer(text: str, rng: random.Random | None = None) -> dict | None:
    """→ {"kind": "definition"|"comparison"|"tour"|"small_talk", "topic", "title", "text", "example", "tries"} or None."""
    t = understand(text.lower().strip().rstrip("?!. "))
    rng = rng or random
    for pat, replies in SMALL_TALK:
        if re.search(pat, t):
            reply = rng.choice(replies)
            if reply == "__time__":
                import datetime
                now = datetime.datetime.now()
                reply = now.strftime("It's %H:%M on %A, %d %B %Y (this computer's clock).")
            return {"kind": "small_talk", "topic": "chat", "title": "", "text": reply, "example": "", "tries": []}
    if re.search(r"\d", _spotter().sub(" ", t)):
        return None  # "what is 2+2", "explain incident 40" are not definitions; "p95 vs p99" is
    both = compare(t) or tour(t)
    if both:
        return both
    m = DEF_PATTERN.match(t)
    e = _lookup(m.group(1)) if m else None
    if not e:
        return concept(t)
    if re.match(r"(?:explain|describe)\b", t) and e.topic in ("monitoring", "kepler") and e.terms[0] != "kepler":
        return None  # "explain incident" means "explain the latest incident" (an action), not a definition
    return {"kind": "definition", "topic": e.topic, "title": e.terms[0], "text": e.text, "example": e.example, "tries": e.tries}


SPELLED = {"ph": "pH", "cagr": "CAGR", "emi": "EMI", "lcm": "LCM", "gcd": "GCD", "e": "e"}  # titles that aren't sentence case


def render(k: dict):
    from rich.console import Group
    from rich.text import Text
    from ..cli import render as R
    if k["kind"] == "small_talk":
        return Text(k["text"])
    title = SPELLED.get(k["title"], k["title"][:1].upper() + k["title"][1:])
    parts = [Text.assemble((title, f"bold {R.ACCENT}"), (f"  · {k['topic']}", "grey50")), Text(k["text"])]
    if k["example"]:
        parts.append(Text.assemble(("Example  ", "grey50"), k["example"]))
    parts += supporting_lines(k)
    if k["tries"]:
        parts.append(Text.assemble(("Try      ", "grey50"), ("  ·  ".join(k["tries"]), "grey70")))
    return Group(*parts)


def supporting_lines(d: dict) -> list:
    """'Also' lines for other streams that answered the same question, and whether they agree."""
    from rich.text import Text
    from ..cli import render as R
    out = []
    for s in d.get("supporting") or []:
        text = s["text"] if len(s["text"]) < 220 else s["text"][:217] + "…"
        out.append(Text.assemble(("Also     ", "grey50"), (f"[{s['origin']}] ", R.ACCENT), (text, "grey70")))
    if d.get("supporting"):
        agree = d.get("agreement", 0)
        word = "agree" if agree >= 0.3 else "partly agree" if agree >= 0.12 else "say different things"
        out.append(Text(f"         {1 + len(d['supporting'])} sources {word} (overlap {agree:.0%})", style="grey50"))
    return out
