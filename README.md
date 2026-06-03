# Appliance Price Tracker (Irish retailers)

A small, re-runnable tool that does in code what we did by hand: search each
retailer for a **specific model/variant**, extract the live price, match it to
the variant you actually want, record it, and analyse the cheapest source plus
single-basket bundle totals. Re-run it any time to track prices over the build.

## What it tracks
Configured in `models.yaml` — currently your seven appliances, with the
washer pinned to the black Series 6 **WGG244ZCGB**, the heat-pump dryer to
**WQG245R1GB**, and the fridge to the **Bosch KIN96VFD0** XXL fully integrated
60/40 (193cm, 290L). The matcher enforces the variant: a black *dishwasher* will not satisfy the black *washer* query,
and a Series 8 combi will not satisfy the single-oven query.

## Run without installing Python
Three options, no local Python required:

* **Ask Claude (zero install).** With Claude for Chrome connected, ask it to
  pull live prices for these models and build the board in-chat. Interactive,
  not scheduled.
* **GitHub Actions (cloud, recommended).** Upload this folder to a GitHub repo,
  set *Settings → Pages → Source: GitHub Actions*, then run the **Appliance
  prices** workflow (`.github/workflows/prices.yml`). It installs everything in
  the cloud, scrapes, commits history back, and publishes the board to your
  Pages URL (also attached as a downloadable artifact). Runs weekly by default.
* **Docker (one install).** Install Docker Desktop, then from this folder:
  `docker build -t prices .` and
  `docker run --rm -v "%cd%/data:/app/data" prices` (PowerShell: `${PWD}`).
  Open `data/report.html`.

## Install (local Python)
```bash
pip install -r requirements.txt
python -m playwright install chromium      # only needed for live scraping
```
`beautifulsoup4` + `PyYAML` are enough for `--mock`/tests; Playwright (and its
Chromium binary) is only needed for live runs, because the target sites render
prices with JavaScript.

## Use
```bash
# Offline demo against bundled fixtures (no network, proves the pipeline):
python -m appliance_price_tracker.cli --history data/hist.csv track --mock fixtures
python -m appliance_price_tracker.cli --history data/hist.csv analyze

# Live run (on a machine that can reach the Irish sites):
python -m appliance_price_tracker.cli track            # scrape + append history
python -m appliance_price_tracker.cli analyze          # cheapest source + bundles
python -m appliance_price_tracker.cli report --open    # build + open the HTML board
```
`track` appends a timestamped row per (retailer × model) to
`data/prices_history.csv`, so repeated runs build a price history.
`analyze` writes `data/report.md`. **`report`** writes `data/report.html` —
a single self-contained overview page: a side-by-side matrix of every model
across retailers with the cheapest cell highlighted in emerald and premiums
shown as `+€/%` (deeper red = pricier), summary stats, and per-retailer
single-basket bundle totals with your discounts applied and the winner
flagged. `--open` launches it in your browser.

### Replay on a schedule
```cron
0 8 * * *  cd /path/to/appliance-price-tracker && /usr/bin/python -m appliance_price_tracker.cli track
```

## How it works
1. **fetch** — Playwright renders the retailer's search page (headless Chromium,
   waits for network idle, best-effort cookie dismiss) and returns final HTML.
2. **extract** — `jsonld` (Schema.org Product/offers) or `text` (pair a
   brand-prefixed title with the next €price), chosen per retailer.
3. **match** — `must_include` is a hard variant filter (colour, integrated,
   category); `exclude` drops wrong categories; `model` number match scores
   highest; `prefer` tokens break ties. Lowest price among valid matches wins.
4. **store / analyze** — append to CSV; report best source + bundle maths.

## Tuning
* **Add a retailer**: add an entry under `retailers:` with a `search_url`
  containing `{query}` and a `strategy`. Run `track`, watch the
  "N candidates" counts; if 0, switch `strategy` between `jsonld`/`text`.
* **Pin a variant harder**: put the exact SKU in `model:` (most precise),
  and/or tighten `must_include` / `exclude`.
* **Bundle rules**: edit `discounts:` (flat Bosch-bundle € and multibuy %s)
  to match each retailer's stated terms.

## Caveats (please read)
* Check each retailer's **robots.txt / terms** before live scraping; keep the
  `--delay` polite. This is for personal price comparison, not redistribution.
* Sites get redesigned — if extraction returns nothing, the `search_url` or
  `strategy` likely needs a tweak. The `text` strategy is the resilient
  fallback when structured data disappears.
* Prices/promotions change constantly; treat a run as a snapshot. The history
  CSV is what makes trends meaningful.
* The washer, dryer and fridge SKUs are locked; the dishwasher, single oven
  and venting hob still match on name + attributes. Drop their exact SKUs into
  `models.yaml` (`model:`) when you choose them for the tightest matches.
```
