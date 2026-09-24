"""Read-only observability for the bit.analyze raw structural ingest sidecar."""
from __future__ import annotations

from collections import deque
from math import log1p
import json
import os
from pathlib import Path


SCHEMA = "memoria-bit-analyze-status/v1"


def _safe_child(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute():
        raise ValueError("checkpoint path must be relative")
    base = root.resolve()
    candidate = (base / rel).resolve()
    if Path(os.path.commonpath([str(base), str(candidate)])) != base:
        raise ValueError("checkpoint path escapes state directory")
    return candidate


class StructuralIngestStatus:
    def __init__(self, state_dir: str | Path) -> None:
        self.state_dir = Path(state_dir)
        self.checkpoint_dir = self.state_dir / "checkpoints"

    @staticmethod
    def _read_json(path: Path) -> dict[str, object] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None
        except Exception:
            return None

    def _recent_events(self, checkpoint: dict[str, object], limit: int) -> list[dict[str, object]]:
        if limit <= 0:
            return []
        relative = str(checkpoint.get("events_file") or "")
        if not relative:
            return []
        path = _safe_child(self.checkpoint_dir, relative)
        if not path.is_file():
            return []
        lines: deque[str] = deque(maxlen=max(1, min(limit, 100)))
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    lines.append(line)
        result = []
        for line in lines:
            try:
                event = json.loads(line)
            except Exception:
                continue
            if not isinstance(event, dict):
                continue
            trail = event.get("trail") if isinstance(event.get("trail"), list) else []
            relations = event.get("relation_ids") if isinstance(event.get("relation_ids"), list) else []
            result.append({
                "source_id": event.get("source_id"),
                "sequence": event.get("sequence"),
                "byte_offset": event.get("byte_offset"),
                "byte_length": event.get("byte_length"),
                "signature": event.get("signature"),
                "resolution": event.get("resolution"),
                "trail_symbols": len(trail),
                "relation_ids": len(relations),
            })
        return result

    def source_novelty(self, source_id: str, *, history_checkpoints: int = 32) -> dict[str, object]:
        """Measure structural novelty for one captured source from bit.analyze IDs.

        Novelty is evidence from relation/signature recurrence, not a semantic
        judgement. The newest checkpoint containing source_id is the target;
        older checkpoints in the same hierarchy provide the comparison field.
        """
        source_id = str(source_id or "").strip()
        if not source_id:
            raise ValueError("source_id is required")
        current = self._read_json(self.checkpoint_dir / "current.json")
        if current is None:
            return {"status": "pending", "source_id": source_id, "basis": "bit_analyze_structural_ids"}

        chain: list[dict[str, object]] = []
        checkpoint = current
        seen: set[str] = set()
        while checkpoint is not None and len(chain) < max(2, int(history_checkpoints)):
            name = str(checkpoint.get("checkpoint_file") or "")
            if name and name in seen:
                break
            if name:
                seen.add(name)
            chain.append(checkpoint)
            previous = str(checkpoint.get("previous_checkpoint_file") or "")
            if not previous:
                break
            path = _safe_child(self.checkpoint_dir, previous)
            checkpoint = self._read_json(path)

        def events(cp: dict[str, object]) -> list[dict[str, object]]:
            relative = str(cp.get("events_file") or "")
            if not relative:
                return []
            path = _safe_child(self.checkpoint_dir, relative)
            if not path.is_file():
                return []
            rows = []
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
            return rows

        target_index = None
        target_events: list[dict[str, object]] = []
        for index, cp in enumerate(chain):
            matched = [row for row in events(cp) if str(row.get("source_id") or "") == source_id]
            if matched:
                target_index = index
                target_events = matched
                break
        if target_index is None:
            return {"status": "pending", "source_id": source_id, "basis": "bit_analyze_structural_ids"}

        target_relations = {
            int(value)
            for row in target_events
            for value in (row.get("relation_ids") if isinstance(row.get("relation_ids"), list) else [])
        }
        target_signatures = {
            str(row.get("signature"))
            for row in target_events
            if str(row.get("signature") or "")
        }
        historical_relations: set[int] = set()
        historical_signatures: set[str] = set()
        for cp in chain[target_index + 1:]:
            for row in events(cp):
                historical_relations.update(
                    int(value)
                    for value in (row.get("relation_ids") if isinstance(row.get("relation_ids"), list) else [])
                )
                signature = str(row.get("signature") or "")
                if signature:
                    historical_signatures.add(signature)

        relation_overlap = len(target_relations & historical_relations)
        signature_overlap = len(target_signatures & historical_signatures)
        relation_novelty = (
            1.0 if not target_relations
            else 1.0 - relation_overlap / len(target_relations)
        )
        signature_novelty = (
            1.0 if not target_signatures
            else 1.0 - signature_overlap / len(target_signatures)
        )
        # Relations are learned reusable structure; window signatures preserve
        # evidence when a page has not yet produced higher-order relations.
        relation_weight = log1p(len(target_relations))
        signature_weight = log1p(len(target_signatures))
        total_weight = relation_weight + signature_weight
        novelty = (
            1.0 if total_weight == 0.0
            else (relation_novelty * relation_weight + signature_novelty * signature_weight) / total_weight
        )
        return {
            "status": "ready",
            "source_id": source_id,
            "basis": "bit_analyze_structural_ids",
            "novelty": round(novelty, 6),
            "event_count": len(target_events),
            "relation_ids": len(target_relations),
            "relation_ids_seen_before": relation_overlap,
            "signatures": len(target_signatures),
            "signatures_seen_before": signature_overlap,
            "history_checkpoints": max(0, len(chain) - target_index - 1),
            "hierarchy_id": chain[target_index].get("hierarchy_id"),
            "checkpoint_file": chain[target_index].get("checkpoint_file"),
        }

    def snapshot(self, limit: int = 10) -> dict[str, object]:
        worker = self._read_json(self.state_dir / "worker-status.json")
        checkpoint = self._read_json(self.checkpoint_dir / "current.json")
        status = str((worker or {}).get("status") or "waiting")
        response: dict[str, object] = {
            "schema": SCHEMA,
            "status": status,
            "available": self.state_dir.exists(),
            "worker": worker,
            "checkpoint": checkpoint,
            "recent_events": [],
        }
        if checkpoint is None:
            return response
        try:
            response["recent_events"] = self._recent_events(checkpoint, limit)
        except ValueError as exc:
            response["status"] = "degraded"
            response["checkpoint_error"] = str(exc)
        return response
