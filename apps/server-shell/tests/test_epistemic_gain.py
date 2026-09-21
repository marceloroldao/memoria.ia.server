from pathlib import Path
import sys
SHELL_DIR=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(SHELL_DIR))
from epistemic_curiosity import measure_epistemic_gain, rank_epistemic_targets
from server_knowledge import ServerKnowledge


def ev(terms, provider="web", url="https://example.org/a"):
    return {"kind":"evidence","title":"test","description":"test evidence","terms":terms,"provider":provider,"url":url}


def test_gain_is_positive_after_reinforcement(tmp_path):
    k=ServerKnowledge(str(tmp_path/"knowledge")); k.learn_from_evidence(ev(["robotica","sensores"],url="https://example.org/a"))
    k.learn_from_evidence(ev(["robotica","sensores"],"wikipedia","https://example.org/b"))
    target=next(x for x in rank_epistemic_targets(k) if x["topic"]=="robotica")
    k.learn_from_evidence(ev(["robotica","controle"],"arxiv","https://example.org/c"))
    gain=measure_epistemic_gain(k,target)
    assert gain["gain"] > 0
    assert gain["after"] < gain["before"]
    assert gain["observations_after"] > gain["observations_before"]
    assert gain["provider_diversity_after"] > gain["provider_diversity_before"]


def test_gain_zero_without_new_evidence(tmp_path):
    k=ServerKnowledge(str(tmp_path/"knowledge")); k.learn_from_evidence(ev(["energia","bateria"],url="https://example.org/a"))
    k.learn_from_evidence(ev(["energia","bateria"],url="https://example.org/b"))
    target=next(x for x in rank_epistemic_targets(k) if x["topic"]=="energia")
    gain=measure_epistemic_gain(k,target)
    assert gain["gain"] == 0
    assert not gain["resolved"]
