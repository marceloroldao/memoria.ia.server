from pathlib import Path
import sys
SHELL_DIR=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(SHELL_DIR))
from epistemic_curiosity import choose_epistemic_topic, rank_epistemic_targets
from server_knowledge import ServerKnowledge


def ev(terms, provider="web", url="https://example.org/a"):
    return {"kind":"evidence","title":"test","description":"test evidence","terms":terms,"provider":provider,"url":url}


def test_weakly_supported_content_is_prioritized(tmp_path):
    k=ServerKnowledge(str(tmp_path/"knowledge"))
    k.learn_from_evidence(ev(["fraco","vizinho"]))
    for n,provider in enumerate(["web","wikipedia","arxiv","nasa"]):
        k.learn_from_evidence(ev(["forte","estavel"],provider,f"https://example.org/{n}"))
    ranked=rank_epistemic_targets(k)
    assert ranked[0]["topic"] in {"fraco","vizinho"}
    assert ranked[0]["epistemic_need"] > next(x for x in ranked if x["topic"]=="forte")["epistemic_need"]


def test_interface_noise_does_not_steer_research(tmp_path):
    k=ServerKnowledge(str(tmp_path/"knowledge"))
    k.learn_from_evidence(ev(["editar","bldc"],"wikipedia"))
    topics={x["topic"] for x in rank_epistemic_targets(k)}
    assert "bldc" in topics and "editar" not in topics


def test_trajectory_avoids_immediate_research_loop(tmp_path):
    k=ServerKnowledge(str(tmp_path/"knowledge")); k.learn_from_evidence(ev(["alpha","beta"]))
    first=rank_epistemic_targets(k)[0]["topic"]
    chosen=choose_epistemic_topic(k,trajectory=[first])
    assert chosen is not None and chosen[0] != first
