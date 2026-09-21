from pathlib import Path
import sys
SHELL_DIR=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(SHELL_DIR))
from epistemic_curiosity import choose_epistemic_topic, rank_epistemic_targets
from server_knowledge import ServerKnowledge


def ev(terms, provider="web", url="https://example.org/a"):
    return {"kind":"evidence","title":"test","description":"test evidence","terms":terms,"provider":provider,"url":url}


def test_single_observation_is_remembered_but_not_promoted_to_target(tmp_path):
    k=ServerKnowledge(str(tmp_path/"knowledge"))
    k.learn_from_evidence(ev(["fraco","vizinho"]))
    assert {x["key"] for x in k.recent()["items"]} >= {"fraco","vizinho"}
    assert rank_epistemic_targets(k) == []


def test_reinforcement_makes_address_eligible_without_vocabulary_rules(tmp_path):
    k=ServerKnowledge(str(tmp_path/"knowledge"))
    k.learn_from_evidence(ev(["editar","bldc"],"wikipedia","https://example.org/a"))
    k.learn_from_evidence(ev(["editar","bldc"],"wikipedia","https://example.org/b"))
    topics={x["topic"] for x in rank_epistemic_targets(k)}
    assert {"editar","bldc"}.issubset(topics)
    assert all(x["reinforcement_ready"] is True for x in rank_epistemic_targets(k))


def test_trajectory_avoids_immediate_research_loop(tmp_path):
    k=ServerKnowledge(str(tmp_path/"knowledge"))
    k.learn_from_evidence(ev(["alpha","beta"],url="https://example.org/a"))
    k.learn_from_evidence(ev(["alpha","beta"],url="https://example.org/b"))
    first=rank_epistemic_targets(k)[0]["topic"]
    chosen=choose_epistemic_topic(k,trajectory=[first])
    assert chosen is not None and chosen[0] != first
