"""Mechanics and basic physics solver: chatty word problems in, exact answers with steps out; everything else None."""
import time

import pytest

from kepler.bot.solvers.physics import solve

CASES = [
    # kinematics (SUVAT)
    ("quick one: a car accelerates from rest at 3 m/s^2 for 5 s, how far does it go?", "37.5 m"),
    ("car goes from 10 m/s to 30 m/s in 4 s, acceleration pls", "5 m/s²"),
    ("car at 25 m/s decelerates at 5 m/s^2, stopping distance?", "62.5 m"),
    # free fall, custom gravity
    ("a ball is dropped from 20 m, g = 10, how long to hit the ground?", "2 s"),
    ("a stone dropped on the Moon (1.62 m/s²) falls for 3 s, how far?", "7.29 m"),
    # vertical throws
    ("ball thrown straight up at 20 m/s, max height? use g = 10", "20 m"),
    ("ball thrown up at 15 m/s, time to reach the top? g=9.81", "500/327 s ≈ 1.529 s"),
    ("a ball is thrown vertically upward at 20 m/s with g = 10. total flight time?", "4 s"),
    # horizontal launch
    ("a ball is launched horizontally at 5 m/s from a 20 m cliff, how far from the base does it land? g = 10", "10 m"),
    # average speed
    ("i drive 60 km at 30 km/h and then 60 km at 60 km/h, what's my average speed?", "40 km/h"),
    # braking
    ("a 1200 kg car at 20 m/s brakes with a force of 6000 N, braking distance?", "40 m"),
    # forces
    ("a 10 kg box is pushed with 50 N, friction is 20 N, what is the acceleration?", "3 m/s²"),
    ("what does a 70 kg astronaut weigh on mars", "259.7 N"),
    # momentum, collisions, impulse
    ("what is the momentum of a 2 kg ball moving at 3 m/s", "6 kg·m/s"),
    ("a 2 kg cart at 3 m/s hits a stationary 1 kg cart and they stick together, final velocity?", "2 m/s"),
    ("a 4 kg gun fires a 0.02 kg bullet at 400 m/s, recoil velocity of the gun?", "2 m/s in the opposite direction"),
    ("a force of 50 N acts for 0.2 s, what is the impulse", "10 N·s"),
    # work, power
    ("work done pulling a sled 10 m with 100 N at 60 degrees to the horizontal", "500 J"),
    ("how much work to lift a 5 kg box 2 m? g = 9.8", "98 J"),
    ("a 60 kg person climbs 3 m of stairs in 4 s, power? g=10", "450 W"),
    # energy
    ("a 2 kg ball has 100 J of kinetic energy, speed?", "10 m/s"),
    ("a 2 kg mass has 98 J of potential energy, g = 9.8, height?", "5 m"),
    # springs, efficiency
    ("a spring with k = 200 N/m is stretched 0.1 m, force?", "20 N"),
    ("elastic potential energy of a spring k = 400 N/m compressed 5 cm", "0.5 J"),
    ("a motor uses 500 J and outputs 400 J of useful work, efficiency?", "80%"),
    # density, pressure
    ("density of a block with mass 200 g and volume 50 cm³ in g/cm³", "4 g/cm³"),
    ("mass of 2 L of oil with density 0.9 g/cm^3", "1.8 kg"),
    ("pressure at 10 m depth in water", "98,100 Pa"),
    ("a force of 100 N on 0.5 m^2, pressure?", "200 Pa"),
    # waves
    ("wave with frequency 50 Hz and wavelength 2 m, speed?", "100 m/s"),
    ("a wave has frequency 4 Hz, what is its period", "0.25 s"),
    # energy units
    ("convert 3.6 MJ to kWh", "1 kWh"),
    ("how many joules in 2 kWh", "7,200,000 J"),
    ("5 kJ in J", "5,000 J"),
    # more phrasings
    ("for my homework: a train starts from rest and reaches 20 m/s in 10 s. how far does it travel?", "100 m"),
    ("a rock is released from a height of 45 m. how fast is it going when it hits the ground? take g = 10", "30 m/s"),
    ("what is the weight of a 5 kg bag on the moon", "8.1 N"),
    ("a 1000 kg car going at 72 km/h, braking force 5000 N, how far to stop? show me the steps", "40 m"),
    ("forces of 30 N east and 10 N west act on a 4 kg mass, acceleration?", "5 m/s²"),
    ("a 0.15 kg ball hits a wall at 20 m/s and bounces back at 15 m/s. impulse?", "5.25 N·s"),
    ("a crane lifts 500 kg by 12 m in 30 s, power output? g = 9.8", "1,960 W"),
    ("a car's engine does 2000 J of work in 4 s, what's the power", "500 W"),
    ("how much does a spring with k = 50 N/m stretch under 10 N", "0.2 m (20 cm)"),
    ("a block has density 2.7 g/cm3 and mass 540 g, volume in cm3?", "200 cm³"),
    ("what's the pressure 5 m under the sea", "50,280 Pa"),
    ("sound with frequency 680 Hz travels at 340 m/s, wavelength?", "0.5 m"),
    ("how many kWh is 7200 kJ", "2 kWh"),
    ("kinetic energy of a 1500 kg car at 20 m/s pls", "300,000 J"),
    ("a 3 kg ball moving at 4 m/s collides with a 1 kg ball at rest and they stick, final speed? 4 sig figs", "3.000 m/s"),
    ("a runner covers 400 m in 50 s and then 400 m in 80 s, average speed?", "80/13 m/s ≈ 6.154 m/s"),
    ("a 50 kg box on a floor, pushed with 200 N, coefficient of friction 0.2, g = 10, acceleration?", "2 m/s²"),
    # tester round: several things asked, wording gaps
    ("A ball is released from rest and falls freely for 2.5 seconds with g = 9.8 m/s^2 and no air resistance. How far does it "
     "fall, and what is its speed at the end of the 2.5 seconds?", "s = 30.625 m, v = 24.5 m/s"),
    ("A ball is thrown vertically upward at 15 m/s from ground level. Using g = 10 m/s^2, find the time to reach the top of "
     "its path and the total time in the air.", "time to top = 1.5 s, total flight time = 3 s"),
    ("A spring with spring constant k = 400 N/m is compressed by 0.15 m. What elastic potential energy is stored and what "
     "force does the spring exert?", "energy = 4.5 J, force = 60 N"),
    ("A wave has a frequency of 50 Hz and a wavelength of 6 m. What is its speed and its period?",
     "speed = 300 m/s, period = 0.02 s"),
    ("ok so a wave has frequency 50 Hz and wavelength 6 m. what's the wave speed and the period",
     "speed = 300 m/s, period = 0.02 s"),
    ("walked 3 km in 45 min, then 2 km in 30 min, then ran 5 km in 25 min. avg speed for the whole thing in km/h pls", "6 km/h"),
    ("car 1200 kg doing 72 km/h, brakes give 6000 N of braking force. braking distance? (ignore reaction time)", "40 m"),
    ("on a planet where g = 10 m/s^2 someone throws a rock straight up at 20 m/s. max height and how long to get to the top?",
     "max height = 20 m, time to top = 2 s"),
    ("0.2 kg ball goes from +10 m/s to -15 m/s when hit. impulse? and avg force if contact lasts 0.01 s",
     "impulse = 5 N·s, force = 500 N"),
]

NEGATIVES = [
    "is signups ok", "why did checkout_errors spike 40% at 3pm", "show incidents from the last 6 hours",
    "set sensitivity to 80%", "switch payments to area", "explain incident 42", "mark #12 as a false alarm",
    "connect datadog", "break down signups by region", "chart latency for 24h", "hi kepler", "thanks!",
    "what is a derivative", "what's the difference between mean and median", "who invented the telephone",
    "how are you", "what is momentum", "what is a force",
]


@pytest.mark.parametrize("text,answer", CASES)
def test_answers(text, answer):
    sol = solve(text)
    assert sol is not None, text
    assert sol.answer == answer
    assert sol.steps


@pytest.mark.parametrize("text", NEGATIVES)
def test_not_physics(text):
    assert solve(text) is None


def test_fast():
    t0 = time.perf_counter()
    for text, _ in CASES:
        solve(text)
    assert (time.perf_counter() - t0) / len(CASES) < 0.5
