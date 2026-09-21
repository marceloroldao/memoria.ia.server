from __future__ import annotations

import json

from structural_observation_bridge import StructuralObservationBridge


def _write_checkpoint(root, name, *, previous, events_file, source_id="web:capture"):
    checkpoint = {
        "schema": "bit-analyze-ingest-checkpoint/v2",
        "hierarchy_id": "hierarchy:test",
        "cursor_offset": 100,
        "checkpoint_file": name,
        "events_file": events_file,
        "previous_checkpoint_file": previous,
        "sources": [
            {
                "event_source_id": source_id,
                "capture_id": source_id,
                "content_source_id": "raw-web:sha256:" + "a" * 64,
                "sha256": "a" * 64,
                "byte_length": 32,
                "content_type": "application/octet-stream",
                "observed_at": "2026-09-21T20:00:00+00:00",
                "url": "https://example.invalid/",
                "object_path": "objects/sha256/aa/example.bin",
            }
        ],
    }
    (root / name).write_text(json.dumps(checkpoint), encoding="utf-8")
    return checkpoint


def _event(sequence, offset):
    return {
        "version": 1,
        "source_id": "web:capture",
        "sequence": sequence,
        "byte_offset": offset,
        "byte_length": 16,
        "trail": [65, 66, 300],
        "relation_ids": [300],
        "signature": f"{sequence + 1:016x}",
        "resolution": 2,
    }


def test_bridge_replays_checkpoint_lineage_oldest_first_and_is_idempotent(tmp_path):
    state = tmp_path / "bit-analyze"
    checkpoints = state / "checkpoints"
    checkpoints.mkdir(parents=True)
    (checkpoints / "events-1.jsonl").write_text(json.dumps(_event(0, 0)) + "\n", encoding="utf-8")
    (checkpoints / "events-2.jsonl").write_text(json.dumps(_event(1, 16)) + "\n", encoding="utf-8")
    cp1 = _write_checkpoint(checkpoints, "checkpoint-1.json", previous=None, events_file="events-1.jsonl")
    cp2 = _write_checkpoint(checkpoints, "checkpoint-2.json", previous="checkpoint-1.json", events_file="events-2.jsonl")
    (checkpoints / "current.json").write_text(json.dumps(cp2), encoding="utf-8")

    delivered = []
    bridge = StructuralObservationBridge(
        state,
        tmp_path / "server",
        "http://memoria:8080",
        "secret",
        sender=lambda payload: delivered.append(payload) or {"stored": True},
    )

    status = bridge.run_once()
    assert status["status"] == "healthy"
    assert [row["event"]["sequence"] for row in delivered] == [0, 1]
    assert delivered[0]["provenance"]["hierarchy_id"] == "hierarchy:test"
    assert delivered[0]["provenance"]["checkpoint_file"] == "checkpoint-1.json"
    assert delivered[0]["provenance"]["capture_id"] == "web:capture"
    assert bridge.snapshot()["cursor"] == "checkpoint-2.json"

    bridge.run_once()
    assert [row["event"]["sequence"] for row in delivered] == [0, 1]


def test_bridge_does_not_advance_checkpoint_cursor_on_partial_failure(tmp_path):
    state = tmp_path / "bit-analyze"
    checkpoints = state / "checkpoints"
    checkpoints.mkdir(parents=True)
    events = "\n".join((json.dumps(_event(0, 0)), json.dumps(_event(1, 16)))) + "\n"
    (checkpoints / "events.jsonl").write_text(events, encoding="utf-8")
    cp = _write_checkpoint(checkpoints, "checkpoint.json", previous=None, events_file="events.jsonl")
    (checkpoints / "current.json").write_text(json.dumps(cp), encoding="utf-8")

    calls = []

    def sender(payload):
        calls.append(payload)
        if len(calls) == 2:
            raise RuntimeError("synthetic failure")
        return {"stored": True}

    bridge = StructuralObservationBridge(
        state,
        tmp_path / "server",
        "http://memoria:8080",
        "secret",
        sender=sender,
    )
    status = bridge.run_once()
    assert status["status"] == "degraded"
    assert bridge.snapshot()["cursor"] is None
    assert len(calls) == 2
