#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="${MEMORIA_SERVER_DIR:-$HOME/memoria.ia.server}"
TARGET_SERVER="45e56054089e9a7e1712c3c6a384af58df13f9da"
TARGET_MEMORIA="ea8501c3314ccef700188d14bf29effcf2d82de3"
TARGET_BDR="39c34434b540f4348851703d912277080c8445ec"
BACKUP_ROOT="${MEMORIA_BACKUP_ROOT:-$HOME/memoria.ia.backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$BACKUP_ROOT/bdw4-single-duplicate-$STAMP"
ROLLBACK_SCRIPT="$BACKUP/rollback.sh"
READY_URL="${MEMORIA_SERVER_READY_URL:-http://127.0.0.1/api/server/v1/ready}"

cd "$PROJECT"
mkdir -p "$BACKUP"

echo "======================================================"
echo " M.IA.SERVER - Recovery BDW4 single duplicate"
echo " server=$TARGET_SERVER"
echo " memoria=$TARGET_MEMORIA"
echo " bdr=$TARGET_BDR"
echo "======================================================"

if [ ! -f .env ]; then
  echo "ERRO: .env nao encontrado em $PROJECT"
  exit 1
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERRO: existem alteracoes locais versionadas. Nada sera sobrescrito."
  git status
  exit 1
fi

ORIGINAL_HEAD="$(git rev-parse HEAD)"
cp -a .env "$BACKUP/.env"
cp -a compose.yaml "$BACKUP/compose.yaml"
printf '%s\n' "$ORIGINAL_HEAD" > "$BACKUP/server-head-before.txt"
docker compose config > "$BACKUP/compose.resolved.before.yaml"
docker compose ps > "$BACKUP/compose-ps.before.txt" || true

service_id() { docker compose ps -q "$1"; }
service_image_id() {
  local id
  id="$(service_id "$1")"
  [ -n "$id" ] || return 1
  docker inspect -f '{{.Image}}' "$id"
}
volume_for() {
  local service="$1" destination="$2" id
  id="$(service_id "$service")"
  [ -n "$id" ] || return 1
  docker inspect -f "{{range .Mounts}}{{if eq .Destination \"$destination\"}}{{.Name}}{{end}}{{end}}" "$id"
}

MEMORIA_ID_BEFORE="$(service_id memoria)"
BDR_ID_BEFORE="$(service_id bdr-explorer)"
SERVER_ID_BEFORE="$(service_id server)"
GATEWAY_ID_BEFORE="$(service_id model-gateway)"
GATEWAY_IMAGE_BEFORE="$(service_image_id model-gateway)"
MEMORIA_VOLUME="$(volume_for memoria /data)"
SERVER_VOLUME="$(volume_for server /data)"

for pair in   "memoria:$MEMORIA_ID_BEFORE"   "bdr-explorer:$BDR_ID_BEFORE"   "server:$SERVER_ID_BEFORE"   "model-gateway:$GATEWAY_ID_BEFORE"; do
  name="${pair%%:*}"; id="${pair#*:}"
  if [ -z "$id" ]; then
    echo "ERRO: container $name nao localizado."
    exit 1
  fi
done
if [ -z "$MEMORIA_VOLUME" ] || [ -z "$SERVER_VOLUME" ]; then
  echo "ERRO: volumes persistentes nao localizados."
  exit 1
fi

printf '%s\n' "$MEMORIA_VOLUME" > "$BACKUP/memoria-volume.txt"
printf '%s\n' "$SERVER_VOLUME" > "$BACKUP/server-volume.txt"
printf '%s\n' "$GATEWAY_ID_BEFORE" > "$BACKUP/model-gateway-container-id.before.txt"
printf '%s\n' "$GATEWAY_IMAGE_BEFORE" > "$BACKUP/model-gateway-image-id.before.txt"

check_wal_shape() {
  local volume="$1" label="$2"
  docker run --rm -i     -v "$volume:/data:ro"     --entrypoint python     "$(docker inspect -f '{{.Config.Image}}' "$SERVER_ID_BEFORE")" - "$label" <<'PY'
from pathlib import Path
import hashlib, json, struct, sys, zlib

label=sys.argv[1]
paths=sorted(Path("/data").rglob("atomic.bdw4"))
if len(paths) != 1:
    raise SystemExit(f"{label}: expected exactly one atomic.bdw4, got {len(paths)}")
path=paths[0]
data=path.read_bytes()
pos=0
frame=0
previous=0
duplicates=[]
regressions=[]
forward_gaps=[]
crc_valid=0
last_sequence=0
while pos < len(data):
    if len(data)-pos < 4:
        raise SystemExit(f"{label}: torn tail at offset {pos}")
    total=struct.unpack(">I",data[pos:pos+4])[0]
    if total < 28 or total > (1<<27) or len(data)-pos < total:
        raise SystemExit(f"{label}: invalid/torn frame at offset {pos}")
    raw=data[pos:pos+total]
    frame += 1
    if raw[4:8] != b"BDW4" or struct.unpack(">I",raw[8:12])[0] != 4:
        raise SystemExit(f"{label}: invalid magic/version at frame {frame}")
    expected=struct.unpack(">I",raw[-4:])[0]
    actual=zlib.crc32(raw[:-4]) & 0xffffffff
    if expected != actual:
        raise SystemExit(f"{label}: CRC mismatch at frame {frame}")
    crc_valid += 1
    sequence=struct.unpack(">Q",raw[12:20])[0]
    if frame > 1:
        delta=sequence-previous
        row={"frame":frame,"offset":pos,"previous":previous,"sequence":sequence,"delta":delta,"frame_sha256":hashlib.sha256(raw).hexdigest()}
        if delta == 0: duplicates.append(row)
        elif delta < 0: regressions.append(row)
        elif delta > 1: forward_gaps.append(row)
    previous=sequence
    last_sequence=sequence
    pos += total

expected_duplicate={
    "frame":601,
    "previous":600,
    "sequence":600,
    "delta":0,
    "frame_sha256":"60c8473a6d3ff1797728b6b68aca179a099f8305568ea619f94a5ae95deae265",
}
if len(duplicates) != 1:
    raise SystemExit(f"{label}: expected one duplicate, got {duplicates}")
for key,value in expected_duplicate.items():
    if duplicates[0].get(key) != value:
        raise SystemExit(f"{label}: unexpected duplicate shape: {duplicates[0]}")
if regressions:
    raise SystemExit(f"{label}: regressions found: {regressions[:5]}")
if forward_gaps:
    raise SystemExit(f"{label}: forward gaps found: {forward_gaps[:5]}")

print(json.dumps({
    "schema":"memoria-production-wal-preflight/v1",
    "label":label,
    "path":str(path),
    "bytes":len(data),
    "frames":frame,
    "crc_valid_frames":crc_valid,
    "duplicate":duplicates[0],
    "regressions":0,
    "forward_gaps":0,
    "last_sequence":last_sequence,
},ensure_ascii=False))
PY
}

echo "[1/10] Confirmando exatamente a anomalia observada, somente leitura..."
check_wal_shape "$MEMORIA_VOLUME" "live-before" | tee "$BACKUP/wal-preflight.before.jsonl"

echo "[2/10] Parando writers/proxies para snapshot consistente..."
docker compose stop server bdr-explorer memoria

echo "[3/10] Criando backup byte-preserving dos volumes..."
docker run --rm -v "$MEMORIA_VOLUME:/source:ro" -v "$BACKUP:/backup" alpine:3.20   sh -c 'cd /source && tar czf /backup/memoria-data.tgz .'
docker run --rm -v "$SERVER_VOLUME:/source:ro" -v "$BACKUP:/backup" alpine:3.20   sh -c 'cd /source && tar czf /backup/server-data.tgz .'
test -s "$BACKUP/memoria-data.tgz"
test -s "$BACKUP/server-data.tgz"
sha256sum "$BACKUP/memoria-data.tgz" > "$BACKUP/memoria-data.tgz.sha256"
sha256sum "$BACKUP/server-data.tgz" > "$BACKUP/server-data.tgz.sha256"

docker run --rm -v "$MEMORIA_VOLUME:/source:ro" alpine:3.20   sh -c 'sha256sum /source/native-runtime/atomic.bdw4' > "$BACKUP/atomic.bdw4.before.sha256"

cat > "$ROLLBACK_SCRIPT" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT="$PROJECT"
BACKUP="$BACKUP"
ORIGINAL_HEAD="$ORIGINAL_HEAD"
cd "\$PROJECT"

echo "[rollback] parando server, explorer e memoria"
docker compose stop server bdr-explorer memoria || true

echo "[rollback] restaurando codigo e pins exatos"
git checkout --detach "\$ORIGINAL_HEAD"
cp -a "\$BACKUP/.env" .env

MEMORIA_VOLUME="\$(cat "\$BACKUP/memoria-volume.txt")"
SERVER_VOLUME="\$(cat "\$BACKUP/server-volume.txt")"

echo "[rollback] restaurando memoria-data byte a byte do snapshot"
docker run --rm -v "\$MEMORIA_VOLUME:/target" alpine:3.20   sh -c 'rm -rf /target/* /target/.[!.]* /target/..?* 2>/dev/null || true'
docker run --rm -v "\$MEMORIA_VOLUME:/target" -v "\$BACKUP:/backup:ro" alpine:3.20   sh -c 'cd /target && tar xzf /backup/memoria-data.tgz'

echo "[rollback] restaurando server-data"
docker run --rm -v "\$SERVER_VOLUME:/target" alpine:3.20   sh -c 'rm -rf /target/* /target/.[!.]* /target/..?* 2>/dev/null || true'
docker run --rm -v "\$SERVER_VOLUME:/target" -v "\$BACKUP:/backup:ro" alpine:3.20   sh -c 'cd /target && tar xzf /backup/server-data.tgz'

echo "[rollback] verificando WAL restaurado"
docker run --rm -v "\$MEMORIA_VOLUME:/source:ro" alpine:3.20   sh -c 'sha256sum /source/native-runtime/atomic.bdw4' > /tmp/atomic.rollback.sha256
sed 's#  .*#  WAL#' "\$BACKUP/atomic.bdw4.before.sha256" > /tmp/atomic.before.norm
sed 's#  .*#  WAL#' /tmp/atomic.rollback.sha256 > /tmp/atomic.rollback.norm
cmp /tmp/atomic.before.norm /tmp/atomic.rollback.norm

echo "[rollback] reconstruindo as versoes anteriores"
docker compose build --no-cache memoria bdr-explorer server
docker compose up -d --no-deps memoria || true
sleep 5
docker compose up -d --no-deps bdr-explorer server || true

echo
echo "ROLLBACK EXATO CONCLUIDO"
echo "O estado anterior foi restaurado. Como o estado anterior continha o WAL que o BDR antigo nao abria,"
echo "a Memoria.ia pode retornar ao restart loop conhecido. O rollback prioriza integridade, nao mascara a falha anterior."
EOF
chmod +x "$ROLLBACK_SCRIPT"

echo "[4/10] Atualizando codigo do Server e pins de runtime..."
git fetch origin
git checkout --detach "$TARGET_SERVER"
test "$(git rev-parse HEAD)" = "$TARGET_SERVER"

python3 - "$TARGET_MEMORIA" "$TARGET_BDR" <<'PY'
from pathlib import Path
import sys
path=Path(".env")
targets={"MEMORIA_COMMIT":sys.argv[1],"BDR_COMMIT":sys.argv[2]}
lines=path.read_text().splitlines()
out=[]
seen=set()
for line in lines:
    if "=" in line and not line.lstrip().startswith("#"):
        key=line.split("=",1)[0]
        if key in targets:
            out.append(f"{key}={targets[key]}")
            seen.add(key)
            continue
    out.append(line)
for key,value in targets.items():
    if key not in seen:
        out.append(f"{key}={value}")
path.write_text("\n".join(out)+"\n")
PY

grep -E '^(MEMORIA_COMMIT|BDR_COMMIT)=' .env | tee "$BACKUP/runtime-pins.after.txt"
grep -q "^MEMORIA_COMMIT=$TARGET_MEMORIA$" .env
grep -q "^BDR_COMMIT=$TARGET_BDR$" .env

echo "[5/10] Construindo runtime corrigido, Explorer e Server..."
docker compose build --no-cache memoria bdr-explorer server
NEW_MEMORIA_IMAGE="$(docker image ls -q memoria-ia-server-memoria:latest | head -n1)"
test -n "$NEW_MEMORIA_IMAGE"

echo "[6/10] Validando o backup em volume sombra ANTES de tocar no volume live..."
SHADOW_VOLUME="mia-bdw4-shadow-$STAMP"
docker volume create "$SHADOW_VOLUME" >/dev/null
cleanup_shadow() { docker volume rm -f "$SHADOW_VOLUME" >/dev/null 2>&1 || true; }
trap cleanup_shadow EXIT

docker run --rm -v "$SHADOW_VOLUME:/target" -v "$BACKUP:/backup:ro" alpine:3.20   sh -c 'cd /target && tar xzf /backup/memoria-data.tgz'
ORG_ID="$(awk -F= '$1=="MEMORIA_ORGANIZATION_ID"{sub(/^[^=]*=/,"");print;exit}' .env)"
test -n "$ORG_ID"

docker run --rm -i   -e MEMORIA_ORGANIZATION_ID="$ORG_ID"   -v "$SHADOW_VOLUME:/data"   --entrypoint python   "$NEW_MEMORIA_IMAGE" - <<'PY'
import os
from pathlib import Path
from memoria_resolutiva.native_runtime import NativeRuntime

runtime=NativeRuntime(
    library_path=Path("/usr/local/lib/libmemoria_mobile.so"),
    data_dir=Path("/data/native-runtime"),
    organization_id=os.environ["MEMORIA_ORGANIZATION_ID"],
)
runtime.close()
print("SHADOW_NATIVE_OPEN=PASS")
PY

cleanup_shadow
trap - EXIT

echo "[7/10] Subindo Memoria.ia recuperada..."
docker compose up -d --no-deps memoria
MEMORIA_OK=0
for i in $(seq 1 90); do
  if docker compose exec -T memoria python - <<'PY' >/tmp/memoria-health.json 2>/dev/null
import json, urllib.request
with urllib.request.urlopen("http://127.0.0.1:8080/api/v1/health",timeout=3) as r:
    data=json.load(r)
    assert r.status == 200
    print(json.dumps(data))
PY
  then
    MEMORIA_OK=1
    echo "Memoria health OK na tentativa $i"
    cat /tmp/memoria-health.json
    break
  fi
  sleep 2
done
if [ "$MEMORIA_OK" -ne 1 ]; then
  echo "ERRO: Memoria.ia recuperada nao ficou online."
  docker compose logs --tail=400 memoria || true
  echo "Rollback disponivel: $ROLLBACK_SCRIPT"
  exit 1
fi

echo "[8/10] Subindo BDR Explorer e Server..."
docker compose up -d --no-deps bdr-explorer
for i in $(seq 1 60); do
  if docker compose exec -T bdr-explorer python - <<'PY' >/tmp/bdr-health.json 2>/dev/null
import json, urllib.request
with urllib.request.urlopen("http://127.0.0.1:8765/api/health",timeout=3) as r:
    data=json.load(r)
    assert data.get("status") == "ok"
    print(json.dumps(data))
PY
  then break; fi
  if [ "$i" -eq 60 ]; then
    docker compose logs --tail=250 bdr-explorer || true
    echo "ERRO: BDR Explorer nao ficou online. Rollback: $ROLLBACK_SCRIPT"
    exit 1
  fi
  sleep 2
done

docker compose up -d --no-deps server
SERVER_OK=0
for i in $(seq 1 60); do
  if curl -fsS --max-time 3 "$READY_URL" > "$BACKUP/server-ready.after.json" 2>/dev/null; then
    SERVER_OK=1
    echo "Server readiness OK na tentativa $i"
    cat "$BACKUP/server-ready.after.json"; echo
    break
  fi
  sleep 2
done
if [ "$SERVER_OK" -ne 1 ]; then
  docker compose logs --tail=300 server || true
  echo "ERRO: Server nao ficou ready. Rollback: $ROLLBACK_SCRIPT"
  exit 1
fi

echo "[9/10] Confirmando que o WAL continua com uma unica anomalia historica..."
SERVER_ID_AFTER="$(service_id server)"
SERVER_ID_BEFORE="$SERVER_ID_AFTER"
check_wal_shape "$MEMORIA_VOLUME" "live-after" | tee "$BACKUP/wal-preflight.after.jsonl"

echo "[10/10] Confirmando que Model Gateway permaneceu intocado..."
GATEWAY_ID_AFTER="$(service_id model-gateway)"
GATEWAY_IMAGE_AFTER="$(service_image_id model-gateway)"
[ "$GATEWAY_ID_AFTER" = "$GATEWAY_ID_BEFORE" ] || { echo "ERRO: Model Gateway foi recriado."; exit 1; }
[ "$GATEWAY_IMAGE_AFTER" = "$GATEWAY_IMAGE_BEFORE" ] || { echo "ERRO: imagem do Model Gateway mudou."; exit 1; }

docker compose ps | tee "$BACKUP/compose-ps.after.txt"

echo
echo "======================================================"
echo " RECOVERY BDW4: PASS"
echo "======================================================"
echo "server_commit=$TARGET_SERVER"
echo "memoria_commit=$TARGET_MEMORIA"
echo "bdr_commit=$TARGET_BDR"
echo "memoria_backup=$BACKUP/memoria-data.tgz"
echo "server_backup=$BACKUP/server-data.tgz"
echo "rollback=$ROLLBACK_SCRIPT"
echo "model_gateway_preservado=$GATEWAY_ID_AFTER"
echo
echo "O atomic.bdw4 NAO foi reescrito nem normalizado pelo recovery."
echo "A compatibilidade esta no reader BDR; o historico permanece byte-preservado salvo escritas normais posteriores."
echo "A Memoria.ia agora usa um unico handle BDR compartilhado, impedindo nova colisao dual-handle."
