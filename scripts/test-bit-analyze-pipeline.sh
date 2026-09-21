#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT
SOURCE="$ROOT/source/curiosity/raw-web"
STATE="$ROOT/state"
mkdir -p "$SOURCE/objects/sha256" "$STATE/checkpoints"
chmod -R a+rwx "$STATE"

printf 'raw-web-structural-smoke-ABABABABABAB\n' > "$ROOT/body.bin"
SHA="$(sha256sum "$ROOT/body.bin" | awk '{print $1}')"
BYTES="$(wc -c < "$ROOT/body.bin" | tr -d ' ')"
PREFIX="$(printf '%s' "$SHA" | cut -c1-2)"
REL="objects/sha256/$PREFIX/$SHA.bin"
mkdir -p "$SOURCE/objects/sha256/$PREFIX"
cp "$ROOT/body.bin" "$SOURCE/$REL"

python3 - "$SOURCE/bit-analyze-ingest.jsonl" "$SHA" "$BYTES" "$REL" <<'PY'
import json, sys
path, sha, size, rel = sys.argv[1:]
record = {
    "schema": "bit-analyze-ingest/v1",
    "source_id": f"raw-web:sha256:{sha}",
    "capture_id": "web:deployment-smoke",
    "observed_at": "2026-09-21T20:00:00+00:00",
    "byte_offset": 0,
    "byte_length": int(size),
    "sha256": sha,
    "content_type": "application/octet-stream",
    "url": "https://example.invalid/smoke",
    "object_path": rel,
    "provenance": {
        "kind": "deployment_smoke",
        "requested_url": "https://example.invalid/smoke",
        "final_url": "https://example.invalid/smoke",
    },
}
with open(path, "w", encoding="utf-8") as fh:
    fh.write(json.dumps(record, separators=(",", ":")) + "\n")
PY

IMAGE="$(docker compose images -q bit-analyze)"
test -n "$IMAGE"

docker run --rm --network none \
  -v "$ROOT/source:/source:ro" \
  -v "$STATE:/state" \
  --entrypoint python \
  "$IMAGE" \
  /opt/bit-analyze/consume_ingest.py \
    --spool /source/curiosity/raw-web/bit-analyze-ingest.jsonl \
    --root /source/curiosity/raw-web \
    --binary /usr/local/bin/bit_analyze_structural_ingest \
    --checkpoint-dir /state/checkpoints \
    --max-records 10 \
    --window 16 \
    --hop 16 \
    --chunk-size 3 \
    --layers 2

python3 - "$STATE/checkpoints/current.json" "$STATE/checkpoints" <<'PY'
import json, pathlib, sys
pointer = pathlib.Path(sys.argv[1])
root = pathlib.Path(sys.argv[2])
data = json.loads(pointer.read_text(encoding="utf-8"))
assert data["cursor_offset"] > 0
assert data["record_count"] == 1
state = root / data["state_file"]
events = root / data["events_file"]
assert state.is_file() and state.stat().st_size > 0
rows = [json.loads(x) for x in events.read_text(encoding="utf-8").splitlines() if x.strip()]
assert rows
assert all(row["source_id"] == "web:deployment-smoke" for row in rows)
assert rows[0]["byte_offset"] == 0
assert rows[0]["byte_length"] > 0
print(f"bit.analyze pipeline smoke PASS events={len(rows)} cursor={data['cursor_offset']}")
PY
