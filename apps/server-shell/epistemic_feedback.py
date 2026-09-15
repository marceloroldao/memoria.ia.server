"""Close the curiosity loop after BDR persistence and steer the next exploration."""
from __future__ import annotations
import json
from pathlib import Path
from epistemic_curiosity import measure_epistemic_gain

class EpistemicFeedback:
    def __init__(self, knowledge, curiosity, curiosity_data_dir: str, trajectories=None) -> None:
        self.knowledge=knowledge; self.curiosity=curiosity; self.trajectories=trajectories; self.events_file=Path(curiosity_data_dir)/"events.jsonl"
        self.feedback_count=0; self.positive_gain=0; self.zero_gain=0; self.negative_gain=0; self.total_gain=0.0; self.last_decision=None

    def _target_for(self,event):
        topic=str(event.get("topic") or "").casefold()
        if not topic:return None
        try: lines=self.events_file.read_text(encoding="utf-8").splitlines()
        except OSError:return None
        for line in reversed(lines):
            try:item=json.loads(line)
            except json.JSONDecodeError:continue
            if item.get("kind")=="epistemic_target" and str(item.get("topic") or "").casefold()==topic:
                return {k:v for k,v in item.items() if k in {"topic","key","epistemic_need","confidence","observations","provider_diversity","relation_strength"}}
        return None

    def _steer(self,decision,topic):
        """Translate measured gain into an observable next-cycle control signal."""
        topic=str(topic or "")
        if decision=="change_source_or_jump":
            self.curiosity.state.stagnation=self.curiosity.config.curiosity_stagnation_limit
            self.curiosity._event("epistemic_steering","Sem ganho: próximo ciclo fará salto de trajetória.",topic=topic,decision=decision)
        else:
            folded=topic.casefold(); self.curiosity.state.trajectory=[x for x in self.curiosity.state.trajectory if str(x).casefold()!=folded]
            self.curiosity.state.stagnation=0
            message="Ganho positivo: endereço liberado para reforço/expansão." if decision=="reinforce_or_expand" else "Ganho negativo: endereço liberado para investigação mais profunda."
            self.curiosity._event("epistemic_steering",message,topic=topic,decision=decision)
        self.last_decision=decision
        self.curiosity._wake.set()

    def __call__(self,event,learning_result):
        target=self._target_for(event)
        if target is None:return
        gain=measure_epistemic_gain(self.knowledge,target); value=float(gain.get("gain") or 0.0)
        self.feedback_count+=1; self.total_gain=round(self.total_gain+value,4)
        if value>0:self.positive_gain+=1; decision="reinforce_or_expand"
        elif value<0:self.negative_gain+=1; decision="investigate_deeper"
        else:self.zero_gain+=1; decision="change_source_or_jump"
        topic=gain.get("topic") or target.get("topic")
        feedback={**gain,"key":gain.get("key") or target.get("key") or topic,"gain":value,"decision":decision}
        trajectory=None
        if self.trajectories is not None:
            self.trajectories.open(str(topic),target,"epistemic_gap")
            trajectory=self.trajectories.record_feedback(str(topic),feedback,event)
        details={"topic":target.get("topic"),"decision":decision,"learned":int(learning_result.get("learned") or 0),**gain}
        if trajectory is not None:details["trajectory_id"]=trajectory.get("trajectory_id");details["trajectory_steps"]=trajectory.get("steps");details["trajectory_cumulative_gain"]=trajectory.get("cumulative_gain")
        self.curiosity._event("epistemic_feedback",f"Ganho epistêmico {value:+.4f} em {topic}",**details)
        self._steer(decision,topic)

    def snapshot(self):
        avg=round(self.total_gain/self.feedback_count,4) if self.feedback_count else 0.0
        result={"feedback_count":self.feedback_count,"positive_gain":self.positive_gain,"zero_gain":self.zero_gain,"negative_gain":self.negative_gain,"total_gain":self.total_gain,"average_gain":avg,"last_decision":self.last_decision}
        if self.trajectories is not None:result["trajectories"]=self.trajectories.snapshot()
        return result
