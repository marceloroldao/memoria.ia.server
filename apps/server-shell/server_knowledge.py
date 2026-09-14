"""Persistent server knowledge learned from curiosity evidence without LLMs."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from threading import Lock

PREFIX = "/api/server/v1/knowledge"
TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ0-9_-]{3,}")
STOP = {
    "para","com","uma","umas","uns","dos","das","que","por","como","mais","menos","the","and","from",
    "this","that","www","http","https","sobre","entre","into","pela","pelo","ser","são","foi","sua","seu",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokens(text: str) -> list[str]:
    return [t.casefold() for t in TOKEN_RE.findall(text or "") if t.casefold() not in STOP]


@dataclass
class KnowledgeItem:
    key: str
    label: str
    observations: int = 0
    confidence: float = 0.0
    providers: dict[str, int] = field(default_factory=dict)
    sources: list[dict[str, str]] = field(default_factory=list)
    related: dict[str, int] = field(default_factory=dict)
    first_seen_at: str = ""
    last_seen_at: str = ""
    excerpt: str = ""


class ServerKnowledge:
    def __init__(self, data_dir: str) -> None:
        self.dir = Path(data_dir)
        self.path = self.dir / "knowledge.json"
        self._lock = Lock()
        self.items: dict[str, KnowledgeItem] = {}
        self.observations = 0
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.observations = int(raw.get("observations", 0))
            for key, item in raw.get("items", {}).items():
                self.items[key] = KnowledgeItem(**item)
        except Exception:
            self.items = {}
            self.observations = 0

    def _save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        payload = {
            "schema": "memoria-server-knowledge/v1",
            "observations": self.observations,
            "items": {k: asdict(v) for k, v in self.items.items()},
        }
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def learn_from_evidence(self, evidence: dict[str, object]) -> dict[str, object]:
        title = str(evidence.get("title") or evidence.get("message") or "")
        description = str(evidence.get("description") or "")
        excerpt = str(evidence.get("excerpt") or "")
        provider = str(evidence.get("provider") or "web")
        url = str(evidence.get("url") or "")
        terms = [str(x).casefold() for x in (evidence.get("terms") or []) if str(x).strip()]
        if not terms:
            counts = Counter(_tokens(" ".join([title, description, excerpt])))
            terms = [term for term, n in counts.most_common(12) if n >= 2]
        unique = list(dict.fromkeys(terms))[:12]
        if not unique:
            return {"learned": 0, "keys": []}
        now = _now()
        with self._lock:
            self.observations += 1
            for term in unique:
                item = self.items.get(term)
                if item is None:
                    item = KnowledgeItem(key=term, label=term, first_seen_at=now)
                    self.items[term] = item
                item.observations += 1
                item.last_seen_at = now
                item.providers[provider] = item.providers.get(provider, 0) + 1
                if url and all(src.get("url") != url for src in item.sources):
                    item.sources = ([{"url": url, "provider": provider, "title": title[:180]}] + item.sources)[:8]
                item.excerpt = (description or excerpt or title)[:700]
                # Confidence grows with repeated observations and provider diversity, but never becomes certainty.
                diversity = len(item.providers)
                item.confidence = round(min(0.95, 0.20 + 0.12 * min(item.observations, 5) + 0.05 * min(diversity, 3)), 3)
            for a in unique:
                ia = self.items[a]
                for b in unique:
                    if a == b:
                        continue
                    ia.related[b] = ia.related.get(b, 0) + 1
                ia.related = dict(sorted(ia.related.items(), key=lambda kv: (-kv[1], kv[0]))[:24])
            self._save()
        return {"learned": len(unique), "keys": unique}

    def query(self, text: str, limit: int = 5) -> dict[str, object]:
        q = set(_tokens(text))
        with self._lock:
            scored = []
            for item in self.items.values():
                key_tokens = set(_tokens(item.label)) | {item.key}
                overlap = len(q & key_tokens)
                related_overlap = sum(1 for r in item.related if r in q)
                score = overlap * 10 + related_overlap * 2 + min(item.observations, 5) + item.confidence
                if score > 0:
                    scored.append((score, item))
            scored.sort(key=lambda x: (-x[0], -x[1].confidence, -x[1].observations, x[1].label))
            hits = []
            for score, item in scored[:max(1, min(limit, 20))]:
                hits.append({
                    "key": item.key,
                    "label": item.label,
                    "score": round(score, 3),
                    "confidence": item.confidence,
                    "observations": item.observations,
                    "excerpt": item.excerpt,
                    "providers": item.providers,
                    "sources": item.sources[:3],
                    "related": list(item.related.items())[:8],
                    "first_seen_at": item.first_seen_at,
                    "last_seen_at": item.last_seen_at,
                })
            return {"schema": "memoria-server-knowledge-query/v1", "query": text, "hits": hits, "count": len(hits)}

    def recent(self, limit: int = 20) -> dict[str, object]:
        with self._lock:
            items = sorted(self.items.values(), key=lambda x: x.last_seen_at, reverse=True)[:max(1, min(limit, 100))]
            return {
                "schema": "memoria-server-knowledge/v1",
                "observations": self.observations,
                "concepts": len(self.items),
                "items": [asdict(x) for x in items],
            }

    def dispatch(self, handler, path: str, query: dict[str, list[str]]) -> bool:
        if path != PREFIX and not path.startswith(PREFIX + "/"):
            return False
        suffix = path[len(PREFIX):].strip("/")
        if handler.command != "GET":
            handler._write_json(405, {"error": "method_not_allowed"}); return True
        if suffix == "query":
            text = (query.get("q") or [""])[0]
            handler._write_json(200, self.query(text)); return True
        if suffix in {"", "recent"}:
            handler._write_json(200, self.recent()); return True
        handler._write_json(404, {"error": "knowledge_route_not_found"}); return True
