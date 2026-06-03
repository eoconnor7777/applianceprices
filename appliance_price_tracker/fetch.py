"""Render a search-results page with a real (headless) browser.

Prices on the target sites are JavaScript-rendered, so a plain HTTP GET is
not enough - we learned this the hard way. Playwright drives headless
Chromium, waits for the network to settle, optionally dismisses a cookie
banner, and returns the final HTML for the extractors to parse.

Performance: launching Chromium is expensive (a couple of seconds each), so a
run that scrapes every retailer x product would waste a minute-plus just
starting browsers if it launched one per page. `Renderer` launches a single
browser/context for the whole run, reuses one page across navigations, and
blocks images/fonts/media (we only need the DOM text + JSON-LD, never the
pixels). The module-level `render()` wrapper is kept for one-off / backward-
compatible callers.

Import is lazy so that --mock and the unit tests run without Playwright (or
its browser binaries) installed.
"""
from __future__ import annotations

import time

_DEF_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Best-effort selectors for "reject/accept" on common Irish/EU cookie walls.
_COOKIE_SELECTORS = [
    "text=Reject all", "text=Decline", "text=Only essential",
    "#onetrust-reject-all-handler", "text=Allow cookies", "text=Accept",
]

# Asset types we never need - skipping them shaves a lot off each page load.
_BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}


def _require_playwright():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "Playwright not installed. Run:\n"
            "  pip install playwright && python -m playwright install chromium\n"
            "or use --mock for offline testing."
        ) from exc


# Hide the headless tell-tales (navigator.webdriver etc.) that WAFs like
# Incapsula key off. Applied as an init script to every context.
_STEALTH_JS = (
    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
    "window.chrome={runtime:{}};"
    "Object.defineProperty(navigator,'languages',{get:()=>['en-IE','en']});"
    "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});"
)
_LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]


class Renderer:
    """Headless-browser session with a per-retailer speed/stealth trade-off.

    Launching Chromium is the dominant cost (~2s each), so by default the
    browser is launched ONCE and each `render()` spins up a fresh, isolated
    context+page on it (cheap, and avoids cross-request cookie bleed).

    Some retailers (Currys, DID) sit behind bot protection that fingerprints
    the long-lived browser and starts returning empty results after the first
    hit from a datacenter IP. For those, pass `fresh_browser=True` to get a
    brand-new browser process per page - this mirrors the original (slow but
    high-coverage) behaviour and is the only thing that reliably gets results.

    `warmup_url` first navigates to a homepage in the SAME context so a JS
    challenge (e.g. Incapsula's incap_ses cookie) can solve before the search.
    """

    def __init__(self, headless: bool = True, settle_ms: int = 800,
                 block_assets: bool = True):
        self.headless = headless
        self.settle_ms = settle_ms
        self.block_assets = block_assets
        self._pw = None
        self._browser = None

    def _launch(self):
        return self._pw.chromium.launch(headless=self.headless, args=_LAUNCH_ARGS)

    def __enter__(self) -> "Renderer":
        sync_playwright = _require_playwright()
        self._pw = sync_playwright().start()
        self._browser = self._launch()
        return self

    def render(self, url: str, timeout: float = 30.0,
               fresh_browser: bool = False, warmup_url: str = "") -> str:
        """Return fully rendered HTML for `url` from a fresh, isolated context.

        `fresh_browser` launches a throwaway browser process for this one page
        (for bot-protected sites). `warmup_url` is visited first in the same
        context to let a JS bot-challenge solve.
        """
        browser = self._launch() if fresh_browser else self._browser
        try:
            ctx = browser.new_context(user_agent=_DEF_UA, locale="en-IE",
                                      viewport={"width": 1366, "height": 900})
            ctx.add_init_script(_STEALTH_JS)
            if self.block_assets:
                ctx.route("**/*", _block_heavy_assets)
            page = ctx.new_page()
            try:
                if warmup_url:
                    try:
                        page.goto(warmup_url, timeout=int(timeout * 1000),
                                  wait_until="domcontentloaded")
                        page.wait_for_timeout(3500)   # let the JS challenge solve
                    except Exception:
                        pass
                page.goto(url, timeout=int(timeout * 1000),
                          wait_until="domcontentloaded")
                try:
                    # Cap networkidle low: some sites poll forever and would
                    # otherwise burn the full timeout on every page.
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                _dismiss_cookies(page)
                page.wait_for_timeout(self.settle_ms)
                return page.content()
            finally:
                try:
                    ctx.close()
                except Exception:
                    pass
        finally:
            if fresh_browser:
                try:
                    browser.close()
                except Exception:
                    pass

    def __exit__(self, *exc) -> None:
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception:
            pass
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass


def render(url: str, timeout: float = 30.0, headless: bool = True,
           settle_ms: int = 800) -> str:
    """Render a single URL with a throwaway browser. Prefer `Renderer` for
    multi-URL runs; this stays for one-off callers and backward compatibility.
    """
    with Renderer(headless=headless, settle_ms=settle_ms) as r:
        return r.render(url, timeout=timeout)


def _block_heavy_assets(route) -> None:
    try:
        if route.request.resource_type in _BLOCKED_RESOURCE_TYPES:
            route.abort()
        else:
            route.continue_()
    except Exception:
        try:
            route.continue_()
        except Exception:
            pass


def _dismiss_cookies(page) -> None:
    for sel in _COOKIE_SELECTORS:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=600):
                loc.click(timeout=600)
                return
        except Exception:
            continue


def polite_sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)
