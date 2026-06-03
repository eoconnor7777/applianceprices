"""Command line interface.

  python -m appliance_price_tracker.cli track     # scrape live + record
  python -m appliance_price_tracker.cli track --mock fixtures   # offline demo
  python -m appliance_price_tracker.cli analyze   # report from history
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from urllib.parse import quote_plus

from . import analyze as analyze_mod
from . import report_html
from .config import AppConfig, load_config
from .extract import extract_candidates
from .match import best_match
from .store import append_rows, load_rows


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _html_for(retailer, product, args) -> tuple[str | None, str, str]:
    """Return (html, query, status). Reads a fixture in --mock mode, else
    renders the live search page with Playwright."""
    query = product.query()
    if args.mock:
        path = os.path.join(args.mock, f"{retailer.key}.html")
        if not os.path.exists(path):
            return None, query, "no_fixture"
        with open(path, encoding="utf-8") as fh:
            return fh.read(), query, "ok"
    from .fetch import render, polite_sleep
    url = retailer.search_url.format(query=quote_plus(query))
    try:
        html = render(url, timeout=args.timeout)
        polite_sleep(args.delay)
        return html, query, "ok"
    except Exception as exc:                       # noqa: BLE001
        print(f"  ! {retailer.key}: render failed: {exc}", file=sys.stderr)
        return None, query, "error"


def cmd_track(cfg: AppConfig, args) -> None:
    run_id = _now_iso()
    brands = cfg.brands()
    rows: list[dict] = []
    for retailer in cfg.retailers:
        if not retailer.enabled:
            continue
        print(f"[{retailer.name}]")
        for product in cfg.products:
            html, query, fetch_status = _html_for(retailer, product, args)
            row = {
                "timestamp": _now_iso(), "run_id": run_id,
                "product_key": product.key, "product_name": product.name,
                "retailer": retailer.key, "query": query,
                "currency": cfg.currency,
            }
            if html is None:
                row["status"] = fetch_status
                rows.append(row)
                print(f"  - {product.key:<28} {fetch_status}")
                continue
            cands = extract_candidates(html, retailer.strategy, brands)
            cand, sc = best_match(product, cands, args.min_score)
            if cand:
                row.update(matched_title=cand.title, price=f"{cand.price:.2f}",
                           url=cand.url or "", in_stock=cand.in_stock,
                           score=f"{sc:.1f}", status="ok")
                print(f"  - {product.key:<28} €{cand.price:<9.2f} {cand.title[:48]}")
            else:
                row["status"] = "no_match"
                print(f"  - {product.key:<28} no_match ({len(cands)} candidates)")
            rows.append(row)
    append_rows(args.history, rows)
    print(f"\nRecorded {len(rows)} rows -> {args.history}")


def cmd_analyze(cfg: AppConfig, args) -> None:
    rows = load_rows(args.history)
    if not rows:
        print("No history yet. Run `track` first (or `track --mock fixtures`).")
        return
    report = analyze_mod.render_report(cfg, rows)
    with open(args.report, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(report)
    print(f"\nReport written -> {args.report}")


def cmd_report(cfg: AppConfig, args) -> None:
    rows = load_rows(args.history)
    if not rows:
        print("No history yet. Run `track` first (or `track --mock fixtures`).")
        return
    htmldoc = report_html.build_html(cfg, rows)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(htmldoc)
    print(f"Overview page written -> {args.out}")
    if args.open:
        import webbrowser
        webbrowser.open("file://" + os.path.abspath(args.out))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="appliance-price-tracker")
    p.add_argument("--config", default="models.yaml")
    p.add_argument("--history", default="data/prices_history.csv")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("track", help="scrape retailers and append to history")
    t.add_argument("--mock", metavar="DIR",
                   help="read fixtures/<retailer>.html instead of live scraping")
    t.add_argument("--delay", type=float, default=2.0,
                   help="seconds between live requests (be polite)")
    t.add_argument("--timeout", type=float, default=30.0)
    t.add_argument("--min-score", type=float, default=2.0, dest="min_score")
    t.set_defaults(func=cmd_track)

    a = sub.add_parser("analyze", help="report cheapest sources + bundles")
    a.add_argument("--report", default="data/report.md")
    a.set_defaults(func=cmd_analyze)

    r = sub.add_parser("report", help="build the HTML overview price board")
    r.add_argument("--out", default="data/report.html")
    r.add_argument("--open", action="store_true", help="open in browser when done")
    r.set_defaults(func=cmd_report)
    return p


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    cfg = load_config(args.config)
    args.func(cfg, args)


if __name__ == "__main__":
    main()
