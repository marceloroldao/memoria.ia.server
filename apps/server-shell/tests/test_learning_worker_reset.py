from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from learning_worker import LearningWorker


class Knowledge:
    def learn_from_evidence(self, event):
        return {"learned": 0, "keys": []}


def test_reset_to_current_end_skips_old_evidence(tmp_path):
    curiosity = tmp_path / "curiosity"
    curiosity.mkdir()
    events = curiosity / "events.jsonl"
    events.write_text('{"kind":"evidence","message":"old"}\n{"kind":"status","message":"old"}\n', encoding="utf-8")

    worker = LearningWorker(Knowledge(), str(curiosity), poll_seconds=1)
    end = worker.reset_to_current_end()

    assert end == events.stat().st_size
    assert worker.offset == end
    assert (curiosity / "knowledge.cursor").read_text(encoding="utf-8") == str(end)
    assert worker.backlog_bytes() == 0
