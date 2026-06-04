"""Score candidate listings against a target Product and pick the best.

The scoring deliberately treats `must_include` as a hard filter so the
*variant* is respected: a query for the black freestanding washer will not
match the white one even if the white one is the top search result.
"""
from __future__ import annotations

import re

from .config import Product
from .extract import Candidate


def _norm(s) -> str:
    s = "" if s is None else str(s)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9/]+", " ", s.lower())).strip()


def _contains(haystack_norm: str, needle: str) -> bool:
    return _norm(needle) in haystack_norm


# Bosch-style model code, e.g. HBG7741B1B, CMG7241B1B, SMV6ZCX10G, WGG244ZCGB.
# Three letters, 1-4 digits, then a short alphanumeric tail.
_MODEL_TOKEN_RE = re.compile(r"\b[A-Z]{3}\d{1,4}[A-Z0-9]{2,7}\b")


def _has_conflicting_model(raw_title: str, model: str) -> bool:
    """True if the title names a *different* model code than ours.

    A SKU search can return a sibling variant - Soundstore answered an
    HBG7741B1B query with HBG7341B1B - and our loose must_include ("oven")
    would otherwise accept it and record the wrong product's price. When a title
    carries an explicit model code that isn't ours, reject it. Titles with no
    model code at all are trusted (Power City/DID omit the SKU), so this only
    fires on genuine cross-variant collisions.
    """
    if not model:
        return False
    found = _MODEL_TOKEN_RE.findall(raw_title.upper())
    if not found:
        return False
    return model.upper() not in found


def _must_ok(title_norm: str, must_include: list) -> bool:
    for entry in must_include:
        if isinstance(entry, (list, tuple)):
            if not any(_contains(title_norm, opt) for opt in entry):
                return False
        else:
            if not _contains(title_norm, entry):
                return False
    return True


def score(product: Product, cand: Candidate) -> float:
    """Higher is better. Returns -1 if the candidate fails the hard filter."""
    title_norm = _norm(cand.title)
    if not _must_ok(title_norm, product.must_include):
        return -1.0
    if any(_contains(title_norm, x) for x in product.exclude):
        return -1.0
    if _has_conflicting_model(cand.title, product.model):
        return -1.0
    s = 0.0
    if product.model and _contains(title_norm, product.model):
        s += 5.0
    if product.brand and _contains(title_norm, product.brand):
        s += 2.0
    for token in product.prefer:
        if _contains(title_norm, token):
            s += 0.5
    return s


def best_match(product: Product, candidates: list[Candidate], min_score: float = 2.0):
    """Return (candidate, score) for the best priced match, or (None, 0)."""
    scored = [
        (c, score(product, c))
        for c in candidates
        if c.price is not None
    ]
    scored = [(c, sc) for c, sc in scored if sc >= min_score]
    if not scored:
        return None, 0.0
    # Best score wins; tie-break on lowest price.
    scored.sort(key=lambda cs: (-cs[1], cs[0].price))
    return scored[0]


def closest(product: Product, candidates: list[Candidate]):
    """Diagnostic: the highest-scoring candidate IGNORING the min_score gate,
    plus a one-word reason it didn't qualify. Lets `track` print *why* a page
    came back no_match (failed must_include? excluded token? brand missing?)
    so the YAML filters can be tuned without guessing. Returns
    (candidate, score, reason) or None when there were no priced candidates."""
    best = None
    for c in candidates:
        if c.price is None:
            continue
        title_norm = _norm(c.title)
        if not _must_ok(title_norm, product.must_include):
            sc, reason = -1.0, "must_include"
        elif any(_contains(title_norm, x) for x in product.exclude):
            sc, reason = -1.0, "excluded"
        elif _has_conflicting_model(c.title, product.model):
            sc, reason = -1.0, "wrong_sku"
        else:
            sc = score(product, c)
            reason = "ok" if sc >= 2.0 else "low_score"
        if best is None or sc > best[1]:
            best = (c, sc, reason)
    return best
