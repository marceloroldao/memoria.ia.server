"""Persistent epistemic trajectories for autonomous curiosity, without LLMs."""
from __future__ import annotations
import json, time, uuid
from pathlib import Path
from threading import RLock

class EpistemicTrajectoryStore:
    """Append-only investigation history plus compact current-state index."""
    def __init__(self, data_dir: str) -> None:
        self.root=Path(data_dir); self.root.mkdir(parents=True,exist_ok=True)
        self.events_file=self.root/"epistemic_trajectories.jsonl"; self.state_file=self.root/"epistemic_trajectories.state.json"; self._lock=RLock(); self.state=self._load()
    def _load(self):
        try:return json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception:return {"version":1,"active":{},"closed":{},"stats":{"opened":0,"closed":0,"steps":0,"positive_gain":0,"zero_gain":0,"negative_gain":0}}
    def _save(self):
        tmp=self.state_file.with_suffix(".tmp"); tmp.write_text(json.dumps(self.state,ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(self.state_file)
    def _append(self,event):
        with self.events_file.open("a",encoding="utf-8") as fh: fh.write(json.dumps(event,ensure_ascii=False)+"\n")
    def open(self,topic:str,target:dict|None=None,reason:str="epistemic_gap"):
        with self._lock:
            key=str((target or {}).get("key") or topic).casefold(); existing=self.state["active"].get(key)
            if existing:return existing
            now=time.time(); item={"trajectory_id":uuid.uuid4().hex,"key":key,"topic":topic,"reason":reason,"status":"active","opened_at":now,"updated_at":now,"steps":0,"cumulative_gain":0.0,"last_gain":None,"last_decision":None,"sources":{},"hypotheses":{},"recent_gains":[],"target_before":target or {}}
            self.state["active"][key]=item; self.state["stats"]["opened"]+=1; self._append({"kind":"trajectory_opened",**item}); self._save(); return item
    @staticmethod
    def saturation(item:dict,feedback:dict)->dict:
        """Conservative stop rule: enough evidence, diversity and sustained positive resolution."""
        gains=list(item.get("recent_gains") or [])[-3:]
        steps=int(item.get("steps") or 0); sources=len([k for k in (item.get("sources") or {}) if k!="unknown"])
        after=float(feedback.get("after") if feedback.get("after") is not None else 1.0)
        recent_positive=len(gains)>=2 and all(float(g)>0 for g in gains[-2:])
        no_recent_contradiction=not gains or all(float(g)>=0 for g in gains[-3:])
        saturated=steps>=3 and sources>=2 and after<=0.30 and recent_positive and no_recent_contradiction
        return {"saturated":saturated,"steps":steps,"source_diversity":sources,"epistemic_need":after,"recent_positive":recent_positive,"no_recent_contradiction":no_recent_contradiction}
    def record_feedback(self,topic:str,feedback:dict,event:dict|None=None):
        with self._lock:
            key=str(feedback.get("key") or topic).casefold(); item=self.state["active"].get(key) or self.open(topic,{"key":key},"feedback_recovery")
            gain=float(feedback.get("gain") or 0.0); decision=str(feedback.get("decision") or "")
            item["steps"]+=1; item["cumulative_gain"]=round(float(item.get("cumulative_gain",0))+gain,4); item["last_gain"]=gain; item["last_decision"]=decision; item["updated_at"]=time.time(); item.setdefault("recent_gains",[]).append(gain); item["recent_gains"]=item["recent_gains"][-5:]
            provider=str((event or {}).get("provider") or "unknown"); item["sources"][provider]=int(item["sources"].get(provider,0))+1
            self.state["stats"]["steps"]+=1; bucket="positive_gain" if gain>0 else "negative_gain" if gain<0 else "zero_gain"; self.state["stats"][bucket]+=1
            saturation=self.saturation(item,feedback); item["saturation"]=saturation
            self._append({"kind":"trajectory_step","trajectory_id":item["trajectory_id"],"key":key,"topic":topic,"gain":gain,"decision":decision,"provider":provider,"saturation":saturation,"time":time.time()}); self._save(); return item
    def close(self,key:str,reason:str="saturated"):
        with self._lock:
            key=key.casefold(); item=self.state["active"].pop(key,None)
            if not item:return None
            item["status"]="closed"; item["closed_at"]=time.time(); item["close_reason"]=reason; self.state["closed"][item["trajectory_id"]]=item; self.state["stats"]["closed"]+=1; self._append({"kind":"trajectory_closed",**item}); self._save(); return item
    def snapshot(self):
        with self._lock:return {"stats":dict(self.state["stats"]),"active":list(self.state["active"].values())[-20:],"closed_count":len(self.state["closed"])}
