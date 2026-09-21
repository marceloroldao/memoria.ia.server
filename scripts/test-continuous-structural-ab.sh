#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(mktemp -d)"
trap 'rc=$?; rm -rf "$ROOT"; exit $rc' EXIT
trap 'rc=$?; echo "continuous structural A/B FAILED rc=$rc line=$LINENO command=$BASH_COMMAND" >&2' ERR

SOURCE="$ROOT/source/curiosity/raw-web"
STATE="$ROOT/state"
mkdir -p "$SOURCE/objects/sha256" "$STATE/checkpoints"
chmod -R a+rwx "$STATE"

python3 - "$ROOT/body.bin" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
# Sixteen deterministic 16-byte windows. Each window uses a distinct byte,
# producing distinct real hierarchical symbols after two bit.analyze layers.
path.write_bytes(b"".join(bytes([index + 1]) * 16 for index in range(16)))
PY

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
    "capture_id": "web:continuous-ab",
    "observed_at": "2026-09-21T21:00:00+00:00",
    "byte_offset": 0,
    "byte_length": int(size),
    "sha256": sha,
    "content_type": "application/octet-stream",
    "url": "https://example.invalid/continuous-ab",
    "object_path": rel,
    "provenance": {"kind": "continuous_structural_ab"},
}
with open(path, "w", encoding="utf-8") as fh:
    fh.write(json.dumps(record, separators=(",", ":")) + "\n")
PY

BIT_IMAGE="${BIT_ANALYZE_TEST_IMAGE:-memoria-ia-server-bit-analyze}"
MEMORIA_IMAGE="${MEMORIA_TEST_IMAGE:-memoria-ia-server-memoria}"
for image in "$BIT_IMAGE" "$MEMORIA_IMAGE"; do
  if ! docker image inspect "$image" >/dev/null 2>&1; then
    echo "continuous structural A/B: built image not found: $image" >&2
    exit 1
  fi
done

docker run --rm --network none   -v "$ROOT/source:/source:ro"   -v "$STATE:/state"   --entrypoint python   "$BIT_IMAGE"   /opt/bit-analyze/consume_ingest.py     --spool /source/curiosity/raw-web/bit-analyze-ingest.jsonl     --root /source/curiosity/raw-web     --binary /usr/local/bin/bit_analyze_structural_ingest     --checkpoint-dir /state/checkpoints     --max-records 10     --window 16     --hop 16     --chunk-size 7     --layers 2

EVENTS_REL="$(python3 - "$STATE/checkpoints/current.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
print(data["events_file"])
PY
)"
HIERARCHY_ID="$(python3 - "$STATE/checkpoints/current.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
value = str(data.get("hierarchy_id") or "").strip()
assert value
print(value)
PY
)"
EVENTS_FILE="$STATE/checkpoints/$EVENTS_REL"

docker run --rm   -v "$EVENTS_FILE:/events.jsonl:ro"   --entrypoint python   "$MEMORIA_IMAGE"   - /events.jsonl "$HIERARCHY_ID" <<'PY'
import json
import math
import sys

from memoria_resolutiva.structural_association_field import StructuralAssociationField
from memoria_resolutiva.structural_association_continuous import (
    ContinuousStructuralAssociationField,
)

events_path, hierarchy_id = sys.argv[1:3]
events = [
    json.loads(line)
    for line in open(events_path, encoding="utf-8")
    if line.strip()
]
events = [event for event in events if event.get("trail")]
assert len(events) == 16, len(events)

source = int(events[0]["trail"][0])
target = int(events[10]["trail"][0])

# The deterministic raw windows must give us symbols unique to those positions;
# otherwise this would not isolate the long-lag effect.
source_occurrences = sum(source in event["trail"] for event in events)
target_occurrences = sum(target in event["trail"] for event in events)
assert source_occurrences == 1, source_occurrences
assert target_occurrences == 1, target_occurrences

stable = StructuralAssociationField(
    max_within_distance=8,
    max_event_lag=4,
    forgetting_rate=0,
)
continuous = ContinuousStructuralAssociationField(
    within_decay=0.2,
    temporal_decay=0.2,
    forgetting_rate=0,
    trace_floor=1e-8,
)

for index, event in enumerate(events):
    envelope = {
        "format": "memoria.ia-structural-observation-v1",
        "observation_id": f"continuous-ab:{index}:{event['signature']}",
        "event": event,
        "provenance": {"hierarchy_id": hierarchy_id},
        "semantic_projection": False,
    }
    stable.observe(envelope)
    continuous.observe(envelope)

stable_weight = stable.association(
    hierarchy_id,
    source,
    target,
    channel="temporal",
)
continuous_weight = continuous.association(
    hierarchy_id,
    source,
    target,
    channel="temporal",
)

assert stable_weight == 0.0, stable_weight
assert continuous_weight > 0.0, continuous_weight

# With one unique normalized symbol per window after the real extractor, the
# long-lag contribution follows the event kernel directly.
expected = math.exp(-0.2 * 9.0)
assert abs(continuous_weight - expected) < 1e-12, (
    continuous_weight,
    expected,
)

# The continuous field must preserve a strict causal gradient over the real
# opaque symbols. This checks the field geometry without introducing semantic
# classes, promotion thresholds, grammar rules, or hand-authored relations.
anchors = [int(event["trail"][0]) for event in events]
for anchor in anchors:
    occurrences = sum(anchor in event["trail"] for event in events)
    assert occurrences == 1, (anchor, occurrences)

source_mass = events[0]["trail"].count(source) / float(len(events[0]["trail"]))
normalized_gradient = []
for lag in range(1, len(events)):
    candidate = anchors[lag]
    candidate_mass = events[lag]["trail"].count(candidate) / float(
        len(events[lag]["trail"])
    )
    observed = continuous.association(
        hierarchy_id,
        source,
        candidate,
        channel="temporal",
    )
    predicted = (
        math.exp(-0.2 * float(lag - 1))
        * source_mass
        * candidate_mass
    )
    assert abs(observed - predicted) < 1e-12, (
        lag,
        observed,
        predicted,
    )
    normalized_gradient.append(observed / (source_mass * candidate_mass))

assert all(
    left > right
    for left, right in zip(normalized_gradient, normalized_gradient[1:])
), normalized_gradient

# Repetition must concentrate support naturally. A recurring adjacent pair
# should outrank sparse, rotating distractors using only the same temporal
# dynamics. The test deliberately adds no semantic labels or special-case
# relation rules.
selective = ContinuousStructuralAssociationField(
    within_decay=0.35,
    temporal_decay=0.35,
    forgetting_rate=0.03,
    trace_floor=1e-8,
)
sequence = []
for cycle in range(48):
    sequence.extend((0, 1, 2 + (cycle % (len(events) - 2))))

for index, event_index in enumerate(sequence):
    event = events[event_index]
    selective.observe(
        {
            "format": "memoria.ia-structural-observation-v1",
            "observation_id": (
                f"continuous-selective:{index}:{event_index}:"
                f"{event['signature']}"
            ),
            "event": event,
            "provenance": {"hierarchy_id": hierarchy_id},
            "semantic_projection": False,
        }
    )

repeated_target = anchors[1]
repeated_weight = selective.association(
    hierarchy_id,
    source,
    repeated_target,
    channel="temporal",
)
distractor_weights = {
    anchor: selective.association(
        hierarchy_id,
        source,
        anchor,
        channel="temporal",
    )
    for anchor in anchors[2:]
}
strongest_distractor = max(distractor_weights.values())
assert repeated_weight > strongest_distractor, (
    repeated_weight,
    strongest_distractor,
    distractor_weights,
)

# The new field must remain deterministic over the same real StructuralEvents.
replay = ContinuousStructuralAssociationField(
    within_decay=0.2,
    temporal_decay=0.2,
    forgetting_rate=0,
    trace_floor=1e-8,
)
for index, event in enumerate(events):
    replay.observe(
        {
            "format": "memoria.ia-structural-observation-v1",
            "observation_id": f"continuous-ab:{index}:{event['signature']}",
            "event": event,
            "provenance": {"hierarchy_id": hierarchy_id},
            "semantic_projection": False,
        }
    )
assert replay.snapshot() == continuous.snapshot()

print(
    "continuous structural A/B PASS "
    f"events={len(events)} source={source} target={target} "
    f"stable={stable_weight:.12f} continuous={continuous_weight:.12f} "
    f"horizon={continuous.temporal_horizon}"
)
PY
