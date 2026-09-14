"""Background bridge from evidence streams into persistent Server Knowledge."""
from __future__ import annotations

import json
from pathlib import Path
from threading import Event, Thread
import time


class LearningWorker:
    def __init__(self, knowledge, curiosity_data_dir: str, poll_seconds: float = 2.0) -> None:
        self.knowledge = knowledge
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
                self.offset = fh.tell()
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("kind") != "evidence":
                    continue
                result = self.knowledge.learn_from_evidence(event)
                if result.get("learned"):
                    learned += int(result["learned"])
                    print(f"[learning] evidence -> {result['learned']} conceito(s): {', '.join(result['keys'][:5])}")
        self._save_cursor()
        return learned

    def _loop(self) -> None:
        print("[learning] Server Knowledge worker iniciado.")
        while not self._stop.is_set():
            try:
                self.cycle_once()
            except Exception as exc:
                print(f"[learning] error: {exc}")
            self._stop.wait(self.poll_seconds)
