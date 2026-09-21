#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(mktemp -d)"
MEMORIA_SMOKE_CONTAINER=""
MEMORIA_SMOKE_VOLUME=""
MEMORIA_SMOKE_NETWORK=""

cleanup() {
  rc=$?
  if [[ -n "$MEMORIA_SMOKE_CONTAINER" ]]; then
    docker rm -f "$MEMORIA_SMOKE_CONTAINER" >/dev/null 2>&1 || true
  fi
  if [[ -n "$MEMORIA_SMOKE_VOLUME" ]]; then
    docker volume rm "$MEMORIA_SMOKE_VOLUME" >/dev/null 2>&1 || true
  fi
  if [[ -n "$MEMORIA_SMOKE_NETWORK" ]]; then
    docker network rm "$MEMORIA_SMOKE_NETWORK" >/dev/null 2>&1 || true
  fi
  rm -rf "$ROOT"
  exit "$rc"
}
trap cleanup EXIT
trap 'rc=$?; echo "bit.analyze pipeline smoke FAILED rc=$rc line=$LINENO command=$BASH_COMMAND" >&2' ERR
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

IMAGE="${BIT_ANALYZE_TEST_IMAGE:-memoria-ia-server-bit-analyze}"
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "bit.analyze pipeline smoke: built image not found: $IMAGE" >&2
  docker image ls --format '{{.Repository}}:{{.Tag}} {{.ID}}' >&2
  exit 1
fi

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


if [[ "${STRUCTURAL_RUNTIME_SMOKE:-0}" == "1" ]]; then
  MEMORIA_IMAGE="${MEMORIA_TEST_IMAGE:-memoria-ia-server-memoria}"
  if ! docker image inspect "$MEMORIA_IMAGE" >/dev/null 2>&1; then
    echo "structural runtime smoke: built Memoria image not found: $MEMORIA_IMAGE" >&2
    docker image ls --format '{{.Repository}}:{{.Tag}} {{.ID}}' >&2
    exit 1
  fi

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

  SUFFIX="$$"
  MEMORIA_SMOKE_CONTAINER="memoria-structural-smoke-$SUFFIX"
  MEMORIA_SMOKE_VOLUME="memoria-structural-smoke-data-$SUFFIX"
  MEMORIA_SMOKE_NETWORK="memoria-structural-smoke-net-$SUFFIX"
  docker volume create "$MEMORIA_SMOKE_VOLUME" >/dev/null
  docker network create "$MEMORIA_SMOKE_NETWORK" >/dev/null

  docker run -d     --name "$MEMORIA_SMOKE_CONTAINER"     --network "$MEMORIA_SMOKE_NETWORK"     --network-alias memoria     -e MEMORIA_ORGANIZATION_ID=ci-structural     -e MEMORIA_ORGANIZATION_NAME='CI Structural Smoke'     -e MEMORIA_API_KEY=ci-structural-key     -e MEMORIA_DATA_DIR=/data     -e MEMORIA_CONVERSATION_RUNTIME=native     -e MEMORIA_EPISODIC_RUNTIME=native     -e MEMORIA_NATIVE_LIB=/usr/local/lib/libmemoria_mobile.so     -v "$MEMORIA_SMOKE_VOLUME:/data"     "$MEMORIA_IMAGE" >/dev/null

  python3 - "$MEMORIA_SMOKE_CONTAINER" <<'PY'
import subprocess, sys, time
container = sys.argv[1]
code = (
    "import urllib.request;"
    "urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health',timeout=3).read()"
)
for _ in range(60):
    result = subprocess.run(
        ["docker", "exec", container, "python", "-c", code],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode == 0:
        break
    time.sleep(1)
else:
    raise SystemExit("Memoria structural smoke did not become healthy")
PY

  BEFORE="$(
    docker run --rm       --network "$MEMORIA_SMOKE_NETWORK"       -v "$EVENTS_FILE:/events.jsonl:ro"       -e MEMORIA_API_KEY=ci-structural-key       --entrypoint python       "$MEMORIA_IMAGE"       - /events.jsonl "$HIERARCHY_ID" <<'PY'
import json, os, sys, urllib.parse, urllib.request

events_path, hierarchy_id = sys.argv[1:3]
rows = [
    json.loads(line)
    for line in open(events_path, encoding="utf-8")
    if line.strip()
]
rows = [row for row in rows if row.get("trail")]
assert len(rows) >= 2, "need at least two non-empty StructuralEvents"
rows = rows[:2]

base = "http://memoria:8080"
key = os.environ["MEMORIA_API_KEY"]

def request(path, *, method="GET", body=None):
    headers = {"X-Memoria-Key": key, "Content-Type": "application/json"}
    data = None if body is None else json.dumps(body, separators=(",", ":")).encode()
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.status, json.loads(response.read().decode())

for index, event in enumerate(rows):
    status, body = request(
        "/api/v1/structural/observations",
        method="POST",
        body={
            "event": event,
            "provenance": {
                "hierarchy_id": hierarchy_id,
                "capture_id": f"deployment-smoke:{index}",
                "kind": "bit_analyze_deployment_smoke",
            },
        },
    )
    assert status == 201, body
    assert body["association_sync_observations"] == 1, body

source = int(rows[0]["trail"][0])
target = int(rows[1]["trail"][0])
query = (
    "/api/v1/structural/associations?"
    + urllib.parse.urlencode(
        {
            "hierarchy_id": hierarchy_id,
            "source": source,
            "channel": "temporal",
            "limit": 100,
        }
    )
)
status, body = request(query)
assert status == 200, body
matches = [
    row for row in body["associations"]
    if int(row["target"]) == target and row["channel"] == "temporal"
]
assert matches and float(matches[0]["weight"]) > 0.0, body
weight = float(matches[0]["weight"])

# Re-delivery of the same raw observation must not strengthen the field.
status, duplicate = request(
    "/api/v1/structural/observations",
    method="POST",
    body={
        "event": rows[0],
        "provenance": {
            "hierarchy_id": hierarchy_id,
            "capture_id": "deployment-smoke:0",
            "kind": "bit_analyze_deployment_smoke",
        },
    },
)
assert status == 201, duplicate
assert duplicate["duplicate"] is True, duplicate
assert duplicate["association_sync_observations"] == 0, duplicate
_, after_duplicate = request(query)
same = [
    row for row in after_duplicate["associations"]
    if int(row["target"]) == target and row["channel"] == "temporal"
]
assert same and float(same[0]["weight"]) == weight, after_duplicate

_, runtime = request("/api/v1/structural/associations/status")
assert runtime["derived_observations"] == 2, runtime
assert runtime["pending_observations"] == 0, runtime
print(json.dumps({"source": source, "target": target, "weight": weight, "query": query}))
PY
  )"

  docker restart "$MEMORIA_SMOKE_CONTAINER" >/dev/null

  python3 - "$MEMORIA_SMOKE_CONTAINER" <<'PY'
import subprocess, sys, time
container = sys.argv[1]
code = (
    "import urllib.request;"
    "urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health',timeout=3).read()"
)
for _ in range(60):
    result = subprocess.run(
        ["docker", "exec", container, "python", "-c", code],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode == 0:
        break
    time.sleep(1)
else:
    raise SystemExit("restarted Memoria structural smoke did not become healthy")
PY

  docker run --rm     --network "$MEMORIA_SMOKE_NETWORK"     -e MEMORIA_API_KEY=ci-structural-key     -e BEFORE="$BEFORE"     --entrypoint python     "$MEMORIA_IMAGE"     - <<'PY'
import json, os, urllib.request
before = json.loads(os.environ["BEFORE"])
base = "http://memoria:8080"
headers = {"X-Memoria-Key": os.environ["MEMORIA_API_KEY"]}
req = urllib.request.Request(base + before["query"], headers=headers, method="GET")
with urllib.request.urlopen(req, timeout=10) as response:
    body = json.loads(response.read().decode())
matches = [
    row for row in body["associations"]
    if int(row["target"]) == int(before["target"])
    and row["channel"] == "temporal"
]
assert matches, body
assert float(matches[0]["weight"]) == float(before["weight"]), (before, body)

req = urllib.request.Request(
    base + "/api/v1/structural/associations/status",
    headers=headers,
    method="GET",
)
with urllib.request.urlopen(req, timeout=10) as response:
    runtime = json.loads(response.read().decode())
assert runtime["pending_observations"] == 0, runtime
assert runtime["derived_observations"] == 2, runtime
assert runtime["replayed_on_open"] == 0, runtime
print(
    "structural association runtime smoke PASS "
    f"source={before['source']} target={before['target']} weight={before['weight']}"
)
PY
fi
