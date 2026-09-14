from pathlib import Path
from types import SimpleNamespace
import sys

SHELL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHELL_DIR))

from curiosity_engine import CuriosityEngine


def config(tmp_path):
    return SimpleNamespace(
        curiosity_data_dir=str(tmp_path), curiosity_enabled=True, curiosity_seed=7,
        curiosity_stagnation_limit=2, curiosity_random_jump_rate=0.0,
        curiosity_max_requests_hour=30, curiosity_search_url="https://example.test/?q={query}",
        curiosity_http_timeout=1.0, curiosity_max_page_bytes=100000,
        curiosity_results_per_search=3, curiosity_text_limit=5000,
        curiosity_novelty_threshold=0.25, curiosity_interval_seconds=60.0,
    )


def test_stagnation_forces_jump(tmp_path):
    engine = CuriosityEngine(config(tmp_path))
    engine.state.current_topic = "robótica autônoma"
    engine.state.stagnation = 2
    topic, reason = engine._choose_topic()
    assert reason == "stagnation_jump"
    assert topic != "robótica autônoma"


def test_cycle_records_web_observation_without_promoting_to_personal_memory(tmp_path):
    engine = CuriosityEngine(config(tmp_path))
    engine._search = lambda topic: [("Example", "https://example.test/page")]
    engine.state.last_provider = "wikipedia"
    engine._read = lambda url: {
        "url": url, "domain": "example.test", "title": "Nova bateria experimental",
        "description": "evidência web", "excerpt": "bateria bateria sólida sólida",
        "terms": ["bateria", "sólida"],
    }
    engine.cycle_once()
    snapshot = engine.snapshot()
    evidence = [e for e in snapshot["events"] if e["kind"] == "evidence"]
    assert evidence
    assert evidence[-1]["epistemic_status"] == "web_observation"
    assert evidence[-1]["confidence"] == 0.25
    assert evidence[-1]["provider"] == "wikipedia"
    assert engine.state.discoveries == 1
    assert (tmp_path / "events.jsonl").exists()
    assert (tmp_path / "state.json").exists()


def test_pause_resume_and_manual_jump_are_observable(tmp_path):
    engine = CuriosityEngine(config(tmp_path))
    engine.action("pause")
    assert engine.state.enabled is False
    engine.action("resume")
    assert engine.state.enabled is True
    engine.action("jump")
    assert engine.state.stagnation == 2
    assert any(e["kind"] == "control" for e in engine.snapshot()["events"])


def test_search_falls_back_when_primary_provider_returns_nothing(tmp_path, monkeypatch):
    engine = CuriosityEngine(config(tmp_path))
    monkeypatch.setattr(engine, "_search_duckduckgo", lambda topic: [])

    def fake_wikipedia(topic, fetch_text, limit):
        return [("Robótica", "https://pt.wikipedia.org/wiki/Rob%C3%B3tica")]

    monkeypatch.setattr("curiosity_engine.wikipedia_results", fake_wikipedia)
    results = engine._search("robótica")
    assert results
    assert engine.state.last_provider == "wikipedia"
    assert any(e["kind"] == "provider_fallback" for e in engine.snapshot()["events"])
