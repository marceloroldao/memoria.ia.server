"""Minimal, transport-neutral event model for Explorer observability."""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from threading import RLock
from typing import Any


EVENT_SCHEMA = "bdr-explorer-event/v0.1"


class EventKind(str, Enum):
    NODE_CREATED = "node.created"
    NODE_UPDATED = "node.updated"
    NODE_ACCESSED = "node.accessed"
    RETRIEVAL_STARTED = "retrieval.started"
    CANDIDATE_FOUND = "retrieval.candidate_found"
    NODE_SELECTED = "retrieval.node_selected"
    RETRIEVAL_COMPLETED = "retrieval.completed"
    PERSISTENCE = "persistence.event"
    CHECKPOINT = "checkpoint.event"
    RECOVERY = "recovery.event"


@dataclass(frozen=True, slots=True)
class ExplorerEvent:
    kind: EventKind
    source: str
    data: dict[str, Any]
    occurred_at: str
    schema: str = EVENT_SCHEMA

    @classmethod
    def create(cls, kind: EventKind, source: str, **data: Any) -> "ExplorerEvent":
        return cls(kind, source, data, datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        return payload


class EventBuffer:
    """Small optional in-memory buffer; not part of BDR persistence."""

    def __init__(self, max_events: int = 256) -> None:
        if max_events <= 0:
            raise ValueError("max_events must be > 0")
        self._events: deque[ExplorerEvent] = deque(maxlen=max_events)
        self._lock = RLock()

    def publish(self, event: ExplorerEvent) -> None:
        with self._lock:
            self._events.append(event)

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [event.as_dict() for event in self._events]
