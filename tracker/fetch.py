"""Polite page fetching.

Every request goes through the same rules, whichever engine loads the page:
  * robots.txt is checked first (wildcard-aware parser), and disallowed URLs are never requested;
  * a per-site delay is kept between requests (the robots.txt Crawl-delay wins if it is longer);
  * temporary failures (timeouts, 429, 5xx) are retried with exponential backoff and jitter;
  * if proxies are configured, requests rotate through them and a failing proxy is skipped.
"""
from __future__ import annotations

import itertools
import logging
import random
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import requests
from protego import Protego

from .config import settings

log = logging.getLogger("tracker.fetch")

RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504, 520, 522, 524}


class DisallowedByRobots(Exception):
    pass


class FetchError(Exception):
    pass


class BotChallenge(FetchError):
    """The site answered with a bot check. We stop crawling that site for this run."""


@dataclass
class HostStats:
    pages: int = 0
    retries: int = 0
    failures: int = 0
    blocked_by_robots: int = 0
    bytes: int = 0


@dataclass
class _HostState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    last_request: float = 0.0
    robots: Protego | None = None


class Politeness:
    """Shared robots.txt cache, per-host throttling and stats."""

    def __init__(self, user_agent: str | None = None):
        self.user_agent = user_agent or settings.user_agent
        self._hosts: dict[str, _HostState] = defaultdict(_HostState)
        self._hosts_lock = threading.Lock()
        self.stats: dict[str, HostStats] = defaultdict(HostStats)
        self.min_delay: dict[str, float] = {}

    def _host(self, url: str) -> tuple[str, _HostState]:
        host = urlsplit(url).netloc
        with self._hosts_lock:
            return host, self._hosts[host]

    def _robots(self, url: str, state: _HostState) -> Protego:
        if state.robots is None:
            parts = urlsplit(url)
            robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
            body = None
            for attempt in range(4):
                try:
                    r = requests.get(robots_url, headers={"User-Agent": self.user_agent}, timeout=30)
                    if r.status_code >= 500:
                        raise FetchError(f"robots.txt returned {r.status_code}")
                    # A missing robots.txt (4xx) means everything is allowed.
                    body = r.text if r.status_code == 200 else ""
                    break
                except (requests.RequestException, FetchError) as exc:
                    log.warning("robots.txt for %s: %s (try %d/4)", parts.netloc, exc, attempt + 1)
                    time.sleep(backoff_seconds(attempt))
            if body is None:
                # If we cannot read the rules, we do not crawl the site.
                log.error("cannot read %s; refusing to crawl this host this run", robots_url)
                body = "User-agent: *\nDisallow: /"
            state.robots = Protego.parse(body)
        return state.robots

    def check_and_wait(self, url: str) -> None:
        """Raise if robots.txt forbids the URL, else sleep until it is our turn."""
        host, state = self._host(url)
        with state.lock:
            robots = self._robots(url, state)
            if not robots.can_fetch(url, self.user_agent):
                self.stats[host].blocked_by_robots += 1
                raise DisallowedByRobots(url)
            delay = max(self.min_delay.get(host, 2.0), robots.crawl_delay(self.user_agent) or 0)
            wait = state.last_request + delay * random.uniform(1.0, 1.3) - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            state.last_request = time.monotonic()

    def set_min_delay(self, base_url: str, seconds: float) -> None:
        self.min_delay[urlsplit(base_url).netloc] = seconds


def backoff_seconds(attempt: int, retry_after: str | None = None) -> float:
    if retry_after and retry_after.isdigit():
        return min(float(retry_after), 120.0)
    return min(2 ** attempt, 60) + random.uniform(0, 1.5)


class HttpFetcher:
    """requests-based fetcher for server-rendered pages."""

    def __init__(self, politeness: Politeness):
        self.p = politeness
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": politeness.user_agent,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.6",
        })
        self._proxies = itertools.cycle(settings.proxies) if settings.proxies else None

    def _next_proxy(self) -> dict | None:
        if not self._proxies:
            return None
        proxy = next(self._proxies)
        return {"http": proxy, "https": proxy}

    def get(self, url: str) -> str:
        host = urlsplit(url).netloc

        def attempt_once() -> str:
            self.p.check_and_wait(url)
            try:
                r = self.session.get(url, timeout=settings.request_timeout_s, proxies=self._next_proxy())
            except requests.RequestException as exc:
                raise RetryableError(str(exc)) from exc
            if r.status_code in RETRY_STATUS:
                raise RetryableError(f"HTTP {r.status_code}", r.headers.get("Retry-After"))
            if r.status_code >= 400:
                raise FetchError(f"HTTP {r.status_code} for {url}")  # 403/404 will not fix themselves
            self.p.stats[host].bytes += len(r.content)
            return r.text

        return with_retries(self.p, url, attempt_once)


class RetryableError(Exception):
    def __init__(self, message: str, retry_after: str | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def with_retries(p: Politeness, url: str, fn):
    """Run fn() with exponential backoff on RetryableError. Records stats."""
    host = urlsplit(url).netloc
    for attempt in range(settings.max_retries + 1):
        try:
            result = fn()
            p.stats[host].pages += 1
            return result
        except RetryableError as exc:
            if attempt == settings.max_retries:
                p.stats[host].failures += 1
                raise FetchError(f"giving up on {url} after {attempt + 1} tries: {exc}") from exc
            p.stats[host].retries += 1
            pause = backoff_seconds(attempt, exc.retry_after)
            log.warning("%s failed (%s), retry %d/%d in %.1fs",
                        url, exc, attempt + 1, settings.max_retries, pause)
            time.sleep(pause)
        except FetchError:
            p.stats[host].failures += 1
            raise
