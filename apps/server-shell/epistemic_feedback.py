"""Close the curiosity loop after BDR persistence and local knowledge update."""
from __future__ import annotations
import json
from pathlib import Path
from epistemic_curiosity import measure_epistemic_gain

class EpistemicFeedback:
    def __init__(self, knowledge, curiosity, curiosity_data_dir: str) -> None:
        self.knowledge=knowledge; self.curiosity=curiosity; self.events_file=Path(curiosity_data_dir)/"events.jsonl"
        self.feedback_count=0; self.positive_gain=0; self.zero_gain=0; self.negative_gain=0; self.total_gain=0.0

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

    def __call__(self,event,learning_result):
        target=self._target_for(event)
        if target is None:return
        gain=measure_epistemic_gain(self.knowledge,target); value=float(gain.get("gain") or 0.0)
        self.feedback_count+=1; self.total_gain=round(self.total_gain+value,4)
        if value>0:self.positive_gain+=1; decision="reinforce_or_expand"
        elif value<0:self.negative_gain+=1; decision="investigate_deeper"
        else:self.zero_gain+=1; decision="change_source_or_jump"
        self.curiosity._event("epistemic_feedback",f"Ganho epistêmico {value:+.4f} em {gain.get('topic') or target.get('topic')}",topic=target.get("topic"),decision=decision,learned=int(learning_result.get("learned") or 0),**gain)

    def snapshot(self):
        avg=round(self.total_gain/self.feedback_count,4) if self.feedback_count else 0.0
        return {"feedback_count":self.feedback_count,"positive_gain":self.positive_gain,"zero_gain":self.zero_gain,"negative_gain":self.negative_gain,"total_gain":self.total_gain,"average_gain":avg}
