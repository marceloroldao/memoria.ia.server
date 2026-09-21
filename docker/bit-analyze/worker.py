from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time


def env_int(name: str, default: int, minimum: int = 1) -> int:
    return max(minimum, int(os.getenv(name, str(default))))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


STATE_DIR = Path(os.getenv("BIT_ANALYZE_STATE_DIR", "/state"))
STATUS_FILE = STATE_DIR / "worker-status.json"
SPOOL = Path(os.getenv("BIT_ANALYZE_SPOOL", "/source/curiosity/raw-web/bit-analyze-ingest.jsonl"))
RAW_ROOT = Path(os.getenv("BIT_ANALYZE_RAW_ROOT", "/source/curiosity/raw-web"))
CHECKPOINT_DIR = Path(os.getenv("BIT_ANALYZE_CHECKPOINT_DIR", "/state/checkpoints"))
BINARY = os.getenv("BIT_ANALYZE_BINARY", "/usr/local/bin/bit_analyze_structural_ingest")
CONSUMER = os.getenv("BIT_ANALYZE_CONSUMER", "/opt/bit-analyze/consume_ingest.py")
INTERVAL = env_int("BIT_ANALYZE_INTERVAL_SECONDS", 5)
MAX_RECORDS = env_int("BIT_ANALYZE_MAX_RECORDS", 100)
WINDOW = env_int("BIT_ANALYZE_WINDOW_BYTES", 4096)
HOP = env_int("BIT_ANALYZE_HOP_BYTES", 4096)
CHUNK = env_int("BIT_ANALYZE_CHUNK_BYTES", 65536)
LAYERS = env_int("BIT_ANALYZE_LAYERS", 2)


def write_status(payload: dict[str, object]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATUS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, STATUS_FILE)


def main() -> None:
    failures = 0
    last_success = None
    while True:
        if not SPOOL.is_file():
            write_status({
                "schema": "bit-analyze-worker-status/v1",
                "status": "waiting",
                "time": now(),
                "last_success_at": last_success,
                "consecutive_failures": failures,
                "reason": "ingest_spool_not_created_yet",
                "spool": str(SPOOL),
            })
            time.sleep(INTERVAL)
            continue

        command = [
            "python", CONSUMER,
            "--spool", str(SPOOL),
            "--root", str(RAW_ROOT),
            "--binary", BINARY,
            "--checkpoint-dir", str(CHECKPOINT_DIR),
            "--max-records", str(MAX_RECORDS),
            "--window", str(WINDOW),
            "--hop", str(HOP),
            "--chunk-size", str(CHUNK),
            "--layers", str(LAYERS),
        ]
        started = time.monotonic()
        completed = subprocess.run(command, check=False)
        elapsed_ms = round((time.monotonic() - started) * 1000, 1)

        if completed.returncode == 0:
            failures = 0
            last_success = now()
            write_status({
                "schema": "bit-analyze-worker-status/v1",
                "status": "healthy",
                "time": last_success,
                "last_success_at": last_success,
                "consecutive_failures": 0,
                "last_cycle_ms": elapsed_ms,
                "spool": str(SPOOL),
                "checkpoint_dir": str(CHECKPOINT_DIR),
            })
            time.sleep(INTERVAL)
            continue

        failures += 1
        write_status({
            "schema": "bit-analyze-worker-status/v1",
            "status": "degraded",
            "time": now(),
            "last_success_at": last_success,
            "consecutive_failures": failures,
            "last_exit_code": completed.returncode,
            "last_cycle_ms": elapsed_ms,
            "spool": str(SPOOL),
            "checkpoint_dir": str(CHECKPOINT_DIR),
        })
        time.sleep(min(60, INTERVAL * (2 ** min(failures, 4))))


if __name__ == "__main__":
    main()
