from pathlib import Path
import sys
from unittest.mock import Mock, patch

SHELL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHELL_DIR))

from autonomous_tests import (
    AutonomousTestManager,
    CuriosityGenerator,
    MemoriaClient,
    TestRun as AutonomousRun,
    UpstreamError,
    _normalize,
    evaluate_expected,
    extract_json_object,
)


class DummyConfig:
    memoria_api_url = "http://memoria:8080"
    memoria_api_key = "key"
    autotest_timeout_seconds = 180.0
    proxy_timeout_seconds = 10.0


def test_extract_json_accepts_markdown_wrapping():
    value = extract_json_object('```json\n{"assertion":"A é B","question":"O quê?","expected_terms":["B"]}\n```')
    assert value["expected_terms"] == ["B"]


def test_evaluator_is_case_and_accent_insensitive():
    response = {"selected_context": "A Kombi é PRETA", "status": "HIT"}
    assert evaluate_expected(["kombi", "preta"], response)
    assert not evaluate_expected(["corsa"], response)


def test_normalizer_removes_punctuation_and_accents():
    assert _normalize("Relação: José!") == "relacao jose"


def test_run_starts_unpaused():
    run = AutonomousRun("abcdef012345", 5, 0, "autotest:run")
    assert run.pause.is_set()
    assert run.seed != 0


def test_memoria_client_reports_configured_timeout():
    client = MemoriaClient("http://memoria:8080", "key", 180)
    with patch("autonomous_tests.urlopen", side_effect=TimeoutError):
        try:
            client.post("/api/v1/chat", {"message": "teste"})
        except UpstreamError as error:
            assert "180s" in str(error)
        else:
            raise AssertionError("timeout should become an upstream error")


def test_local_curiosity_generates_scenario_without_calling_llm():
    manager = AutonomousTestManager(DummyConfig())
    manager.client.post = Mock(side_effect=AssertionError("scenario generation must not call upstream"))
    run = AutonomousRun("abcdef012345", 5, 0, "autotest:run", seed=1234)

    scenario = manager._generate_scenario(run, 1)

    assert scenario["provider"] == "local-curiosity"
    assert scenario["model"] is None
    assert scenario["assertion"]
    assert scenario["question"]
    assert scenario["expected_terms"]


def test_curiosity_forces_jump_after_two_cycles_in_same_topic():
    generator = CuriosityGenerator()
    run = AutonomousRun("abcdef012345", 5, 0, "autotest:run", jump_rate=0.0, seed=1234)
    run.last_topic = "attribute"
    run.topic_streak = 2

    topic, jumped = generator.choose_topic(run, 3)

    assert jumped is True
    assert topic != "attribute"


def test_curiosity_seed_is_reproducible():
    generator = CuriosityGenerator()
    first = AutonomousRun("abcdef012345", 5, 0, "autotest:first", seed=4321)
    second = AutonomousRun("abcdef012345", 5, 0, "autotest:second", seed=4321)

    scenario_a = generator.build(first, 1)
    scenario_b = generator.build(second, 1)

    assert scenario_a == scenario_b
