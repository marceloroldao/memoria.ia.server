from pathlib import Path
import sys
from types import SimpleNamespace

SHELL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHELL))

from guided_curiosity import TrajectoryGuidedCuriosityEngine


class SnapshotStore:
    def __init__(self, snapshot):
        self.value = snapshot
    def snapshot(self):
        return self.value


def config(tmp_path):
    return SimpleNamespace(
        curiosity_data_dir=str(tmp_path), curiosity_enabled=True, curiosity_seed=7,
        curiosity_stagnation_limit=3, curiosity_random_jump_rate=0.0,
        curiosity_interval_seconds=60,
        curiosity_max_requests_hour=100, curiosity_http_timeout=1,
        curiosity_max_page_bytes=1000, curiosity_search_url="https://example.invalid/?q={query}",
        curiosity_results_per_search=5, curiosity_text_limit=1000,
        curiosity_novelty_threshold=0.2,
    )


def test_contradictory_address_wins_forced_next_address(tmp_path):
    store = SnapshotStore({
        "active": [{"key":"energia","topic":"energia","last_gain":-0.2,"steps":3,"generation":1}],
        "closed": [],
    })
    engine = TrajectoryGuidedCuriosityEngine(config(tmp_path), trajectories=store)
    engine.state.current_topic = "sensores"
    engine.state.stagnation = 3
    topic, reason = engine._choose_topic()
    assert topic == "energia"
    assert reason == "trajectory_contradiction"
    event = list(engine._events)[-1]
    assert event["kind"] == "trajectory_guidance"
    assert event["topic"] == "energia"
    assert event["trajectory_state"] == "contradictory"


def test_saturated_address_is_not_selected_when_unexplored_exists(tmp_path):
    store = SnapshotStore({
        "active": [],
        "closed": [{"key":"energia","topic":"energia","steps":5,"generation":0}],
    })
    engine = TrajectoryGuidedCuriosityEngine(config(tmp_path), trajectories=store)
    engine.state.current_topic = "sensores"
    engine.state.stagnation = 3
    topic, reason = engine._choose_topic()
    assert topic != "energia"
    assert reason == "trajectory_unexplored"


def test_recent_address_gets_recency_penalty(tmp_path):
    store = SnapshotStore({"active": [], "closed": []})
    engine = TrajectoryGuidedCuriosityEngine(config(tmp_path), trajectories=store)
    engine.state.current_topic = "sensores"
    engine.state.stagnation = 3
    engine.state.trajectory = ["astronomia"]
    topic, _ = engine._choose_topic()
    assert topic != "astronomia"


def test_snapshot_reports_guidance_enabled(tmp_path):
    engine = TrajectoryGuidedCuriosityEngine(config(tmp_path), trajectories=SnapshotStore({"active":[],"closed":[]}))
    assert engine.snapshot()["configuration"]["trajectory_guidance"] is True
