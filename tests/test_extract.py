"""Extraction tests (run: python tests/test_extract.py).

Pins the €0.00 fix: live pages sprinkle in zero-euro placeholders
("you save €0.00", finance lines, the search-banner echo) and the text
scraper must skip them rather than recording a €0.00 price.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from appliance_price_tracker.extract import (parse_jsonld,   # noqa: E402
                                             parse_text)


def test_text_skips_zero_and_takes_real_price():
    html = """
    <p>POWERCITY - WGG244ZCGB BOSCH SERIES 6 9KG WASHING MACHINE - GRAPHITE</p>
    <p>You save €0.00</p>
    <p>€749.95</p>
    """
    cands = parse_text(html, {"Bosch"})
    assert len(cands) == 1
    assert cands[0].price == 749.95


def test_text_drops_candidate_with_only_zero_price():
    html = """
    <p>POWERCITY - search Bosch Series 6 dishwasher - Free Recycling *</p>
    <p>€0.00</p>
    """
    cands = parse_text(html, {"Bosch"})
    assert cands == []


def test_jsonld_skips_zero_price():
    html = """
    <script type="application/ld+json">
    {"@type":"Product","name":"Bosch Dishwasher",
     "offers":{"@type":"Offer","price":"0.00","priceCurrency":"EUR"}}
    </script>
    """
    assert parse_jsonld(html) == []


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("All tests passed.")
