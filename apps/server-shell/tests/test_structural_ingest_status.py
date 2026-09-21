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
