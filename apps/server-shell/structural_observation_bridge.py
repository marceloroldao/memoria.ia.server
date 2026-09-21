"""Reliable bridge from bit.analyze checkpoints into Memoria.ia raw structural intake."""
from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Event, Lock, Thread
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SCHEMA = "memoria-structural-observation-bridge/v1"


def _safe_child(root: Path, relative: str, *, field: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute():
        raise ValueError(f"{field} must be relative")
    base = root.resolve()
    candidate = (base / rel).resolve()
    if Path(os.path.commonpath([str(base), str(candidate)])) != base:
        raise ValueError(f"{field} escapes checkpoint directory")
    return candidate


class StructuralObservationBridge:
    """Deliver immutable bit.analyze event batches to Memoria.ia exactly-once logically.

    Transport retries may resend events after a crash or network failure. The
    Memoria.ia structural intake is content-addressed and idempotent, while this
    bridge advances its local checkpoint cursor only after an entire immutable
    checkpoint batch has been accepted.
    """

    def __init__(
        self,
        bit_analyze_state_dir: str | Path,
        data_dir: str | Path,
        memoria_api_url: str,
        memoria_api_key: str,
        *,
        interval_seconds: float = 5.0,
        timeout_seconds: float = 10.0,
        sender: Callable[[dict[str, object]], dict[str, object]] | None = None,
    ) -> None:
        self.state_dir = Path(bit_analyze_state_dir)
        self.checkpoint_dir = self.state_dir / "checkpoints"
        self.data_dir = Path(data_dir) / "structural-bridge"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cursor_path = self.data_dir / "cursor.json"
        self.memoria_api_url = memoria_api_url.rstrip("/")
        self.memoria_api_key = memoria_api_key
        self.interval_seconds = max(1.0, float(interval_seconds))
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.sender = sender or self._post
        self._stop = Event()
        self._thread: Thread | None = None
        self._lock = Lock()
        self._status: dict[str, object] = {
            "schema": SCHEMA,
            "status": "waiting",
            "delivered_checkpoints": 0,
            "delivered_events": 0,
            "last_checkpoint_file": None,
            "last_error": None,
        }

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"expected JSON object: {path}")
        return raw

    def _cursor(self) -> str | None:
        if not self.cursor_path.is_file():
            return None
        data = self._read_json(self.cursor_path)
        value = str(data.get("checkpoint_file") or "")
        return value or None

    def _commit_cursor(self, checkpoint: dict[str, object], delivered_events: int) -> None:
        checkpoint_file = str(checkpoint.get("checkpoint_file") or "")
        if not checkpoint_file:
            raise ValueError("checkpoint_file is required")
        payload = {
            "schema": SCHEMA,
            "checkpoint_file": checkpoint_file,
            "hierarchy_id": checkpoint.get("hierarchy_id"),
            "cursor_offset": checkpoint.get("cursor_offset"),
            "delivered_events": int(delivered_events),
        }
        tmp = self.cursor_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
        os.replace(tmp, self.cursor_path)

    def _pending_chain(self, current: dict[str, object]) -> list[dict[str, object]]:
        cursor = self._cursor()
        name = str(current.get("checkpoint_file") or "")
        if not name:
            raise ValueError("current checkpoint has no checkpoint_file")

        pending: list[dict[str, object]] = []
        seen: set[str] = set()
        while name and name != cursor:
            if name in seen:
                raise ValueError("checkpoint lineage cycle detected")
            seen.add(name)
            path = _safe_child(self.checkpoint_dir, name, field="checkpoint_file")
            checkpoint = self._read_json(path)
            if str(checkpoint.get("checkpoint_file") or "") != name:
                raise ValueError("checkpoint manifest identity mismatch")
            pending.append(checkpoint)
            previous = checkpoint.get("previous_checkpoint_file")
            name = "" if previous is None else str(previous)

        if cursor is not None and name != cursor:
            raise ValueError("bridge cursor is not present in current checkpoint lineage")
        pending.reverse()
        return pending

    @staticmethod
    def _source_metadata(checkpoint: dict[str, object], source_id: str) -> dict[str, object]:
        sources = checkpoint.get("sources")
        if not isinstance(sources, list):
            return {}
        for row in sources:
            if isinstance(row, dict) and str(row.get("event_source_id") or "") == source_id:
                return dict(row)
        return {}

    def _events(self, checkpoint: dict[str, object]):
        relative = str(checkpoint.get("events_file") or "")
        if not relative:
            raise ValueError("checkpoint events_file is required")
        path = _safe_child(self.checkpoint_dir, relative, field="events_file")
        if not path.is_file():
            raise ValueError(f"checkpoint events file is missing: {relative}")
        with path.open("r", encoding="utf-8") as fh:
            for line_number, line in enumerate(fh, start=1):
                if not line.strip():
                    continue
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError(f"invalid StructuralEvent at {relative}:{line_number}")
                yield event

    def _payload(self, checkpoint: dict[str, object], event: dict[str, object]) -> dict[str, object]:
        source_id = str(event.get("source_id") or "")
        if not source_id:
            raise ValueError("StructuralEvent source_id is required")
        provenance = self._source_metadata(checkpoint, source_id)
        provenance.update({
            "bridge": SCHEMA,
            "hierarchy_id": checkpoint.get("hierarchy_id"),
            "checkpoint_file": checkpoint.get("checkpoint_file"),
            "events_file": checkpoint.get("events_file"),
        })
        return {"event": event, "provenance": provenance}

    def _post(self, payload: dict[str, object]) -> dict[str, object]:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.memoria_api_key:
            headers["X-Memoria-Key"] = self.memoria_api_key
        request = Request(
            self.memoria_api_url + "/api/v1/structural/observations",
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8") or "{}")
                if response.status not in {200, 201}:
                    raise RuntimeError(f"structural intake returned HTTP {response.status}")
                if not isinstance(body, dict):
                    raise RuntimeError("structural intake returned non-object JSON")
                return body
        except HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            raise RuntimeError(f"structural intake rejected HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"structural intake unavailable: {exc}") from exc

    def run_once(self) -> dict[str, object]:
        current_path = self.checkpoint_dir / "current.json"
        if not current_path.is_file():
            with self._lock:
                self._status.update(status="waiting", last_error=None)
                return dict(self._status)

        try:
            current = self._read_json(current_path)
            pending = self._pending_chain(current)
            delivered_checkpoints = 0
            delivered_events = 0
            for checkpoint in pending:
                checkpoint_events = 0
                for event in self._events(checkpoint):
                    self.sender(self._payload(checkpoint, event))
                    checkpoint_events += 1
                self._commit_cursor(checkpoint, checkpoint_events)
                delivered_checkpoints += 1
                delivered_events += checkpoint_events

            with self._lock:
                self._status.update(
                    status="healthy",
                    delivered_checkpoints=int(self._status["delivered_checkpoints"]) + delivered_checkpoints,
                    delivered_events=int(self._status["delivered_events"]) + delivered_events,
                    last_checkpoint_file=self._cursor(),
                    last_error=None,
                )
                return dict(self._status)
        except Exception as exc:
            with self._lock:
                self._status.update(status="degraded", last_error=str(exc))
                return dict(self._status)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            result = dict(self._status)
        result["cursor"] = self._cursor()
        return result

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.run_once()
            self._stop.wait(self.interval_seconds)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(target=self._loop, name="structural-observation-bridge", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(2.0, self.interval_seconds + 1.0))
        self._thread = None
