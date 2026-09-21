#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(mktemp -d)"
trap 'rc=$?; rm -rf "$ROOT"; exit $rc' EXIT
trap 'rc=$?; echo "physical temporal pipeline FAILED rc=$rc line=$LINENO command=$BASH_COMMAND" >&2' ERR

SOURCE="$ROOT/source/curiosity/raw-web"
STATE="$ROOT/state"
BRIDGE_DATA="$ROOT/bridge-data"
PAYLOADS="$ROOT/bridge-payloads.jsonl"
mkdir -p "$SOURCE/objects/sha256" "$STATE/checkpoints" "$BRIDGE_DATA"
chmod -R a+rwx "$STATE"

python3 - "$SOURCE" <<'PY'
from pathlib import Path
import hashlib
import json
import sys

root = Path(sys.argv[1])
rows = [
    ("near-a", 1, "sensor:near", 0.0),
    ("near-b", 2, "sensor:near", 0.01),
    ("far-a", 3, "sensor:far", 0.0),
    ("far-b", 4, "sensor:far", 5.0),
]
spool = root / "bit-analyze-ingest.jsonl"
with spool.open("w", encoding="utf-8") as fh:
    for capture_id, byte_value, clock_id, stamp in rows:
        data = bytes([byte_value]) * 16
        sha = hashlib.sha256(data).hexdigest()
        rel = Path("objects") / "sha256" / sha[:2] / f"{sha}.bin"
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        record = {
            "schema": "bit-analyze-ingest/v1",
            "source_id": f"raw:sha256:{sha}",
            "capture_id": f"slice:{capture_id}",
            "observed_at": "2026-09-21T23:00:00+00:00",
            "byte_offset": 0,
            "byte_length": len(data),
            "sha256": sha,
            "content_type": "application/octet-stream",
            "object_path": rel.as_posix(),
            "provenance": {
                "kind": "physical_temporal_pipeline",
                "temporal": {
                    "clock_id": clock_id,
                    "t_start": stamp,
                    "t_end": stamp,
                    "unit": "s",
                },
            },
        }
        fh.write(json.dumps(record, separators=(",", ":")) + "\n")
PY

BIT_IMAGE="${BIT_ANALYZE_TEST_IMAGE:-memoria-ia-server-bit-analyze}"
MEMORIA_IMAGE="${MEMORIA_TEST_IMAGE:-memoria-ia-server-memoria}"
for image in "$BIT_IMAGE" "$MEMORIA_IMAGE"; do
  if ! docker image inspect "$image" >/dev/null 2>&1; then
    echo "physical temporal pipeline: built image not found: $image" >&2
    exit 1
  fi
done

docker run --rm --network none \
  -v "$ROOT/source:/source:ro" \
  -v "$STATE:/state" \
  --entrypoint python \
  "$BIT_IMAGE" \
  /opt/bit-analyze/consume_ingest.py \
    --spool /source/curiosity/raw-web/bit-analyze-ingest.jsonl \
    --root /source/curiosity/raw-web \
    --binary /usr/local/bin/bit_analyze_structural_ingest \
    --checkpoint-dir /state/checkpoints \
    --max-records 10 \
    --window 16 \
    --hop 16 \
    --chunk-size 7 \
    --layers 2

python3 - "$STATE/checkpoints/current.json" <<'PY'
import json
import sys

checkpoint = json.load(open(sys.argv[1], encoding="utf-8"))
sources = checkpoint["sources"]
assert len(sources) == 4, len(sources)
expected = [
    ("sensor:near", 0.0),
    ("sensor:near", 0.01),
    ("sensor:far", 0.0),
    ("sensor:far", 5.0),
]
for row, (clock_id, stamp) in zip(sources, expected):
    temporal = row["temporal"]
    assert temporal == {
        "clock_id": clock_id,
        "t_start": stamp,
        "t_end": stamp,
        "unit": "s",
    }, temporal
PY

python3 - "$STATE" "$BRIDGE_DATA" "$PAYLOADS" <<'PY'
import json
from pathlib import Path
import sys

sys.path.insert(0, "apps/server-shell")
from structural_observation_bridge import StructuralObservationBridge

state = Path(sys.argv[1])
bridge_data = Path(sys.argv[2])
out = Path(sys.argv[3])
delivered = []
bridge = StructuralObservationBridge(
    state,
    bridge_data,
    "http://memoria.invalid",
    "unused",
    sender=lambda payload: delivered.append(payload) or {"stored": True},
)
status = bridge.run_once()
assert status["status"] == "healthy", status
assert len(delivered) == 4, len(delivered)
expected = [
    ("sensor:near", 0.0),
    ("sensor:near", 0.01),
    ("sensor:far", 0.0),
    ("sensor:far", 5.0),
]
for payload, (clock_id, stamp) in zip(delivered, expected):
    temporal = payload["provenance"]["temporal"]
    assert temporal["clock_id"] == clock_id, temporal
    assert float(temporal["t_start"]) == stamp, temporal
    assert float(temporal["t_end"]) == stamp, temporal
    assert temporal["unit"] == "s", temporal
with out.open("w", encoding="utf-8") as fh:
    for payload in delivered:
        fh.write(json.dumps(payload, separators=(",", ":")) + "\n")
PY

docker run --rm \
  -v "$PAYLOADS:/payloads.jsonl:ro" \
  --entrypoint python \
  "$MEMORIA_IMAGE" \
  - /payloads.jsonl <<'PY'
import json
import math
import sys

from memoria_resolutiva.structural_association_continuous import (
    ContinuousStructuralAssociationField,
)

payloads = [
    json.loads(line)
    for line in open(sys.argv[1], encoding="utf-8")
    if line.strip()
]
assert len(payloads) == 4

anchors = [int(payload["event"]["trail"][0]) for payload in payloads]
assert len(set(anchors)) == 4, anchors
for anchor in anchors:
    assert sum(anchor in payload["event"]["trail"] for payload in payloads) == 1, anchor

field = ContinuousStructuralAssociationField(
    within_decay=0.35,
    temporal_decay=0.35,
    physical_time_decay=1.0,
    forgetting_rate=0,
    trace_floor=1e-8,
)
for index, payload in enumerate(payloads):
    field.observe(
        {
            "format": "memoria.ia-structural-observation-v1",
            "observation_id": f"physical-pipeline:{index}:{payload['event']['signature']}",
            "event": payload["event"],
            "provenance": payload["provenance"],
            "semantic_projection": False,
        }
    )

def mass(payload, symbol):
    trail = payload["event"]["trail"]
    return trail.count(symbol) / float(len(trail))

near = field.association(
    payloads[0]["provenance"]["hierarchy_id"],
    anchors[0],
    anchors[1],
    channel="temporal",
)
far = field.association(
    payloads[2]["provenance"]["hierarchy_id"],
    anchors[2],
    anchors[3],
    channel="temporal",
)
near_expected = math.exp(-0.01) * mass(payloads[0], anchors[0]) * mass(payloads[1], anchors[1])
far_expected = math.exp(-5.0) * mass(payloads[2], anchors[2]) * mass(payloads[3], anchors[3])

cross_near_far = field.association(
    payloads[0]["provenance"]["hierarchy_id"],
    anchors[0],
    anchors[2],
    channel="temporal",
)
cross_near_far_late = field.association(
    payloads[1]["provenance"]["hierarchy_id"],
    anchors[1],
    anchors[3],
    channel="temporal",
)

assert abs(near - near_expected) < 1e-12, (near, near_expected)
assert abs(far - far_expected) < 1e-12, (far, far_expected)
assert near > far, (near, far)
assert cross_near_far == 0.0, cross_near_far
assert cross_near_far_late == 0.0, cross_near_far_late
print(
    "physical temporal pipeline PASS "
    f"near_10ms={near:.12f} far_5s={far:.12f} ratio={near / far:.3f} "
    f"cross_clock={cross_near_far:.12f}"
)
PY
