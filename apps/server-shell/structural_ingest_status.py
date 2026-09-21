"""Read-only observability for the bit.analyze raw structural ingest sidecar."""
from __future__ import annotations

from collections import deque
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
