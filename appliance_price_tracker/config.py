"""Load the declarative YAML config into typed objects.

A `Product` is a *specific variant* you want to track (e.g. the black,
freestanding Bosch Series 6 washer). A `Retailer` describes how to search a
site and which extraction strategy its pages need.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class Product:
    key: str
    name: str
    brand: str = ""
    model: str = ""                       # SKU if known; preferred search term
    # Hard requirements on the matched title. Each entry is either a string
    # (must be present) or a list (at least one of them must be present).
    # Use this to pin the *variant*: colour, freestanding vs integrated, etc.
    must_include: list = field(default_factory=list)
    # Soft signals that increase the match score but are not required.
    prefer: list[str] = field(default_factory=list)
    # Tokens that, if present in a title, disqualify it (e.g. a single oven
    # excludes "microwave"/"combi" so it never matches a combi oven).
    exclude: list[str] = field(default_factory=list)

    def query(self) -> str:
        """What to type into a retailer's search box. Model first if we have
        one (most precise), otherwise the human name."""
        return self.model or self.name


@dataclass
class Retailer:
    key: str
    name: str
    search_url: str                       # must contain "{query}"
    strategy: str = "auto"                # "jsonld" | "text" | "auto" | "buyitdirect"
    enabled: bool = True
    # Bot-protected sites: launch a fresh browser process per page (slower, but
    # the only thing that reliably beats their fingerprinting from CI).
    fresh_browser: bool = False
    # Visit this URL first (same context) so a JS bot-challenge can solve before
    # the search request - e.g. an Incapsula homepage that mints incap_ses.
    warmup_url: str = ""


@dataclass
class Discounts:
    bosch_bundle_flat: float = 0.0        # flat € off a qualifying Bosch order
    bosch_bundle_min_items: int = 3
    # item-count -> fractional discount, e.g. {2: 0.0, 3: 0.0}
    multibuy: dict[int, float] = field(default_factory=dict)


@dataclass
class AppConfig:
    currency: str
    products: list[Product]
    retailers: list[Retailer]
    discounts: Discounts

    def brands(self) -> set[str]:
        return {p.brand for p in self.products if p.brand}


def load_config(path: str) -> AppConfig:
    with open(path, "r", encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh)

    products = [Product(**_clean(p, Product)) for p in raw.get("products", [])]
    retailers = [Retailer(**_clean(r, Retailer)) for r in raw.get("retailers", [])]
    disc_raw = raw.get("discounts", {}) or {}
    # YAML multibuy keys come in as ints already, but be defensive.
    mb = {int(k): float(v) for k, v in (disc_raw.get("multibuy", {}) or {}).items()}
    discounts = Discounts(
        bosch_bundle_flat=float(disc_raw.get("bosch_bundle_flat", 0.0)),
        bosch_bundle_min_items=int(disc_raw.get("bosch_bundle_min_items", 3)),
        multibuy=mb,
    )
    return AppConfig(
        currency=raw.get("currency", "EUR"),
        products=products,
        retailers=retailers,
        discounts=discounts,
    )


def _clean(d: dict, cls) -> dict:
    """Drop unknown keys so a stray YAML field doesn't crash construction."""
    allowed = {f.name for f in dataclasses.fields(cls)}
    return {k: v for k, v in d.items() if k in allowed}
