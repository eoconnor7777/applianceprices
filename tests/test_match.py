"""Tiny self-contained tests (run: python tests/test_match.py).

Proves the variant filter works: the black washer must NOT match the white
listing, and the integrated fridge must NOT match a freestanding one.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from appliance_price_tracker.config import Product            # noqa: E402
from appliance_price_tracker.extract import Candidate         # noqa: E402
from appliance_price_tracker.match import best_match, score   # noqa: E402


def test_black_variant_filter():
    p = Product(key="w", name="washer", brand="Bosch",
                must_include=[["black", "graphite"]], prefer=["series 6"])
    white = Candidate("Bosch Series 6 9kg Washing Machine - White", 599.95)
    black = Candidate("Bosch Series 6 9kg Washing Machine - Graphite", 679.95)
    assert score(p, white) < 0          # filtered out
    cand, sc = best_match(p, [white, black])
    assert cand is black


def test_integrated_filter():
    p = Product(key="f", name="fridge", brand="Liebherr",
                must_include=[["integrated", "built in"]])
    free = Candidate("Liebherr Freestanding Fridge Freezer", 700)
    integ = Candidate("Liebherr Integrated 60/40 Fridge Freezer", 1149)
    cand, _ = best_match(p, [free, integ])
    assert cand is integ


def test_model_number_wins():
    p = Product(key="o", name="combi", brand="Bosch", model="HMG7764B1B",
                must_include=[["air fry", "microwave"]])
    a = Candidate("Bosch Series 8 HMG7764B1B Oven Microwave Air Fry", 1499)
    b = Candidate("Bosch Series 6 Oven with Microwave", 999)
    cand, _ = best_match(p, [a, b])
    assert cand is a       # exact model match beats the cheaper non-match


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("All tests passed.")
