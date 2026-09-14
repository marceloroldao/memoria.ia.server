from pathlib import Path
import json
import sys

SHELL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SHELL_DIR))

from server_knowledge import ServerKnowledge
from learning_worker import LearningWorker


def evidence(url="https://example.org/a", provider="wikipedia", terms=None):
    return {
        "kind": "evidence",
        "title": "Controle de motores BLDC",
        "description": "Motores BLDC usam comutação eletrônica e podem ser controlados por FOC.",
        "excerpt": "BLDC FOC motor motor controle controle eletrônica eletrônica",
        "terms": terms or ["bldc", "motor", "controle", "foc"],
        "provider": provider,
        "url": url,
    }


def test_learning_persists_and_reinforcement_increases_confidence(tmp_path):
    knowledge = ServerKnowledge(str(tmp_path / "knowledge"))
    first = knowledge.learn_from_evidence(evidence())
    assert first["learned"] == 4
    q1 = knowledge.query("o que sabe sobre BLDC?")
    assert q1["hits"]
    c1 = q1["hits"][0]["confidence"]

    knowledge.learn_from_evidence(evidence("https://example.net/b", "arxiv"))
    q2 = knowledge.query("BLDC")
    assert q2["hits"][0]["confidence"] > c1
    assert q2["hits"][0]["observations"] == 2

    reloaded = ServerKnowledge(str(tmp_path / "knowledge"))
    assert reloaded.query("BLDC")["hits"][0]["observations"] == 2


def test_related_terms_are_formed_from_same_observation(tmp_path):
    knowledge = ServerKnowledge(str(tmp_path / "knowledge"))
    knowledge.learn_from_evidence(evidence())
    hit = knowledge.query("BLDC")["hits"][0]
    related = dict(hit["related"])
    assert "foc" in related
    assert "motor" in related


def test_wikipedia_navigation_noise_is_filtered(tmp_path):
    knowledge = ServerKnowledge(str(tmp_path / "knowledge"))
    result = knowledge.learn_from_evidence(evidence(terms=["bldc", "motor", "editar", "página", "barra", "código"]))
    assert result["learned"] == 2
    assert result["filtered"] == 4
    assert not knowledge.query("editar")["hits"]
    assert knowledge.query("BLDC")["hits"]


class FakeBDR:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.writes = []
    def append_evidence(self, event):
        self.writes.append(event)
        return "knowledge:test"
    def load_evidence(self, limit=5000):
        return list(self.rows)


def test_learning_worker_persists_to_bdr_before_advancing_cursor(tmp_path):
    curiosity = tmp_path / "curiosity"
    curiosity.mkdir()
    events = curiosity / "events.jsonl"
    events.write_text(
        json.dumps({"kind":"topic","message":"Pesquisando: motores"}) + "\n" +
        json.dumps(evidence(), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    knowledge = ServerKnowledge(str(tmp_path / "knowledge"))
    bdr = FakeBDR()
    worker = LearningWorker(knowledge, str(curiosity), bdr=bdr)
    learned = worker.cycle_once()
    assert learned == 4
    assert len(bdr.writes) == 1
    assert knowledge.query("FOC")["hits"]
    assert (curiosity / "knowledge.cursor").exists()


def test_bdr_replay_rebuilds_local_cache(tmp_path):
    knowledge = ServerKnowledge(str(tmp_path / "knowledge"))
    bdr = FakeBDR([evidence(), evidence("https://example.net/b", "arxiv")])
    worker = LearningWorker(knowledge, str(tmp_path / "curiosity"), bdr=bdr)
    result = worker.rebuild_from_bdr()
    assert result["observations"] == 2
    assert result["concepts"] == 4
    assert knowledge.query("BLDC")["hits"][0]["observations"] == 2


def test_recent_reports_server_learning_state(tmp_path):
    knowledge = ServerKnowledge(str(tmp_path / "knowledge"))
    knowledge.learn_from_evidence(evidence())
    recent = knowledge.recent()
    assert recent["concepts"] == 4
    assert recent["observations"] == 1
    assert recent["storage"] == "bdr+journal/cache"
    assert recent["items"]
