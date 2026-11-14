"""Playwright fetcher for pages that need a real browser (JavaScript checks, client rendering).

It follows the same robots.txt, delay and retry rules as the HTTP fetcher. It does not try
to hide that it is automated: if a site still refuses the browser, the run reports it.
"""
from __future__ import annotations

import logging
from urllib.parse import urlsplit

from .config import settings
from .fetch import BotChallenge, FetchError, Politeness, RetryableError, with_retries

log = logging.getLogger("tracker.browser")

CHALLENGE_TITLES = ("just a moment", "attention required", "un instant")


class BrowserFetcher:
    """Use as a context manager, from a single thread."""

    def __init__(self, politeness: Politeness, wait_selector: str | None = None):
        self.p = politeness
        self.wait_selector = wait_selector
        self._pw = self._browser = self._context = None

    def __enter__(self) -> "BrowserFetcher":
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        proxy = {"server": settings.proxies[0]} if settings.proxies else None
        self._browser = self._pw.chromium.launch(
            headless=True, proxy=proxy, channel=settings.browser_channel or None)
        self._context = self._browser.new_context(
            user_agent=self.p.user_agent, locale="fr-FR", viewport={"width": 1366, "height": 900}
        )
        # Images, fonts and media are not needed for prices: skip them to save bandwidth.
        self._context.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in {"image", "media", "font"}
            else route.continue_(),
        )
        return self

    def __exit__(self, *exc) -> None:
        for closer in (self._context, self._browser):
            try:
                closer and closer.close()
            except Exception:  # noqa: BLE001 - best effort cleanup
                pass
        if self._pw:
            self._pw.stop()

    def get(self, url: str) -> str:
        host = urlsplit(url).netloc

        def attempt_once() -> str:
            self.p.check_and_wait(url)
            page = self._context.new_page()
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=settings.request_timeout_s * 1000)
                if self.wait_selector:
                    try:
                        page.wait_for_selector(self.wait_selector, timeout=20_000)
                    except Exception:  # noqa: BLE001 - checked below
                        pass
                title = (page.title() or "").lower()
                if any(t in title for t in CHALLENGE_TITLES):
                    raise BotChallenge(f"{host} served a bot check page; stopping this site for today")
                if resp is not None and resp.status in (429, 500, 502, 503, 504):
                    raise RetryableError(f"HTTP {resp.status}")
                html = page.content()
                self.p.stats[host].bytes += len(html)
                return html
            except FetchError:
                raise
            except RetryableError:
                raise
            except Exception as exc:  # Playwright timeouts, navigation errors
                raise RetryableError(str(exc).splitlines()[0]) from exc
            finally:
                page.close()

        return with_retries(self.p, url, attempt_once)
