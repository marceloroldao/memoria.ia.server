"""Pluggable discovery providers for the curiosity engine."""
from __future__ import annotations

import json
from urllib.parse import quote_plus


class SearchProviderError(RuntimeError):
    pass


def wikipedia_results(topic: str, fetch_text, limit: int) -> list[tuple[str, str]]:
    """Use MediaWiki OpenSearch as a keyless fallback discovery source."""
    url = (
        "https://pt.wikipedia.org/w/api.php?action=opensearch"
        f"&search={quote_plus(topic)}&limit={max(1, min(limit, 10))}&namespace=0&format=json"
    )
    text, _ = fetch_text(url, 500_000, accept_json=True)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SearchProviderError("wikipedia returned invalid JSON") from exc
    if not isinstance(payload, list) or len(payload) < 4:
        raise SearchProviderError("wikipedia returned unexpected payload")
    titles = payload[1] if isinstance(payload[1], list) else []
    urls = payload[3] if isinstance(payload[3], list) else []
    return [
        (str(title), str(url))
        for title, url in zip(titles, urls)
        if str(title).strip() and str(url).startswith("http")
    ][:limit]
