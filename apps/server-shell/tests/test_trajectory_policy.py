from pathlib import Path
import sys
SHELL=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(SHELL))
from trajectory_policy import rank_topics, trajectory_signal


def test_unexplored_address_gets_exploration_priority():
    s=trajectory_signal("robotica",{"active":[],"closed":[]})
    assert s["state"]=="unexplored"; assert s["priority"]>0


def test_negative_gain_is_investigated_not_suppressed():
    snap={"active":[{"key":"energia","last_gain":-.2,"steps":3,"generation":1}]}
    s=trajectory_signal("energia",snap)
    assert s["state"]=="contradictory"; assert s["priority"]==1.0


def test_repeated_zero_gain_reduces_priority_without_erasing_address():
    snap={"active":[{"key":"tempo","last_gain":0,"steps":4,"generation":0}]}
    s=trajectory_signal("tempo",snap)
    assert s["state"]=="stagnant"; assert s["priority"]<0


def test_saturated_address_is_deprioritized():
    snap={"active":[],"closed":[{"key":"luz","steps":5,"generation":2}]}
    s=trajectory_signal("luz",snap)
    assert s["state"]=="saturated"; assert s["priority"]==-1.0


def test_ranking_prefers_contradiction_over_recent_repetition():
    snap={"active":[{"key":"energia","last_gain":-.1,"steps":2}],"closed":[{"key":"luz","steps":4}]}
    ranked=rank_topics([("luz",1.0),("energia",.5),("materia",.5)],snap,recent=["materia"])
    assert ranked[0]["topic"]=="energia"
    assert ranked[-1]["topic"]=="luz"
