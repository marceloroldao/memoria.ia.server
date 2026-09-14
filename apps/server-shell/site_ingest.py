"""Recursive same-site ingestion started from URLs sent in the admin chat.

Pages are fetched through CuriosityEngine so the same network protections, pacing,
limits and evidence journal are reused. External links are recorded but are not
traversed automatically; this prevents one pasted URL from turning into an
unbounded Internet crawl.
"""
from __future__ import annotations

from collections import deque
from html.parser import HTMLParser
import json
from threading import Lock, Thread
from urllib.parse import urldefrag, urljoin, urlparse

from curiosity_engine import PageHTML, _words

PREFIX = "/api/server/v1/site-ingest"


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(str(href))


class SiteIngestManager:
    def __init__(self, curiosity, *, max_pages: int = 200, max_depth: int = 5) -> None:
        self.curiosity = curiosity
        self.max_pages = max(1, max_pages)
        self.max_depth = max(0, max_depth)
        self._lock = Lock()
        self._jobs: dict[str, dict[str, object]] = {}

    @staticmethod
    def _clean_url(url: str) -> str:
        clean, _fragment = urldefrag(url.strip())
        return clean

    @staticmethod
    def _same_site(root_host: str, url: str) -> bool:
        host = (urlparse(url).hostname or "").casefold()
        return host == root_host or host.endswith("." + root_host)

    def start(self, url: str) -> dict[str, object]:
        url = self._clean_url(url)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("invalid public http(s) URL")
        job_id = f"site:{abs(hash(url)) & 0xffffffff:08x}"
        with self._lock:
            current = self._jobs.get(job_id)
            if current and current.get("status") == "running":
                return dict(current)
            self._jobs[job_id] = {
                "job_id": job_id,
                "url": url,
                "status": "running",
                "pages_read": 0,
                "pages_failed": 0,
                "internal_links_found": 0,
                "external_links_found": 0,
                "max_pages": self.max_pages,
                "max_depth": self.max_depth,
            }
        Thread(target=self._run, args=(job_id, url), daemon=True, name=f"site-ingest-{job_id[-8:]}").start()
        return self.status(job_id)

    def status(self, job_id: str) -> dict[str, object]:
        with self._lock:
            return dict(self._jobs.get(job_id) or {"job_id": job_id, "status": "not_found"})

    def _update(self, job_id: str, **fields) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(fields)

    def _page_from_html(self, url: str, html: str) -> dict[str, object]:
        parser = PageHTML()
        parser.feed(html)
        text = parser.text[:self.curiosity.config.curiosity_text_limit]
        counts: dict[str, int] = {}
        for word in _words(parser.title + " " + parser.description + " " + text):
            counts[word] = counts.get(word, 0) + 1
        terms = [word for word, count in sorted(counts.items(), key=lambda x: (-x[1], x[0])) if count >= 2][:12]
        self.curiosity.state.pages_read += 1
        return {
            "url": url,
            "domain": urlparse(url).netloc,
            "title": parser.title[:300],
            "description": parser.description[:1000],
            "excerpt": text[:1800],
            "terms": terms,
            "links_offered": 0,
        }

    def _run(self, job_id: str, root_url: str) -> None:
        root_host = (urlparse(root_url).hostname or "").casefold()
        queue = deque([(root_url, 0)])
        seen: set[str] = set()
        external_seen: set[str] = set()
        internal_found = 0
        pages_read = 0
        pages_failed = 0
        try:
            self.curiosity._event("site_ingest_started", "Leitura de site iniciada pelo chat.", url=root_url, job_id=job_id)
            while queue and pages_read < self.max_pages:
                url, depth = queue.popleft()
                url = self._clean_url(url)
                if not url or url in seen:
                    continue
                seen.add(url)
                try:
                    html, _ctype = self.curiosity._get(url)
                    page = self._page_from_html(url, html)
                    page.update({
                        "kind": "evidence",
                        "message": str(page.get("title") or url),
                        "topic": root_url,
                        "novelty": 1.0,
                        "epistemic_status": "site_ingest_observation",
                        "confidence": 0.25,
                        "provider": "chat_site_ingest",
                        "site_root": root_url,
                        "site_depth": depth,
                        "site_job_id": job_id,
                    })
                    self.curiosity._event(**page)
                    pages_read += 1

                    parser = LinkParser()
                    parser.feed(html)
                    for href in parser.links:
                        absolute = self._clean_url(urljoin(url, href))
                        parsed = urlparse(absolute)
                        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                            continue
                        if self._same_site(root_host, absolute):
                            internal_found += 1
                            if depth < self.max_depth and absolute not in seen:
                                queue.append((absolute, depth + 1))
                        elif absolute not in external_seen:
                            external_seen.add(absolute)
                    self._update(
                        job_id,
                        pages_read=pages_read,
                        pages_failed=pages_failed,
                        internal_links_found=internal_found,
                        external_links_found=len(external_seen),
                        queued=len(queue),
                        current_url=url,
                    )
                except Exception as exc:
                    pages_failed += 1
                    self.curiosity._event("site_ingest_page_error", str(exc), url=url, job_id=job_id, depth=depth)
                    self._update(job_id, pages_failed=pages_failed, current_url=url)

            status = "completed" if not queue else "limit_reached"
            self._update(
                job_id,
                status=status,
                pages_read=pages_read,
                pages_failed=pages_failed,
                internal_links_found=internal_found,
                external_links_found=len(external_seen),
                queued=len(queue),
            )
            self.curiosity._event(
                "site_ingest_completed",
                f"Leitura do site concluída: {pages_read} página(s), {internal_found} link(s) interno(s), {len(external_seen)} externo(s).",
                url=root_url,
                job_id=job_id,
                status=status,
                pages_read=pages_read,
                pages_failed=pages_failed,
                internal_links_found=internal_found,
                external_links_found=len(external_seen),
            )
        except Exception as exc:
            self._update(job_id, status="error", error=str(exc))
            self.curiosity._event("site_ingest_error", str(exc), url=root_url, job_id=job_id)

    def dispatch(self, handler, path: str, query: dict[str, list[str]]) -> bool:
        if path != PREFIX and not path.startswith(PREFIX + "/"):
            return False
        suffix = path[len(PREFIX):].strip("/")
        if handler.command == "POST" and suffix == "":
            body = handler._read_body()
            if body is None:
                return True
            try:
                payload = json.loads(body.decode("utf-8"))
                result = self.start(str(payload.get("url") or ""))
            except Exception as exc:
                handler._write_json(400, {"error": "invalid_site_ingest_request", "detail": str(exc)})
                return True
            handler._write_json(202, result)
            return True
        if handler.command == "GET" and suffix:
            handler._write_json(200, self.status(suffix))
            return True
        handler._write_json(405, {"error": "method_not_allowed"})
        return True
