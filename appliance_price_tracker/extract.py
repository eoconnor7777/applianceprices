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

# Appliances are never €0. Live pages sprinkle in €0.00 placeholders ("you
# save €0.00", finance-from lines, the search-banner echo) that the text
# scraper would otherwise latch onto first. Treat anything under this floor as
# "not a real price" so we keep scanning for the genuine one.
MIN_PRICE = 1.0


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
            money = _money(str(price)) if price is not None else None
            if name and money is not None and money >= MIN_PRICE:
                out.append(Candidate(str(name), money, url, _avail(avail)))
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
            if not m:
                continue
            price = _money(m.group(1))
            if price is None or price < MIN_PRICE:   # skip €0.00 placeholders
                continue
            out.append(Candidate(line, price))
            break
    return out


# Buy It Direct has no stable "?q=" results-page template and no JSON-LD on
# its search page (it redirects term searches to a JS-driven category grid).
# Its autocomplete endpoint, however, returns clean JSON we can parse directly:
#   /Search/Autocomplete?term={query}  ->  {"Products":[{WebTitle, URL, ItemPrice}]}
# Skip refurbished/graded listings - we only track new stock.
_BID_SKIP = ("refurbished", "grade a1", "graded")


def _json_blob(text: str) -> dict | None:
    """Return the parsed JSON object from `text`, tolerating a headless browser
    that wraps a raw JSON response in <pre>...</pre> (or full HTML)."""
    s = text.strip()
    if s.startswith("{"):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass
    inner = BeautifulSoup(text, "html.parser").get_text().strip()
    if inner.startswith("{"):
        try:
            return json.loads(inner)
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def parse_buyitdirect(html: str) -> list[Candidate]:
    data = _json_blob(html)
    if not data:
        return []
    out: list[Candidate] = []
    for p in data.get("Products", []) or []:
        title = (p.get("WebTitle") or "").strip()
        if not title or any(s in title.lower() for s in _BID_SKIP):
            continue
        ip = p.get("ItemPrice") or {}
        price = None
        if isinstance(ip, dict):
            disp = ip.get("Display")
            if isinstance(disp, (int, float)):
                price = round(float(disp), 2)
            elif ip.get("DisplayPriceWithCurrency"):
                m = PRICE_RE.search(str(ip["DisplayPriceWithCurrency"]))
                price = _money(m.group(1)) if m else None
        if price is None or price < MIN_PRICE:
            continue
        rel = (p.get("URL") or "").lstrip("/")
        url = f"https://www.buyitdirect.ie/{rel}" if rel else None
        out.append(Candidate(title, price, url))
    return out


def extract_candidates(html: str, strategy: str, brands: set[str]) -> list[Candidate]:
    if strategy == "jsonld":
        return parse_jsonld(html)
    if strategy == "text":
        return parse_text(html, brands)
    if strategy == "buyitdirect":
        return parse_buyitdirect(html)
    if strategy == "jsonld_http":   # plain-HTTP fetch, structured-data parse
        return parse_jsonld(html)
    # auto: prefer structured data, fall back to text scraping
    cands = parse_jsonld(html)
    return cands if cands else parse_text(html, brands)
