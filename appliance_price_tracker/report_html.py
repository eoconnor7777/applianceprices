"""Generate a single self-contained HTML 'price board' from the history.

Design: an architect's-ledger aesthetic - warm paper, ink text, a single
emerald accent for the best price in each row, burnt-clay deltas that deepen
with how much more expensive a cell is, and monospaced figures for tabular
alignment. No external JS; fonts via CDN with graceful fallbacks so the file
still reads well offline.
"""
from __future__ import annotations

import html
from datetime import datetime, timezone

from .analyze import (best_per_product, latest_run, lowest_ever,
                      per_retailer_basket)
from .config import AppConfig

_EN = "\u2014"      # em dash (not found)
_MINUS = "\u2212"   # minus sign
_MID = "\u00b7"     # middot


def _sym(cfg: AppConfig) -> str:
    return "\u20ac" if cfg.currency == "EUR" else cfg.currency + " "


def _money(sym: str, v) -> str:
    return f"{sym}{v:,.2f}" if v is not None else "\u2014"


def _matrix(rows: list[dict]):
    """product_key -> retailer_key -> price (latest, ok only)."""
    m: dict[str, dict[str, float]] = {}
    titles: dict[str, dict[str, str]] = {}
    urls: dict[str, dict[str, str]] = {}
    for r in rows:
        if r.get("status") != "ok" or r.get("price") is None:
            continue
        m.setdefault(r["product_key"], {})[r["retailer"]] = r["price"]
        titles.setdefault(r["product_key"], {})[r["retailer"]] = r.get("matched_title", "")
        urls.setdefault(r["product_key"], {})[r["retailer"]] = r.get("url", "")
    return m, titles, urls


def _premium_style(pct: float) -> str:
    alpha = min(0.30, (pct / 40.0) * 0.30)
    return f"background:rgba(168,68,42,{alpha:.3f});"


def build_html(cfg: AppConfig, all_rows: list[dict]) -> str:
    sym = _sym(cfg)
    latest = latest_run(all_rows)
    run_id = latest[0]["run_id"] if latest else "no data"
    matrix, titles, urls = _matrix(latest)
    ever = lowest_ever(all_rows)
    bpp = best_per_product(latest)
    baskets = per_retailer_basket(cfg, latest)

    # Retailers shown = configured order, those with >=1 found item this run.
    cols = [r for r in cfg.retailers
            if any(r.key in matrix.get(p.key, {}) for p in cfg.products)]

    # ---- summary numbers ----
    cheapest_mix = sum(b["price"] for b in bpp.values())
    # "Best bundle" = cheapest among the *most complete* baskets, so a shop
    # missing half your models can't look like the winner on price alone.
    best_bundle = best_bundle_key = None
    if baskets:
        max_cov = max(b["count"] for b in baskets.values())
        complete = {k: b for k, b in baskets.items() if b["count"] == max_cov}
        best_bundle_key, best_bundle = min(
            complete.items(), key=lambda kv: kv[1]["discounted"])
    n_models = len(cfg.products)
    found_models = sum(1 for p in cfg.products if p.key in bpp)

    # ===== build comparison rows =====
    body_rows = []
    for p in cfg.products:
        prices = matrix.get(p.key, {})
        row_min = min(prices.values()) if prices else None
        cells = []
        for ret in cols:
            v = prices.get(ret.key)
            if v is None:
                cells.append('<td class="cell na">\u2014</td>')
                continue
            url = urls.get(p.key, {}).get(ret.key) or ""
            title = html.escape(titles.get(p.key, {}).get(ret.key, ""))
            price_html = _money(sym, v)
            if url:
                price_html = (f'<a href="{html.escape(url)}" target="_blank" '
                              f'rel="noopener" title="{title}">{price_html}</a>')
            if v == row_min:
                cells.append(
                    f'<td class="cell best"><span class="tag">BEST</span>'
                    f'<span class="price">{price_html}</span></td>')
            else:
                pct = (v - row_min) / row_min * 100 if row_min else 0
                delta = v - row_min
                cells.append(
                    f'<td class="cell premium" style="{_premium_style(pct)}">'
                    f'<span class="price">{price_html}</span>'
                    f'<span class="delta">+{sym}{delta:,.0f} '
                    f'<em>+{pct:.0f}%</em></span></td>')
        ev = ever.get(p.key)
        ev_html = _money(sym, ev["price"]) if ev else "\u2014"
        best_ret = bpp[p.key]["retailer"] if p.key in bpp else "\u2014"
        sku_html = (f'<span class="msku">{html.escape(p.model)}</span>'
                    if p.model else "")
        body_rows.append(
            f'<tr><th scope="row"><span class="mname">{html.escape(p.name)}</span>'
            f'{sku_html}'
            f'<span class="mmeta">best @ {html.escape(best_ret)} '
            f'\u00b7 low ever {ev_html}</span></th>{"".join(cells)}</tr>')

    head_cells = "".join(
        f'<th class="rhead">{html.escape(r.name)}</th>' for r in cols)

    # ===== bundle basket section =====
    basket_rows = []
    for key, b in sorted(baskets.items(), key=lambda kv: kv[1]["discounted"]):
        missing = [p.name for p in cfg.products
                   if key not in matrix.get(p.key, {})]
        saving = b["subtotal"] - b["discounted"]
        win = "win" if key == best_bundle_key else ""
        miss_html = (f'<span class="miss">missing: '
                     f'{html.escape(", ".join(missing))}</span>' if missing else
                     '<span class="full">full coverage</span>')
        saving_txt = (_MINUS + sym + format(saving, ",.2f")) if saving else _EN
        basket_rows.append(
            f'<tr class="{win}"><th scope="row">{html.escape(b["name"])}'
            f'<span class="cov">{b["count"]}/{n_models} items {_MID} {miss_html}</span></th>'
            f'<td class="num">{_money(sym, b["subtotal"])}</td>'
            f'<td class="num save">{saving_txt}</td>'
            f'<td class="num total">{_money(sym, b["discounted"])}</td></tr>')

    when = datetime.strptime(run_id, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc).strftime("%d %b %Y, %H:%M UTC") if latest else "\u2014"

    best_bundle_txt = (
        f'{_money(sym, best_bundle["discounted"])} '
        f'<small>at {html.escape(best_bundle["name"])} '
        f'({best_bundle["count"]}/{n_models})</small>'
        if best_bundle else _EN)

    return _TEMPLATE.format(
        when=when, currency=cfg.currency,
        cheapest_mix=_money(sym, cheapest_mix),
        best_bundle=best_bundle_txt,
        found=found_models, total=n_models, retailers=len(cols),
        head_cells=head_cells, body_rows="".join(body_rows),
        basket_rows="".join(basket_rows),
        bosch_flat=_money(sym, cfg.discounts.bosch_bundle_flat),
        bosch_min=cfg.discounts.bosch_bundle_min_items,
    )


_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kitchen Appliance Price Board</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,900&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{{
  --paper:#f3eee2; --panel:#fbf8f0; --ink:#1d1b16; --muted:#726a5b;
  --line:#ded6c4; --best:#1f6f4a; --best-bg:#e1efe4; --clay:#a8442a; --gold:#b9892f;
  --serif:'Fraunces',Georgia,'Times New Roman',serif;
  --mono:'IBM Plex Mono',ui-monospace,'Cascadia Code',Menlo,monospace;
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--paper);color:var(--ink);font-family:var(--serif);
  background-image:radial-gradient(rgba(0,0,0,.025) 1px,transparent 1px);
  background-size:4px 4px;}}
.wrap{{max-width:1180px;margin:0 auto;padding:38px 26px 70px;}}
header.top{{border-bottom:3px solid var(--ink);padding-bottom:18px;margin-bottom:8px;
  display:flex;justify-content:space-between;align-items:flex-end;gap:20px;flex-wrap:wrap;}}
h1{{font-weight:900;font-size:clamp(30px,5vw,52px);line-height:.95;margin:0;letter-spacing:-.02em;}}
h1 em{{font-style:italic;color:var(--clay);}}
.sub{{font-family:var(--mono);font-size:12px;color:var(--muted);text-transform:uppercase;
  letter-spacing:.12em;text-align:right;line-height:1.7;}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1px;
  background:var(--line);border:1px solid var(--line);margin:26px 0 34px;}}
.stat{{background:var(--panel);padding:16px 18px;}}
.stat .k{{font-family:var(--mono);font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);}}
.stat .v{{font-family:var(--mono);font-weight:600;font-size:26px;margin-top:6px;letter-spacing:-.01em;}}
.stat .v small{{display:block;font-weight:400;font-size:11px;color:var(--muted);letter-spacing:0;margin-top:3px;}}
.stat.hero{{background:var(--ink);color:var(--paper);}}
.stat.hero .k{{color:#c9bfa8;}} .stat.hero .v small{{color:#b9ad94;}}
h2{{font-weight:600;font-size:13px;font-family:var(--mono);text-transform:uppercase;
  letter-spacing:.16em;color:var(--muted);margin:40px 0 14px;
  display:flex;align-items:center;gap:12px;}}
h2::after{{content:"";flex:1;height:1px;background:var(--line);}}
.scroll{{overflow-x:auto;border:1px solid var(--line);background:var(--panel);}}
table{{border-collapse:collapse;width:100%;min-width:640px;}}
thead th{{position:sticky;top:0;background:var(--ink);color:var(--paper);
  font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;
  padding:13px 14px;text-align:right;font-weight:500;}}
thead th.corner{{text-align:left;}}
th.rhead{{border-left:1px solid #3a352b;}}
tbody th[scope=row]{{text-align:left;padding:14px;border-top:1px solid var(--line);
  vertical-align:top;max-width:280px;}}
.mname{{display:block;font-weight:600;font-size:15.5px;line-height:1.2;}}
.msku{{display:inline-block;font-family:var(--mono);font-size:10.5px;font-weight:500;
  color:var(--clay);background:rgba(168,68,42,.08);border:1px solid var(--line);
  border-radius:3px;padding:1px 6px;margin-top:6px;letter-spacing:.06em;}}
.mmeta{{display:block;font-family:var(--mono);font-size:10.5px;color:var(--muted);
  margin-top:5px;letter-spacing:.04em;}}
td.cell{{border-top:1px solid var(--line);border-left:1px solid var(--line);
  padding:13px 14px;text-align:right;font-family:var(--mono);vertical-align:top;min-width:120px;}}
td.cell .price{{font-size:15px;font-weight:500;display:block;}}
td.cell a{{color:inherit;text-decoration:none;border-bottom:1px dotted currentColor;}}
td.cell.na{{color:#bcb3a0;}}
td.best{{background:var(--best-bg);box-shadow:inset 3px 0 0 var(--best);}}
td.best .tag{{display:inline-block;font-size:9px;letter-spacing:.12em;background:var(--best);
  color:#fff;padding:2px 6px;border-radius:2px;margin-bottom:5px;}}
td.best .price{{color:var(--best);font-weight:600;}}
td.premium .delta{{display:block;font-size:11px;color:var(--clay);margin-top:4px;}}
td.premium .delta em{{font-style:normal;opacity:.7;}}
table.bundle{{min-width:520px;}}
table.bundle th[scope=row]{{font-size:15px;}}
.cov{{display:block;font-family:var(--mono);font-size:10.5px;color:var(--muted);margin-top:5px;}}
.miss{{color:var(--clay);}} .full{{color:var(--best);}}
td.num{{text-align:right;font-family:var(--mono);padding:14px;border-top:1px solid var(--line);
  border-left:1px solid var(--line);font-size:14px;}}
td.num.save{{color:var(--best);}}
td.num.total{{font-weight:600;font-size:16px;}}
tr.win td,tr.win th{{background:var(--best-bg);}}
tr.win td.total{{color:var(--best);}}
.legend{{display:flex;gap:22px;flex-wrap:wrap;font-family:var(--mono);font-size:11px;
  color:var(--muted);margin:14px 2px 0;}}
.legend span{{display:inline-flex;align-items:center;gap:7px;}}
.sw{{width:13px;height:13px;border-radius:2px;display:inline-block;}}
.note{{font-family:var(--mono);font-size:11.5px;color:var(--muted);line-height:1.7;
  margin-top:34px;border-top:1px solid var(--line);padding-top:16px;}}
.note b{{color:var(--ink);}}
@media print{{body{{background:#fff}} .scroll{{overflow:visible}} thead th{{position:static}}}}
</style></head>
<body><div class="wrap">
<header class="top">
  <h1>The Kitchen<br><em>Price Board</em></h1>
  <div class="sub">Live retailer comparison<br>Updated {when}<br>Currency: {currency}</div>
</header>

<div class="stats">
  <div class="stat hero"><div class="k">Cheapest bundle</div>
    <div class="v">{best_bundle}</div></div>
  <div class="stat"><div class="k">Cheapest-mix floor</div>
    <div class="v">{cheapest_mix}<small>each item at its lowest</small></div></div>
  <div class="stat"><div class="k">Models matched</div>
    <div class="v">{found}/{total}</div></div>
  <div class="stat"><div class="k">Retailers compared</div>
    <div class="v">{retailers}</div></div>
</div>

<h2>Side-by-side by model</h2>
<div class="scroll"><table>
<thead><tr><th class="corner">Model</th>{head_cells}</tr></thead>
<tbody>{body_rows}</tbody>
</table></div>
<div class="legend">
  <span><i class="sw" style="background:var(--best-bg);box-shadow:inset 3px 0 0 var(--best)"></i> lowest in row</span>
  <span><i class="sw" style="background:rgba(168,68,42,.22)"></i> premium vs best (deeper = pricier)</span>
  <span><i class="sw" style="background:var(--panel);border:1px solid var(--line)"></i> not found</span>
</div>

<h2>Single-basket bundle totals</h2>
<div class="scroll"><table class="bundle">
<thead><tr><th class="corner">Buy everything at\u2026</th><th>Subtotal</th>
<th>Bundle saving</th><th>After discounts</th></tr></thead>
<tbody>{basket_rows}</tbody>
</table></div>

<div class="note">
<b>How to read this.</b> Each row compares the same specific variant across
retailers; the emerald cell is the cheapest and premiums show how much more
you'd pay. Bundle totals apply the discount rules in <b>models.yaml</b>
(currently {bosch_flat} off a qualifying order of {bosch_min}+ Bosch items,
plus any multibuy %). <b>Compare bundles at equal coverage only</b> \u2014 a
retailer that stocks fewer of your models will show a lower total simply
because it's missing items (see the per-row item count). Prices are a snapshot
from the run above; re-run <b>track</b> to refresh.
</div>
</div></body></html>
"""
