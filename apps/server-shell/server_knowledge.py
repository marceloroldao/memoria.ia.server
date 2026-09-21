"""Persistent server knowledge learned from evidence without LLMs."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from threading import Lock

PREFIX = "/api/server/v1/knowledge"
TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ0-9_-]{4,}")
STOP = {
    "para","com","uma","umas","uns","dos","das","que","por","como","mais","menos","the","and","from",
    "this","that","www","http","https","sobre","entre","into","pela","pelo","ser","são","foi","sua","seu",
    "também","todas","todos","cada","onde","quando","muito","muita","muitos","muitas",
}
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokens(text: str) -> list[str]:
    return [t.casefold() for t in TOKEN_RE.findall(text or "") if t.casefold() not in STOP]


def _normalize_terms(terms: list[str]) -> list[str]:
    normalized = []
    for raw in terms:
        term = str(raw).casefold().strip(" _-")
        if len(term) < 4 or term in STOP:
            continue
        if term.isdigit() and len(term) != 4:
            continue
        normalized.append(term)
    return list(dict.fromkeys(normalized))


def _semantic_weight(term: str, provider: str) -> tuple[float, str]:
    # No provider- or vocabulary-specific semantic suppression is applied.
    # Repetition, source diversity and relations are learned from observations.
    (term, provider)
    return 1.0, "content"


@dataclass
class KnowledgeItem:
    key: str
    label: str
    observations: int = 0
    confidence: float = 0.0
    semantic_weight: float = 1.0
    semantic_class: str = "content"
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
                item.setdefault("semantic_weight", 1.0)
                item.setdefault("semantic_class", "content")
                self.items[key] = KnowledgeItem(**item)
        except Exception:
            self.items = {}
            self.observations = 0

    def reset(self) -> None:
        with self._lock:
            self.items = {}
            self.observations = 0
            self._save()

    def _save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        payload = {
            "schema": "memoria-server-knowledge/v3",
            "storage_role": "local_cache_rebuildable_from_bdr",
            "principle": "address_first_weight_later",
            "observations": self.observations,
            "items": {k: asdict(v) for k, v in self.items.items()},
        }
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def learn_from_evidence(self, evidence: dict[str, object], save: bool = True) -> dict[str, object]:
        title = str(evidence.get("title") or evidence.get("message") or "")
        description = str(evidence.get("description") or "")
        excerpt = str(evidence.get("excerpt") or "")
        provider = str(evidence.get("provider") or "web").casefold()
        url = str(evidence.get("url") or "")
        supplied = [str(x) for x in (evidence.get("terms") or []) if str(x).strip()]
        terms = _normalize_terms(supplied)
        if not terms:
            counts = Counter(_tokens(" ".join([title, description, excerpt])))
            terms = _normalize_terms([term for term, n in counts.most_common(24) if n >= 2])
        unique = terms[:12]
        if not unique:
            return {"learned": 0, "keys": [], "addressed": 0}
        now = str(evidence.get("time") or _now())
        with self._lock:
            self.observations += 1
            for term in unique:
                weight, semantic_class = _semantic_weight(term, provider)
                item = self.items.get(term)
                if item is None:
                    item = KnowledgeItem(
                        key=term,
                        label=term,
                        first_seen_at=now,
                        semantic_weight=weight,
                        semantic_class=semantic_class,
                    )
                    self.items[term] = item
                else:
                    item.semantic_weight = weight
                    item.semantic_class = semantic_class
                item.observations += 1
                item.last_seen_at = now
                item.providers[provider] = item.providers.get(provider, 0) + 1
                if url and all(src.get("url") != url for src in item.sources):
                    item.sources = ([{"url": url, "provider": provider, "title": title[:180]}] + item.sources)[:8]
                item.excerpt = (description or excerpt or title)[:700]
                diversity = len(item.providers)
                base_conf = min(0.95, 0.20 + 0.12 * min(item.observations, 5) + 0.05 * min(diversity, 3))
                item.confidence = round(base_conf, 3)
            for a in unique:
                ia = self.items[a]
                for b in unique:
                    if a != b:
                        ia.related[b] = ia.related.get(b, 0) + 1
                ia.related = dict(sorted(ia.related.items(), key=lambda kv: (-kv[1], kv[0]))[:24])
            if save:
                self._save()
        return {"learned": len(unique), "keys": unique, "addressed": len(unique)}

    def rebuild(self, evidence_rows: list[dict[str, object]]) -> dict[str, int]:
        with self._lock:
            self.items = {}
            self.observations = 0
        learned = 0
        for evidence in evidence_rows:
            learned += int(self.learn_from_evidence(evidence, save=False).get("learned") or 0)
        with self._lock:
            self._save()
            return {"observations": self.observations, "concepts": len(self.items), "learned": learned}

    def query(self, text: str, limit: int = 5) -> dict[str, object]:
        q = set(_tokens(text))
        with self._lock:
            scored = []
            for item in self.items.values():
                key_tokens = set(_tokens(item.label)) | {item.key}
                overlap = len(q & key_tokens)
                related_overlap = sum(1 for r in item.related if r in q)
                raw_score = overlap * 10 + related_overlap * 2 + min(item.observations, 5) + item.confidence
                score = raw_score * max(0.01, item.semantic_weight)
                if score > 0:
                    scored.append((score, item))
            scored.sort(key=lambda x: (-x[0], -x[1].confidence, -x[1].observations, x[1].label))
            hits = []
            for score, item in scored[:max(1, min(limit, 20))]:
                hits.append({
                    "key": item.key, "label": item.label, "score": round(score, 3),
                    "confidence": item.confidence, "observations": item.observations,
                    "semantic_weight": item.semantic_weight, "semantic_class": item.semantic_class,
                    "excerpt": item.excerpt, "providers": item.providers, "sources": item.sources[:3],
                    "related": list(item.related.items())[:8], "first_seen_at": item.first_seen_at,
                    "last_seen_at": item.last_seen_at,
                })
            return {"schema": "memoria-server-knowledge-query/v3", "query": text, "hits": hits, "count": len(hits)}

    def recent(self, limit: int = 20) -> dict[str, object]:
        with self._lock:
            items = sorted(self.items.values(), key=lambda x: x.last_seen_at, reverse=True)[:max(1, min(limit, 100))]
            return {
                "schema": "memoria-server-knowledge/v3", "storage": "bdr-canonical/cache",
                "principle": "address_first_weight_later",
                "observations": self.observations, "concepts": len(self.items), "items": [asdict(x) for x in items],
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
