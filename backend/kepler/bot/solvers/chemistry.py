"""Chemistry calculations in plain English, each answered with worked steps and a check.

  molar mass     any formula: CuSO4·5H2O (also CuSO4.5H2O, CuSO4*5H2O), Ca3(PO4)2, K4[Fe(CN)6], H₂O; named compounds
                 (caffeine, aspirin, aluminium sulfate, iron(III) oxide, copper(II) sulfate pentahydrate, dinitrogen
                 pentoxide, baking soda …); several at once ("molar masses of H2O, CO2 and NaCl")
  conversions    grams ↔ moles ↔ particles (molecules, atoms, ions, formula units; N_A = 6.022 × 10^23), atoms or moles
                 of one element in a sample, molar mass from a mass and an amount
  solutions      molarity from moles or grams and a volume (mL or L); grams, moles or volume for a target molarity
  dilution       C1V1 = C2V2: volume of stock, final concentration, final volume, water to add
  composition    percent by mass of every element, of one element, or of the water in a hydrate; grams of an element
  gases          PV = nRT (atm, kPa, Pa, mmHg, torr, bar, psi; L, mL, m³; K, °C, °F; STP, SATP), moles, mass, molar mass
                 and density of a gas; Boyle, Charles, Gay-Lussac and the combined gas law
  pH             pH, pOH, [H⁺], [OH⁻] from one another; strong acids and bases from a concentration or from moles or
                 grams in a volume; weak acids and bases when Ka, Kb or pKa is given (acetic acid, ammonia known)

Anything else (Kepler commands, definitions, other subjects) returns None so the next solver can try.
"""
import math
import re
from dataclasses import dataclass, field

import sympy as sp

from .. import fields
from ..reasoning import Solution

NA = 6.022e23                   # Avogadro constant, /mol
R_ATM = 0.082057366080960       # L·atm/(mol·K)
R_KPA = 8.314462618             # L·kPa/(mol·K)
KW = 1e-14                      # ion product of water at 25 °C

# ---------------------------------------------------------------- elements

_ELEMENTS = """H 1.008 hydrogen|He 4.0026 helium|Li 6.94 lithium|Be 9.0122 beryllium|B 10.81 boron|C 12.011 carbon|
N 14.007 nitrogen|O 15.999 oxygen|F 18.998 fluorine|Ne 20.180 neon|Na 22.990 sodium|Mg 24.305 magnesium|
Al 26.982 aluminium|Si 28.085 silicon|P 30.974 phosphorus|S 32.06 sulfur|Cl 35.45 chlorine|Ar 39.948 argon|
K 39.098 potassium|Ca 40.078 calcium|Sc 44.956 scandium|Ti 47.867 titanium|V 50.942 vanadium|Cr 51.996 chromium|
Mn 54.938 manganese|Fe 55.845 iron|Co 58.933 cobalt|Ni 58.693 nickel|Cu 63.546 copper|Zn 65.38 zinc|Ga 69.723 gallium|
Ge 72.630 germanium|As 74.922 arsenic|Se 78.971 selenium|Br 79.904 bromine|Kr 83.798 krypton|Rb 85.468 rubidium|
Sr 87.62 strontium|Y 88.906 yttrium|Zr 91.224 zirconium|Nb 92.906 niobium|Mo 95.95 molybdenum|Tc 98 technetium|
Ru 101.07 ruthenium|Rh 102.91 rhodium|Pd 106.42 palladium|Ag 107.87 silver|Cd 112.41 cadmium|In 114.82 indium|
Sn 118.71 tin|Sb 121.76 antimony|Te 127.60 tellurium|I 126.90 iodine|Xe 131.29 xenon|Cs 132.91 caesium|
Ba 137.33 barium|La 138.91 lanthanum|Ce 140.12 cerium|Pr 140.91 praseodymium|Nd 144.24 neodymium|Pm 145 promethium|
Sm 150.36 samarium|Eu 151.96 europium|Gd 157.25 gadolinium|Tb 158.93 terbium|Dy 162.50 dysprosium|Ho 164.93 holmium|
Er 167.26 erbium|Tm 168.93 thulium|Yb 173.05 ytterbium|Lu 174.97 lutetium|Hf 178.49 hafnium|Ta 180.95 tantalum|
W 183.84 tungsten|Re 186.21 rhenium|Os 190.23 osmium|Ir 192.22 iridium|Pt 195.08 platinum|Au 196.97 gold|
Hg 200.59 mercury|Tl 204.38 thallium|Pb 207.2 lead|Bi 208.98 bismuth|Po 209 polonium|At 210 astatine|Rn 222 radon|
Fr 223 francium|Ra 226 radium|Ac 227 actinium|Th 232.04 thorium|Pa 231.04 protactinium|U 238.03 uranium|
Np 237 neptunium|Pu 244 plutonium|Am 243 americium|Cm 247 curium|Bk 247 berkelium|Cf 251 californium|
Es 252 einsteinium|Fm 257 fermium|Md 258 mendelevium|No 259 nobelium|Lr 262 lawrencium"""
ATOMIC: dict[str, float] = {}
ELEMENT_NAMES: dict[str, str] = {}   # "iron" → "Fe"
SYMBOL_NAMES: dict[str, str] = {}    # "Fe" → "iron"
for _row in _ELEMENTS.replace("\n", "").split("|"):
    _sym, _w, _name = _row.split()
    ATOMIC[_sym], ELEMENT_NAMES[_name], SYMBOL_NAMES[_sym] = float(_w), _sym, _name
ATOMIC.update(fields.ATOMIC)  # the field engine's values win, so both engines agree to the last digit
DIATOMIC = {"H", "N", "O", "F", "Cl", "Br", "I"}
# elements that turn up in everyday compounds; a lower-case formula ("cuso4") may only be read with these
COMMON_EL = set("H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Ti V Cr Mn Fe Co Ni Cu Zn As Se Br Kr Rb Sr Ag "
                "Cd Sn Sb I Xe Cs Ba W Pt Au Hg Pb Bi U".split())
MOLECULAR = {"H2", "N2", "O2", "O3", "F2", "Cl2", "Br2", "I2", "P4", "S8", "C60"}

# ---------------------------------------------------------------- formulas


def parse_formula(s: str) -> dict[str, float] | None:
    """Element counts of a formula, in order of first appearance; None if it isn't one.

    Handles groups "Ca3(PO4)2", brackets "K4[Fe(CN)6]" and hydrates "CuSO4·5H2O" (a leading number multiplies its part)."""
    counts: dict[str, float] = {}

    def group(s: str, i: int, mult: float, close: str | None) -> int:
        while i < len(s):
            ch = s[i]
            if ch in "([":
                j = group(s, i + 1, 1.0, ")" if ch == "(" else "]")
                m = re.match(r"\d*", s[j:])
                inner = counts_stack.pop()
                k = int(m.group(0)) if m.group(0) else 1
                for el, n in inner.items():
                    counts_stack[-1][el] = counts_stack[-1].get(el, 0) + n * k
                i = j + len(m.group(0))
                continue
            if ch in ")]":
                if ch != close:
                    raise ValueError(s)
                return i + 1
            m = re.match(r"([A-Z][a-z]?)(\d*)", s[i:])
            if not m or m.group(1) not in ATOMIC:
                raise ValueError(s)
            el = m.group(1)
            counts_stack[-1][el] = counts_stack[-1].get(el, 0) + (int(m.group(2)) if m.group(2) else 1)
            i += len(m.group(0))
        if close:
            raise ValueError(s)
        return i

    try:
        for part in s.split("·"):
            m = re.match(r"(\d+(?:\.\d+)?|½)?(.+)$", part)
            if not m:
                return None
            k = 0.5 if m.group(1) == "½" else float(m.group(1)) if m.group(1) else 1.0
            body = m.group(2)
            counts_stack: list[dict[str, float]] = [{}]

            def push(s=body):
                # group() pushes a fresh dict for every "(" so nested multipliers apply to the right atoms
                return s
            # re-implemented with an explicit stack: every bracket opens a new level
            stack: list[dict[str, float]] = [{}]
            i = 0
            while i < len(body):
                ch = body[i]
                if ch in "([":
                    stack.append({})
                    stack[-1]["__close__"] = ")" if ch == "(" else "]"  # type: ignore[assignment]
                    i += 1
                    continue
                if ch in ")]":
                    top = stack.pop()
                    if len(stack) == 0 or top.pop("__close__", None) != ch:
                        return None
                    n = re.match(r"\d*", body[i + 1:]).group(0)
                    k2 = int(n) if n else 1
                    for el, c in top.items():
                        stack[-1][el] = stack[-1].get(el, 0) + c * k2
                    i += 1 + len(n)
                    continue
                em = re.match(r"([A-Z][a-z]?)(\d*)", body[i:])
                if not em or em.group(1) not in ATOMIC:
                    return None
                stack[-1][em.group(1)] = stack[-1].get(em.group(1), 0) + (int(em.group(2)) if em.group(2) else 1)
                i += len(em.group(0))
            if len(stack) != 1:
                return None
            for el, c in stack[0].items():
                counts[el] = counts.get(el, 0) + c * k
    except (ValueError, IndexError, AttributeError):
        return None
    return counts or None


def molar_mass(formula: str) -> float:
    return sum(ATOMIC[el] * n for el, n in parse_formula(formula).items())


def _cnt(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else f"{n:g}"


# ---------------------------------------------------------------- named compounds

COMPOUNDS = {
    # everyday and simple molecules
    "water": "H2O", "distilled water": "H2O", "hydrogen peroxide": "H2O2", "ammonia": "NH3", "ozone": "O3",
    "methane": "CH4", "ethane": "C2H6", "propane": "C3H8", "butane": "C4H10", "pentane": "C5H12", "hexane": "C6H14",
    "heptane": "C7H16", "octane": "C8H18", "nonane": "C9H20", "decane": "C10H22", "ethene": "C2H4",
    "ethylene": "C2H4", "propene": "C3H6", "propylene": "C3H6", "ethyne": "C2H2", "acetylene": "C2H2",
    "benzene": "C6H6", "toluene": "C7H8", "naphthalene": "C10H8", "cyclohexane": "C6H12", "styrene": "C8H8",
    "methanol": "CH3OH", "methyl alcohol": "CH3OH", "ethanol": "C2H5OH", "ethyl alcohol": "C2H5OH",
    "alcohol": "C2H5OH", "propanol": "C3H7OH", "isopropanol": "C3H8O", "isopropyl alcohol": "C3H8O",
    "rubbing alcohol": "C3H8O", "butanol": "C4H9OH", "glycerol": "C3H8O3", "glycerin": "C3H8O3",
    "glycerine": "C3H8O3", "ethylene glycol": "C2H6O2", "phenol": "C6H5OH", "acetone": "C3H6O",
    "propanone": "C3H6O", "formaldehyde": "CH2O", "methanal": "CH2O", "acetaldehyde": "C2H4O", "ethanal": "C2H4O",
    "diethyl ether": "C4H10O", "chloroform": "CHCl3", "trichloromethane": "CHCl3", "dichloromethane": "CH2Cl2",
    "tetrachloromethane": "CCl4", "ethyl acetate": "C4H8O2", "urea": "CO(NH2)2",
    # organic acids
    "acetic acid": "CH3COOH", "formic acid": "HCOOH", "methanoic acid": "HCOOH", "citric acid": "C6H8O7",
    "lactic acid": "C3H6O3", "oxalic acid": "H2C2O4", "benzoic acid": "C6H5COOH", "salicylic acid": "C7H6O3",
    "ascorbic acid": "C6H8O6", "vitamin c": "C6H8O6", "stearic acid": "C18H36O2", "palmitic acid": "C16H32O2",
    "oleic acid": "C18H34O2", "butyric acid": "C4H8O2", "propanoic acid": "C2H5COOH", "propionic acid": "C2H5COOH",
    "tartaric acid": "C4H6O6", "malic acid": "C4H6O5", "uric acid": "C5H4N4O3", "glycine": "C2H5NO2",
    "alanine": "C3H7NO2",
    # sugars
    "glucose": "C6H12O6", "dextrose": "C6H12O6", "fructose": "C6H12O6", "galactose": "C6H12O6",
    "sucrose": "C12H22O11", "table sugar": "C12H22O11", "sugar": "C12H22O11", "lactose": "C12H22O11",
    "maltose": "C12H22O11", "ribose": "C5H10O5", "deoxyribose": "C5H10O4",
    # drugs and biomolecules
    "caffeine": "C8H10N4O2", "aspirin": "C9H8O4", "acetylsalicylic acid": "C9H8O4", "paracetamol": "C8H9NO2",
    "acetaminophen": "C8H9NO2", "ibuprofen": "C13H18O2", "nicotine": "C10H14N2", "morphine": "C17H19NO3",
    "codeine": "C18H21NO3", "theobromine": "C7H8N4O2", "capsaicin": "C18H27NO3", "dopamine": "C8H11NO2",
    "serotonin": "C10H12N2O", "adrenaline": "C9H13NO3", "epinephrine": "C9H13NO3", "cholesterol": "C27H46O",
    "testosterone": "C19H28O2", "vanillin": "C8H8O3", "menthol": "C10H20O", "limonene": "C10H16",
    "nitroglycerin": "C3H5N3O9", "nitroglycerine": "C3H5N3O9", "tnt": "C7H5N3O6", "trinitrotoluene": "C7H5N3O6",
    "aspartame": "C14H18N2O5", "saccharin": "C7H5NO3S", "quinine": "C20H24N2O2", "melatonin": "C13H16N2O2",
    "atp": "C10H16N5O13P3", "adenine": "C5H5N5", "guanine": "C5H5N5O", "cytosine": "C4H5N3O",
    "thymine": "C5H6N2O2", "uracil": "C4H4N2O2",
    # gases
    "oxygen gas": "O2", "hydrogen gas": "H2", "nitrogen gas": "N2", "chlorine gas": "Cl2", "fluorine gas": "F2",
    "dry ice": "CO2", "nitrous oxide": "N2O", "laughing gas": "N2O", "nitric oxide": "NO", "hydrogen sulfide": "H2S",
    "hydrogen chloride": "HCl", "hydrogen fluoride": "HF", "hydrogen bromide": "HBr", "hydrogen iodide": "HI",
    "hydrogen cyanide": "HCN", "phosphine": "PH3", "silane": "SiH4", "hydrazine": "N2H4",
    "carbon dioxide": "CO2", "carbon monoxide": "CO",
    # mineral acids
    "hydrochloric acid": "HCl", "muriatic acid": "HCl", "sulfuric acid": "H2SO4", "nitric acid": "HNO3",
    "phosphoric acid": "H3PO4", "orthophosphoric acid": "H3PO4", "carbonic acid": "H2CO3",
    "hydrofluoric acid": "HF", "hydrobromic acid": "HBr", "hydroiodic acid": "HI", "hydriodic acid": "HI",
    "perchloric acid": "HClO4", "chloric acid": "HClO3", "chlorous acid": "HClO2", "hypochlorous acid": "HClO",
    "nitrous acid": "HNO2", "sulfurous acid": "H2SO3", "boric acid": "H3BO3", "hydrocyanic acid": "HCN",
    "phosphorous acid": "H3PO3", "chromic acid": "H2CrO4", "hydrosulfuric acid": "H2S",
    # bases and common names
    "caustic soda": "NaOH", "lye": "NaOH", "caustic potash": "KOH", "slaked lime": "Ca(OH)2",
    "hydrated lime": "Ca(OH)2", "limewater": "Ca(OH)2", "lime water": "Ca(OH)2", "milk of magnesia": "Mg(OH)2",
    "quicklime": "CaO", "burnt lime": "CaO", "table salt": "NaCl", "salt": "NaCl", "rock salt": "NaCl",
    "halite": "NaCl", "baking soda": "NaHCO3", "bicarbonate of soda": "NaHCO3", "washing soda": "Na2CO3·10H2O",
    "soda ash": "Na2CO3", "chalk": "CaCO3", "limestone": "CaCO3", "marble": "CaCO3", "calcite": "CaCO3",
    "rust": "Fe2O3", "hematite": "Fe2O3", "haematite": "Fe2O3", "magnetite": "Fe3O4", "pyrite": "FeS2",
    "fool's gold": "FeS2", "galena": "PbS", "cinnabar": "HgS", "alumina": "Al2O3", "corundum": "Al2O3",
    "silica": "SiO2", "quartz": "SiO2", "sand": "SiO2", "gypsum": "CaSO4·2H2O", "plaster of paris": "CaSO4·0.5H2O",
    "epsom salt": "MgSO4·7H2O", "epsom salts": "MgSO4·7H2O", "blue vitriol": "CuSO4·5H2O",
    "green vitriol": "FeSO4·7H2O", "borax": "Na2B4O7·10H2O", "saltpeter": "KNO3", "saltpetre": "KNO3",
    "chile saltpeter": "NaNO3", "potash": "K2CO3", "bleach": "NaClO", "fluorite": "CaF2", "dolomite": "CaMg(CO3)2",
    "malachite": "Cu2CO3(OH)2", "cryolite": "Na3AlF6", "alum": "KAl(SO4)2·12H2O", "potash alum": "KAl(SO4)2·12H2O",
    "glauber's salt": "Na2SO4·10H2O", "mohr's salt": "(NH4)2Fe(SO4)2·6H2O", "sal ammoniac": "NH4Cl",
    "potassium ferrocyanide": "K4[Fe(CN)6]", "potassium ferricyanide": "K3[Fe(CN)6]", "trisodium phosphate": "Na3PO4",
    "disodium phosphate": "Na2HPO4", "monosodium glutamate": "C5H8NO4Na",
}
for _name, _f in fields.NAMES.items():
    COMPOUNDS.setdefault(_name, _f)
COMPOUNDS.pop("oxygen", None)  # a bare element name is read by the element rule below (with its note)

# ions: name → (formula, |charge|, polyatomic?). Metals with one usual charge need no numeral; "copper sulfate" is CuSO4.
CATIONS = {
    "lithium": ("Li", 1, False), "sodium": ("Na", 1, False), "potassium": ("K", 1, False),
    "rubidium": ("Rb", 1, False), "caesium": ("Cs", 1, False), "ammonium": ("NH4", 1, True),
    "silver": ("Ag", 1, False), "copper(i)": ("Cu", 1, False), "cuprous": ("Cu", 1, False),
    "copper(ii)": ("Cu", 2, False), "cupric": ("Cu", 2, False), "copper": ("Cu", 2, False),
    "magnesium": ("Mg", 2, False), "calcium": ("Ca", 2, False), "strontium": ("Sr", 2, False),
    "barium": ("Ba", 2, False), "beryllium": ("Be", 2, False), "zinc": ("Zn", 2, False), "cadmium": ("Cd", 2, False),
    "nickel(ii)": ("Ni", 2, False), "nickel": ("Ni", 2, False), "cobalt(ii)": ("Co", 2, False),
    "cobalt(iii)": ("Co", 3, False), "cobalt": ("Co", 2, False), "iron(ii)": ("Fe", 2, False),
    "ferrous": ("Fe", 2, False), "iron(iii)": ("Fe", 3, False), "ferric": ("Fe", 3, False),
    "manganese(ii)": ("Mn", 2, False), "manganese(iv)": ("Mn", 4, False), "manganese": ("Mn", 2, False),
    "chromium(ii)": ("Cr", 2, False), "chromium(iii)": ("Cr", 3, False), "chromium": ("Cr", 3, False),
    "lead(ii)": ("Pb", 2, False), "plumbous": ("Pb", 2, False), "lead(iv)": ("Pb", 4, False),
    "plumbic": ("Pb", 4, False), "lead": ("Pb", 2, False), "tin(ii)": ("Sn", 2, False), "stannous": ("Sn", 2, False),
    "tin(iv)": ("Sn", 4, False), "stannic": ("Sn", 4, False), "mercury(ii)": ("Hg", 2, False),
    "mercuric": ("Hg", 2, False), "mercury(i)": ("Hg2", 2, True), "mercurous": ("Hg2", 2, True),
    "aluminium": ("Al", 3, False), "gallium": ("Ga", 3, False), "titanium(iv)": ("Ti", 4, False),
    "gold(i)": ("Au", 1, False), "gold(iii)": ("Au", 3, False),
}
ANIONS = {
    "fluoride": ("F", 1, False), "chloride": ("Cl", 1, False), "bromide": ("Br", 1, False), "iodide": ("I", 1, False),
    "oxide": ("O", 2, False), "sulfide": ("S", 2, False), "selenide": ("Se", 2, False), "nitride": ("N", 3, False),
    "phosphide": ("P", 3, False), "hydride": ("H", 1, False), "hydroxide": ("OH", 1, True),
    "cyanide": ("CN", 1, True), "nitrate": ("NO3", 1, True), "nitrite": ("NO2", 1, True),
    "sulfate": ("SO4", 2, True), "sulfite": ("SO3", 2, True), "hydrogen sulfate": ("HSO4", 1, True),
    "bisulfate": ("HSO4", 1, True), "hydrogen sulfite": ("HSO3", 1, True), "bisulfite": ("HSO3", 1, True),
    "carbonate": ("CO3", 2, True), "hydrogen carbonate": ("HCO3", 1, True), "bicarbonate": ("HCO3", 1, True),
    "phosphate": ("PO4", 3, True), "hydrogen phosphate": ("HPO4", 2, True),
    "dihydrogen phosphate": ("H2PO4", 1, True), "acetate": ("CH3COO", 1, True), "formate": ("HCOO", 1, True),
    "permanganate": ("MnO4", 1, True), "chromate": ("CrO4", 2, True), "dichromate": ("Cr2O7", 2, True),
    "chlorate": ("ClO3", 1, True), "perchlorate": ("ClO4", 1, True), "chlorite": ("ClO2", 1, True),
    "hypochlorite": ("ClO", 1, True), "bromate": ("BrO3", 1, True), "iodate": ("IO3", 1, True),
    "thiosulfate": ("S2O3", 2, True), "oxalate": ("C2O4", 2, True), "peroxide": ("O2", 2, True),
    "silicate": ("SiO3", 2, True), "thiocyanate": ("SCN", 1, True), "borate": ("BO3", 3, True),
    "arsenate": ("AsO4", 3, True),
}


def _ionic(cat: tuple, an: tuple) -> tuple[str, int, int]:
    (cf, cq, cp), (af, aq, ap) = cat, an
    lcm = cq * aq // math.gcd(cq, aq)
    nc, na = lcm // cq, lcm // aq

    def part(f, n, poly):
        return f if n == 1 else (f"({f}){n}" if poly else f"{f}{n}")
    return part(cf, nc, cp) + part(af, na, ap), nc, na


IONIC: dict[str, tuple] = {}   # formula → (cation name, cations per unit, anion name, anions per unit)
for _cn, _c in CATIONS.items():
    for _an, _a in ANIONS.items():
        _f, _nc, _na = _ionic(_c, _a)
        IONIC.setdefault(_f, (_cn, _nc, _an, _na))
for _f, _row in (("NaCl", ("sodium", 1, "chloride", 1)),):
    IONIC.setdefault(_f, _row)

PREFIX = {"mono": 1, "mon": 1, "di": 2, "tri": 3, "tetra": 4, "tetr": 4, "penta": 5, "pent": 5, "hexa": 6, "hex": 6,
          "hepta": 7, "hept": 7, "octa": 8, "oct": 8, "nona": 9, "non": 9, "deca": 10, "dec": 10}
HYDRATE = {"hemi": 0.5, "mono": 1, "di": 2, "tri": 3, "tetra": 4, "penta": 5, "hexa": 6, "hepta": 7, "octa": 8,
           "nona": 9, "deca": 10, "dodeca": 12}
NONMETALS = {n: ELEMENT_NAMES[n] for n in ("boron", "carbon", "nitrogen", "phosphorus", "sulfur", "silicon",
                                            "selenium", "chlorine", "bromine", "iodine", "xenon", "arsenic", "oxygen",
                                            "fluorine", "hydrogen")}
BINARY = {"oxide": "O", "fluoride": "F", "chloride": "Cl", "bromide": "Br", "iodide": "I", "sulfide": "S",
          "nitride": "N"}


def _alt(words) -> str:
    return "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))


NAME_RE = re.compile(rf"(?<![\w-])(?:{_alt(COMPOUNDS)})(?![\w-])")
IONIC_RE = re.compile(rf"(?<![\w-])({_alt(CATIONS)})\s+({_alt(ANIONS)})(?![\w-])")
COVALENT_RE = re.compile(rf"(?<![\w-])(di|tri|tetra|penta|hexa)?({_alt(NONMETALS)})\s+"
                         rf"(mono|mon|di|tri|tetra|tetr|penta|pent|hexa|hex|hepta|hept|octa|oct|nona|non|deca|dec)"
                         rf"({_alt(BINARY)})(?![\w-])")
HYDRATE_RE = re.compile(rf"\s*-?\s*({_alt(HYDRATE)})hydrate\b")
ELEMENT_CTX_RE = re.compile(rf"(?:\b(?:of|for)\s+(?:(?:the|a|an|pure|solid|liquid|metallic|elemental|element|"
                            rf"some|natural)\s+)*)({_alt(ELEMENT_NAMES)})(?![\w-])(?!\s+ions?\b)"
                            rf"|(?<![\w-])({_alt(ELEMENT_NAMES)})\s+(?=(?:atoms?|gas|metal|sample|powder|wire|foil)\b)")
ELEMENT_ANY_RE = re.compile(rf"(?<![\w-])({_alt(ELEMENT_NAMES)})(?![\w-])")

# formulas people type in lower case, read without guessing; everything known above, minus English words
_KNOWN_FORMULAS = set(COMPOUNDS.values()) | set(IONIC) | set(fields.LOWER.values()) | MOLECULAR
LOWER_MAP: dict[str, str] = {}
for _f in sorted(_KNOWN_FORMULAS):
    LOWER_MAP.setdefault(_f.lower(), _f)
for _w in ("no", "hi", "co", "cs", "bi", "os", "cus", "in", "as", "be", "he", "at", "nab", "cab", "sin", "cos", "nap",
           "bas", "pb", "he", "hf"):
    LOWER_MAP.pop(_w, None)
LOWER_MAP["hf"] = "HF"
# all-caps tokens with no digit that are formulas (others, like "CPU", "UI", "OK", are words)
CAPS_OK = {"CO", "NO", "HF", "KI", "KF", "HCN", "KCN", "KOH", "HI", "CS2", "BN"}
STOP = {"I", "OK", "PV", "SI", "PH", "POH", "HOW", "CPU", "UI", "CI", "BI", "IO", "OS", "US", "UK", "NaN", "CS", "NB",
        "SNS", "NYC", "CNN", "BBC", "HI", "PS", "HP", "PC", "CC", "IV", "VI", "II", "III", "VII", "SO", "STP", "SATP",
        "KB", "MB", "GB", "TB", "PB", "BC", "AC", "DC", "Hi", "Ho", "No", "In", "As", "At", "Be", "He", "Am", "Es"}

# ---------------------------------------------------------------- numbers and units

NUM = r"-?(?:\d{1,3}(?:,\d{3})+(?!\d)|\d+)(?:\.\d+)?(?:e[+-]?\d+)?|-?\.\d+(?:e[+-]?\d+)?"
_UNITS = [
    # mass → g
    ("kilograms", "mass", "1000", "kg"), ("kilogram", "mass", "1000", "kg"), ("kg", "mass", "1000", "kg"),
    ("milligrams", "mass", "0.001", "mg"), ("milligram", "mass", "0.001", "mg"), ("mg", "mass", "0.001", "mg"),
    ("micrograms", "mass", "0.000001", "µg"), ("µg", "mass", "0.000001", "µg"), ("ug", "mass", "0.000001", "µg"),
    ("mcg", "mass", "0.000001", "µg"), ("grams", "mass", "1", "g"), ("gram", "mass", "1", "g"),
    ("gms", "mass", "1", "g"), ("gm", "mass", "1", "g"), ("g", "mass", "1", "g"),
    # molar mass → g/mol
    ("g/mol", "molar_mass", "1", "g/mol"), ("g mol-1", "molar_mass", "1", "g/mol"),
    ("grams per mole", "molar_mass", "1", "g/mol"), ("g per mol", "molar_mass", "1", "g/mol"),
    # concentration → mol/L
    ("mol/l", "conc", "1", "M"), ("mol/dm3", "conc", "1", "M"), ("mol dm-3", "conc", "1", "M"),
    ("mol l-1", "conc", "1", "M"), ("mol/litre", "conc", "1", "M"), ("mol/liter", "conc", "1", "M"),
    ("moles per liter", "conc", "1", "M"), ("moles per litre", "conc", "1", "M"), ("mol per litre", "conc", "1", "M"),
    ("mol per liter", "conc", "1", "M"), ("moles/l", "conc", "1", "M"), ("mmol/l", "conc", "0.001", "mM"),
    ("millimolar", "conc", "0.001", "mM"), ("molar", "conc", "1", "M"), ("mm", "conc", "0.001", "mM"),
    ("m", "conc", "1", "M"),
    # amount → mol
    ("millimoles", "amount", "0.001", "mmol"), ("millimole", "amount", "0.001", "mmol"),
    ("mmol", "amount", "0.001", "mmol"), ("kmol", "amount", "1000", "kmol"), ("moles", "amount", "1", "mol"),
    ("mole", "amount", "1", "mol"), ("mols", "amount", "1", "mol"), ("mol", "amount", "1", "mol"),
    # volume → L
    ("millilitres", "vol", "0.001", "mL"), ("milliliters", "vol", "0.001", "mL"), ("millilitre", "vol", "0.001", "mL"),
    ("milliliter", "vol", "0.001", "mL"), ("ml", "vol", "0.001", "mL"), ("cm3", "vol", "0.001", "cm³"),
    ("cm^3", "vol", "0.001", "cm³"), ("cc", "vol", "0.001", "cm³"), ("µl", "vol", "0.000001", "µL"),
    ("ul", "vol", "0.000001", "µL"), ("microliters", "vol", "0.000001", "µL"), ("dm3", "vol", "1", "dm³"),
    ("dm^3", "vol", "1", "dm³"), ("litres", "vol", "1", "L"), ("liters", "vol", "1", "L"), ("litre", "vol", "1", "L"),
    ("liter", "vol", "1", "L"), ("l", "vol", "1", "L"), ("m3", "vol", "1000", "m³"), ("m^3", "vol", "1000", "m³"),
    # pressure → atm
    ("atmospheres", "pressure", "1", "atm"), ("atmosphere", "pressure", "1", "atm"), ("atm", "pressure", "1", "atm"),
    ("kilopascals", "pressure", "1/101.325", "kPa"), ("kpa", "pressure", "1/101.325", "kPa"),
    ("hpa", "pressure", "1/1013.25", "hPa"), ("mbar", "pressure", "1/1013.25", "mbar"),
    ("pascals", "pressure", "1/101325", "Pa"), ("pa", "pressure", "1/101325", "Pa"),
    ("mmhg", "pressure", "1/760", "mmHg"), ("mm hg", "pressure", "1/760", "mmHg"),
    ("millimeters of mercury", "pressure", "1/760", "mmHg"), ("torr", "pressure", "1/760", "torr"),
    ("bar", "pressure", "1/1.01325", "bar"), ("psi", "pressure", "1/14.6959488", "psi"),
    # temperature → K
    ("kelvin", "temp", "K", "K"), ("k", "temp", "K", "K"), ("°c", "temp", "C", "°C"), ("° c", "temp", "C", "°C"),
    ("degrees celsius", "temp", "C", "°C"), ("degree celsius", "temp", "C", "°C"),
    ("degrees centigrade", "temp", "C", "°C"), ("degrees c", "temp", "C", "°C"), ("deg c", "temp", "C", "°C"),
    ("celsius", "temp", "C", "°C"), ("c", "temp", "C", "°C"), ("°f", "temp", "F", "°F"),
    ("degrees fahrenheit", "temp", "F", "°F"), ("degrees f", "temp", "F", "°F"), ("fahrenheit", "temp", "F", "°F"),
    ("degrees", "temp", "C", "°C"),
    # particles
    ("formula units", "particles", "1", "formula units"), ("formula unit", "particles", "1", "formula units"),
    ("molecules", "particles", "1", "molecules"), ("molecule", "particles", "1", "molecules"),
    ("atoms", "particles", "1", "atoms"), ("atom", "particles", "1", "atoms"),
    ("particles", "particles", "1", "particles"), ("particle", "particles", "1", "particles"),
    ("ions", "particles", "1", "ions"), ("ion", "particles", "1", "ions"),
]


def _rat(s: str) -> sp.Rational:
    if "/" in s:
        a, b = s.split("/")
        return sp.Rational(a) / sp.Rational(b)
    return sp.Rational(s)


UNITS = {u: (kind, factor if kind == "temp" else _rat(factor), shown) for u, kind, factor, shown in _UNITS}
QTY_RE = re.compile(rf"(?<![\w.·)\]^/])({NUM})\s*({_alt(UNITS)})(?![a-z0-9²³])", re.I)
RANGE_RE = re.compile(rf"\bfrom\s+({NUM})\s*(?:to|-)\s*(?={NUM}\s*(?:{_alt(UNITS)})(?![a-z0-9]))", re.I)
SIG_RE = re.compile(r"(?:\b(?:to|in|with|at|using|round(?:ed)?(?: it)?(?: to)?|give(?: it)?(?: to| in)?)\s+)?"
                    r"\b(\d{1,2})\s*(?:sig(?:nificant)?\.?\s*(?:figs?|figures|digits)|s\.?f\.?(?![a-z]))", re.I)
DP_RE = re.compile(r"(?:\b(?:to|in|with|at|round(?:ed)?(?: it)?(?: to)?)\s+)?\b(\d{1,2})\s*(?:d\.?p\.?(?![a-z])|"
                   r"decimal places?|decimals?)", re.I)
EXACT_RE = re.compile(r"\bexact(?:ly)?\b|\bfraction\b|\bexact form\b", re.I)


@dataclass
class Qty:
    kind: str           # mass (g), amount (mol), vol (L), conc (mol/L), pressure (atm), temp (K), particles, molar_mass
    value: float        # in the base unit above
    num: float          # the number as typed
    unit: str           # the unit as shown
    start: int
    end: int
    exact: sp.Expr | None = None

    @property
    def shown(self) -> str:
        return f"{_w(self.num)} {self.unit}"


@dataclass
class Comp:
    formula: str
    label: str
    start: int
    end: int
    tier: int                       # 0 written as a formula, 1 named, 2 a lone element
    counts: dict = field(default_factory=dict)
    mm: float = 0.0
    note: str = ""

    @property
    def name(self) -> str:
        return self.label if self.label == self.formula else f"{self.label} ({self.formula})"


# ---------------------------------------------------------------- formatting


def _sci(x: float, sig: int, keep: bool) -> str:
    m, e = f"{x:.{sig - 1}e}".split("e")
    if not keep and "." in m:
        m = m.rstrip("0").rstrip(".")
    return f"{m} × 10^{int(e)}"


def num(x: float, sig: int | None = None, dp: int | None = None) -> str:
    """4 significant figures by default (trailing zeros dropped); exactly `sig` figures, or `dp` decimals, when asked.
    Very large or small values in scientific notation: 6.022 × 10^23."""
    if dp is not None and 1e-3 <= abs(x) < 1e7:
        return f"{x:,.{dp}f}"
    s_fig, keep = (sig, True) if sig else (4, False)
    if x == 0 or not math.isfinite(x):
        return "0" if x == 0 else str(x)
    x = float(f"{x:.{s_fig}g}")
    ax = abs(x)
    if ax >= 1e7 or ax < 1e-3:
        return _sci(x, s_fig, keep)
    digits = max(0, s_fig - int(math.floor(math.log10(ax))) - 1)
    s = f"{x:,.{digits}f}"
    if not keep and "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def _w(x: float) -> str:
    """A working value in the steps: up to 6 significant figures, so rounding never shows in the arithmetic."""
    if x == 0:
        return "0"
    ax = abs(x)
    if ax >= 1e7 or ax < 1e-4:
        return _sci(x, 5, False)
    s = f"{float(f'{x:.6g}'):,.10f}".rstrip("0").rstrip(".")
    return s


# ---------------------------------------------------------------- reading the message

_SUB = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-")
_ROMAN = {"1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v", "6": "vi", "7": "vii"}
_METALS = r"iron|copper|lead|tin|mercury|cobalt|manganese|chromium|nickel|gold|titanium"
_SPELL = [(r"sulph", "sulf"), (r"\baluminum\b", "aluminium"), (r"\bcesium\b", "caesium"), (r"ethanoate", "acetate"),
          (r"ethanoic acid", "acetic acid"), (r"hydrogencarbonate", "hydrogen carbonate"), (r"\bflour", "fluor"),
          (r"\bamon(ia|ium)", r"ammon\1"), (r"\bpotasium\b", "potassium"), (r"\bcaffiene\b", "caffeine"),
          (r"\basprin\b", "aspirin"), (r"\bclorine\b", "chlorine"), (r"\bclor", "chlor"), (r"\bsodim\b", "sodium"),
          (r"\bpheonol\b", "phenol")]


def normalize(text: str) -> str:
    s = text.replace("’", "'").replace("−", "-").replace("–", "-").replace("º", "°").replace("˚", "°")
    s = re.sub(r"[•⋅∙・]", "·", s).replace("μ", "µ")
    s = s.translate(_SUB)
    s = re.sub(r"10([⁺⁻]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+)", lambda m: "10^" + m.group(1).translate(_SUP), s)
    s = s.translate(_SUP)
    # scientific notation: 6.022 x 10^23, 6.022×10^23, 1.5*10**-3, 10^-4 → 6.022e23 …
    s = re.sub(r"(\d(?:\.\d+)?)\s*(?:x|×|\*|·|X)\s*10\s*(?:\^|\*\*)\s*\(?\s*([+-]?\d+)\s*\)?", r"\1e\2", s)
    s = re.sub(r"(?<![\d.e])10\s*(?:\^|\*\*)\s*\(?\s*([+-]?\d+)\s*\)?", r"1e\1", s)
    s = re.sub(r"(\d)E([+-]?\d)", r"\1e\2", s)
    # a formula hint like "(C1V1 = C2V2)" or "M1V1=M2V2" names the method; it is not a pair of compounds
    s = re.sub(r"\(?\s*\b([cm])1\s*[·*]?\s*v1\s*=\s*\1(?:2)\s*[·*]?\s*v2\b\s*\)?", " (dilution) ", s, flags=re.I)
    # hydrates: CuSO4.5H2O, CuSO4*5H2O, CuSO4 · 5 H2O → CuSO4·5H2O
    s = re.sub(r"((?:[A-Z][a-z]?\d*|[(\[](?:[A-Z][a-z]?\d*)+[)\]]\d*)+)\s*[.*·]\s*(\d+(?:\.\d+)?|½)?\s*(H2O)\b",
               r"\1·\2\3", s)
    s = re.sub(r"\b([a-z][a-z0-9()]*\d)\s*[.*·]\s*(\d+)\s*(h2o)\b", r"\1·\2\3", s)
    for a, b in _SPELL:
        s = re.sub(a, b, s, flags=re.I)
    # iron (III), iron(3), iron(3+), iron iii oxide → iron(III)
    s = re.sub(rf"\b({_METALS})\s*\(\s*([ivx]+)\s*\)", r"\1(\2)", s, flags=re.I)
    s = re.sub(rf"\b({_METALS})\s*\(\s*([1-7])\s*\+?\s*\)", lambda m: f"{m.group(1)}({_ROMAN[m.group(2)].upper()})",
               s, flags=re.I)
    s = re.sub(rf"\b({_METALS})\s+(i{{1,3}}|iv|vi?|vii)\s+(?=[a-z])", r"\1(\2) ", s, flags=re.I)
    return s


def _blank(s: str, a: int, b: int, ch: str = " ") -> str:
    return s[:a] + ch * (b - a) + s[b:]


class Parsed:
    """The message read once: quantities with units, the compounds named, and what is left when both are removed."""

    def __init__(self, text: str):
        raw = normalize(text)
        self.sig = self.dp = None
        for rx, attr in ((SIG_RE, "sig"), (DP_RE, "dp")):
            for m in list(rx.finditer(raw)):
                v = int(m.group(1))
                if 1 <= v <= 12:
                    setattr(self, attr, v)
                raw = _blank(raw, m.start(), m.end())
        self.exact = bool(EXACT_RE.search(raw))
        self.raw, self.t = raw, raw.lower()
        self.comps = _compounds(raw, self.t)
        main = [c for c in self.comps if c.tier < 2]
        self.solution_ctx = bool(main) or bool(re.search(r"\b(?:solution|dilut\w*|stock|molar\w*|ph|poh|solute|"
                                                         r"dissolv\w*|concentration)\b", self.t))
        self.qs = self._quantities()
        tc = self.t
        for c in self.comps:
            tc = _blank(tc, c.start, c.end, "§")
        self.tc = tc   # compounds blanked, numbers kept
        rem = tc
        for q in self.qs:
            rem = _blank(rem, q.start, q.end, "#")
        rem = re.sub(rf"(?<![\w.]){NUM}\s*%", lambda m: "#" * len(m.group(0)), rem)  # "a 5% solution" is given
        self.rem = rem  # what the question asks, with every given quantity and compound blanked
        self.comp = _choose(self.comps)

    def _quantities(self) -> list[Qty]:
        out: list[Qty] = []
        for m in QTY_RE.finditer(self.raw):
            q = self._qty(m.group(1), m.group(2), m.start(), m.end())
            if q:
                out.append(q)
        for m in RANGE_RE.finditer(self.raw):  # "heated from 25 to 100 °C": the 25 takes the unit of the 100
            nxt = QTY_RE.match(self.raw, m.end())
            if nxt and not any(q.start == m.start(1) for q in out):
                q = self._qty(m.group(1), nxt.group(2), m.start(1), m.end(1))
                if q:
                    out.append(q)
        # "1.2e24 of water molecules", "3.01e23 H2O molecules": a big count with the particle word a little later
        for m in re.finditer(rf"(?<![\w.])({NUM})\s+(?:of\s+)?(?:[\w()·\[\]]+\s+){{1,2}}?"
                             rf"(molecules?|atoms?|particles?|formula units?|ions?)\b", self.raw, re.I):
            v = float(m.group(1).replace(",", ""))
            if v >= 1e6 and not any(q.start <= m.start(1) < q.end for q in out):
                out.append(Qty("particles", v, v, UNITS[m.group(2).lower()][2], m.start(1), m.end(), sp.Rational(
                    m.group(1).replace(",", ""))))
        return sorted(out, key=lambda q: q.start)

    def _qty(self, n: str, unit: str, a: int, b: int) -> Qty | None:
        low = unit.lower()
        kind, factor, shown = UNITS[low]
        if low == "m" and unit != "M" and not self.solution_ctx:
            return None  # "3 m" is metres unless this is about a solution
        if low == "mm" and unit != "mM":
            return None  # millimetres
        if any(c.start <= a < c.end for c in self.comps):
            return None
        v = float(n.replace(",", ""))
        ex = sp.Rational(n.replace(",", ""))
        if kind == "temp":
            if factor == "C":
                k, kx = v + 273.15, ex + sp.Rational("273.15")
            elif factor == "F":
                k, kx = (v - 32) * 5 / 9 + 273.15, (ex - 32) * sp.Rational(5, 9) + sp.Rational("273.15")
            else:
                k, kx = v, ex
            if k <= 0:
                return None
            return Qty("temp", k, v, shown, a, b, kx)
        return Qty(kind, v * float(factor), v, shown, a, b, ex * factor)

    def of(self, kind: str) -> list[Qty]:
        return [q for q in self.qs if q.kind == kind]

    def asks(self, key: str) -> bool:
        return bool(ASK[key].search(self.rem))

    def f(self, x: float, unit: str = "") -> str:
        return f"{num(x, self.sig, self.dp)} {unit}".strip()

    def mmf(self, x: float) -> str:
        """Molar masses are quoted to 2 decimals (18.02 g/mol) unless a precision was asked for."""
        if self.sig or self.dp is not None:
            return self.f(x, "g/mol")
        return f"{x:,.2f} g/mol"

    def exact_ans(self, x: float, ex, unit: str = "") -> str:
        """The answer, with its exact fraction first when one was asked for and it is a tidy one."""
        s = self.f(x, unit)
        if self.exact and ex is not None:
            ex = sp.nsimplify(ex)
            if ex.is_Rational and not ex.is_Integer and ex.q < 10000:
                return f"{ex} ≈ {s}"
        return s


def _strip_wrap(tok: str) -> tuple[str, int, int]:
    """Drop unbalanced brackets at either end, and a pair wrapping the whole token: "(Fe2O3)" → "Fe2O3"."""
    lead = trail = 0

    def bal(s):
        d = 0
        for ch in s:
            d += ch in "([" and 1 or ch in ")]" and -1 or 0
            if d < 0:
                return False
        return d == 0
    while tok and not bal(tok):
        if tok[0] in "([" and tok.count("(") + tok.count("[") > tok.count(")") + tok.count("]"):
            tok, lead = tok[1:], lead + 1
        elif tok[-1] in ")]":
            tok, trail = tok[:-1], trail + 1
        elif tok[0] in ")]":
            tok, lead = tok[1:], lead + 1
        else:
            break
    while len(tok) > 2 and tok[0] in "([" and tok[-1] in ")]" and bal(tok[1:-1]):
        tok, lead, trail = tok[1:-1], lead + 1, trail + 1
    while tok.endswith("·"):
        tok, trail = tok[:-1], trail + 1
    return tok, lead, trail


def _lower_parse(tok: str) -> str | None:
    """A formula typed in lower case ("c8h10n4o2"), when it reads one way only with everyday elements."""
    if tok in LOWER_MAP:
        return LOWER_MAP[tok]
    if not re.search(r"\d", tok) or not re.fullmatch(r"[a-z0-9()·]+", tok) or len(tok) > 30:
        return None
    found: list[str] = []

    def walk(i: int, acc: str) -> None:
        if len(found) > 1:
            return
        if i == len(tok):
            found.append(acc)
            return
        ch = tok[i]
        if ch.isdigit() or ch in "()·":
            walk(i + 1, acc + ch)
            return
        for ln in (2, 1):
            sym = tok[i:i + ln].capitalize()
            if len(tok[i:i + ln]) == ln and sym in COMMON_EL:
                walk(i + ln, acc + sym)
    walk(0, "")
    if len(found) == 1 and parse_formula(found[0]):
        return found[0]
    return None


def _make(formula: str, label: str, a: int, b: int, tier: int, note: str = "") -> Comp | None:
    counts = parse_formula(formula)
    if not counts:
        return None
    return Comp(formula, label, a, b, tier, counts, sum(ATOMIC[el] * n for el, n in counts.items()), note)


def _hydrate(t: str, c: Comp) -> Comp:
    m = HYDRATE_RE.match(t, c.end)
    if m and "·" not in c.formula:
        k = HYDRATE[m.group(1)]
        f = f"{c.formula}·{_cnt(k)}H2O"
        return _make(f, f"{c.label} {m.group(1)}hydrate", c.start, m.end(), c.tier) or c
    return c


def _compounds(raw: str, t: str) -> list[Comp]:
    found: list[Comp] = []
    # 1. formulas as written: NaCl, Ca(OH)2, CuSO4·5H2O, (NH4)2SO4, K4[Fe(CN)6]
    for m in re.finditer(r"[A-Za-z0-9()\[\]·½]+", raw):
        tok, lead, trail = _strip_wrap(m.group(0))
        a, b = m.start() + lead, m.end() - trail
        if not tok or not (tok[0].isupper() or (tok[0] in "([" and len(tok) > 1 and tok[1].isupper())):
            continue
        if re.search(r"\((?:I{1,3}|IV|VI{0,3}|IX|X)\)", tok, re.I) or tok in STOP:
            continue  # "Fe(III)" is a charge, not FeI3
        if raw[b:b + 1] in ("+", "-", "^") and not raw[b:b + 2].startswith("- "):
            continue  # an ion: H3O+, OH-
        counts = parse_formula(tok)
        if not counts:
            continue
        n_sym = len(re.findall(r"[A-Z]", tok))
        digit = bool(re.search(r"\d", tok))
        ctx = bool(re.search(r"\b(?:of|for)\s+(?:the\s+)?(?:element\s+)?$", raw[:a], re.I)) or \
            bool(re.match(r"\s+atoms?\b", raw[b:], re.I))
        if n_sym == 1 and not digit:
            if not ctx or tok in ("I", "A"):
                continue
            found.append(_make(tok, f"{SYMBOL_NAMES.get(tok, tok)}", a, b, 2))
            continue
        if n_sym == 1 and tok not in MOLECULAR and not ctx:
            continue  # "S3", "P4" (a priority) without chemistry around them
        if not digit and tok.isupper() and tok not in CAPS_OK:
            continue
        found.append(_make(tok, tok, a, b, 0))
    # 2. names: caffeine, aluminium sulfate, iron(III) oxide, dinitrogen pentoxide …
    for m in NAME_RE.finditer(t):
        found.append(_make(COMPOUNDS[m.group(0)], m.group(0), m.start(), m.end(), 1))
    for m in IONIC_RE.finditer(t):
        f, _, _ = _ionic(CATIONS[m.group(1)], ANIONS[m.group(2)])
        label = re.sub(r"\((i{1,3}|iv|vi?)\)", lambda r: f"({r.group(1).upper()})", m.group(0))
        found.append(_make(f, label, m.start(), m.end(), 1))
    for m in COVALENT_RE.finditer(t):
        n1 = PREFIX.get(m.group(1) or "mono", 1)
        n2 = PREFIX[m.group(3)]
        e1, e2 = NONMETALS[m.group(2)], BINARY[m.group(4)]
        if e1 == e2:
            continue
        f = f"{e1}{n1 if n1 > 1 else ''}{e2}{n2 if n2 > 1 else ''}"
        found.append(_make(f, m.group(0), m.start(), m.end(), 1))
    for m in ELEMENT_CTX_RE.finditer(t):
        name = m.group(1) or m.group(2)
        a = m.start(1) if m.group(1) else m.start(2)
        sym = ELEMENT_NAMES[name]
        atoms = bool(re.match(r"\s+atoms?\b", t[a + len(name):])) or t[max(0, a - 7):a] == "atomic "
        gas = bool(re.match(r"\s+gas\b", t[a + len(name):]))
        if sym in DIATOMIC and not atoms:
            note = "" if gas else (f"{name} taken as {sym}2 gas; one {sym} atom is {fields.fmt(ATOMIC[sym])} g/mol")
            found.append(_make(f"{sym}2", name, a, a + len(name), 2, note))
        else:
            found.append(_make(sym, name, a, a + len(name), 2))
    # 3. formulas typed in lower case: h2so4, nacl, cuso4·5h2o
    for m in re.finditer(r"[a-z][a-z0-9()·]*", t):
        tok = m.group(0)
        if raw[m.start()].isupper():
            continue
        f = _lower_parse(tok)
        if f:
            found.append(_make(f, f, m.start(), m.end(), 1))
    found = [c for c in found if c]
    found = [_hydrate(t, c) for c in found]
    # where two readings overlap, the longer one wins ("sodium hydrogen carbonate" over "hydrogen carbonate")
    found.sort(key=lambda c: (-(c.end - c.start), c.tier, c.start))
    kept: list[Comp] = []
    for c in found:
        if not any(c.start < k.end and k.start < c.end for k in kept):
            kept.append(c)
    return sorted(kept, key=lambda c: c.start)


def _choose(comps: list[Comp]) -> Comp | None:
    """The compound the question is about: one written as a formula beats a name, a name beats a lone element, and
    water steps aside for the solute when there is one ("5 g of NaCl in water")."""
    if not comps:
        return None
    non_water = [c for c in comps if c.formula != "H2O"]
    pool = non_water or comps
    return sorted(pool, key=lambda c: (c.tier, c.start))[0]


def _distinct(p: Parsed) -> set[str]:
    return {c.formula for c in p.comps if c.tier < 2 and c.formula != "H2O"}


# ---------------------------------------------------------------- what is asked

ASK = {k: re.compile(v) for k, v in {
    "molar_mass": r"molar mass|molecular (?:weight|mass)|formula (?:weight|mass)|\bmw\b|\bm\.w\.|gram formula mass|"
                  r"relative (?:formula|molecular) mass|\bmr\b|\bg/mol\b|(?:mass|weight) of (?:one|1|a) mole\b|"
                  r"molar weight|molecular wt|mol(?:ar)? wt",
    "moles": r"\bhow many (?:moles|mols?)\b|\bnumber of moles\b|\bamount of substance\b|\bmoles\b|\bmols?\b|"
             r"\bmole\b|\bamount\b(?! of (?:water|solution|stock))",
    "moles_strong": r"\bhow many (?:moles|mols?)\b|\bnumber of (?:moles|mols?)\b|\b(?:in|to|into) (?:moles|mols?)\b|"
                    r"\bamount of substance\b|\bfind (?:the )?(?:moles|mols?)\b|\bmoles (?:of [^#]*)?(?:are|is) "
                    r"(?:there|present|contained|in)\b|\bwhat (?:amount|number of moles)\b",
    "mass": r"\bgrams?\b|(?<!molar )(?<!molecular )(?<!formula )\bmass\b(?! (?:percent|%|fraction))|\bweigh\w*\b|"
            r"\bhow many g\b|\bin g\b|\bkilograms?\b|\bmilligrams?\b|\bhow many (?:mg|kg)\b|\bin (?:mg|kg)\b",
    "particles": r"\b(molecules?|atoms?|particles?|formula units?|ions?)\b",
    "conc": r"\bmolarity\b|\bconcentration\b|\bmolar\b(?! mass)|\bhow concentrated\b|\bin (?:m|mm|mol/l)\b",
    "volume": r"\bvolume\b|\bhow many (?:ml|millilit\w*|l|lit\w*|cm3|dm3|cc)\b|\bhow much (?:water|solution|stock|"
              r"of (?:the|this|that) (?:stock|solution)|of it|space)\b|\bin (?:ml|l|liters?|litres?|cm3|dm3)\b|"
              r"\bwhat size\b|\bhow (?:big|large)\b",
    "pressure": r"\bpressure\b|\bhow many (?:atm|kpa|mmhg|torr|pa)\b|\bin (?:atm|kpa|pa|mmhg|torr|bar|psi)\b",
    "temp": r"\btemperature\b|\btemp\b|\bhow (?:hot|cold|warm)\b|\bin (?:kelvin|celsius|°c|k)\b",
    "density": r"\bdensity\b",
    "percent": r"%|\bpercent|\bpercentage|\bmass fraction|\bcomposition\b",
    "how_much": r"\bhow much\b|\bneed(?:ed)?\b|\brequired?\b|\bmake\b|\bprepare\b|\bweigh out\b|\bdissolve\b",
}.items()}


def _sol(p: Parsed, formula: str, known: list[str], sub: str, answer: str, check: str = "",
         extra: list[str] | None = None) -> Solution:
    steps = [f"formula: {formula}", "known: " + ", ".join(known), f"substitute: {sub}"]
    steps += extra or []
    steps.append(f"result: {answer}")
    return Solution("chemistry", p.raw, answer, steps, check=check, confidence=0.97)


def _mm_known(c: Comp) -> str:
    return f"M({c.formula}) = {c.mm:.2f} g/mol"


def _element_target(p: Parsed, c: Comp) -> str | None:
    """An element named outside the compound ("atoms of oxygen", "% N in"), present in it."""
    for m in ELEMENT_ANY_RE.finditer(p.t):
        if c.start <= m.start() < c.end:
            continue
        sym = ELEMENT_NAMES[m.group(1)]
        if sym in c.counts:
            return sym
    for m in re.finditer(r"(?<![\w(\[·])([A-Z][a-z]?)(?![a-z0-9(\[])", p.raw):
        if any(k.start <= m.start() < k.end for k in p.comps if k is c):
            continue
        sym = m.group(1)
        if sym in c.counts and sym != "I" or (sym == "I" and re.search(r"\b(?:of|%)\s*I\b", p.raw)):
            return sym
    return None


# ---------------------------------------------------------------- molar mass


def _mm_steps(c: Comp) -> tuple[str, list[str], str, list[str]]:
    known = ([f"{c.label} = {c.formula}"] if c.label != c.formula else []) + \
            [f"{el} {ATOMIC[el]:g}" for el in c.counts]
    sub = " + ".join(f"{el} {_cnt(n)} × {ATOMIC[el]:g}" for el, n in c.counts.items())
    extra = []
    if "·" in c.formula:
        parts = c.formula.split("·")
        pm = []
        for part in parts:
            m = re.match(r"(\d+(?:\.\d+)?|½)?(.+)$", part)
            k = 0.5 if m.group(1) == "½" else float(m.group(1) or 1)
            body_m = molar_mass(m.group(2))
            pm.append(f"{_cnt(k)} × {m.group(2)} {body_m:.2f}" if k != 1 else f"{m.group(2)} {body_m:.2f}")
        extra.append("by parts: " + " + ".join(pm) + " g/mol")
    return "M = Σ (number of atoms × atomic mass)", known, sub, extra


def molar_mass_problem(p: Parsed) -> Solution | None:
    if not p.asks("molar_mass") or not p.comp:
        return None
    if p.of("mass") and p.of("amount"):
        return None
    many = [c for c in p.comps if c.tier < 2] or [p.comp]
    uniq: list[Comp] = []
    for c in many:
        if c.formula not in [u.formula for u in uniq]:
            uniq.append(c)
    if len(uniq) > 1:
        answers = [f"{u.formula} {p.mmf(u.mm)}" for u in uniq]
        steps = ["formula: M = Σ (number of atoms × atomic mass)"]
        for u in uniq:
            steps.append(f"{u.name}: " + " + ".join(f"{el} {_cnt(n)} × {ATOMIC[el]:g}" for el, n in u.counts.items())
                         + f" = {u.mm:.3f}")
        steps.append("result: " + "; ".join(answers))
        return Solution("chemistry", p.raw, "; ".join(answers), steps, confidence=0.97)
    c = p.comp
    formula, known, sub, extra = _mm_steps(c)
    answer = p.mmf(c.mm)
    if c.note:
        extra.append(f"note: {c.note}")
    check = ""
    if "·" in c.formula:
        check = f"the parts add up: {extra[0].split(': ', 1)[1]} = {c.mm:.2f} g/mol ✓"
    elif len(c.counts) > 1:
        shares = [ATOMIC[el] * n / c.mm * 100 for el, n in c.counts.items()]
        check = "mass shares " + " + ".join(f"{el} {s:.2f}%" for el, s in zip(c.counts, shares)) + \
                f" = {sum(shares):.0f}% ✓"
    return _sol(p, formula, known, sub, answer, check, extra)


# ---------------------------------------------------------------- grams ↔ moles ↔ particles

ION_WORDS = {**{k: ("cation", k) for k in CATIONS}, **{k: ("anion", k) for k in ANIONS}}


def _particle_word(p: Parsed) -> str | None:
    m = ASK["particles"].search(p.rem)
    if not m:
        return None
    w = m.group(1)
    return {"molecule": "molecules", "atom": "atoms", "particle": "particles", "formula unit": "formula units",
            "ion": "ions"}.get(w, w)


def _per_unit(p: Parsed, c: Comp | None, word: str) -> tuple[float, str, str]:
    """How many of the asked particles one formula unit gives: (count, label, explanation)."""
    if c is None or word in ("molecules", "particles", "formula units"):
        return 1, word, ""
    if word == "atoms":
        el = _element_target(p, c)
        if el:
            n = c.counts[el]
            return n, f"{el} atoms", f"each {c.formula} has {_cnt(n)} {el} atom{'s' if n != 1 else ''}"
        total = sum(c.counts.values())
        if total == 1:
            return 1, "atoms", ""
        return total, "atoms", f"each {c.formula} has {_cnt(total)} atoms"
    if word == "ions":
        ion = IONIC.get(c.formula)
        if not ion:
            return 1, "ions", ""
        cat, nc, an, na = ion
        named = re.search(rf"\b({_alt(ION_WORDS)})\s+ions?\b", p.tc)
        if named and named.group(1) in (cat, an):
            n = nc if named.group(1) == cat else na
            return n, f"{named.group(1)} ions", f"each {c.formula} gives {n} {named.group(1)} ion{'s' if n > 1 else ''}"
        return nc + na, "ions", f"each {c.formula} gives {nc} {cat} + {na} {an} = {nc + na} ions"
    return 1, word, ""


def conversions(p: Parsed) -> Solution | None:
    if p.of("vol") or p.of("conc") or p.of("pressure") or p.of("temp"):
        return None
    c = p.comp
    if len(_distinct(p)) > 1:
        return None  # two different compounds: a reaction (stoichiometry), not a conversion
    mass, amt, parts = p.of("mass"), p.of("amount"), p.of("particles")
    given = sorted(mass[:1] + amt[:1] + parts[:1], key=lambda q: q.start)
    if not given:
        return None
    # molar mass from a mass and an amount: "0.25 mol of X weighs 10 g"
    if mass and amt and (p.asks("molar_mass") or not c):
        m, n = mass[0], amt[0]
        mm = m.value / n.value
        return _sol(p, "M = m / n", [f"m = {m.shown}", f"n = {n.shown}"], f"M = {_w(m.value)} / {_w(n.value)}",
                    p.f(mm, "g/mol"), f"n × M = {_w(n.value)} × {_w(mm)} = {_w(n.value * mm)} g ✓")
    if len(given) != 1:
        return None
    g = given[0]
    word = _particle_word(p)
    if p.asks("moles_strong"):
        want = "moles"
    elif word:
        want = "particles"
    elif p.asks("mass"):
        want = "mass"
    elif p.asks("moles"):
        want = "moles"
    else:
        return None
    if want == g.kind or (want == "moles" and g.kind == "amount") or (want == "particles" and g.kind == "particles"):
        if not (want == "moles" and g.kind == "amount" and word == "atoms" and c):
            return None
    na_txt = "N_A = 6.022 × 10^23 /mol"
    if g.kind == "mass":
        if not c:
            return None
        n = g.value / c.mm
        known = [f"m = {g.shown}" + (f" = {_w(g.value)} g" if g.unit != "g" else ""), _mm_known(c)]
        if want == "moles":
            el = _element_target(p, c) if word == "atoms" else None
            if el:
                k = c.counts[el]
                return _sol(p, f"n({el}) = (m / M) × {_cnt(k)}  ({_cnt(k)} {el} per {c.formula})", known,
                            f"n({el}) = ({_w(g.value)} / {_w(c.mm)}) × {_cnt(k)}", p.f(n * k, "mol"),
                            f"{_w(n * k)} mol × {ATOMIC[el]:g} g/mol = {_w(n * k * ATOMIC[el])} g of {el}, "
                            f"which is {ATOMIC[el] * k / c.mm * 100:.2f}% of {_w(g.value)} g ✓")
            return _sol(p, "n = m / M", known, f"n = {_w(g.value)} / {_w(c.mm)}", p.f(n, "mol"),
                        f"n × M = {_w(n)} × {_w(c.mm)} = {_w(n * c.mm)} g ✓", _notes(c))
        if want == "particles":
            k, label, why = _per_unit(p, c, word)
            total = n * NA * k
            ex = [f"n = {_w(g.value)} / {_w(c.mm)} = {_w(n)} mol"] + ([why] if why else [])
            sub = f"N = {_w(n)} × 6.022 × 10^23" + (f" × {_cnt(k)}" if k != 1 else "")
            return _sol(p, "N = (m / M) × N_A" + (f" × {_cnt(k)}" if k != 1 else ""), known + [na_txt], sub,
                        p.f(total, label), f"N / N_A = {_w(total / NA)} mol ✓", ex)
        return None
    if g.kind == "amount":
        known = [f"n = {g.shown}" + (f" = {_w(g.value)} mol" if g.unit != "mol" else "")]
        if want == "mass":
            if not c:
                return None
            m = g.value * c.mm
            unit, scale = _mass_unit(p, m)
            return _sol(p, "m = n × M", known + [_mm_known(c)], f"m = {_w(g.value)} × {_w(c.mm)}",
                        p.f(m / scale, unit), f"m / M = {_w(m)} / {_w(c.mm)} = {_w(g.value)} mol ✓", _notes(c))
        if want == "particles" or (want == "moles" and word == "atoms"):
            k, label, why = _per_unit(p, c, word or "particles")
            if want == "moles":
                return _sol(p, f"n(atoms) = n × {_cnt(k)}", known + ([why] if why else []),
                            f"n = {_w(g.value)} × {_cnt(k)}", p.f(g.value * k, "mol"))
            total = g.value * NA * k
            if not c and word == "atoms" and not re.search(r"\batoms?\b", p.t[g.end:g.end + 40]) and False:
                return None
            return _sol(p, "N = n × N_A" + (f" × {_cnt(k)}" if k != 1 else ""), known + [na_txt] + ([why] if why else []),
                        f"N = {_w(g.value)} × 6.022 × 10^23" + (f" × {_cnt(k)}" if k != 1 else ""),
                        p.f(total, label), f"N / N_A = {_w(total / NA / k)} mol ✓")
        return None
    if g.kind == "particles":
        n = g.value / NA
        known = [f"N = {p.f(g.value)} {g.unit}", na_txt]
        if want == "moles":
            return _sol(p, "n = N / N_A", known, f"n = {_w(g.value)} / 6.022 × 10^23", p.f(n, "mol"),
                        f"n × N_A = {_w(n * NA)} ✓")
        if want == "mass":
            if not c:
                return None
            m = n * c.mm
            unit, scale = _mass_unit(p, m)
            return _sol(p, "m = (N / N_A) × M", known + [_mm_known(c)],
                        f"m = ({_w(g.value)} / 6.022 × 10^23) × {_w(c.mm)} = {_w(n)} mol × {_w(c.mm)}",
                        p.f(m / scale, unit), f"m / M × N_A = {_w(m / c.mm * NA)} ✓")
    return None


def _notes(c: Comp | None) -> list[str]:
    return [f"note: {c.note}"] if c and c.note else []


def _mass_unit(p: Parsed, grams: float) -> tuple[str, float]:
    if re.search(r"\b(?:in )?(?:kg|kilograms?)\b", p.rem):
        return "kg", 1000.0
    if re.search(r"\b(?:in )?(?:mg|milligrams?)\b", p.rem):
        return "mg", 0.001
    return "g", 1.0


# ---------------------------------------------------------------- solutions: molarity


def _vol_out(p: Parsed, litres: float, given: list[Qty]) -> tuple[float, str]:
    if re.search(r"\b(?:ml|millilit\w*)\b", p.rem) or (not re.search(r"\b(?:l|lit\w*)\b", p.rem) and
                                                       (litres < 1 or any(q.unit == "mL" for q in given))):
        return litres * 1000, "mL"
    return litres, "L"


def _litres(q: Qty) -> str:
    return q.shown if q.unit == "L" else f"{q.shown} = {_w(q.value)} L"


def molarity(p: Parsed) -> Solution | None:
    if p.of("pressure") or re.search(r"\bstp\b|\bmolal(?:ity)?\b|\bgas\b", p.t):
        return None
    conc, vol, amt, mass = p.of("conc"), p.of("vol"), p.of("amount"), p.of("mass")
    c = p.comp
    if len(conc) > 1 or len(_distinct(p)) > 1:
        return None
    mm_given = p.of("molar_mass")
    mmv = c.mm if c else (mm_given[0].value if mm_given else None)
    mm_txt = _mm_known(c) if c else (f"M = {mm_given[0].shown}" if mm_given else "")
    # c = n / V
    if vol and (amt or mass) and not conc:
        if len(vol) > 1 or (amt and mass and not p.asks("conc")):
            return None
        if not (p.asks("conc") or re.search(r"\b(?:solution|dissolv\w*)\b", p.t)):
            return None
        if p.asks("volume") or p.asks("mass") and not p.asks("conc"):
            return None
        v = vol[0]
        extra = []
        if amt:
            n, n_ex = amt[0].value, amt[0].exact
            known = [f"n = {amt[0].shown}"]
        else:
            if mmv is None:
                return None
            n, n_ex = mass[0].value / mmv, None
            known = [f"m = {mass[0].shown}", mm_txt]
            extra.append(f"n = m / M = {_w(mass[0].value)} / {_w(mmv)} = {_w(n)} mol")
        cm = n / v.value
        ex = n_ex / v.exact if n_ex is not None else None
        unit = "M"
        if re.search(r"\b(?:mm|millimolar)\b", p.rem):
            cm, ex, unit = cm * 1000, (ex * 1000 if ex is not None else None), "mM"
        return _sol(p, "c = n / V" + ("  with n = m / M" if not amt else ""), known + [f"V = {_litres(v)}"],
                    f"c = {_w(n)} / {_w(v.value)}", p.exact_ans(cm, ex, unit),
                    f"c × V = {_w(n / v.value)} × {_w(v.value)} = {_w(n)} mol ✓", extra)
    if not conc:
        return None
    cq = conc[0]
    # n = c × V, m = c × V × M
    if vol and not amt and not mass:
        if len(vol) > 1:
            return None
        v = vol[0]
        n = cq.value * v.value
        n_ex = cq.exact * v.exact
        known = [f"c = {cq.shown}", f"V = {_litres(v)}"]
        word = _particle_word(p)
        if p.asks("moles_strong") or (p.asks("moles") and not p.asks("mass")):
            return _sol(p, "n = c × V", known, f"n = {_w(cq.value)} × {_w(v.value)}", p.exact_ans(n, n_ex, "mol"),
                        f"n / V = {_w(n)} / {_w(v.value)} = {_w(cq.value)} M ✓")
        if word and not p.asks("mass"):
            k, label, why = _per_unit(p, c, word)
            return _sol(p, "N = c × V × N_A", known + ["N_A = 6.022 × 10^23 /mol"] + ([why] if why else []),
                        f"N = {_w(cq.value)} × {_w(v.value)} × 6.022 × 10^23" + (f" × {_cnt(k)}" if k != 1 else ""),
                        p.f(n * NA * k, label))
        if (p.asks("mass") or p.asks("how_much")) and mmv:
            m = n * mmv
            unit, scale = _mass_unit(p, m)
            return _sol(p, "m = c × V × M", known + [mm_txt], f"m = {_w(cq.value)} × {_w(v.value)} × {_w(mmv)}",
                        p.f(m / scale, unit), f"n = m / M = {_w(m)} / {_w(mmv)} = {_w(n)} mol, and n / V = "
                        f"{_w(n / v.value)} M ✓", [f"n = c × V = {_w(n)} mol"] + _notes(c))
        return None
    # V = n / c
    if (amt or mass) and not vol and p.asks("volume"):
        if amt:
            n, known, extra = amt[0].value, [f"n = {amt[0].shown}"], []
        else:
            if mmv is None:
                return None
            n = mass[0].value / mmv
            known, extra = [f"m = {mass[0].shown}", mm_txt], [f"n = m / M = {_w(n)} mol"]
        litres = n / cq.value
        out, unit = _vol_out(p, litres, [])
        ex = amt[0].exact / cq.exact * (1000 if unit == "mL" else 1) if amt else None
        return _sol(p, "V = n / c", known + [f"c = {cq.shown}"], f"V = {_w(n)} / {_w(cq.value)}",
                    p.exact_ans(out, ex, unit), f"c × V = {_w(cq.value)} × {_w(litres)} L = {_w(n)} mol ✓", extra)
    return None


# ---------------------------------------------------------------- dilution

DIL_RE = re.compile(r"\bdilut\w*|\bstock\b|\bwater (?:is |was )?added\b|\badd(?:ed|ing)? (?:some )?water\b|"
                    r"\bmade? up to\b|\bmake (?:it )?up to\b|\btop(?:ped)? up\b|\bfinal volume\b|\bc1\s*v1\b|"
                    r"\bdiluted to\b|\bfinal concentration\b|\bnew concentration\b")


def _asks_water(p: Parsed) -> bool:
    """"how much water to add" (water is blanked as a compound in p.rem, so read p.t)."""
    return bool(re.search(r"\b(?:how much|how many|what volume|amount|volume) (?:of )?(?:\w+ )?water\b|"
                          r"\bwater (?:should|must|do|to|is|needs?)\b.*\badd", p.t))


def dilution(p: Parsed) -> Solution | None:
    if p.of("pressure") or p.of("amount") or p.of("mass"):
        return None
    conc, vols = p.of("conc"), p.of("vol")
    if len(_distinct(p)) > 1:
        return None
    water = None
    for m in re.finditer(rf"\badd(?:ed|ing|s)?\s+(?:about\s+)?#+\s+(?:of\s+)?(?:distilled\s+|pure\s+)?§*\s*"
                         rf"|#+\s+(?:of\s+)?(?:distilled\s+|pure\s+)?§+\s+(?:is |are |was |were )?added", p.rem):
        q = next((v for v in vols if m.start() <= v.start < m.end()), None)
        if q and re.search(r"water|§", p.t[m.start():m.end() + 10]):
            water = q
    others = [v for v in vols if v is not water]
    dil_word = bool(DIL_RE.search(p.t)) or water is not None
    if len({round(c.value, 12) for c in conc}) >= 2:
        hi, lo = max(conc[:2], key=lambda q: q.value), min(conc[:2], key=lambda q: q.value)
        if len(others) != 1:
            return None
        v = others[0]
        to_lo = abs(v.start - lo.start) < abs(v.start - hi.start)
        if re.search(r"(?:to|into|up to|of)\s*$", p.t[:v.start]) and re.match(r"\s*(?:of\s+)?(?:a\s+)?(?:§+\s+)?#",
                                                                               p.rem[v.end:]):
            to_lo = abs(v.end - lo.start) <= abs(v.end - hi.start)
        if to_lo:   # the volume is of the diluted solution: how much stock?
            v1 = lo.value * v.value / hi.value
            ex = lo.exact * v.exact / hi.exact
            unit, f = (v.unit, v.value / v.num) if v.num else ("L", 1.0)
            wat = v.value - v1
            known = [f"C1 = {hi.shown} (stock)", f"C2 = {lo.shown}", f"V2 = {v.shown}"]
            asks_water = _asks_water(p)
            ans = p.exact_ans(v1 / f, ex / sp.Rational(str(f)) if ex is not None else None, unit)
            extra = [f"water to add: V2 − V1 = {_w(v.value / f)} − {_w(v1 / f)} = {_w(wat / f)} {unit}"]
            if asks_water:
                ans = p.f(wat / f, unit) + " of water"
            return _sol(p, "C1 × V1 = C2 × V2  →  V1 = C2 × V2 / C1", known,
                        f"V1 = {_w(lo.num)} × {_w(v.num)} / {_w(hi.num * hi.value / lo.value * lo.num / lo.num)}"
                        if False else f"V1 = {_w(lo.value)} × {_w(v.value / f)} / {_w(hi.value)}",
                        ans, f"C1 × V1 = {_w(hi.value * v1 / f)} = C2 × V2 = {_w(lo.value * v.value / f)} ✓", extra)
        v2 = hi.value * v.value / lo.value
        unit, f = v.unit, v.value / v.num
        ex = hi.exact * v.exact / lo.exact / sp.Rational(str(f))
        asks_water = _asks_water(p)
        known = [f"C1 = {hi.shown}", f"V1 = {v.shown}", f"C2 = {lo.shown}"]
        extra = [f"water to add: V2 − V1 = {_w(v2 / f)} − {_w(v.value / f)} = {_w((v2 - v.value) / f)} {unit}"]
        ans = p.f((v2 - v.value) / f, unit) + " of water" if asks_water else p.exact_ans(v2 / f, ex, unit)
        return _sol(p, "C1 × V1 = C2 × V2  →  V2 = C1 × V1 / C2", known,
                    f"V2 = {_w(hi.value)} × {_w(v.value / f)} / {_w(lo.value)}", ans,
                    f"C2 × V2 = {_w(lo.value * v2 / f)} = C1 × V1 = {_w(hi.value * v.value / f)} ✓", extra)
    if len(conc) == 1 and dil_word and (len(others) == 2 or (len(others) == 1 and water)):
        cq = conc[0]
        if water:
            v1, v2_val = others[0], others[0].value + water.value
            v2_shown = f"{v1.shown} + {water.shown} = {_w(v2_val)} L"
            v2_ex = v1.exact + water.exact
            initial = True
        else:
            a, b = sorted(others, key=lambda q: q.value)
            v1, v2_val, v2_shown, v2_ex = a, b.value, b.shown, b.exact
            near = min(others, key=lambda q: abs(q.start - cq.start))
            initial = near is a or not re.search(r"\b(?:original|initial|stock|starting)\b", p.rem)
        if initial:
            c2 = cq.value * v1.value / v2_val
            ex = cq.exact * v1.exact / v2_ex
            return _sol(p, "C1 × V1 = C2 × V2  →  C2 = C1 × V1 / V2",
                        [f"C1 = {cq.shown}", f"V1 = {_litres(v1)}", f"V2 = {v2_shown}"],
                        f"C2 = {_w(cq.value)} × {_w(v1.value)} / {_w(v2_val)}", p.exact_ans(c2, ex, "M"),
                        f"C1 × V1 = {_w(cq.value * v1.value)} mol = C2 × V2 = {_w(c2 * v2_val)} mol ✓")
        c1 = cq.value * v2_val / v1.value
        return _sol(p, "C1 × V1 = C2 × V2  →  C1 = C2 × V2 / V1",
                    [f"C2 = {cq.shown}", f"V1 = {_litres(v1)}", f"V2 = {v2_shown}"],
                    f"C1 = {_w(cq.value)} × {_w(v2_val)} / {_w(v1.value)}",
                    p.exact_ans(c1, cq.exact * v2_ex / v1.exact, "M"),
                    f"C1 × V1 = {_w(c1 * v1.value)} mol = C2 × V2 = {_w(cq.value * v2_val)} mol ✓")
    return None


# ---------------------------------------------------------------- percent composition


def _outside(t: str, c: Comp) -> str:
    return _blank(t, c.start, c.end)


def composition(p: Parsed) -> Solution | None:
    c = p.comp
    if not c or c.tier == 2 or len(_distinct(p)) > 1:
        return None
    pct = p.asks("percent")
    mass = p.of("mass")
    target = _element_target(p, c)
    water = "·" in c.formula and bool(re.search(r"\bwater\b|\bh2o\b|crystalli[sz]ation", _outside(p.t, c)))
    grams_of = mass and target and p.asks("mass") and not pct and len(mass) == 1 and not p.of("amount")
    if not (pct or grams_of) or len(c.counts) < 2 and not water:
        return None
    if p.of("vol") or p.of("conc") or p.of("pressure"):
        return None
    formula, known, sub, extra = _mm_steps(c)
    mm_line = f"M({c.formula}) = {sub} = {c.mm:.3f} g/mol"
    if water:
        k = float(re.search(r"·(\d+(?:\.\d+)?)?H2O", c.formula).group(1) or 1)
        wm = k * molar_mass("H2O")
        share = wm / c.mm * 100
        return _sol(p, "% water = (n × M(H2O) / M(hydrate)) × 100", known,
                    f"% = {_cnt(k)} × {molar_mass('H2O'):.3f} / {c.mm:.3f} × 100", p.f(share, "%"),
                    f"anhydrous part {100 - share:.2f}% + water {share:.2f}% = 100% ✓", [mm_line])
    if grams_of:
        el, n = target, c.counts[target]
        frac = ATOMIC[el] * n / c.mm
        g = mass[0].value * frac
        return _sol(p, f"m({el}) = m × ({_cnt(n)} × M({el}) / M({c.formula}))",
                    [f"m = {mass[0].shown}", f"M({el}) = {ATOMIC[el]:g} g/mol", _mm_known(c)],
                    f"m({el}) = {_w(mass[0].value)} × {_cnt(n)} × {ATOMIC[el]:g} / {c.mm:.3f}", p.f(g, "g"),
                    f"{el} is {frac * 100:.2f}% of {c.formula}, and {frac * 100:.2f}% of {_w(mass[0].value)} g is "
                    f"{_w(g)} g ✓", [mm_line])
    shares = {el: ATOMIC[el] * n / c.mm * 100 for el, n in c.counts.items()}
    if target:
        el, n = target, c.counts[target]
        return _sol(p, f"% {el} = ({_cnt(n)} × M({el}) / M({c.formula})) × 100",
                    [f"M({el}) = {ATOMIC[el]:g} g/mol", _mm_known(c)],
                    f"% {el} = {_cnt(n)} × {ATOMIC[el]:g} / {c.mm:.3f} × 100", p.f(shares[el], "%"),
                    f"all elements: " + ", ".join(f"{e} {s:.2f}%" for e, s in shares.items()) +
                    f" (sum {sum(shares.values()):.1f}%) ✓", [mm_line])
    answer = ", ".join(f"{el} {p.f(s, '%')}" for el, s in shares.items())
    return _sol(p, "% element = (atoms × atomic mass / molar mass) × 100", known + [_mm_known(c)],
                "; ".join(f"{el}: {_cnt(c.counts[el])} × {ATOMIC[el]:g} / {c.mm:.3f} × 100" for el in shares),
                answer, f"{' + '.join(f'{s:.2f}' for s in shares.values())} = {sum(shares.values()):.1f}% ✓", [mm_line])


# ---------------------------------------------------------------- gases

GASES = {"O2", "N2", "H2", "CO2", "He", "Ne", "Ar", "Kr", "Xe", "Rn", "CH4", "NH3", "CO", "Cl2", "F2", "SO2", "NO2",
         "N2O", "NO", "C3H8", "C4H10", "C2H6", "C2H4", "C2H2", "H2S", "HCl", "O3", "SO3", "SF6", "HF", "N2O4"}
GAS_WORDS = re.compile(r"\bgas(?:es|eous)?\b|\bideal\b|\bpv\s*=\s*nrt\b|\bballoon\b|\bcontainer\b|\btank\b|"
                       r"\bcylinder\b|\bflask\b|\bvessel\b|\bvapou?r\b|\bair\b|\bpiston\b|\bsyringe\b|\btyre\b|\btire\b")
STP_RE = re.compile(r"\bstp\b|standard temperature and pressure|\bs\.t\.p\.?")
SATP_RE = re.compile(r"\bsatp\b")
P_UNIT = {"atm": 1.0, "kPa": 101.325, "Pa": 101325.0, "mmHg": 760.0, "torr": 760.0, "bar": 1.01325,
          "psi": 14.6959488, "hPa": 1013.25, "mbar": 1013.25}


def _p_out(p: Parsed, given: list[Qty]) -> str:
    m = re.search(r"\b(?:in|into|to)\s+(atm|kpa|pa|mmhg|mm hg|torr|bar|psi|atmospheres)\b", p.t)
    if m:
        return {"kpa": "kPa", "pa": "Pa", "mmhg": "mmHg", "mm hg": "mmHg", "atmospheres": "atm"}.get(m.group(1),
                                                                                                    m.group(1))
    return given[0].unit if given else "atm"


def _t_shown(q_or_k, unit: str = "K") -> str:
    if isinstance(q_or_k, Qty):
        q = q_or_k
        return q.shown if q.unit == "K" else f"{q.shown} = {_w(q.value)} K"
    return f"{_w(q_or_k)} K"


def gas(p: Parsed) -> Solution | None:
    P, V, T, n, m = p.of("pressure"), p.of("vol"), p.of("temp"), p.of("amount"), p.of("mass")
    if p.of("conc"):
        return None
    stp, satp = STP_RE.search(p.t), SATP_RE.search(p.t)
    c = p.comp
    gasy = bool(GAS_WORDS.search(p.t)) or bool(c and c.formula in GASES)
    if not (P or stp or satp) and not (gasy and T):
        return None
    if len(_distinct(p)) > 1:
        return None
    mm_given = p.of("molar_mass")
    std_note = []
    if stp:
        std_note = ["STP: 0 °C = 273.15 K and 1 atm"]
    elif satp:
        std_note = ["SATP: 25 °C = 298.15 K and 100 kPa"]
    # ---- combined gas law: the same gas changing state
    if not n and not m and (len(P) == 2 or len(V) == 2 or len(T) == 2 or ((stp or satp) and (P or T) and V)):
        return _combined(p, P, V, T, stp, satp)
    if len(P) > 1 or len(V) > 1 or len(T) > 1:
        return None
    # ---- PV = nRT
    p_atm = P[0].value if P else (1.0 if stp else (100 / 101.325 if satp else None))
    t_k = T[0].value if T else (273.15 if stp else (298.15 if satp else None))
    v_l = V[0].value if V else None
    mmv = c.mm if c else (mm_given[0].value if mm_given else None)
    n_mol = n[0].value if n else (m[0].value / mmv if m and mmv else None)
    kpa = bool(P and P[0].unit in ("kPa", "Pa", "hPa")) or bool(satp and not P)
    R, r_txt = (R_KPA, "R = 8.314 L·kPa/(mol·K)") if kpa else (R_ATM, "R = 0.08206 L·atm/(mol·K)")
    pf = 101.325 if kpa else 1.0
    pu = "kPa" if kpa else "atm"
    known = []
    if P:
        known.append(P[0].shown if P[0].unit == pu else f"P = {P[0].shown} = {_w(P[0].value * pf)} {pu}")
        if P[0].unit == pu:
            known[-1] = f"P = {P[0].shown}"
    elif p_atm is not None:
        known.append(f"P = {_w(p_atm * pf)} {pu}")
    if V:
        known.append(f"V = {_litres(V[0])}")
    if t_k is not None:
        known.append("T = " + (_t_shown(T[0]) if T else f"{_w(t_k)} K"))
    if n:
        known.append(f"n = {n[0].shown}")
    elif m:
        known.append(f"m = {m[0].shown}")
        if mmv:
            known.append(_mm_known(c) if c else f"M = {mm_given[0].shown}")
    known.append(r_txt)
    extra = std_note + ([f"n = m / M = {_w(m[0].value)} / {_w(mmv)} = {_w(n_mol)} mol"] if m and not n and mmv else [])
    pP = p_atm * pf if p_atm is not None else None
    ask = _gas_ask(p, have={"P": pP is not None, "V": v_l is not None, "T": t_k is not None, "n": n_mol is not None})
    if ask == "M":
        if not (m and pP and v_l and t_k):
            return None
        M = m[0].value * R * t_k / (pP * v_l)
        return _sol(p, "PV = nRT with n = m / M  →  M = m·R·T / (P·V)", known,
                    f"M = {_w(m[0].value)} × {R:g} × {_w(t_k)} / ({_w(pP)} × {_w(v_l)})", p.f(M, "g/mol"),
                    f"n = m / M = {_w(m[0].value / M)} mol, and nRT / V = {_w(m[0].value / M * R * t_k / v_l)} {pu} ✓",
                    extra)
    if ask == "density":
        if not (mmv and pP and t_k):
            return None
        rho = pP * mmv / (R * t_k)
        known = [k for k in known if not k.startswith("V =")]
        if not any(k.startswith("M(") or k.startswith("M =") for k in known):
            known.insert(-1, _mm_known(c) if c else f"M = {mm_given[0].shown}")
        return _sol(p, "ρ = P·M / (R·T)  (from PV = nRT with n = m / M)", known,
                    f"ρ = {_w(pP)} × {_w(mmv)} / ({R:g} × {_w(t_k)})", p.f(rho, "g/L"),
                    f"1 L holds {_w(pP / (R * t_k))} mol × {_w(mmv)} g/mol = {_w(rho)} g ✓", extra)
    if ask == "P":
        if n_mol is None or v_l is None or t_k is None:
            return None
        val = n_mol * R * t_k / v_l
        out = _p_out(p, [])
        shown = p.f(val / pf * P_UNIT[out], out) if out != pu else p.f(val, pu)
        if out != pu:
            extra.append(f"{_w(val)} {pu} = {shown}")
        return _sol(p, "PV = nRT  →  P = nRT / V", known, f"P = {_w(n_mol)} × {R:g} × {_w(t_k)} / {_w(v_l)}", shown,
                    f"PV = {_w(val * v_l)} = nRT = {_w(n_mol * R * t_k)} ✓", extra)
    if ask == "V":
        if n_mol is None or pP is None or t_k is None:
            return None
        val = n_mol * R * t_k / pP
        out, unit = (val * 1000, "mL") if re.search(r"\b(?:in )?(?:ml|millilit\w*|cm3)\b", p.rem) else (val, "L")
        return _sol(p, "PV = nRT  →  V = nRT / P", known, f"V = {_w(n_mol)} × {R:g} × {_w(t_k)} / {_w(pP)}",
                    p.f(out, unit), f"PV = {_w(pP * val)} = nRT = {_w(n_mol * R * t_k)} ✓", extra)
    if ask == "T":
        if n_mol is None or pP is None or v_l is None:
            return None
        val = pP * v_l / (n_mol * R)
        ans = f"{p.f(val, 'K')} ({p.f(val - 273.15, '°C')})"
        if re.search(r"\b(?:in )?(?:celsius|°c|degrees c)\b", p.rem):
            ans = f"{p.f(val - 273.15, '°C')} ({p.f(val, 'K')})"
        return _sol(p, "PV = nRT  →  T = PV / (nR)", known, f"T = {_w(pP)} × {_w(v_l)} / ({_w(n_mol)} × {R:g})", ans,
                    f"nRT / V = {_w(n_mol * R * val / v_l)} {pu} = P ✓", extra)
    if ask in ("n", "mass", "particles"):
        if pP is None or v_l is None or t_k is None or (n_mol is not None and ask == "n"):
            return None
        nn = pP * v_l / (R * t_k)
        if ask == "mass":
            if not mmv:
                return None
            return _sol(p, "PV = nRT  →  n = PV / (RT), then m = n × M", known,
                        f"n = {_w(pP)} × {_w(v_l)} / ({R:g} × {_w(t_k)}) = {_w(nn)} mol; m = {_w(nn)} × {_w(mmv)}",
                        p.f(nn * mmv, "g"), f"m / M × RT / V = {_w(nn * R * t_k / v_l)} {pu} = P ✓",
                        extra + [_mm_known(c) if c else f"M = {mm_given[0].shown}"])
        if ask == "particles":
            word = _particle_word(p) or "molecules"
            return _sol(p, "PV = nRT  →  n = PV / (RT), then N = n × N_A", known + ["N_A = 6.022 × 10^23 /mol"],
                        f"n = {_w(pP)} × {_w(v_l)} / ({R:g} × {_w(t_k)}) = {_w(nn)} mol; N = {_w(nn)} × 6.022 × 10^23",
                        p.f(nn * NA, word), f"N / N_A × RT / V = {_w(nn * R * t_k / v_l)} {pu} = P ✓", extra)
        return _sol(p, "PV = nRT  →  n = PV / (RT)", known, f"n = {_w(pP)} × {_w(v_l)} / ({R:g} × {_w(t_k)})",
                    p.f(nn, "mol"), f"nRT / V = {_w(nn * R * t_k / v_l)} {pu} = P ✓", extra)
    return None


def _gas_ask(p: Parsed, have: dict) -> str | None:
    if p.asks("molar_mass"):
        return "M"
    if p.asks("density"):
        return "density"
    if p.asks("pressure") and not have["P"]:
        return "P"
    if p.asks("volume") and not have["V"]:
        return "V"
    if p.asks("temp") and not have["T"]:
        return "T"
    if p.asks("moles_strong") or (p.asks("moles") and not have["n"]):
        return "n"
    if _particle_word(p) and not have["n"]:
        return "particles"
    if p.asks("mass") and not have["n"]:
        return "mass"
    missing = [k for k, v in have.items() if not v]
    if len(missing) == 1:
        return missing[0]
    return None


def _combined(p: Parsed, P: list[Qty], V: list[Qty], T: list[Qty], stp, satp) -> Solution | None:
    # each quantity as (value, shown, position); a standard state adds its P and T at the point it is mentioned
    std = stp or satp
    vals: dict[str, list] = {"P": [(q.value, q.shown, q.start) for q in P], "V": [(q.value, q.shown, q.start) for q in V],
                             "T": [(q.value, _t_shown(q), q.start) for q in T]}
    if std:
        sp_atm, st_k, label = (1.0, 273.15, "STP") if stp else (100 / 101.325, 298.15, "SATP")
        if len(vals["P"]) < 2 and vals["P"]:
            vals["P"].append((sp_atm, f"{label} {'1 atm' if stp else '100 kPa'}", std.start()))
        if len(vals["T"]) < 2 and vals["T"]:
            vals["T"].append((st_k, f"{label} {_w(st_k)} K", std.start()))
        for k in ("P", "T"):
            vals[k].sort(key=lambda x: x[2])
    if any(len(v) > 2 for v in vals.values()):
        return None
    asked = None
    for k, key in (("P", "pressure"), ("V", "volume"), ("T", "temp")):
        if p.asks(key) and len(vals[k]) == 1:
            asked = k
    if asked is None:
        singles = [k for k, v in vals.items() if len(v) == 1]
        if len(singles) == 1:
            asked = singles[0]
    if asked is None or not any(len(v) == 2 for k, v in vals.items() if k != asked):
        return None
    ratio = {"P": 1.0, "V": 1.0, "T": 1.0}
    # X2 = X1 × Π ratios: P2 = P1·(V1/V2)·(T2/T1); V2 = V1·(P1/P2)·(T2/T1); T2 = T1·(P2/P1)·(V2/V1)
    for k, v in vals.items():
        if k == asked or len(v) < 2:
            continue
        (a, _, _), (b, _, _) = v
        if asked == "T":
            ratio[k] = b / a
        elif k == "T":
            ratio[k] = b / a
        else:
            ratio[k] = a / b
    x1 = vals[asked][0][0]
    x2 = x1 * ratio["P"] * ratio["V"] * ratio["T"]
    law = {frozenset("PV"): "Boyle's law", frozenset("VT"): "Charles's law", frozenset("PT"): "Gay-Lussac's law"}
    changing = frozenset([asked] + [k for k, v in vals.items() if len(v) == 2])
    name = law.get(changing, "combined gas law")
    if asked == "P":
        unit = P[0].unit
        out = x2 * P_UNIT[unit]
        known_unit = unit
    elif asked == "V":
        unit = V[0].unit
        out = x2 / (V[0].value / V[0].num) if V[0].num else x2
        known_unit = unit
    else:
        out, known_unit = x2, "K"
    known = []
    for k in ("P", "V", "T"):
        for i, (_, shown, _) in enumerate(vals[k]):
            known.append(f"{k}{i + 1} = {shown}")
    known += [f"{k} constant" for k in ("P", "V", "T") if not vals[k] and k != asked]
    eq = {"P": "P2 = P1 × (V1 / V2) × (T2 / T1)", "V": "V2 = V1 × (P1 / P2) × (T2 / T1)",
          "T": "T2 = T1 × (P2 / P1) × (V2 / V1)"}[asked]
    factors = " × ".join(f"{_w(ratio[k])}" for k in ("P", "V", "T") if k != asked and len(vals[k]) == 2)
    x1_shown = (P[0].num if asked == "P" else V[0].num if asked == "V" else vals["T"][0][0])
    sub = f"{asked}2 = {_w(x1_shown)} × {factors}"
    if asked == "T":
        ans = f"{p.f(out, 'K')} ({p.f(out - 273.15, '°C')})"
        if re.search(r"\b(?:in )?(?:celsius|°c|degrees c)\b", p.rem):
            ans = f"{p.f(out - 273.15, '°C')} ({p.f(out, 'K')})"
    else:
        ans = p.f(out, known_unit)

    def pv_t(i):
        pv = (vals["P"][min(i, len(vals["P"]) - 1)][0] if vals["P"] else 1) * \
             (vals["V"][min(i, len(vals["V"]) - 1)][0] if vals["V"] else 1)
        tt = vals["T"][min(i, len(vals["T"]) - 1)][0] if vals["T"] else 1
        return pv, tt
    vals[asked].append((x2, "", 0))
    (pv1, t1), (pv2, t2) = pv_t(0), pv_t(1)
    check = f"P1·V1/T1 = {_w(pv1 / t1)} = P2·V2/T2 = {_w(pv2 / t2)} ✓ (in atm, L and K)"
    return _sol(p, f"P1·V1 / T1 = P2·V2 / T2  ({name}; temperatures in K)  →  {eq}", known, sub, ans, check)


# ---------------------------------------------------------------- pH

PH_TRIG = re.compile(r"\bp(?:h|oh)\b|\[\s*h3?o?\s*\+\s*\]|\[\s*oh\s*-\s*\]|\bh3o\+|\bh\+|\boh-|hydronium|"
                     r"hydrogen[\s-]ions?|hydroxide[\s-]ions?|hydroxyl ions?|hydroxide concentration|\bp?k[ab]\b")
_EQ = r"(?:\s*(?:=|:|is|of|was|equals|equal to|reading of|reads|at|around|about|approximately|~|≈|value of|value))*\s*"
_NOT_CONC = r"(?!\s*(?:m\b|mm\b|mol|molar|g\b|mg\b|%|ml\b|l\b|§|#|e[+-]?\d))"
_OF_SOL = r"(?:\s+(?:of|in)\s+(?:a|an|the|this|that|some)\s+(?:\w+\s+)?(?:solution|sample|liquid|drink))?"
PH_VAL = re.compile(rf"\bph{_OF_SOL}{_EQ}({NUM})(?!\d|\.\d){_NOT_CONC}")
POH_VAL = re.compile(rf"\bpoh{_OF_SOL}{_EQ}({NUM})(?!\d|\.\d){_NOT_CONC}")
_H = r"(?:\[\s*h3?o?\s*\+\s*\]|\bh3o\+|\bh\+|hydronium(?:\s+ions?)?|hydrogen[\s-]ions?)"
_OH = r"(?:\[\s*oh\s*-\s*\]|\boh-|hydroxide[\s-]ions?|hydroxyl ions?|hydroxide)"
_CU = r"\s*(?:m\b|mol/l|molar|mol\s*l-1|mol/dm3)?"
H_VAL = [re.compile(rf"{_H}(?:\s+(?:ion\s+)?concentration{_OF_SOL})?{_EQ}({NUM}){_CU}"),
         re.compile(rf"concentration of (?:the\s+)?(?:h\+|h3o\+|hydrogen ions?|hydronium(?: ions?)?){_EQ}({NUM}){_CU}"),
         re.compile(rf"(?<![\w.])({NUM}){_CU}\s*(?:of\s+)?{_H}")]
OH_VAL = [re.compile(rf"{_OH}(?:\s+(?:ion\s+)?concentration{_OF_SOL})?{_EQ}({NUM}){_CU}"),
          re.compile(rf"concentration of (?:the\s+)?(?:oh-|hydroxide(?: ions?)?|hydroxyl ions?){_EQ}({NUM}){_CU}"),
          re.compile(rf"(?<![\w.])({NUM}){_CU}\s*(?:of\s+)?{_OH}")]
KA_VAL = re.compile(rf"\b(p?)k([ab])\b{_EQ}({NUM})")
WEAK = {"CH3COOH": ("a", 1.8e-5), "NH3": ("b", 1.8e-5)}
STRONG_A = {**fields.STRONG_ACIDS, "HClO3": 1}
STRONG_B = {**fields.STRONG_BASES, "Sr(OH)2": 2, "RbOH": 1, "CsOH": 1}


def _grab(rxs, s: str):
    for rx in rxs if isinstance(rxs, list) else [rxs]:
        m = rx.search(s)
        if m:
            return float(m.group(1).replace(",", "")), m.group(1).replace(",", ""), m.span()
    return None


def _log_exact(x_str: str) -> sp.Expr | None:
    """−log10 of a typed concentration when it is an exact power of ten (0.001 → 3), else None."""
    r = sp.Rational(x_str)
    if r <= 0:
        return None
    k = sp.log(r, 10)
    k = sp.nsimplify(sp.simplify(k))
    return -k if k.is_Integer else None


def _sci_exact(x: float) -> str:
    m, e = f"{x:.6e}".split("e")
    return f"{float(m):g} × 10^{int(e)}"


def ph_problem(p: Parsed) -> Solution | None:
    s = p.tc
    if not PH_TRIG.search(s):
        return None
    given_rem = p.rem
    ph = _grab(PH_VAL, s)
    poh = _grab(POH_VAL, s)
    h = _grab(H_VAL, s)
    oh = _grab(OH_VAL, s)
    for g in (ph, poh, h, oh):
        if g:
            given_rem = _blank(given_rem, *g[2])
    ask = {"pH": bool(re.search(r"\bph\b", given_rem)), "pOH": bool(re.search(r"\bpoh\b", given_rem)),
           "H": bool(re.search(rf"{_H}|hydrogen ion|\[h", given_rem)),
           "OH": bool(re.search(rf"{_OH}|\[oh", given_rem)),
           "class": bool(re.search(r"\bacidic\b|\bbasic\b|\balkaline\b|\bneutral\b|\bacid or (?:a )?base\b",
                                   given_rem))}
    steps_known: list[str] = []
    formula = ""
    sub = ""
    extra: list[str] = []
    hv = None
    exact_ph = None
    check = ""
    if ph or poh:
        if ph:
            v, vs = ph[0], ph[1]
            if not -2 <= v <= 16:
                return None
            hv = 10 ** -v
            exact_ph = sp.Rational(vs)
            steps_known = [f"pH = {vs}"]
            default = "H"
        else:
            v, vs = poh[0], poh[1]
            if not -2 <= v <= 16:
                return None
            hv = 10 ** -(14 - v)
            exact_ph = 14 - sp.Rational(vs)
            steps_known = [f"pOH = {vs}"]
            default = "pH"
        formula = "pH + pOH = 14, [H⁺] = 10^(−pH), [OH⁻] = 10^(−pOH)  (25 °C)"
    elif h or oh:
        if h:
            hv = h[0]
            if hv <= 0:
                return None
            steps_known = [f"[H⁺] = {_conc(h[0])}"]
            exact_ph = _log_exact(h[1])
            formula = "pH = −log₁₀[H⁺]"
        else:
            if oh[0] <= 0:
                return None
            hv = KW / oh[0]
            steps_known = [f"[OH⁻] = {_conc(oh[0])}"]
            e = _log_exact(oh[1])
            exact_ph = 14 - e if e is not None else None
            formula = "pOH = −log₁₀[OH⁻], pH = 14 − pOH  (25 °C)"
        default = "pH"
    else:
        r = _ph_from_compound(p)
        if r is None:
            return None
        hv, exact_ph, formula, steps_known, extra = r
        default = "pH"
    phv = -math.log10(hv)
    pohv = 14 - phv
    ohv = KW / hv
    if exact_ph is not None and abs(float(exact_ph) - phv) > 1e-9:
        exact_ph = None
    wants = [k for k in ("pH", "pOH", "H", "OH") if ask[k]]
    if ph and "pH" in wants:
        wants.remove("pH")
    if poh and "pOH" in wants:
        wants.remove("pOH")
    if h and "H" in wants:
        wants.remove("H")
    if oh and "OH" in wants:
        wants.remove("OH")
    if not wants:
        wants = [default]

    def dec(e) -> str:
        return str(e) if e.is_Integer else _w(float(e))

    def show(k):
        if k == "pH":
            return p.f(phv) if exact_ph is None else dec(exact_ph)
        if k == "pOH":
            return p.f(pohv) if exact_ph is None else dec(14 - exact_ph)
        if k == "H":
            if exact_ph is not None and not exact_ph.is_Integer:
                return f"10^-{dec(exact_ph)} ≈ {p.f(hv, 'M')}"
            return p.f(hv, "M")
        if exact_ph is not None and not (14 - exact_ph).is_Integer:
            return f"10^-{dec(14 - exact_ph)} ≈ {p.f(ohv, 'M')}"
        return p.f(ohv, "M")
    label = {"pH": "pH", "pOH": "pOH", "H": "[H⁺]", "OH": "[OH⁻]"}
    if len(wants) == 1:
        answer = show(wants[0])
    else:
        answer = ", ".join(f"{label[k]} = {show(k)}" for k in wants)
    if ask["class"]:
        answer += " (acidic)" if phv < 7 - 1e-9 else " (basic)" if phv > 7 + 1e-9 else " (neutral)"
    if not sub:
        parts = []
        if ph or poh:
            if ph:
                parts.append(f"pOH = 14 − {ph[1]} = {_w(pohv)}")
            else:
                parts.append(f"pH = 14 − {poh[1]} = {_w(phv)}")
            parts.append(f"[H⁺] = 10^−{_w(phv)} = {_conc(hv)}")
            parts.append(f"[OH⁻] = 10^−{_w(pohv)} = {_conc(ohv)}")
        elif h:
            parts.append(f"pH = −log₁₀({_conc(hv)}) = {_w(phv)}")
            parts.append(f"pOH = 14 − {_w(phv)} = {_w(pohv)}")
        elif oh:
            parts.append(f"pOH = −log₁₀({_conc(ohv)}) = {_w(pohv)}")
            parts.append(f"pH = 14 − {_w(pohv)} = {_w(phv)}")
        else:
            parts.append(f"pH = −log₁₀({_conc(hv)}) = {_w(phv)}")
            parts.append(f"pOH = 14 − {_w(phv)} = {_w(pohv)}")
        sub = "; ".join(parts)
    check = check or f"[H⁺] × [OH⁻] = {_conc(hv)} × {_conc(ohv)} = {_sci_exact(hv * ohv)} = Kw ✓"
    return _sol(p, formula, steps_known, sub, answer, check, extra)


def _conc(x: float) -> str:
    return f"{_w(x)} M"


def _ph_from_compound(p: Parsed):
    """[H⁺] from a named acid or base: strong ones dissociate fully; weak ones need Ka / Kb (given, or a known one)."""
    c = p.comp
    conc, vol, amt, mass = p.of("conc"), p.of("vol"), p.of("amount"), p.of("mass")
    ka = KA_VAL.search(p.tc)
    if len(_distinct(p)) > 1:
        return None
    known: list[str] = []
    extra: list[str] = []
    if conc:
        cv = conc[0].value
        known.append(f"[{c.formula if c else 'acid'}] = {conc[0].shown}")
        cx = conc[0].exact
        if len(vol) == 2 and DIL_RE.search(p.t):   # diluted first: C2 = C1·V1/V2
            v1, v2 = sorted(vol, key=lambda q: q.value)
            cv, cx = cv * v1.value / v2.value, cx * v1.exact / v2.exact
            extra.append(f"after dilution: C = {_w(conc[0].value)} × {_w(v1.value)} / {_w(v2.value)} = {_w(cv)} M")
    elif vol and (amt or mass):
        v = vol[0]
        if amt:
            n = amt[0].value
            known.append(f"n = {amt[0].shown}")
        else:
            if not c:
                return None
            n = mass[0].value / c.mm
            known += [f"m = {mass[0].shown}", _mm_known(c)]
            extra.append(f"n = m / M = {_w(mass[0].value)} / {_w(c.mm)} = {_w(n)} mol")
        cv, cx = n / v.value, None
        known.append(f"V = {_litres(v)}")
        extra.append(f"C = n / V = {_w(n)} / {_w(v.value)} = {_w(cv)} M")
    else:
        return None
    if cv <= 0:
        return None
    weak = None
    if ka:
        k = float(ka.group(3))
        k = 10 ** -k if ka.group(1) else k
        weak = (ka.group(2), k, f"{'p' if ka.group(1) else ''}K{ka.group(2)} = {ka.group(3)}")
    elif c and c.formula in WEAK and c.formula not in STRONG_A:
        side, k = WEAK[c.formula]
        weak = (side, k, f"K{side} = {_sci_exact(k)} (standard value, 25 °C)")
    if weak is None and c and c.formula in STRONG_A:
        k = STRONG_A[c.formula]
        h = cv * k
        known.append(f"{k} H⁺ per {c.formula} (strong acid, fully dissociated" +
                     (", both protons counted)" if k == 2 else ")"))
        extra.append(f"[H⁺] = {_w(cv)} × {k} = {_conc(h)}" if k != 1 else f"[H⁺] = {_conc(h)}")
        if h < 1e-6:   # so dilute that water's own H⁺ matters: [H⁺]² − C[H⁺] − Kw = 0
            h = (h + math.sqrt(h * h + 4 * KW)) / 2
            extra.append(f"very dilute, so water's own ions count: [H⁺] = (C + √(C² + 4Kw)) / 2 = {_conc(h)}")
            cx = None
        ex = _log_exact(str(sp.nsimplify(cx * k))) if cx is not None else None
        return h, ex, "pH = −log₁₀[H⁺]", known, extra
    if weak is None and c and c.formula in STRONG_B:
        k = STRONG_B[c.formula]
        oh = cv * k
        known.append(f"{k} OH⁻ per {c.formula} (strong base, fully dissociated)")
        extra.append(f"[OH⁻] = {_w(cv)} × {k} = {_conc(oh)}" if k != 1 else f"[OH⁻] = {_conc(oh)}")
        if oh < 1e-6:
            oh = (oh + math.sqrt(oh * oh + 4 * KW)) / 2
            extra.append(f"very dilute, so water's own ions count: [OH⁻] = {_conc(oh)}")
            cx = None
        e = _log_exact(str(sp.nsimplify(cx * k))) if cx is not None else None
        return KW / oh, (14 - e if e is not None else None), "pOH = −log₁₀[OH⁻], pH = 14 − pOH  (25 °C)", known, extra
    if weak is None:
        return None
    side, k, k_txt = weak
    x = (-k + math.sqrt(k * k + 4 * k * cv)) / 2   # x² / (C − x) = K, the positive root
    known.append(k_txt)
    ion = "H⁺" if side == "a" else "OH⁻"
    extra.append(f"K{side} = x² / (C − x) with x = [{ion}]: x² + {_w(k)}·x − {_w(k * cv)} = 0 → x = {_conc(x)}")
    extra.append(f"check: x² / (C − x) = {_sci_exact(x * x / (cv - x))} = K{side} ✓; ionised {x / cv * 100:.2f}%")
    h = x if side == "a" else KW / x
    formula = "pH = −log₁₀[H⁺], weak acid: Ka = x² / (C − x)" if side == "a" else \
        "pOH = −log₁₀[OH⁻], pH = 14 − pOH; weak base: Kb = x² / (C − x)"
    return h, None, formula, known, extra


# ---------------------------------------------------------------- entry point

TRIGGER = re.compile(r"\bmol\w*|\bmolar\w*|\bmolecul\w*|\batoms?\b|\bions?\b|\bparticles?\b|\bformula units?\b|"
                     r"\bgrams?\b|\bmass\b|\bweigh\w*|\bp(?:h|oh)\b|\[|\bh\+|\bh3o\+|\boh-|hydronium|\bhydrogen ion|"
                     r"\bhydroxide|\bconcentrat\w*|\bdilut\w*|\bstock\b|\bstp\b|\bsatp\b|\bgas\b|\bideal\b|"
                     r"\bpressure\b|\bvolume\b|\btemperature\b|\bpercent\w*|%|\bcomposition\b|\bdensity\b|\bmw\b|\bmr\b|"
                     r"\bk[ab]\b|\bpk[ab]\b|\bhow (?:many|much)\b|\bconvert\b|\bneed(?:ed)?\b|\bmake\b|\bprepare\b|"
                     r"\b\d+(?:\.\d+)?\s*(?:m|mm|g|mg|kg|ml|l|atm|kpa|mmhg|torr|k)\b")
NOT_CHEM = re.compile(r"^\s*(?:what(?:'s| is| are)|define|explain|meaning of|tell me about)\s+(?:a |an |the )?"
                      r"(?:mole|molarity|molality|molar mass|ph|poh|avogadro'?s? (?:number|constant)|ideal gas(?: law)?|"
                      r"dilution|stp|percent composition|a hydrate|hydrate|titration|buffer|acid|base|ion|isotope)"
                      r"s?\s*\??\s*$")


def solve(text: str) -> Solution | None:
    """A chemistry calculation in plain English, solved with steps; None when the message isn't one."""
    if not text or len(text) > 600 or NOT_CHEM.match(text.lower()):
        return None
    low = normalize(text).lower()
    if not TRIGGER.search(low):
        return None
    try:
        p = Parsed(text)
        if not p.comps and not p.qs and not PH_TRIG.search(p.t):
            return None
        for fn in (ph_problem, gas, dilution, molarity, composition, conversions, molar_mass_problem):
            sol = fn(p)
            if sol is not None:
                return sol
    except (ValueError, ZeroDivisionError, OverflowError, TypeError, AttributeError, KeyError, IndexError):
        return None
    return None
