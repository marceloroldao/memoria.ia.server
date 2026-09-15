from pathlib import Path
import json, sys
SHELL_DIR=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(SHELL_DIR))
from server_knowledge import ServerKnowledge
from learning_worker import LearningWorker

def evidence(url="https://example.org/a",provider="wikipedia",terms=None): return {"kind":"evidence","title":"Controle de motores BLDC","description":"Motores BLDC usam comutação eletrônica e podem ser controlados por FOC.","excerpt":"BLDC FOC motor motor controle controle eletrônica eletrônica","terms":terms or ["bldc","motor","controle","foc"],"provider":provider,"url":url}

def test_learning_persists_and_reinforcement_increases_confidence(tmp_path):
    k=ServerKnowledge(str(tmp_path/"knowledge")); k.learn_from_evidence(evidence()); c1=k.query("BLDC")["hits"][0]["confidence"]; k.learn_from_evidence(evidence("https://example.net/b","arxiv")); assert k.query("BLDC")["hits"][0]["confidence"]>c1

def test_related_terms_are_formed_from_same_observation(tmp_path):
    k=ServerKnowledge(str(tmp_path/"knowledge")); k.learn_from_evidence(evidence()); assert "foc" in dict(k.query("BLDC")["hits"][0]["related"])

def test_wikipedia_navigation_terms_remain_addressed_but_low_weight(tmp_path):
    k=ServerKnowledge(str(tmp_path/"knowledge")); k.learn_from_evidence(evidence(terms=["bldc","motor","editar","página"])); assert k.query("editar")["hits"][0]["semantic_weight"]<k.query("BLDC")["hits"][0]["semantic_weight"]

class FakeBDR:
    def __init__(self,rows=None):self.rows=list(rows or []);self.writes=[]
    def append_evidence(self,event):self.writes.append(event);return "knowledge:test"
    def load_evidence(self,limit=5000):return list(self.rows)
class FailingBDR(FakeBDR):
    def append_evidence(self,event):raise RuntimeError("synthetic BDR outage")

def make_events(tmp_path):
    c=tmp_path/"curiosity"; c.mkdir(); (c/"events.jsonl").write_text(json.dumps({"kind":"topic","message":"x"})+"\n"+json.dumps(evidence(),ensure_ascii=False)+"\n",encoding="utf-8"); return c

def test_learning_worker_persists_to_bdr_before_advancing_cursor(tmp_path):
    c=make_events(tmp_path); k=ServerKnowledge(str(tmp_path/"knowledge")); b=FakeBDR(); w=LearningWorker(k,str(c),bdr=b); assert w.cycle_once()==4; assert len(b.writes)==1; assert w.snapshot()["processed_evidence"]==1

def test_learning_worker_keeps_evidence_pending_on_bdr_failure(tmp_path):
    c=make_events(tmp_path); k=ServerKnowledge(str(tmp_path/"knowledge")); w=LearningWorker(k,str(c),bdr=FailingBDR()); start=w.offset
    try:w.cycle_once()
    except RuntimeError:pass
    else:raise AssertionError("failure expected")
    state=w.snapshot(); assert w.offset>start; assert state["persistence_failures"]==1; assert state["consecutive_failures"]==1; assert state["status"]=="degraded"; assert not k.query("BLDC")["hits"]
    # cursor may pass non-evidence metadata, but must remain before the failed evidence end.
    assert state["backlog_bytes"]>0 and w._retry_delay()>w.poll_seconds

def test_bdr_replay_rebuilds_local_cache(tmp_path):
    k=ServerKnowledge(str(tmp_path/"knowledge")); w=LearningWorker(k,str(tmp_path/"curiosity"),bdr=FakeBDR([evidence(),evidence("https://example.net/b","arxiv")])); r=w.rebuild_from_bdr(); assert r["observations"]==2 and r["concepts"]==4

def test_recent_reports_server_learning_state(tmp_path):
    k=ServerKnowledge(str(tmp_path/"knowledge")); k.learn_from_evidence(evidence()); r=k.recent(); assert r["storage"]=="bdr-canonical/cache" and r["principle"]=="address_first_weight_later"
