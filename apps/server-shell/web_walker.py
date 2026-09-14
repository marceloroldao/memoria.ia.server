"""Bounded public-web random walker for the curiosity engine.

The walker does not bypass CAPTCHAs or anti-bot controls. It follows ordinary
public HTTP links, applies domain cooldowns, and keeps a small frontier so the
curiosity engine can continue exploring when search providers return nothing.
"""
from __future__ import annotations

from collections import deque
from html.parser import HTMLParser
import random
import time
from urllib.parse import urljoin, urlparse


DEFAULT_SEEDS = [
    "https://pt.wikipedia.org/wiki/Especial:Aleat%C3%B3ria",
    "https://www.nasa.gov/",
    "https://www.mit.edu/",
    "https://arxiv.org/",
    "https://www.python.org/",
]


class LinkCollector(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: list[tuple[str, str]] = []
        self._href = ""
        self._capture = False
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href", "")
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            return
        url = urljoin(self.base_url, href)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return
        self._href = url
        self._capture = True
        self._text = []

    def handle_data(self, data):
        if self._capture:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() != "a" or not self._capture:
            return
        title = " ".join("".join(self._text).split()) or urlparse(self._href).netloc
        self.links.append((title[:200], self._href))
        self._capture = False


class WebWalker:
    def __init__(self, rng: random.Random, seeds: list[str] | None = None, *, domain_cooldown_seconds: float = 120.0) -> None:
        self.rng = rng
        self.seeds = list(seeds or DEFAULT_SEEDS)
        self.frontier: deque[tuple[str, str]] = deque(maxlen=250)
        self.seen: set[str] = set()
        self.domain_last_visit: dict[str, float] = {}
        self.domain_cooldown_seconds = domain_cooldown_seconds

    def offer(self, title: str, url: str) -> None:
        if url in self.seen:
            return
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return
        self.frontier.append((title[:200] or parsed.netloc, url))

    def offer_page_links(self, page_url: str, html: str, *, max_links: int = 20) -> int:
        parser = LinkCollector(page_url)
        parser.feed(html)
        candidates = []
        local_seen = set()
        for title, url in parser.links:
            if url in local_seen or url in self.seen:
                continue
            local_seen.add(url)
            candidates.append((title, url))
        self.rng.shuffle(candidates)
        for title, url in candidates[:max_links]:
            self.offer(title, url)
        return min(len(candidates), max_links)

    def _domain_ready(self, url: str) -> bool:
        domain = urlparse(url).netloc.casefold()
        last = self.domain_last_visit.get(domain, 0.0)
        return (time.monotonic() - last) >= self.domain_cooldown_seconds

    def next_candidates(self, limit: int = 3) -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        attempts = 0
        while self.frontier and len(results) < limit and attempts < len(self.frontier) + 10:
            attempts += 1
            title, url = self.frontier.popleft()
            if url in self.seen:
                continue
            if not self._domain_ready(url):
                self.frontier.append((title, url))
                continue
            self.seen.add(url)
            domain = urlparse(url).netloc.casefold()
            self.domain_last_visit[domain] = time.monotonic()
            results.append((title, url))
        if results:
            return results

        seeds = list(self.seeds)
        self.rng.shuffle(seeds)
        for url in seeds:
            if len(results) >= limit:
                break
            if not self._domain_ready(url):
                continue
            domain = urlparse(url).netloc.casefold()
            self.domain_last_visit[domain] = time.monotonic()
            results.append((f"exploração aleatória · {domain}", url))
        return results
