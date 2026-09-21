#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="${MEMORIA_SERVER_DIR:-$HOME/memoria.ia.server}"
cd "$PROJECT"

echo "============================================================"
echo " M.IA.SERVER - BDW4 frame 600/601 forensic inspector"
echo " modo: somente leitura"
echo "============================================================"

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

docker run --rm -i \
  -v "$MEMORIA_VOLUME:/data:ro" \
  --entrypoint python \
  "$SERVER_IMAGE" - <<'PY'
from __future__ import annotations

from pathlib import Path
from collections import Counter
import hashlib
import json
import struct
import zlib

ROOT = Path("/data")
TARGETS = (600, 601)
MAX_TARGET = max(TARGETS)

MIN_FRAME = 28
MAX_FRAME = 1 << 27
MAX_KEY = 1 << 20
MAX_VALUE = 1 << 24
SUPPORTED_VERSION = 4


def be32(buf: bytes, start: int) -> int:
    return struct.unpack(">I", buf[start:start + 4])[0]


def be64(buf: bytes, start: int) -> int:
    return struct.unpack(">Q", buf[start:start + 8])[0]


def sha256_hex(buf: bytes) -> str:
    return hashlib.sha256(buf).hexdigest()


def parse_operations(raw: bytes, count: int) -> dict:
    payload_end = len(raw) - 4
    cursor = 24
    operations = []

    for index in range(1, count + 1):
        if cursor + 9 > payload_end:
            raise ValueError(f"operation_header_truncated:index={index}")

        op_start = cursor
        raw_type = raw[cursor]
        cursor += 1
        key_len = be32(raw, cursor)
        cursor += 4
        value_len = be32(raw, cursor)
        cursor += 4

        if raw_type not in (1, 2):
            raise ValueError(f"operation_type_invalid:index={index}:type={raw_type}")
        if key_len == 0 or key_len > MAX_KEY:
            raise ValueError(f"key_length_invalid:index={index}:length={key_len}")
        if value_len > MAX_VALUE:
            raise ValueError(f"value_length_invalid:index={index}:length={value_len}")
        if raw_type == 2 and value_len != 0:
            raise ValueError(f"delete_contains_value:index={index}:length={value_len}")

        payload_size = key_len + value_len
        if cursor + payload_size > payload_end:
            raise ValueError(f"operation_payload_truncated:index={index}")

        # We advance across key/value bytes but never decode, print or return them.
        cursor += payload_size
        op_end = cursor
        op_raw = raw[op_start:op_end]

        operations.append({
            "index": index,
            "type": "put" if raw_type == 1 else "delete",
            "key_bytes": key_len,
            "value_bytes": value_len,
            "serialized_bytes": len(op_raw),
            "fingerprint_sha256": sha256_hex(op_raw),
        })

    if cursor != payload_end:
        raise ValueError(f"trailing_payload_bytes:{payload_end - cursor}")

    operations_region = raw[24:payload_end]
    return {
        "operations": operations,
        "operations_region_sha256": sha256_hex(operations_region),
        "operations_region_bytes": len(operations_region),
    }


def analyze_frame(raw: bytes, frame_index: int, offset: int) -> dict:
    total = len(raw)
    if total < MIN_FRAME or total > MAX_FRAME:
        raise ValueError(f"frame_length_invalid:frame={frame_index}:total={total}")
    if raw[4:8] != b"BDW4":
        raise ValueError(f"magic_mismatch:frame={frame_index}")

    version = be32(raw, 8)
    if version != SUPPORTED_VERSION:
        raise ValueError(f"version_unsupported:frame={frame_index}:version={version}")

    sequence = be64(raw, 12)
    operation_count = be32(raw, 20)
    if operation_count == 0 or operation_count > 1_000_000:
        raise ValueError(
            f"operation_count_invalid:frame={frame_index}:count={operation_count}"
        )

    stored_crc = be32(raw, total - 4)
    computed_crc = zlib.crc32(raw[:-4]) & 0xFFFFFFFF

    parsed = parse_operations(raw, operation_count)

    # Fixed BDW4 frame header is bytes 0..23:
    # total(4), magic(4), version(4), sequence(8), operation_count(4).
    # Zero only sequence bytes 12..19 for a privacy-safe structural comparison.
    normalized_header = raw[:12] + (b"\x00" * 8) + raw[20:24]

    return {
        "frame": frame_index,
        "offset": offset,
        "size_bytes": total,
        "sha256": sha256_hex(raw),
        "version": version,
        "sequence": sequence,
        "operation_count": operation_count,
        "crc32": {
            "stored_hex": f"{stored_crc:08x}",
            "computed_hex": f"{computed_crc:08x}",
            "valid": stored_crc == computed_crc,
        },
        "header_ignoring_sequence_sha256": sha256_hex(normalized_header),
        "operations_region_bytes": parsed["operations_region_bytes"],
        "operations_region_sha256": parsed["operations_region_sha256"],
        "operation_fingerprints": parsed["operations"],
        "_raw": raw,
        "_normalized_header": normalized_header,
    }


def read_targets(path: Path) -> dict[int, dict]:
    found: dict[int, dict] = {}
    offset = 0
    frame_index = 0

    with path.open("rb") as fh:
        while frame_index < MAX_TARGET:
            prefix = fh.read(4)
            if not prefix:
                break
            if len(prefix) != 4:
                raise ValueError(
                    f"truncated_length_prefix:frame={frame_index + 1}:offset={offset}"
                )

            total = struct.unpack(">I", prefix)[0]
            if total < MIN_FRAME or total > MAX_FRAME:
                raise ValueError(
                    f"frame_length_invalid:frame={frame_index + 1}:offset={offset}:total={total}"
                )

            remainder = fh.read(total - 4)
            if len(remainder) != total - 4:
                raise ValueError(
                    f"torn_frame:frame={frame_index + 1}:offset={offset}:total={total}"
                )

            raw = prefix + remainder
            frame_index += 1

            if frame_index in TARGETS:
                found[frame_index] = analyze_frame(raw, frame_index, offset)

            offset += total

    return found


def public_frame(frame: dict) -> dict:
    return {k: v for k, v in frame.items() if not k.startswith("_")}


def compare_pair(a: dict, b: dict) -> dict:
    fp_a = [op["fingerprint_sha256"] for op in a["operation_fingerprints"]]
    fp_b = [op["fingerprint_sha256"] for op in b["operation_fingerprints"]]

    binary_equal = a["_raw"] == b["_raw"]
    header_equal = a["_normalized_header"] == b["_normalized_header"]
    operations_equal_ordered = fp_a == fp_b
    operations_equal_multiset = Counter(fp_a) == Counter(fp_b)

    if binary_equal:
        classification = "physical_duplicate"
    elif a["sequence"] == b["sequence"]:
        classification = "sequence_collision_or_reuse"
    else:
        classification = "distinct_sequences"

    return {
        "binary_equal": binary_equal,
        "header_equal_ignoring_sequence": header_equal,
        "same_sequence": a["sequence"] == b["sequence"],
        "same_size": a["size_bytes"] == b["size_bytes"],
        "same_operation_count": a["operation_count"] == b["operation_count"],
        "operations_equal_ordered": operations_equal_ordered,
        "operations_equal_as_multiset": operations_equal_multiset,
        "operations_region_equal": (
            a["operations_region_sha256"] == b["operations_region_sha256"]
        ),
        "classification": classification,
    }


paths = sorted(ROOT.rglob("atomic.bdw4"))
if not paths:
    print(json.dumps({
        "schema": "memoria-bdw4-frame-pair-inspection/v1",
        "status": "no_wal_found",
        "read_only": True,
        "root": str(ROOT),
        "target_frames": list(TARGETS),
    }, indent=2))
    raise SystemExit(0)

reports = []
for path in paths:
    try:
        found = read_targets(path)
        missing = [frame for frame in TARGETS if frame not in found]
        if missing:
            reports.append({
                "path": str(path),
                "status": "target_frame_missing",
                "missing_frames": missing,
                "frames_found": sorted(found),
            })
            continue

        a = found[TARGETS[0]]
        b = found[TARGETS[1]]
        reports.append({
            "path": str(path),
            "status": "ok",
            "frames": [public_frame(a), public_frame(b)],
            "comparison": compare_pair(a, b),
        })
    except Exception as exc:
        reports.append({
            "path": str(path),
            "status": "error",
            "error": str(exc),
        })

print(json.dumps({
    "schema": "memoria-bdw4-frame-pair-inspection/v1",
    "status": "ok" if all(r["status"] == "ok" for r in reports) else "partial_or_error",
    "read_only": True,
    "privacy": {
        "keys_exposed": False,
        "values_exposed": False,
        "key_hashes_exposed": False,
        "value_hashes_exposed": False,
        "operation_fingerprint": "sha256(serialized operation: type + lengths + key + value)",
    },
    "target_frames": list(TARGETS),
    "wal_count": len(reports),
    "reports": reports,
}, ensure_ascii=False, indent=2))
PY

echo
echo "INSPECAO FORENSE CONCLUIDA"
echo "Nenhum arquivo do volume foi aberto para escrita."
echo "Nenhum payload de key/value foi impresso."
echo "Nenhum container foi parado, reiniciado ou reconstruido."
