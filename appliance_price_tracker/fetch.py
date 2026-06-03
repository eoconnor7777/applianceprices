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


class Renderer:
    """Reusable headless-browser session.

    Launch once, render many URLs, close once:

        with Renderer() as r:
            html = r.render(url)

    Reusing the browser/context/page across the whole run is the single
    biggest speed win versus launching Chromium per page.
    """

    def __init__(self, headless: bool = True, settle_ms: int = 800,
                 block_assets: bool = True):
        self.headless = headless
        self.settle_ms = settle_ms
        self.block_assets = block_assets
        self._pw = None
        self._browser = None
        self._ctx = None
        self._page = None

    def __enter__(self) -> "Renderer":
        sync_playwright = _require_playwright()
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._ctx = self._browser.new_context(user_agent=_DEF_UA, locale="en-IE")
        if self.block_assets:
            self._ctx.route("**/*", _block_heavy_assets)
        self._page = self._ctx.new_page()
        return self

    def render(self, url: str, timeout: float = 30.0) -> str:
        """Return fully rendered HTML for `url`."""
        page = self._page
        page.goto(url, timeout=int(timeout * 1000), wait_until="domcontentloaded")
        try:
            # Cap networkidle low: some sites poll forever and would otherwise
            # burn the full timeout on every page. domcontentloaded + a short
            # settle is enough for the price DOM/JSON-LD.
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        _dismiss_cookies(page)
        page.wait_for_timeout(self.settle_ms)
        return page.content()

    def __exit__(self, *exc) -> None:
        for closer in (self._ctx, self._browser):
            try:
                if closer is not None:
                    closer.close()
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
