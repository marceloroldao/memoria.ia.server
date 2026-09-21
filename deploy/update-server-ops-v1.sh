#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="${MEMORIA_SERVER_DIR:-$HOME/memoria.ia.server}"
TARGET_SERVER="eebf6a0a73ba3a20a12cb50343af2af889da739e"
BACKUP_ROOT="${MEMORIA_BACKUP_ROOT:-$HOME/memoria.ia.backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$BACKUP_ROOT/server-ops-v1-$STAMP"
HEALTH_URL="${MEMORIA_SERVER_HEALTH_URL:-http://127.0.0.1/api/server/v1/health}"
ROLLBACK_SCRIPT="$BACKUP/rollback.sh"

cd "$PROJECT"
mkdir -p "$BACKUP"

echo "==============================================="
echo " M.IA.SERVER - Server Ops V1"
echo " target: $TARGET_SERVER"
echo " escopo: SOMENTE container server + server-data"
echo "==============================================="

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
ENV_HASH_BEFORE="$(sha256sum .env | awk '{print $1}')"
printf '%s\n' "$ORIGINAL_HEAD" > "$BACKUP/server-head-before.txt"
cp -a .env "$BACKUP/.env"
cp -a compose.yaml "$BACKUP/compose.yaml"
docker compose config > "$BACKUP/compose.resolved.before.yaml"
docker compose ps > "$BACKUP/compose-ps.before.txt" || true

service_id() {
  docker compose ps -q "$1"
}
service_image_id() {
  local id
  id="$(service_id "$1")"
  [ -n "$id" ] || return 1
  docker inspect -f '{{.Image}}' "$id"
}
server_volume() {
  local id
  id="$(service_id server)"
  [ -n "$id" ] || return 1
  docker inspect -f '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' "$id"
}

MEMORIA_ID_BEFORE="$(service_id memoria)"
BDR_ID_BEFORE="$(service_id bdr-explorer)"
GATEWAY_ID_BEFORE="$(service_id model-gateway)"
SERVER_ID_BEFORE="$(service_id server)"
MEMORIA_IMAGE_BEFORE="$(service_image_id memoria)"
BDR_IMAGE_BEFORE="$(service_image_id bdr-explorer)"
GATEWAY_IMAGE_BEFORE="$(service_image_id model-gateway)"
SERVER_VOLUME="$(server_volume)"

for pair in   "memoria:$MEMORIA_ID_BEFORE"   "bdr-explorer:$BDR_ID_BEFORE"   "model-gateway:$GATEWAY_ID_BEFORE"   "server:$SERVER_ID_BEFORE"; do
  name="${pair%%:*}"
  id="${pair#*:}"
  if [ -z "$id" ]; then
    echo "ERRO: servico $name nao esta em execucao."
    exit 1
  fi
done
if [ -z "$SERVER_VOLUME" ]; then
  echo "ERRO: volume real de server:/data nao localizado."
  exit 1
fi

printf '%s\n' "$MEMORIA_ID_BEFORE" > "$BACKUP/memoria-container-id.before.txt"
printf '%s\n' "$MEMORIA_IMAGE_BEFORE" > "$BACKUP/memoria-image-id.before.txt"
printf '%s\n' "$BDR_ID_BEFORE" > "$BACKUP/bdr-container-id.before.txt"
printf '%s\n' "$BDR_IMAGE_BEFORE" > "$BACKUP/bdr-image-id.before.txt"
printf '%s\n' "$GATEWAY_ID_BEFORE" > "$BACKUP/model-gateway-container-id.before.txt"
printf '%s\n' "$GATEWAY_IMAGE_BEFORE" > "$BACKUP/model-gateway-image-id.before.txt"
printf '%s\n' "$SERVER_VOLUME" > "$BACKUP/server-volume.txt"

echo "[1/7] Parando SOMENTE o M.IA.SERVER para snapshot consistente..."
docker compose stop server

echo "[2/7] Backup completo de server-data..."
docker run --rm -v "$SERVER_VOLUME:/source:ro" -v "$BACKUP:/backup" alpine:3.20   sh -c 'cd /source && tar czf /backup/server-data.tgz .'
test -s "$BACKUP/server-data.tgz"
sha256sum "$BACKUP/server-data.tgz" > "$BACKUP/server-data.tgz.sha256"

cat > "$ROLLBACK_SCRIPT" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT="$PROJECT"
BACKUP="$BACKUP"
ORIGINAL_HEAD="$ORIGINAL_HEAD"
HEALTH_URL="${MEMORIA_SERVER_HEALTH_URL:-$HEALTH_URL}"
cd "\$PROJECT"

echo "[rollback] parando SOMENTE server"
docker compose stop server || true

echo "[rollback] restaurando codigo anterior"
git checkout --detach "\$ORIGINAL_HEAD"
cp -a "\$BACKUP/.env" .env

SERVER_VOLUME="\$(cat "\$BACKUP/server-volume.txt")"
echo "[rollback] restaurando server-data"
docker run --rm -v "\$SERVER_VOLUME:/target" alpine:3.20   sh -c 'rm -rf /target/* /target/.[!.]* /target/..?* 2>/dev/null || true'
docker run --rm -v "\$SERVER_VOLUME:/target" -v "\$BACKUP:/backup:ro" alpine:3.20   sh -c 'cd /target && tar xzf /backup/server-data.tgz'

echo "[rollback] reconstruindo SOMENTE server"
docker compose build --no-cache server
docker compose up -d --no-deps server

for i in \$(seq 1 60); do
  if curl -fsS --max-time 3 "\$HEALTH_URL" > /tmp/mia-server-rollback-health.json 2>/dev/null; then
    echo "[rollback] health OK"
    cat /tmp/mia-server-rollback-health.json; echo
    exit 0
  fi
  sleep 3
done

echo "[rollback] ERRO: server nao recuperou health"
docker compose ps
docker compose logs --tail=300 server || true
exit 1
EOF
chmod +x "$ROLLBACK_SCRIPT"

echo "[3/7] Atualizando SOMENTE o codigo do repositorio do Server..."
git fetch origin
git checkout --detach "$TARGET_SERVER"
if [ "$(git rev-parse HEAD)" != "$TARGET_SERVER" ]; then
  echo "ERRO: HEAD do Server diferente do alvo."
  exit 1
fi
if [ "$(sha256sum .env | awk '{print $1}')" != "$ENV_HASH_BEFORE" ]; then
  echo "ERRO: .env foi alterado durante checkout."
  exit 1
fi

echo "[4/7] Construindo SOMENTE a imagem server..."
docker compose build --no-cache server

echo "[5/7] Subindo SOMENTE server, sem dependencias..."
docker compose up -d --no-deps server

OK=0
for i in $(seq 1 60); do
  if curl -fsS --max-time 3 "$HEALTH_URL" > "$BACKUP/health.after.json" 2>/dev/null; then
    OK=1
    echo "HEALTH: OK na tentativa $i"
    cat "$BACKUP/health.after.json"; echo
    break
  fi
  sleep 3
done
if [ "$OK" -ne 1 ]; then
  echo "ERRO: server nao voltou. Rollback: $ROLLBACK_SCRIPT"
  docker compose ps
  docker compose logs --tail=300 server || true
  exit 1
fi

echo "[6/7] Provando que Memoria.ia, BDR Explorer e Model Gateway NAO foram recriados..."
MEMORIA_ID_AFTER="$(service_id memoria)"
BDR_ID_AFTER="$(service_id bdr-explorer)"
GATEWAY_ID_AFTER="$(service_id model-gateway)"
MEMORIA_IMAGE_AFTER="$(service_image_id memoria)"
BDR_IMAGE_AFTER="$(service_image_id bdr-explorer)"
GATEWAY_IMAGE_AFTER="$(service_image_id model-gateway)"

[ "$MEMORIA_ID_AFTER" = "$MEMORIA_ID_BEFORE" ] || { echo "ERRO: container Memoria.ia mudou."; exit 1; }
[ "$BDR_ID_AFTER" = "$BDR_ID_BEFORE" ] || { echo "ERRO: container BDR Explorer mudou."; exit 1; }
[ "$GATEWAY_ID_AFTER" = "$GATEWAY_ID_BEFORE" ] || { echo "ERRO: container Model Gateway mudou."; exit 1; }
[ "$MEMORIA_IMAGE_AFTER" = "$MEMORIA_IMAGE_BEFORE" ] || { echo "ERRO: imagem Memoria.ia mudou."; exit 1; }
[ "$BDR_IMAGE_AFTER" = "$BDR_IMAGE_BEFORE" ] || { echo "ERRO: imagem BDR Explorer mudou."; exit 1; }
[ "$GATEWAY_IMAGE_AFTER" = "$GATEWAY_IMAGE_BEFORE" ] || { echo "ERRO: imagem Model Gateway mudou."; exit 1; }
[ "$(sha256sum .env | awk '{print $1}')" = "$ENV_HASH_BEFORE" ] || { echo "ERRO: .env mudou."; exit 1; }

echo "[7/7] Validando capacidades novas via sessao administrativa, sem criar dados de teste..."
docker compose exec -T server python - <<'PY' > "$BACKUP/server-capabilities.json"
import http.cookiejar
import json
import os
from urllib.request import HTTPCookieProcessor, Request, build_opener

base = "http://127.0.0.1:8780"
user = os.environ.get("MEMORIA_SERVER_ADMIN_USER", "admin")
password = os.environ["MEMORIA_SERVER_ADMIN_PASSWORD"]
opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
login = json.dumps({"username": user, "password": password}).encode()
with opener.open(Request(base + "/api/server/v1/login", data=login, headers={"Content-Type":"application/json"}, method="POST"), timeout=10) as response:
    assert response.status == 200
with opener.open(base + "/api/server/v1/capabilities", timeout=10) as response:
    caps = json.load(response)
for key in (
    "device_registry_v1",
    "device_auth_v1",
    "device_certificates_v1",
    "device_permissions_v1",
    "device_enrollment_v1",
    "audit_log_v1",
):
    assert caps.get(key) is True, (key, caps)
assert caps.get("format_bdr") is False, caps
with opener.open(base + "/api/server/v1/server/identity", timeout=10) as response:
    identity = json.load(response)
with opener.open(base + "/api/server/v1/enrollments", timeout=10) as response:
    enrollments = json.load(response)
print(json.dumps({
    "capabilities": caps,
    "server_id": identity.get("server_id"),
    "enrollments": enrollments.get("count"),
}, ensure_ascii=False))
PY
cat "$BACKUP/server-capabilities.json"

echo
echo "==============================================="
echo " SERVER OPS V1 ATIVO"
echo "==============================================="
echo "server_commit=$TARGET_SERVER"
echo "server_data_backup=$BACKUP/server-data.tgz"
echo "rollback=$ROLLBACK_SCRIPT"
echo "memoria_container_preservado=$MEMORIA_ID_AFTER"
echo "bdr_container_preservado=$BDR_ID_AFTER"
echo "model_gateway_preservado=$GATEWAY_ID_AFTER"
echo
echo "Memoria.ia NAO foi parada, reconstruida ou recriada."
echo "BDR Explorer NAO foi parado, reconstruido ou recriado."
echo "Model Gateway NAO foi parado, reconstruido ou recriado."
