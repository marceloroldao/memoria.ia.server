from pathlib import Path
import sys
from unittest.mock import patch

SHELL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHELL_DIR))

from autonomous_tests import (
    MemoriaClient,
    TestRun as AutonomousRun,
    UpstreamError,
    _normalize,
    evaluate_expected,
    extract_json_object,
)


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
    run = AutonomousRun("run", 5, 0, "autotest:run")
    assert run.pause.is_set()


def test_memoria_client_reports_configured_timeout():
    client = MemoriaClient("http://memoria:8080", "key", 180)
    with patch("autonomous_tests.urlopen", side_effect=TimeoutError):
        try:
            client.post("/api/v1/chat", {"message": "teste"})
        except UpstreamError as error:
            assert "180s" in str(error)
        else:
            raise AssertionError("timeout should become an upstream error")
