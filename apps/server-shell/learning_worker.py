"""Background bridge from curiosity evidence into BDR-backed Server Knowledge."""
from __future__ import annotations

import json
from pathlib import Path
from threading import Event, Thread


class LearningWorker:
    def __init__(self, knowledge, curiosity_data_dir: str, bdr=None, poll_seconds: float = 2.0) -> None:
        self.knowledge = knowledge
        self.bdr = bdr
        self.events_file = Path(curiosity_data_dir) / "events.jsonl"
        self.cursor_file = Path(curiosity_data_dir) / "knowledge.cursor"
        self.poll_seconds = max(0.5, poll_seconds)
        self._stop = Event()
        self._thread = Thread(target=self._loop, daemon=True, name="server-learning-worker")
        self.offset = self._load_cursor()

    def _load_cursor(self) -> int:
        try:
            return max(0, int(self.cursor_file.read_text(encoding="utf-8").strip()))
        except Exception:
            return 0

    def _save_cursor(self) -> None:
        self.cursor_file.parent.mkdir(parents=True, exist_ok=True)
        self.cursor_file.write_text(str(self.offset), encoding="utf-8")

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def rebuild_from_bdr(self) -> dict[str, int] | None:
        if self.bdr is None:
            return None
        rows = self.bdr.load_evidence()
        if not rows:
            return None
        result = self.knowledge.rebuild(rows)
        print(f"[learning] BDR replay -> {result['observations']} evidência(s), {result['concepts']} conceito(s)")
        return result

    def cycle_once(self) -> int:
        if not self.events_file.exists():
            return 0
        size = self.events_file.stat().st_size
        if self.offset > size:
            self.offset = 0
        learned = 0
        with self.events_file.open("r", encoding="utf-8") as fh:
            fh.seek(self.offset)
            while True:
                line = fh.readline()
                if not line:
                    break
                next_offset = fh.tell()
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    self.offset = next_offset
                    continue
                if event.get("kind") != "evidence":
                    self.offset = next_offset
                    continue
                # Canonical durability first: only advance the cursor after BDR accepts the evidence.
                if self.bdr is not None:
                    self.bdr.append_evidence(event)
                result = self.knowledge.learn_from_evidence(event)
                self.offset = next_offset
                if result.get("learned"):
                    learned += int(result["learned"])
                    suffix = f"; filtrados={result.get('filtered', 0)}" if result.get("filtered") else ""
                    print(f"[learning] BDR+knowledge -> {result['learned']} conceito(s): {', '.join(result['keys'][:5])}{suffix}")
        self._save_cursor()
        return learned

    def _loop(self) -> None:
        print("[learning] Server Knowledge worker iniciado (BDR canonical).")
        try:
            self.rebuild_from_bdr()
        except Exception as exc:
            print(f"[learning] BDR replay indisponível: {exc}")
        while not self._stop.is_set():
            try:
                self.cycle_once()
            except Exception as exc:
                print(f"[learning] error: {exc}")
            self._stop.wait(self.poll_seconds)
