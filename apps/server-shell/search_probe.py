from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlsplit


class SearchProbe(HTMLParser):
    """Permissive parser for non-JavaScript search result pages."""

    RESULT_CLASS_HINTS = {"result__a", "result-link", "result-link__a", "result-title-a"}

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href = ""
        self._capture = False
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        a = dict(attrs)
        href = a.get("href", "")
        classes = set(a.get("class", "").split())
        if classes & self.RESULT_CLASS_HINTS or "uddg=" in href:
            self._href = href
            self._capture = True
            self._text = []

    def handle_data(self, data):
        if self._capture:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() != "a" or not self._capture:
            return
        href = self._href
        if "uddg=" in href:
            try:
                href = unquote((parse_qs(urlsplit(href).query).get("uddg") or [href])[0])
            except Exception:
                pass
        title = " ".join("".join(self._text).split())
        if href.startswith("http") and title:
            self.links.append((title, href))
        self._capture = False
