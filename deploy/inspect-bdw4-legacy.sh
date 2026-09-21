#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="${MEMORIA_SERVER_DIR:-$HOME/memoria.ia.server}"
cd "$PROJECT"

echo "==============================================="
echo " M.IA.SERVER - BDW4 legacy inspector"
echo " modo: somente leitura"
echo "==============================================="

MEMORIA_ID="$(docker compose ps -q memoria)"
SERVER_ID="$(docker compose ps -q server)"
if [ -z "$MEMORIA_ID" ]; then
  echo "ERRO: container memoria nao localizado"
  exit 1
fi
if [ -z "$SERVER_ID" ]; then
  echo "ERRO: container server nao localizado"
  exit 1
fi

MEMORIA_VOLUME="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' "$MEMORIA_ID")"
SERVER_IMAGE="$(docker inspect -f '{{.Config.Image}}' "$SERVER_ID")"

if [ -z "$MEMORIA_VOLUME" ]; then
  echo "ERRO: volume memoria:/data nao localizado"
  exit 1
fi
if [ -z "$SERVER_IMAGE" ]; then
  echo "ERRO: imagem do server nao localizada"
  exit 1
fi

echo "memoria_container=$MEMORIA_ID"
echo "memoria_volume=$MEMORIA_VOLUME"
echo "inspector_image=$SERVER_IMAGE"
echo

docker run --rm -i   -v "$MEMORIA_VOLUME:/data:ro"   --entrypoint python   "$SERVER_IMAGE" - <<'PY'
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import struct
import zlib

ROOT = Path("/data")
MAX_FRAME = 1 << 27
MIN_FRAME = 28

paths = sorted(ROOT.rglob("atomic.bdw4"))
if not paths:
    print(json.dumps({
        "schema":"memoria-bdw4-inspection/v1",
        "status":"no_wal_found",
        "root":str(ROOT),
        "read_only":True,
    }, indent=2))
    raise SystemExit(0)

reports = []

for path in paths:
    data = path.read_bytes()
    pos = 0
    frame = 0
    sequences = []
    first_error = None
    torn_tail = False
    strict_last = 0
    compatible_last = 0
    legacy_head_duplicate = False
    compatible = True
    anomalies = []
    duplicate_count = 0
    regression_count = 0
    forward_gap_count = 0
    crc_valid_frames = 0
    operation_count_total = 0

    while pos < len(data):
        if len(data) - pos < 4:
            torn_tail = True
            break

        total = struct.unpack(">I", data[pos:pos+4])[0]
        if total < MIN_FRAME or total > MAX_FRAME:
            first_error = {
                "frame": frame + 1,
                "offset": pos,
                "reason": "total_length_invalid",
                "total": total,
            }
            compatible = False
            break

        if len(data) - pos < total:
            torn_tail = True
            break

        raw = data[pos:pos+total]
        frame += 1

        if raw[4:8] != b"BDW4":
            first_error = {"frame":frame,"offset":pos,"reason":"magic_mismatch"}
            compatible = False
            break

        version = struct.unpack(">I", raw[8:12])[0]
        if version != 4:
            first_error = {"frame":frame,"offset":pos,"reason":"version_unsupported","version":version}
            compatible = False
            break

        expected_crc = struct.unpack(">I", raw[-4:])[0]
        actual_crc = zlib.crc32(raw[:-4]) & 0xFFFFFFFF
        if expected_crc != actual_crc:
            first_error = {
                "frame":frame,
                "offset":pos,
                "reason":"crc_mismatch",
                "expected_crc":expected_crc,
                "actual_crc":actual_crc,
            }
            compatible = False
            break
        crc_valid_frames += 1

        sequence = struct.unpack(">Q", raw[12:20])[0]
        count = struct.unpack(">I", raw[20:24])[0]
        if count == 0 or count > 1_000_000:
            first_error = {
                "frame":frame,
                "offset":pos,
                "reason":"operation_count_invalid",
                "count":count,
            }
            compatible = False
            break
        operation_count_total += count
        sequences.append(sequence)

        # Strict RC1 rule plus a complete anomaly map. We intentionally
        # report hashes/counts only; key/value payloads are never emitted.
        if frame > 1:
            delta = sequence - strict_last
            if delta != 1:
                if delta == 0:
                    kind = "duplicate"
                    duplicate_count += 1
                elif delta < 0:
                    kind = "regression"
                    regression_count += 1
                else:
                    kind = "forward_gap"
                    forward_gap_count += 1
                anomaly = {
                    "frame": frame,
                    "offset": pos,
                    "kind": kind,
                    "previous_sequence": strict_last,
                    "sequence": sequence,
                    "expected": strict_last + 1,
                    "delta": delta,
                    "operation_count": count,
                    "frame_sha256": hashlib.sha256(raw).hexdigest(),
                }
                if len(anomalies) < 128:
                    anomalies.append(anomaly)
                if first_error is None:
                    first_error = {
                        "frame":frame,
                        "offset":pos,
                        "reason":"strict_sequence_gap",
                        "previous_sequence":strict_last,
                        "sequence":sequence,
                        "expected":strict_last + 1,
                    }
        strict_last = sequence

        # RC3 bounded compatibility:
        # only the exact head prefix 1,1 is accepted; after that monotonic +1.
        if frame == 1:
            if sequence != 1:
                compatible = False
        elif frame == 2 and sequences[0] == 1 and sequence == 1:
            legacy_head_duplicate = True
            compatible_last = 1
        else:
            expected = compatible_last + 1
            if sequence != expected:
                compatible = False
        if frame == 1:
            compatible_last = sequence
        elif not (frame == 2 and legacy_head_duplicate):
            compatible_last = sequence

        pos += total

    complete_bytes = pos
    seq_head = sequences[:20]
    seq_tail = sequences[-20:] if len(sequences) > 20 else list(sequences)
    bounded_single_adjacent_duplicate_compatible = bool(
        not torn_tail
        and complete_bytes == len(data)
        and frame == len(sequences)
        and bool(sequences)
        and sequences[0] == 1
        and duplicate_count == 1
        and regression_count == 0
        and forward_gap_count == 0
    )

    reports.append({
        "path":str(path),
        "bytes":len(data),
        "complete_bytes":complete_bytes,
        "frames_parsed":frame,
        "crc_valid_frames":crc_valid_frames,
        "operations_declared":operation_count_total,
        "sequence_head":seq_head,
        "sequence_tail":seq_tail,
        "duplicate_count": duplicate_count,
        "regression_count": regression_count,
        "forward_gap_count": forward_gap_count,
        "anomalies": anomalies,
        "strict_rc1_valid":first_error is None,
        "first_strict_or_structural_error":first_error,
        "legacy_head_duplicate_1_1":legacy_head_duplicate,
        "bounded_rc3_compatible":bool(compatible and legacy_head_duplicate and not torn_tail),
        "bounded_single_adjacent_duplicate_compatible":bounded_single_adjacent_duplicate_compatible,
        "torn_tail":torn_tail,
    })

print(json.dumps({
    "schema":"memoria-bdw4-inspection/v1",
    "status":"ok",
    "read_only":True,
    "wal_count":len(reports),
    "reports":reports,
}, ensure_ascii=False, indent=2))
PY

echo
echo "INSPECAO CONCLUIDA"
echo "Nenhum arquivo do volume foi aberto para escrita."
echo "Nenhum container foi parado, reiniciado ou reconstruido."
