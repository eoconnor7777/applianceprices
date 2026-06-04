"""Analyse the price history: cheapest source per model, per-retailer
single-basket bundle totals (with discount rules), and lowest-ever prices."""
from __future__ import annotations

from .config import AppConfig


def latest_run(rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    newest = max(r["run_id"] for r in rows)
    return [r for r in rows if r["run_id"] == newest]


def _ok(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r.get("status") == "ok" and r.get("price") is not None]


def best_per_product(rows: list[dict]) -> dict[str, dict]:
    """product_key -> cheapest ok row."""
    best: dict[str, dict] = {}
    for r in _ok(rows):
        k = r["product_key"]
        if k not in best or r["price"] < best[k]["price"]:
            best[k] = r
    return best


def per_retailer_basket(cfg: AppConfig, rows: list[dict]) -> dict[str, dict]:
    """For each retailer: items found, raw subtotal, and discounted total."""
    out: dict[str, dict] = {}
    ok = _ok(rows)
    for ret in cfg.retailers:
        items = [r for r in ok if r["retailer"] == ret.key]
        if not items:
            continue
        subtotal = round(sum(r["price"] for r in items), 2)
        out[ret.key] = {
            "name": ret.name,
            "count": len(items),
            "subtotal": subtotal,
            "discounted": _apply_discounts(cfg, items, subtotal),
        }
    return out


def _apply_discounts(cfg: AppConfig, items: list[dict], subtotal: float) -> float:
    d = cfg.discounts
    total = subtotal
    pct = 0.0
    for n in sorted(d.multibuy):                 # highest qualifying tier wins
        if len(items) >= n:
            pct = d.multibuy[n]
    total *= (1 - pct)
    bosch = sum(1 for r in items if "bosch" in (r.get("matched_title", "").lower()))
    if bosch >= d.bosch_bundle_min_items:
        total -= d.bosch_bundle_flat
    return round(max(total, 0.0), 2)


def lowest_ever(rows: list[dict]) -> dict[str, dict]:
    best: dict[str, dict] = {}
    for r in _ok(rows):
        k = r["product_key"]
        if k not in best or r["price"] < best[k]["price"]:
            best[k] = r
    return best


def render_report(cfg: AppConfig, all_rows: list[dict]) -> str:
    latest = latest_run(all_rows)
    bpp = best_per_product(latest)
    baskets = per_retailer_basket(cfg, latest)
    ever = lowest_ever(all_rows)
    sym = "€" if cfg.currency == "EUR" else cfg.currency + " "
    L: list[str] = []
    run_id = latest[0]["run_id"] if latest else "n/a"
    L.append(f"# Appliance price report\n\nLatest run: `{run_id}`\n")

    L.append("## Cheapest source per model\n")
    L.append("| Model | Model # | Best price | Retailer | Lowest ever |")
    L.append("|---|---|---|---|---|")
    cheapest_sum = 0.0
    for p in cfg.products:
        b = bpp.get(p.key)
        e = ever.get(p.key)
        if b:
            cheapest_sum += b["price"]
            price = f"{sym}{b['price']:.2f}"
            who = b["retailer"]
        else:
            price, who = "—", "not found"
        ev = f"{sym}{e['price']:.2f}" if e else "—"
        sku = p.model or "—"
        L.append(f"| {p.name} | {sku} | {price} | {who} | {ev} |")
    L.append(f"\n**Cheapest-mix basket (one item each, best retailer): "
             f"{sym}{cheapest_sum:.2f}**\n")

    n_products = len(cfg.products)
    L.append("## Single-retailer baskets (with bundle/multibuy rules applied)\n")
    L.append("_Preference is one shop for all - a ✅ marks retailers that carry "
             "every tracked item._\n")
    L.append("| Retailer | Items found | Full basket | Subtotal | After discounts |")
    L.append("|---|---|---|---|---|")
    for key, b in sorted(baskets.items(), key=lambda kv: kv[1]["discounted"]):
        full = "✅" if b["count"] == n_products else ""
        L.append(f"| {b['name']} | {b['count']}/{n_products} | {full} | "
                 f"{sym}{b['subtotal']:.2f} | {sym}{b['discounted']:.2f} |")
    L.append("\n_Discount rules are configurable in `models.yaml` "
             "(`discounts:`) and reflect each retailer's stated bundle terms._\n")

    # One-shop-for-all vs mix-and-match: surface the best single-shop that has
    # the WHOLE basket, and what staying loyal to it costs over splitting.
    full_baskets = {k: b for k, b in baskets.items() if b["count"] == n_products}
    L.append("## One shop vs mix-and-match\n")
    if full_baskets:
        bk, bb = min(full_baskets.items(), key=lambda kv: kv[1]["discounted"])
        delta = round(bb["discounted"] - cheapest_sum, 2)
        L.append(f"- **Best one-shop-for-all:** {bb['name']} - "
                 f"{sym}{bb['discounted']:.2f} (all {n_products} items, "
                 f"after discounts).")
        L.append(f"- **Cheapest mix-and-match:** {sym}{cheapest_sum:.2f} "
                 f"(splitting across retailers).")
        if delta <= 0:
            L.append(f"- Staying with **{bb['name']}** is already the cheapest "
                     f"option - no saving from splitting.")
        else:
            L.append(f"- Splitting saves **{sym}{delta:.2f}** vs the best single "
                     f"shop - your call whether the convenience is worth it.")
    else:
        L.append(f"- No single retailer currently carries all {n_products} items, "
                 f"so a mix-and-match basket ({sym}{cheapest_sum:.2f}) is the only "
                 f"way to get everything. Cheapest near-complete shops are listed "
                 f"above.")
    L.append("")
    return "\n".join(L)
