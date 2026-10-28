"""Geometry and trigonometry solver: exact answers (π and √ kept, decimals to 2 places) and None for everything else."""
import pytest

from kepler.bot.solvers import geometry

CASES = {
    # squares and rectangles
    "quick one: perimeter of a square with side 7 cm": "28 cm",
    "area of a rectangle 8 by 5 pls": "40 square units",
    "what's the perimeter of a rectangle 8 m by 5 m": "26 m",
    "area of a square of side 2.5 m to 2 decimal places": "6.25 m²",
    "square with area 49 cm2, side length?": "7 cm",
    "a garden 12 m by 8 m, turf costs £4.50 per square metre, how much": "£432.00",
    "fencing costs $12 per metre, how much to fence a garden 20 m by 30 m": "$1,200.00",
    # triangles
    "triangle base 10 cm height 6 cm, area?": "30 cm²",
    "area of a triangle with base 7 and height 3": "10.5 square units",
    "triangle with sides 5, 6 and 7 - area? show me the steps": "6√6 square units ≈ 14.70 square units",
    "what's the area of an equilateral triangle with side 6 cm": "9√3 cm² ≈ 15.59 cm²",
    "perimeter of a triangle with sides 3, 4 and 5 cm": "12 cm",
    # circles and parts
    "area of a circle with radius 7 cm": "49π cm² ≈ 153.94 cm²",
    "circle diameter 10 m circumference": "10π m ≈ 31.42 m",
    "what is the radius of a circle with circumference 44 cm": "7.00 cm",
    "radius of a circle with area 154 sq cm": "7.00 cm",
    "find the area of a circle whose diameter is 14 in, 4 sig figs": "49π in² ≈ 153.9 in²",
    "a pizza has a 12 inch diameter, what's its area": "36π in² ≈ 113.10 in²",
    "area of a sector radius 6 cm angle 60 degrees": "6π cm² ≈ 18.85 cm²",
    "length of an arc of a circle radius 9 cm subtending 40 degrees": "2π cm ≈ 6.28 cm",
    "arc length of a sector with radius 10 and angle 2 radians": "20 units",
    "area of a ring with outer radius 5 cm and inner radius 3 cm": "16π cm² ≈ 50.27 cm²",
    # other quadrilaterals
    "trapezoid with parallel sides 6 and 10 and height 4, area?": "32 square units",
    "parallelogram base 9 height 4 area": "36 square units",
    "area of a rhombus with diagonals 6 and 8": "24 square units",
    # diagonals and Pythagoras
    "diagonal of a square with side 6 cm": "6√2 cm ≈ 8.49 cm",
    "diagonal of a rectangle 8 by 6": "10 units",
    "right triangle legs 3 and 4, hypotenuse? i keep mixing up pythagoras": "5 units",
    "hypotenuse is 17 and one short side is 8, what's the other side?": "15 units",
    "a right triangle has a hypotenuse of 10 and a leg of 6. find the other leg": "8 units",
    # solids
    "volume of a cube with side 4 cm": "64 cm³",
    "cube with edge 3 m surface area": "54 m²",
    "surface area of a box 2 by 3 by 4 m": "52 m²",
    "a room is 5 m long, 4 m wide and 3 m high. what's its volume": "60 m³",
    "a cylindrical tank of radius 2 m and height 5 m holds how much water": "20π m³ ≈ 62.83 m³",
    "how much water does a cylinder with diameter 10 cm and height 20 cm hold in litres": "π/2 L ≈ 1.57 L",
    "total surface area of a cylinder radius 3 cm height 5 cm": "48π cm² ≈ 150.80 cm²",
    "hey can u find the volume of a cylinder r=3 h=10? exact form if you can": "90π cubic units ≈ 282.74 cubic units",
    "volume of a cone radius 3 cm height 4 cm": "12π cm³ ≈ 37.70 cm³",
    "cone radius 5 height 12 surface area": "90π square units ≈ 282.74 square units",
    "volume of a ball of radius 3 in": "36π in³ ≈ 113.10 in³",
    "volume of a sphere with diameter 6 cm": "36π cm³ ≈ 113.10 cm³",
    "surface area of a sphere radius 5": "100π square units ≈ 314.16 square units",
    "volume of a hemisphere radius 6 cm": "144π cm³ ≈ 452.39 cm³",
    "volume of a square pyramid with base 6 and height 10": "120 cubic units",
    "surface area of a square pyramid base 6 height 4": "96 square units",
    # trigonometry
    "sin 60°": "√3/2 ≈ 0.8660",
    "cos(45°) exact value": "√2/2 ≈ 0.7071",
    "tan 60 degrees": "√3 ≈ 1.7321",
    "sin(30 degrees)": "0.5",
    "what's cos 120°": "-0.5",
    "sin(pi/6)": "0.5",
    "tan 90°": "undefined",
    "a 10 m ladder leans against a wall at 60° to the ground, how high does it reach": "5√3 m ≈ 8.66 m",
    "a ladder 13 ft long reaches up a wall with its foot 5 ft from the wall. how high up the wall does it reach?": "12 ft",
    "from 50 m away the angle of elevation to the top of a tree is 30°, how tall is the tree": "50√3/3 m ≈ 28.87 m",
    "a 30 m tower casts a 40 m shadow, what is the angle of elevation of the sun": "36.87°",
    "a 6 ft pole, sun elevation 40 degrees, how long is the shadow": "7.15 ft",
    "convert 180 degrees to radians": "π rad ≈ 3.1416 rad",
    "convert 45° to radians": "π/4 rad ≈ 0.7854 rad",
    "what is 2pi/3 radians in degrees": "120°",
    # polygons, wheels, similar figures
    "sum of interior angles of a hexagon": "720°",
    "each interior angle of a regular octagon": "135°",
    "what is the interior angle sum of a 12-sided polygon?": "1,800°",
    "a regular polygon has interior angles of 150°. how many sides?": "12 sides",
    "exterior angle of a regular pentagon": "72°",
    "how far does a wheel of diameter 70 cm roll in one turn": "70π cm ≈ 219.91 cm",
    "two similar triangles have corresponding sides 4 and 10. the smaller has area 12 cm^2, what's the area of the larger": "75 cm²",
    "triangles abc and def are similar with scale factor 3. perimeter of abc is 12 cm, perimeter of def?": "36 cm",
    "a 1.8 m man casts a 2.4 m shadow. at the same time a tree casts a 12 m shadow. how tall is the tree?": "9 m",
    # regressions: multiples of π, sentence-final numbers, two measures asked together
    "A pyramid has a square base of side 6 and a height of 4. Find its volume.": "48 cubic units",
    "The area of a circle is 81π square units. Find its radius.": "9 units",
    "A cube has an edge length of 3 cm. Find its volume and its surface area.": "volume 27 cm³; surface area 54 cm²",
    "A circle has a radius of 4 inches. Find its area and its circumference, giving exact answers in terms of pi and decimal approximations.":
        "area 16π in² ≈ 50.27 in²; circumference 8π in ≈ 25.13 in",
    "A square has a side length of 7 cm. Find its perimeter and its area.": "perimeter 28 cm; area 49 cm²",
    "A rectangle is 8 by 5 meters. Find the perimeter and the area of the rectangle.": "perimeter 26 m; area 40 m²",
    "hey can u tell me perimeter and area of a square with side 7.5 cm": "perimeter 30 cm; area 56.25 cm²",
    "rectangle 8 by 5 whats the area n perimeter": "area 40 square units; perimeter 26 units",
    "circle radius 4 cm, area and circumference??": "area 16π cm² ≈ 50.27 cm²; circumference 8π cm ≈ 25.13 cm",
    "a cylinder has radius 2 and height 5, find its volume and surface area": "volume 20π cubic units ≈ 62.83 cubic units; surface area 28π square units ≈ 87.96 square units",
    "a circle has circumference 10π cm, find its radius": "5 cm",
}

NEGATIVES = [
    "is signups ok", "why did checkout_errors spike 40% at 3pm", "show incidents from the last 6 hours",
    "set sensitivity to 80%", "switch payments to area", "explain incident 42", "mark #12 as a false alarm",
    "connect datadog", "break down signups by region", "chart latency for 24h", "hi kepler", "thanks!",
    "what is a derivative", "what's the difference between mean and median", "who invented the telephone",
    "how are you", "what is the area of a circle", "cos 30 + sin 30",
]


@pytest.mark.parametrize("q,want", list(CASES.items()))
def test_answers(q, want):
    sol = geometry.solve(q)
    assert sol is not None, q
    assert sol.answer == want
    assert sol.steps


@pytest.mark.parametrize("q", NEGATIVES)
def test_not_geometry(q):
    assert geometry.solve(q) is None
