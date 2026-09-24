from pathlib import Path
import json
import sys

SHELL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHELL_DIR))

from structural_ingest_status import StructuralIngestStatus


def test_structural_ingest_status_summarizes_events_without_full_trails(tmp_path):
    state = tmp_path / "bit"
    checkpoints = state / "checkpoints"
    checkpoints.mkdir(parents=True)
    (state / "worker-status.json").write_text(
        json.dumps({"status": "healthy", "consecutive_failures": 0}),
        encoding="utf-8",
    )
    event_file = checkpoints / "events-10.jsonl"
    event_file.write_text(
        json.dumps({
            "source_id": "web:c1",
            "sequence": 2,
            "byte_offset": 8192,
            "byte_length": 4096,
            "trail": [1, 2, 3, 4],
            "relation_ids": [256, 257],
            "signature": "abc",
            "resolution": 2,
        }) + "\n",
        encoding="utf-8",
    )
    (checkpoints / "current.json").write_text(
        json.dumps({
            "schema": "bit-analyze-ingest-checkpoint/v1",
            "cursor_offset": 10,
            "state_file": "state-10.bin",
            "events_file": event_file.name,
            "record_count": 1,
        }),
        encoding="utf-8",
    )

    result = StructuralIngestStatus(state).snapshot()
    assert result["status"] == "healthy"
    assert result["checkpoint"]["cursor_offset"] == 10
    assert result["recent_events"] == [{
        "source_id": "web:c1",
        "sequence": 2,
        "byte_offset": 8192,
        "byte_length": 4096,
        "signature": "abc",
        "resolution": 2,
        "trail_symbols": 4,
        "relation_ids": 2,
    }]


def test_structural_ingest_status_rejects_checkpoint_path_escape(tmp_path):
    state = tmp_path / "bit"
    checkpoints = state / "checkpoints"
    checkpoints.mkdir(parents=True)
    (checkpoints / "current.json").write_text(
        json.dumps({
            "schema": "bit-analyze-ingest-checkpoint/v1",
            "cursor_offset": 1,
            "state_file": "state.bin",
            "events_file": "../outside.jsonl",
        }),
        encoding="utf-8",
    )

    result = StructuralIngestStatus(state).snapshot()
    assert result["status"] == "degraded"
    assert "escapes" in result["checkpoint_error"]


def test_structural_ingest_status_waits_before_first_checkpoint(tmp_path):
    result = StructuralIngestStatus(tmp_path / "missing").snapshot()
    assert result["status"] == "waiting"
    assert result["checkpoint"] is None
    assert result["recent_events"] == []


def _write_structural_checkpoint(checkpoints, name, previous, source_id, relations, signatures):
    events_name = f"events-{name}.jsonl"
    rows = []
    for sequence, (relation_ids, signature) in enumerate(zip(relations, signatures)):
        rows.append(json.dumps({
            "source_id": source_id,
            "sequence": sequence,
            "byte_offset": sequence * 16,
            "byte_length": 16,
            "trail": [1] + list(relation_ids),
            "relation_ids": list(relation_ids),
            "signature": signature,
            "resolution": 2,
        }))
    (checkpoints / events_name).write_text("\n".join(rows) + "\n", encoding="utf-8")
    payload = {
        "schema": "bit-analyze-ingest-checkpoint/v2",
        "hierarchy_id": "hierarchy:test",
        "checkpoint_file": f"checkpoint-{name}.json",
        "previous_checkpoint_file": previous,
        "events_file": events_name,
        "state_file": f"state-{name}.bin",
        "cursor_offset": int(name),
    }
    (checkpoints / payload["checkpoint_file"]).write_text(json.dumps(payload), encoding="utf-8")
    return payload


def test_source_novelty_uses_structural_ids_not_text_terms(tmp_path):
    state = tmp_path / "bit"
    checkpoints = state / "checkpoints"
    checkpoints.mkdir(parents=True)
    old = _write_structural_checkpoint(
        checkpoints, "10", None, "web:old", [[256, 257], [258]], ["same-window", "old-window"]
    )
    current = _write_structural_checkpoint(
        checkpoints, "20", old["checkpoint_file"], "web:new", [[256, 300], [301]], ["same-window", "new-window"]
    )
    (checkpoints / "current.json").write_text(json.dumps(current), encoding="utf-8")

    result = StructuralIngestStatus(state).source_novelty("web:new")
    assert result["status"] == "ready"
    assert result["basis"] == "bit_analyze_structural_ids"
    assert result["relation_ids"] == 3
    assert result["relation_ids_seen_before"] == 1
    assert result["signatures"] == 2
    assert result["signatures_seen_before"] == 1
    assert 0.5 < result["novelty"] < 0.67


def test_source_novelty_is_pending_until_bit_analyze_has_source(tmp_path):
    state = tmp_path / "bit"
    checkpoints = state / "checkpoints"
    checkpoints.mkdir(parents=True)
    current = _write_structural_checkpoint(
        checkpoints, "10", None, "web:other", [[256]], ["window"]
    )
    (checkpoints / "current.json").write_text(json.dumps(current), encoding="utf-8")

    result = StructuralIngestStatus(state).source_novelty("web:not-yet-consumed")
    assert result == {
        "status": "pending",
        "source_id": "web:not-yet-consumed",
        "basis": "bit_analyze_structural_ids",
    }
