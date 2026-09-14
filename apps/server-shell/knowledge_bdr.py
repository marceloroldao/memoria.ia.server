"""BDR persistence adapter for Server Knowledge evidence.

The BDR/episodes API is the canonical durable journal. The local knowledge.json
remains a cache/index that can be rebuilt by replaying these evidence episodes.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from urllib.parse import quote
from urllib.request import Request, urlopen


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class KnowledgeBDR:
    EVENT_TYPE = "server_knowledge_evidence"
    SESSION_ID = "server:knowledge"

    def __init__(self, memoria_api_url: str, memoria_api_key: str = "", timeout: float = 10.0) -> None:
        self.base = memoria_api_url.rstrip("/")
        self.api_key = memoria_api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Memoria-Key"] = self.api_key
        return headers

    def append_evidence(self, evidence: dict[str, object]) -> str:
        canonical = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
        episode_id = f"knowledge:{digest}"
        payload = {
            "episode_id": episode_id,
            "role": "system",
            "text": canonical,
            "session_id": self.SESSION_ID,
            "order": int(datetime.now(timezone.utc).timestamp() * 1000),
            "timestamp": str(evidence.get("time") or _now()),
            "event_type": self.EVENT_TYPE,
            "topics": ["server-knowledge", "evidence", str(evidence.get("provider") or "web")],
        }
        request = Request(
            self.base + "/api/v1/episodes",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                response.read()
        except Exception as exc:
            # Duplicate episode ids are safe to ignore if the upstream rejects them.
            message = str(exc)
            if "409" not in message and "already" not in message.casefold() and "duplicate" not in message.casefold():
                raise
        return episode_id

    def load_evidence(self, limit: int = 5000) -> list[dict[str, object]]:
        url = self.base + "/api/v1/episodes/history?event_type=" + quote(self.EVENT_TYPE) + f"&limit={max(1, min(limit, 20000))}"
        request = Request(url, headers=self._headers(), method="GET")
        with urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("episodes") or payload.get("items") or payload.get("history") or []
        result = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            text = row.get("text") or row.get("content") or ""
            try:
                evidence = json.loads(text)
            except Exception:
                continue
            if isinstance(evidence, dict):
                result.append(evidence)
        return result
