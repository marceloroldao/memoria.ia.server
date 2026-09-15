from pathlib import Path
from types import SimpleNamespace
import sys
SHELL_DIR=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(SHELL_DIR))
from epistemic_feedback import EpistemicFeedback

class Wake:
    def __init__(self):self.called=False
    def set(self):self.called=True
class Curiosity:
    def __init__(self):
        self.state=SimpleNamespace(stagnation=0,trajectory=["alpha","robotica","beta"]); self.config=SimpleNamespace(curiosity_stagnation_limit=3); self._wake=Wake(); self.events=[]
    def _event(self,kind,message,**details):self.events.append({"kind":kind,"message":message,**details})

def feedback(tmp_path):return EpistemicFeedback(None,Curiosity(),str(tmp_path))

def test_positive_gain_releases_topic_for_reinforcement(tmp_path):
    f=feedback(tmp_path); f._steer("reinforce_or_expand","robotica")
    assert "robotica" not in f.curiosity.state.trajectory; assert f.curiosity.state.stagnation==0; assert f.curiosity._wake.called; assert f.last_decision=="reinforce_or_expand"

def test_negative_gain_releases_topic_for_deeper_investigation(tmp_path):
    f=feedback(tmp_path); f.curiosity.state.stagnation=2; f._steer("investigate_deeper","robotica")
    assert "robotica" not in f.curiosity.state.trajectory; assert f.curiosity.state.stagnation==0; assert f.curiosity._wake.called

def test_zero_gain_forces_next_cycle_jump(tmp_path):
    f=feedback(tmp_path); f._steer("change_source_or_jump","robotica")
    assert f.curiosity.state.stagnation==3; assert f.curiosity._wake.called; assert f.last_decision=="change_source_or_jump"
    assert f.curiosity.events[-1]["kind"]=="epistemic_steering"
