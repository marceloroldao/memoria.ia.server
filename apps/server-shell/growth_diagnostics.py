"""Growth diagnostics for Curiosity -> Learning -> BDR -> Explorer.

Read-only report plus an explicit synthetic persistence probe. No LLM involved.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import time
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

PREFIX = "/api/server/v1/growth-diagnostics"


def _now(): return datetime.now(timezone.utc).isoformat()

class GrowthDiagnostics:
    def __init__(self, config, curiosity, knowledge, *, write_lock=None):
        self.config=config; self.curiosity=curiosity; self.knowledge=knowledge; self.write_lock=write_lock
        self.path=Path(config.curiosity_data_dir).parent / "diagnostics" / "growth-report.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _json_get(self,url,headers=None,timeout=8):
        with urlopen(Request(url,headers=headers or {},method="GET"),timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _episodes(self):
        h={"X-Memoria-Key":self.config.memoria_api_key} if self.config.memoria_api_key else {}
        return self._json_get(self.config.memoria_api_url+"/api/v1/episodes/history?limit=5000",h).get("episodes",[])

    def _explorer(self):
        return self._json_get(self.config.bdr_explorer_url+"/api/snapshot")

    def _event_stats(self):
        p=Path(self.config.curiosity_data_dir)/"events.jsonl"; counts={}; total=0; evidence=0
        if p.exists():
            for line in p.read_text(encoding="utf-8",errors="replace").splitlines():
                try: row=json.loads(line)
                except Exception: continue
                k=str(row.get("kind") or "unknown"); counts[k]=counts.get(k,0)+1; total+=1
                if k=="evidence": evidence+=1
        return {"total":total,"by_kind":counts,"evidence":evidence}

    def report(self):
        errors=[]
        try: episodes=self._episodes()
        except Exception as e: episodes=[]; errors.append("episodes: "+str(e))
        try: explorer=self._explorer()
        except Exception as e: explorer={}; errors.append("explorer: "+str(e))
        ev=self._event_stats(); state=self.curiosity.snapshot() if hasattr(self.curiosity,"snapshot") else {}
        if not isinstance(state,dict): state={}
        knowledge=self.knowledge.recent(limit=1)
        event_types={}
        for row in episodes:
            t=str(row.get("event_type") or "unknown"); event_types[t]=event_types.get(t,0)+1
        stats=explorer.get("statistics",{}) if isinstance(explorer,dict) else {}
        explorer_records=int(stats.get("total_entidades",0) or 0) if isinstance(stats,dict) else 0
        persisted=len(episodes); evidence_events=ev["evidence"]; learned=int(knowledge.get("observations",0) or 0)
        diagnosis=[]
        if errors: diagnosis.append("UPSTREAM_ERROR")
        if evidence_events==0: diagnosis.append("CRAWLER_NOT_PRODUCING_EVIDENCE")
        if evidence_events>0 and learned==0: diagnosis.append("LEARNING_NOT_CONSUMING_EVIDENCE")
        if learned>0 and event_types.get("server_knowledge_evidence",0)==0: diagnosis.append("LEARNING_NOT_PERSISTING_TO_BDR")
        if persisted>explorer_records: diagnosis.append("EXPLORER_PROJECTION_TRUNCATED_OR_COLLIDING")
        if persisted==256: diagnosis.append("SUSPECT_256_HISTORY_CAP")
        if not diagnosis: diagnosis=["HEALTHY"]
        payload={"schema":"memoria-growth-diagnostics/v1","generated_at":_now(),"diagnosis":diagnosis,"funnel":{"curiosity_events":ev["total"],"web_evidence":evidence_events,"knowledge_observations":learned,"bdr_history_rows":persisted,"bdr_knowledge_rows":event_types.get("server_knowledge_evidence",0),"explorer_records":explorer_records},"curiosity":state,"event_types":event_types,"event_kinds":ev["by_kind"],"explorer_statistics":stats,"errors":errors,"last_probe":self._load().get("last_probe")}
        self._save(payload); return payload

    def probe(self):
        before=self.report(); probe_id="diagnostic:"+uuid.uuid4().hex
        payload={"episode_id":probe_id,"role":"assistant","text":"Synthetic growth diagnostic "+probe_id,"session_id":"server:growth-diagnostic","order":int(time.time()*1000),"timestamp":_now(),"event_type":"growth_diagnostic_probe","topics":["diagnostic","growth"]}
        data=json.dumps(payload,separators=(",",":")).encode(); headers={"Content-Type":"application/json"}
        if self.config.memoria_api_key: headers["X-Memoria-Key"]=self.config.memoria_api_key
        status=None; detail=""; started=time.monotonic()
        try:
            lock=self.write_lock
            if lock: lock.acquire()
            try:
                with urlopen(Request(self.config.memoria_api_url+"/api/v1/episodes",data=data,headers=headers,method="POST"),timeout=15) as r:
                    status=r.status; detail=r.read().decode("utf-8",errors="replace")[:1000]
            finally:
                if lock: lock.release()
        except HTTPError as e: status=e.code; detail=e.read().decode("utf-8",errors="replace")[:2000]
        except Exception as e: detail=repr(e)
        elapsed=round((time.monotonic()-started)*1000,1); time.sleep(.15)
        try: rows=self._episodes(); found=any(str(x.get("episode_id"))==probe_id for x in rows)
        except Exception: found=False
        after=self.report(); probe={"id":probe_id,"http_status":status,"stored_and_read_back":found,"latency_ms":elapsed,"response":detail,"before_rows":before["funnel"]["bdr_history_rows"],"after_rows":after["funnel"]["bdr_history_rows"],"passed":status in (200,201) and found}
        final=after; final["last_probe"]=probe
        if not probe["passed"]: final["diagnosis"]=[x for x in final["diagnosis"] if x!="HEALTHY"]+["BDR_SYNTHETIC_WRITE_FAILED"]
        self._save(final); return final

    def _load(self):
        try: return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception: return {}
    def _save(self,p):
        tmp=self.path.with_suffix(".tmp"); tmp.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(self.path)

    def dispatch(self,handler,path,query):
        if path!=PREFIX: return False
        if handler.command=="GET": handler._write_json(200,self.report()); return True
        if handler.command=="POST": handler._write_json(200,self.probe()); return True
        handler._write_json(405,{"error":"method_not_allowed"},{"Allow":"GET, POST"}); return True
