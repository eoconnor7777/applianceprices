"""Render a search-results page with a real (headless) browser.

Prices on the target sites are JavaScript-rendered, so a plain HTTP GET is
not enough - we learned this the hard way. Playwright drives headless
Chromium, waits for the network to settle, optionally dismisses a cookie
banner, and returns the final HTML for the extractors to parse.

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


def render(url: str, timeout: float = 30.0, headless: bool = True,
           settle_ms: int = 1500) -> str:
    """Return fully rendered HTML for `url`. Raises if Playwright is missing."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "Playwright not installed. Run:\n"
            "  pip install playwright && python -m playwright install chromium\n"
            "or use --mock for offline testing."
        ) from exc

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        ctx = browser.new_context(user_agent=_DEF_UA, locale="en-IE")
        page = ctx.new_page()
        try:
            page.goto(url, timeout=int(timeout * 1000), wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=int(timeout * 1000))
            except Exception:
                pass
            _dismiss_cookies(page)
            page.wait_for_timeout(settle_ms)
            return page.content()
        finally:
            ctx.close()
            browser.close()


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
