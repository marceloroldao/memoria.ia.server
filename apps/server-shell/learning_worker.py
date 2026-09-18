"""Background bridge from curiosity evidence into BDR-backed Server Knowledge."""
from __future__ import annotations
import json, time
from pathlib import Path
from contextlib import contextmanager
from threading import Event, RLock, Thread

class LearningWorker:
    def __init__(self, knowledge, curiosity_data_dir: str, bdr=None, feedback=None, poll_seconds: float=2.0, max_evidence_per_cycle: int=5) -> None:
        self.knowledge=knowledge; self.bdr=bdr; self.feedback=feedback; self.events_file=Path(curiosity_data_dir)/"events.jsonl"; self.cursor_file=Path(curiosity_data_dir)/"knowledge.cursor"
        self.poll_seconds=max(.5,poll_seconds); self.max_evidence_per_cycle=max(1,int(max_evidence_per_cycle)); self._stop=Event(); self._cycle_lock=RLock(); self._thread=Thread(target=self._loop,daemon=True,name="server-learning-worker"); self.offset=self._load_cursor()
        self.processed_evidence=0; self.learned_symbols=0; self.persistence_failures=0; self.consecutive_failures=0; self.feedback_failures=0; self.last_error=None; self.last_success_at=None; self.last_cycle_ms=0.0
    def _load_cursor(self):
        try:return max(0,int(self.cursor_file.read_text(encoding="utf-8").strip()))
        except Exception:return 0
    def _save_cursor(self): self.cursor_file.parent.mkdir(parents=True,exist_ok=True); self.cursor_file.write_text(str(self.offset),encoding="utf-8")
    def start(self): self._thread.start()
    def stop(self): self._stop.set()
    def backlog_bytes(self):
        try:return max(0,self.events_file.stat().st_size-self.offset)
        except OSError:return 0
    def snapshot(self):
        return {"status":"degraded" if self.consecutive_failures else "healthy","cursor":self.offset,"backlog_bytes":self.backlog_bytes(),"processed_evidence":self.processed_evidence,"learned_symbols":self.learned_symbols,"persistence_failures":self.persistence_failures,"feedback_failures":self.feedback_failures,"consecutive_failures":self.consecutive_failures,"last_error":self.last_error,"last_success_at":self.last_success_at,"last_cycle_ms":self.last_cycle_ms}
    def rebuild_from_bdr(self):
        if self.bdr is None:return None
        rows=self.bdr.load_evidence()
        if not rows:return None
        result=self.knowledge.rebuild(rows); print(f"[learning] BDR replay -> {result['observations']} evidência(s), {result['concepts']} conceito(s)"); return result
    def _emit_feedback(self,event,result):
        if self.feedback is None:return
        try:self.feedback(event,result)
        except Exception as exc:self.feedback_failures+=1; print(f"[learning] feedback error: {exc}")
    @contextmanager
    def quiesced(self):
        self._cycle_lock.acquire()
        try:
            yield
        finally:
            self._cycle_lock.release()
    def reset_to_current_end(self):
        with self._cycle_lock:
            try:self.offset=self.events_file.stat().st_size
            except OSError:self.offset=0
            self._save_cursor()
            self.processed_evidence=0; self.learned_symbols=0; self.persistence_failures=0; self.consecutive_failures=0; self.feedback_failures=0; self.last_error=None
            return self.offset
    def cycle_once(self):
        with self._cycle_lock:
            return self._cycle_once_unlocked()
    def _cycle_once_unlocked(self):
        started=time.monotonic()
        if not self.events_file.exists():return 0
        size=self.events_file.stat().st_size
        if self.offset>size:self.offset=0
        learned=0; processed=0
        with self.events_file.open("r",encoding="utf-8") as fh:
            fh.seek(self.offset)
            while processed<self.max_evidence_per_cycle:
                line=fh.readline()
                if not line:break
                next_offset=fh.tell()
                try:event=json.loads(line)
                except json.JSONDecodeError:self.offset=next_offset; continue
                if event.get("kind")!="evidence":self.offset=next_offset; continue
                try:
                    if self.bdr is not None:self.bdr.append_evidence(event)
                except Exception as exc:
                    self.persistence_failures+=1; self.consecutive_failures+=1; self.last_error=str(exc); self.last_cycle_ms=round((time.monotonic()-started)*1000,1); raise
                result=self.knowledge.learn_from_evidence(event); self.offset=next_offset; processed+=1; self.processed_evidence+=1; self.consecutive_failures=0; self.last_error=None; self.last_success_at=time.time(); self._emit_feedback(event,result)
                if result.get("learned"):
                    count=int(result["learned"]); learned+=count; self.learned_symbols+=count; print(f"[learning] BDR+knowledge -> {count} conceito(s): {', '.join(result['keys'][:5])}")
        self._save_cursor(); self.last_cycle_ms=round((time.monotonic()-started)*1000,1); return learned
    def _retry_delay(self):
        return self.poll_seconds if not self.consecutive_failures else min(60.0,self.poll_seconds*(2**min(self.consecutive_failures,5)))
    def _loop(self):
        print("[learning] Server Knowledge worker iniciado (BDR canonical).")
        try:self.rebuild_from_bdr()
        except Exception as exc:print(f"[learning] BDR replay indisponível: {exc}")
        while not self._stop.is_set():
            try:self.cycle_once()
            except Exception as exc:print(f"[learning] error: {exc}; retry={self._retry_delay():.1f}s")
            self._stop.wait(self._retry_delay())
