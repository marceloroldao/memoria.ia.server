"""Canonical growth diagnostics for Curiosity -> Learning -> BDR -> Explorer.

The GET endpoint is read-only. POST performs an explicit synthetic BDR
persistence probe. No LLM is involved in either path.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import time
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

PREFIX = "/api/server/v1/growth-diagnostics"
SCHEMA = "memoria-growth-diagnostics/v2"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _ratio(numerator, denominator):
    if not denominator:
        return None
    return round(float(numerator) / float(denominator), 4)


class GrowthDiagnostics:
    def __init__(self, config, curiosity, knowledge, *, write_lock=None):
        self.config = config
        self.curiosity = curiosity
        self.knowledge = knowledge
        self.write_lock = write_lock
        self.path = Path(config.curiosity_data_dir).parent / "diagnostics" / "growth-report.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _json_get(self, url, headers=None, timeout=8):
        with urlopen(Request(url, headers=headers or {}, method="GET"), timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _episodes(self):
        headers = {"X-Memoria-Key": self.config.memoria_api_key} if self.config.memoria_api_key else {}
        payload = self._json_get(
            self.config.memoria_api_url + "/api/v1/episodes/history?limit=5000",
            headers,
        )
        rows = payload.get("episodes", []) if isinstance(payload, dict) else []
        return rows if isinstance(rows, list) else []

    def _explorer(self):
        payload = self._json_get(self.config.bdr_explorer_url + "/api/snapshot")
        return payload if isinstance(payload, dict) else {}

    def _event_stats(self):
        path = Path(self.config.curiosity_data_dir) / "events.jsonl"
        counts = {}
        total = 0
        evidence = 0
        if path.exists():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                kind = str(row.get("kind") or "unknown")
                counts[kind] = counts.get(kind, 0) + 1
                total += 1
                if kind == "evidence":
                    evidence += 1
        return {"total": total, "by_kind": counts, "evidence": evidence}

    @staticmethod
    def _curiosity_metrics(state):
        if not isinstance(state, dict):
            return {}
        # Keep the raw snapshot, but also expose a stable metrics projection for
        # support tooling even if Curiosity changes where counters are nested.
        candidates = [state]
        for key in ("metrics", "stats", "counters", "state"):
            value = state.get(key)
            if isinstance(value, dict):
                candidates.append(value)
        aliases = {
            "cycles": ("cycles", "ciclos"),
            "searches": ("searches", "buscas"),
            "pages": ("pages", "pages_read", "paginas"),
            "discoveries": ("discoveries", "novelties", "novidades"),
            "jumps": ("jumps", "saltos"),
            "errors": ("errors", "erros"),
        }
        projected = {}
        for target, names in aliases.items():
            for source in candidates:
                found = next((source[name] for name in names if name in source), None)
                if found is not None:
                    try:
                        projected[target] = int(found)
                    except (TypeError, ValueError):
                        projected[target] = found
                    break
        return projected

    def report(self):
        errors = []
        try:
            episodes = self._episodes()
        except Exception as exc:
            episodes = []
            errors.append("episodes: " + str(exc))
        try:
            explorer = self._explorer()
        except Exception as exc:
            explorer = {}
            errors.append("explorer: " + str(exc))

        event_stats = self._event_stats()
        state = self.curiosity.snapshot() if hasattr(self.curiosity, "snapshot") else {}
        if not isinstance(state, dict):
            state = {}
        knowledge = self.knowledge.recent(limit=1)
        if not isinstance(knowledge, dict):
            knowledge = {}

        event_types = {}
        for row in episodes:
            event_type = str(row.get("event_type") or "unknown")
            event_types[event_type] = event_types.get(event_type, 0) + 1

        stats = explorer.get("statistics", {}) if isinstance(explorer, dict) else {}
        if not isinstance(stats, dict):
            stats = {}
        explorer_records = int(stats.get("total_entidades", 0) or 0)
        persisted = len(episodes)
        evidence_events = event_stats["evidence"]
        learned = int(knowledge.get("observations", 0) or 0)
        concepts = int(knowledge.get("concepts", 0) or 0)
        knowledge_rows = int(event_types.get("server_knowledge_evidence", 0) or 0)

        persistence_rate = _ratio(knowledge_rows, learned)
        learning_rate = _ratio(learned, evidence_events)
        projection_rate = _ratio(explorer_records, persisted)
        curiosity_metrics = self._curiosity_metrics(state)

        diagnosis = []
        if errors:
            diagnosis.append("UPSTREAM_ERROR")
        if evidence_events == 0:
            diagnosis.append("CRAWLER_NOT_PRODUCING_EVIDENCE")
        if evidence_events > 0 and learned == 0:
            diagnosis.append("LEARNING_NOT_CONSUMING_EVIDENCE")
        if learned > 0 and knowledge_rows == 0:
            diagnosis.append("LEARNING_NOT_PERSISTING_TO_BDR")
        if persisted > explorer_records:
            diagnosis.append("EXPLORER_PROJECTION_TRUNCATED_OR_COLLIDING")
        if persisted == 256:
            diagnosis.append("SUSPECT_256_HISTORY_CAP")
        if not diagnosis:
            diagnosis = ["HEALTHY"]

        payload = {
            "schema": SCHEMA,
            "generated_at": _now(),
            "diagnosis": diagnosis,
            "metrics": {
                "bdr_history_rows": persisted,
                "bdr_knowledge_rows": knowledge_rows,
                "knowledge_observations": learned,
                "knowledge_concepts": concepts,
                "curiosity_events": event_stats["total"],
                "web_evidence": evidence_events,
                "explorer_records": explorer_records,
                "learning_rate": learning_rate,
                "persistence_rate": persistence_rate,
                "explorer_projection_rate": projection_rate,
                **curiosity_metrics,
            },
            "funnel": {
                "curiosity_events": event_stats["total"],
                "web_evidence": evidence_events,
                "knowledge_observations": learned,
                "knowledge_concepts": concepts,
                "bdr_history_rows": persisted,
                "bdr_knowledge_rows": knowledge_rows,
                "explorer_records": explorer_records,
            },
            "rates": {
                "evidence_to_learning": learning_rate,
                "learning_to_bdr": persistence_rate,
                "bdr_to_explorer": projection_rate,
            },
            "curiosity": state,
            "event_types": event_types,
            "event_kinds": event_stats["by_kind"],
            "explorer_statistics": stats,
            "errors": errors,
            "last_probe": self._load().get("last_probe"),
        }
        self._save(payload)
        return payload

    def probe(self):
        before = self.report()
        probe_id = "diagnostic:" + uuid.uuid4().hex
        payload = {
            "episode_id": probe_id,
            "role": "assistant",
            "text": "Synthetic growth diagnostic " + probe_id,
            "session_id": "server:growth-diagnostic",
            "order": int(time.time() * 1000),
            "timestamp": _now(),
            "event_type": "growth_diagnostic_probe",
            "topics": ["diagnostic", "growth"],
        }
        data = json.dumps(payload, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json"}
        if self.config.memoria_api_key:
            headers["X-Memoria-Key"] = self.config.memoria_api_key
        status = None
        detail = ""
        started = time.monotonic()
        try:
            lock = self.write_lock
            if lock:
                lock.acquire()
            try:
                with urlopen(
                    Request(self.config.memoria_api_url + "/api/v1/episodes", data=data, headers=headers, method="POST"),
                    timeout=15,
                ) as response:
                    status = response.status
                    detail = response.read().decode("utf-8", errors="replace")[:1000]
            finally:
                if lock:
                    lock.release()
        except HTTPError as exc:
            status = exc.code
            detail = exc.read().decode("utf-8", errors="replace")[:2000]
        except Exception as exc:
            detail = repr(exc)

        elapsed = round((time.monotonic() - started) * 1000, 1)
        time.sleep(0.15)
        try:
            rows = self._episodes()
            found = any(str(row.get("episode_id")) == probe_id for row in rows)
        except Exception:
            found = False
        after = self.report()
        probe = {
            "id": probe_id,
            "http_status": status,
            "stored_and_read_back": found,
            "latency_ms": elapsed,
            "response": detail,
            "before_rows": before["funnel"]["bdr_history_rows"],
            "after_rows": after["funnel"]["bdr_history_rows"],
            "passed": status in (200, 201) and found,
        }
        final = after
        final["last_probe"] = probe
        if not probe["passed"]:
            final["diagnosis"] = [x for x in final["diagnosis"] if x != "HEALTHY"] + ["BDR_SYNTHETIC_WRITE_FAILED"]
        self._save(final)
        return final

    def _load(self):
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, payload):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def dispatch(self, handler, path, query):
        if path != PREFIX:
            return False
        if handler.command == "GET":
            handler._write_json(200, self.report())
            return True
        if handler.command == "POST":
            handler._write_json(200, self.probe())
            return True
        handler._write_json(405, {"error": "method_not_allowed"}, {"Allow": "GET, POST"})
        return True
