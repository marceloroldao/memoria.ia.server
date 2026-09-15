from pathlib import Path
import json, sys
SHELL=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(SHELL))
from epistemic_trajectory import EpistemicTrajectoryStore

def test_trajectory_persists_and_accumulates_gain(tmp_path):
    s=EpistemicTrajectoryStore(str(tmp_path)); t=s.open("robotica",{"key":"robotica","epistemic_need":.8})
    s.record_feedback("robotica",{"key":"robotica","gain":.2,"after":.6,"decision":"reinforce_or_expand"},{"provider":"wikipedia"})
    r=EpistemicTrajectoryStore(str(tmp_path)); snap=r.snapshot(); assert snap["stats"]["opened"]==1; assert snap["stats"]["positive_gain"]==1
    active=snap["active"][0]; assert active["trajectory_id"]==t["trajectory_id"]; assert active["steps"]==1; assert active["cumulative_gain"]==.2; assert active["sources"]["wikipedia"]==1

def test_zero_and_negative_gain_remain_visible(tmp_path):
    s=EpistemicTrajectoryStore(str(tmp_path)); s.open("energia",{"key":"energia"})
    s.record_feedback("energia",{"key":"energia","gain":0,"after":.7,"decision":"change_source_or_jump"},{"provider":"web"})
    item=s.record_feedback("energia",{"key":"energia","gain":-.1,"after":.8,"decision":"investigate_deeper"},{"provider":"arxiv"})
    snap=s.snapshot(); assert snap["stats"]["zero_gain"]==1; assert snap["stats"]["negative_gain"]==1; assert snap["active"][0]["steps"]==2; assert not item["saturation"]["saturated"]

def test_close_preserves_history(tmp_path):
    s=EpistemicTrajectoryStore(str(tmp_path)); s.open("sensores",{"key":"sensores"}); closed=s.close("sensores","saturated")
    assert closed["status"]=="closed"; snap=s.snapshot(); assert not snap["active"]; assert snap["closed_count"]==1; assert snap["stats"]["closed"]==1

def test_saturation_requires_evidence_diversity_and_positive_resolution(tmp_path):
    s=EpistemicTrajectoryStore(str(tmp_path)); s.open("controle",{"key":"controle","epistemic_need":.8})
    s.record_feedback("controle",{"key":"controle","gain":.2,"after":.6,"decision":"reinforce_or_expand"},{"provider":"wikipedia"})
    s.record_feedback("controle",{"key":"controle","gain":.2,"after":.4,"decision":"reinforce_or_expand"},{"provider":"arxiv"})
    item=s.record_feedback("controle",{"key":"controle","gain":.15,"after":.25,"decision":"reinforce_or_expand"},{"provider":"arxiv"})
    assert item["saturation"]["saturated"]; assert item["saturation"]["source_diversity"]==2

def test_negative_recent_gain_blocks_saturation(tmp_path):
    s=EpistemicTrajectoryStore(str(tmp_path)); s.open("fisica",{"key":"fisica"})
    s.record_feedback("fisica",{"key":"fisica","gain":.3,"after":.3,"decision":"reinforce_or_expand"},{"provider":"a"})
    s.record_feedback("fisica",{"key":"fisica","gain":-.1,"after":.25,"decision":"investigate_deeper"},{"provider":"b"})
    item=s.record_feedback("fisica",{"key":"fisica","gain":.1,"after":.2,"decision":"reinforce_or_expand"},{"provider":"b"})
    assert not item["saturation"]["saturated"]; assert not item["saturation"]["no_recent_contradiction"]

def test_closed_trajectory_reopens_as_linked_generation(tmp_path):
    s=EpistemicTrajectoryStore(str(tmp_path)); first=s.open("materia",{"key":"materia"}); s.close("materia","evidence_saturated")
    second=s.open("materia",{"key":"materia","epistemic_need":.7},"new_evidence_after_closure")
    assert second["trajectory_id"]!=first["trajectory_id"]; assert second["parent_trajectory_id"]==first["trajectory_id"]; assert second["root_trajectory_id"]==first["trajectory_id"]; assert second["generation"]==1; assert s.snapshot()["stats"]["reopened"]==1

def test_reopening_lineage_survives_restart_and_multiple_generations(tmp_path):
    s=EpistemicTrajectoryStore(str(tmp_path)); first=s.open("tempo",{"key":"tempo"}); s.close("tempo")
    second=s.open("tempo",{"key":"tempo"}); s.close("tempo")
    r=EpistemicTrajectoryStore(str(tmp_path)); third=r.open("tempo",{"key":"tempo"})
    assert third["parent_trajectory_id"]==second["trajectory_id"]; assert third["root_trajectory_id"]==first["trajectory_id"]; assert third["generation"]==2; assert r.snapshot()["stats"]["reopened"]==2

def test_old_state_is_migrated_without_losing_closed_history(tmp_path):
    state={"version":1,"active":{},"closed":{"old":{"trajectory_id":"old","key":"luz","status":"closed","closed_at":1}},"stats":{"opened":1,"closed":1,"steps":0,"positive_gain":0,"zero_gain":0,"negative_gain":0}}
    (tmp_path/"epistemic_trajectories.state.json").write_text(json.dumps(state),encoding="utf-8")
    s=EpistemicTrajectoryStore(str(tmp_path)); reopened=s.open("luz",{"key":"luz"})
    assert s.snapshot()["version"]==2; assert reopened["parent_trajectory_id"]=="old"; assert reopened["generation"]==1; assert s.snapshot()["closed_count"]==1
