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
WIKI_UI_NOISE = {
    "editar","edição","página","páginas","wikipédia","enciclopédia","código","barra","barras","criar","busca",
    "mensagem","imagem","imagens","informação","internacional","displaystyle","isbn","esboço","categoria","portal",
    "discussão","referências","ligações","externas","navegação","conteúdo","artigo","artigos",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokens(text: str) -> list[str]:
    return [t.casefold() for t in TOKEN_RE.findall(text or "") if t.casefold() not in STOP]


def _clean_terms(terms: list[str], provider: str) -> list[str]:
    cleaned = []
    for raw in terms:
        term = str(raw).casefold().strip(" _-")
        if len(term) < 4 or term in STOP:
            continue
        if provider == "wikipedia" and term in WIKI_UI_NOISE:
            continue
        if term.isdigit() and len(term) != 4:
            continue
        cleaned.append(term)
    return list(dict.fromkeys(cleaned))


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

    def reset(self) -> None:
        with self._lock:
            self.items = {}
            self.observations = 0
            self._save()

    def _save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        payload = {
            "schema": "memoria-server-knowledge/v2",
            "storage_role": "local_cache_rebuildable_from_bdr",
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
        terms = _clean_terms(supplied, provider)
        if not terms:
            counts = Counter(_tokens(" ".join([title, description, excerpt])))
            terms = _clean_terms([term for term, n in counts.most_common(24) if n >= 2], provider)
        unique = terms[:12]
        if not unique:
            return {"learned": 0, "keys": [], "filtered": len(supplied)}
        now = str(evidence.get("time") or _now())
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
                diversity = len(item.providers)
                item.confidence = round(min(0.95, 0.20 + 0.12 * min(item.observations, 5) + 0.05 * min(diversity, 3)), 3)
            for a in unique:
                ia = self.items[a]
                for b in unique:
                    if a != b:
                        ia.related[b] = ia.related.get(b, 0) + 1
                ia.related = dict(sorted(ia.related.items(), key=lambda kv: (-kv[1], kv[0]))[:24])
            if save:
                self._save()
        return {"learned": len(unique), "keys": unique, "filtered": max(0, len(supplied) - len(unique))}

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
                score = overlap * 10 + related_overlap * 2 + min(item.observations, 5) + item.confidence
                if score > 0:
                    scored.append((score, item))
            scored.sort(key=lambda x: (-x[0], -x[1].confidence, -x[1].observations, x[1].label))
            hits = []
            for score, item in scored[:max(1, min(limit, 20))]:
                hits.append({
                    "key": item.key, "label": item.label, "score": round(score, 3),
                    "confidence": item.confidence, "observations": item.observations,
                    "excerpt": item.excerpt, "providers": item.providers, "sources": item.sources[:3],
                    "related": list(item.related.items())[:8], "first_seen_at": item.first_seen_at,
                    "last_seen_at": item.last_seen_at,
                })
            return {"schema": "memoria-server-knowledge-query/v2", "query": text, "hits": hits, "count": len(hits)}

    def recent(self, limit: int = 20) -> dict[str, object]:
        with self._lock:
            items = sorted(self.items.values(), key=lambda x: x.last_seen_at, reverse=True)[:max(1, min(limit, 100))]
            return {
                "schema": "memoria-server-knowledge/v2", "storage": "bdr+journal/cache",
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
