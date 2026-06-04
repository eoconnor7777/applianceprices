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
        else:
            sc = score(product, c)
            reason = "ok" if sc >= 2.0 else "low_score"
        if best is None or sc > best[1]:
            best = (c, sc, reason)
    return best
