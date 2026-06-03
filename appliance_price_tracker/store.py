"""Append-only CSV history so you can replay and trend prices over time."""
from __future__ import annotations

import csv
import os

FIELDS = [
    "timestamp", "run_id", "product_key", "product_name", "retailer",
    "query", "matched_title", "price", "currency", "url",
    "in_stock", "score", "status",
]


def append_rows(path: str, rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    new_file = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def load_rows(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["price"] = float(r["price"]) if r.get("price") not in ("", None) else None
    return rows
