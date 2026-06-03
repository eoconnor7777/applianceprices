"""Turn a rendered HTML page into price `Candidate`s.

Two strategies, because Irish retailers split roughly into two camps:

* **jsonld**  - Shopify/modern stacks embed <script type="application/ld+json">
  with Product/offers. This is the most robust source when present.
* **text**    - Some sites (e.g. Power City) render prices into the DOM text
  but not as clean structured data; we pair a brand-prefixed title line with
  the next "€xx.xx" we see, mirroring the manual browser approach.

Both take an HTML *string*, so they are unit-testable offline without a
browser (see tests / --mock).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

PRICE_RE = re.compile(r"€\s*([\d.,]+)")


@dataclass
class Candidate:
    title: str
    price: float | None
    url: str | None = None
    in_stock: bool | None = None


def _money(s: str) -> float | None:
    s = s.strip().replace(" ", "")
    if "," in s and "." in s:           # 1,039.95 -> 1039.95
        s = s.replace(",", "")
    elif "," in s:                      # 1,99 (decimal) or 1,039 (thousands)
        s = s.replace(",", ".") if re.fullmatch(r"\d+,\d{2}", s) else s.replace(",", "")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _avail(a) -> bool | None:
    if not a:
        return None
    a = str(a).lower()
    if "instock" in a or "in_stock" in a:
        return True
    if "outofstock" in a or "soldout" in a or "discontinued" in a:
        return False
    return None


def _iter_products(node):
    """Walk arbitrarily nested JSON-LD yielding dicts that look like products."""
    if isinstance(node, dict):
        t = node.get("@type")
        types = t if isinstance(t, list) else [t]
        if "Product" in types or "offers" in node:
            yield node
        for v in node.values():
            yield from _iter_products(v)
    elif isinstance(node, list):
        for v in node:
            yield from _iter_products(v)


def parse_jsonld(html: str) -> list[Candidate]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[Candidate] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for p in _iter_products(data):
            name = p.get("name")
            offers = p.get("offers")
            if isinstance(offers, list):
                offers = offers[0] if offers else None
            price = url = avail = None
            if isinstance(offers, dict):
                price = offers.get("price") or offers.get("lowPrice")
                url = offers.get("url")
                avail = offers.get("availability")
            url = url or p.get("url") or p.get("@id")
            if name and price is not None:
                out.append(Candidate(str(name), _money(str(price)), url, _avail(avail)))
    return out


def parse_text(html: str, brands: set[str]) -> list[Candidate]:
    soup = BeautifulSoup(html, "html.parser")
    lines = [ln.strip() for ln in soup.get_text("\n").split("\n") if ln.strip()]
    bl = [b.lower() for b in brands] or [""]
    out: list[Candidate] = []
    for i, line in enumerate(lines):
        low = line.lower()
        looks_like_title = 8 <= len(line) <= 120 and any(b in low for b in bl)
        if not looks_like_title:
            continue
        for j in range(i + 1, min(i + 14, len(lines))):
            m = PRICE_RE.search(lines[j])
            if m:
                out.append(Candidate(line, _money(m.group(1))))
                break
    return out


def extract_candidates(html: str, strategy: str, brands: set[str]) -> list[Candidate]:
    if strategy == "jsonld":
        return parse_jsonld(html)
    if strategy == "text":
        return parse_text(html, brands)
    # auto: prefer structured data, fall back to text scraping
    cands = parse_jsonld(html)
    return cands if cands else parse_text(html, brands)
