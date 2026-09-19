#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="${MEMORIA_SERVER_DIR:-$HOME/memoria.ia.server}"
TARGET_SERVER="ea6cb2adc7124df0eaef5cdab76568525beca6d7"
TARGET_MEMORIA="bae11593f2c64bdb63fce84100213c16f88ca796"
TARGET_BDR="d11926da38f2f2d389dee44db277223bedc315d1"
BACKUP_ROOT="${MEMORIA_BACKUP_ROOT:-$HOME/memoria.ia.backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$BACKUP_ROOT/temporal-explorer-$STAMP"
HEALTH_URL="${MEMORIA_SERVER_HEALTH_URL:-http://127.0.0.1/api/server/v1/health}"
ROLLBACK_SCRIPT="$BACKUP/rollback.sh"

cd "$PROJECT"
mkdir -p "$BACKUP"

echo "==============================================="
echo " Memoria.ia Server - Temporal Explorer Update"
echo " server : $TARGET_SERVER"
echo " memoria: $TARGET_MEMORIA"
echo " BDR    : $TARGET_BDR"
echo "==============================================="

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERRO: existem alteracoes locais versionadas. Nada sera sobrescrito."
  git status
  exit 1
fi

ORIGINAL_HEAD="$(git rev-parse HEAD)"
printf '%s\n' "$ORIGINAL_HEAD" > "$BACKUP/server-head.txt"
cp -a .env "$BACKUP/.env" 2>/dev/null || true
cp -a compose.yaml "$BACKUP/compose.yaml"
docker compose config > "$BACKUP/compose.resolved.before.yaml"
docker compose ps > "$BACKUP/compose-ps-before.txt" || true

actual_volume() {
  local service="$1" destination="$2" container
  container="$(docker compose ps -q "$service")"
  [ -n "$container" ] || return 1
  docker inspect -f "{{range .Mounts}}{{if eq .Destination \"$destination\"}}{{.Name}}{{end}}{{end}}" "$container"
}

MEMORIA_VOLUME="$(actual_volume memoria /data || true)"
SERVER_VOLUME="$(actual_volume server /data || true)"
[ -n "$MEMORIA_VOLUME" ] || { echo "ERRO: volume real de memoria:/data nao localizado."; exit 1; }
[ -n "$SERVER_VOLUME" ] || { echo "ERRO: volume real de server:/data nao localizado."; exit 1; }
printf '%s\n' "$MEMORIA_VOLUME" > "$BACKUP/memoria-volume.txt"
printf '%s\n' "$SERVER_VOLUME" > "$BACKUP/server-volume.txt"

echo "[1/8] Parando escritores para snapshot consistente..."
docker compose stop server bdr-explorer memoria

snapshot_volume() {
  local volume="$1" name="$2"
  echo "[backup] $name <= $volume"
  docker run --rm -v "$volume:/source:ro" -v "$BACKUP:/backup" alpine:3.20     sh -c "cd /source && tar czf /backup/$name.tgz ."
  test -s "$BACKUP/$name.tgz"
  sha256sum "$BACKUP/$name.tgz" > "$BACKUP/$name.tgz.sha256"
  tar tzf "$BACKUP/$name.tgz" | head -n 20 > "$BACKUP/$name.contents.txt" || true
}

echo "[2/8] Criando snapshots dos dados atuais..."
snapshot_volume "$MEMORIA_VOLUME" memoria-data
snapshot_volume "$SERVER_VOLUME" server-data

cat > "$ROLLBACK_SCRIPT" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
cd "$PROJECT"
echo '[rollback] parando stack'
docker compose down
git checkout --detach "$ORIGINAL_HEAD"
cp -a "$BACKUP/.env" .env 2>/dev/null || true
MEMORIA_VOLUME="$(cat "$BACKUP/memoria-volume.txt")"
SERVER_VOLUME="$(cat "$BACKUP/server-volume.txt")"
restore_volume() {
  local volume="\$1" archive="\$2"
  docker run --rm -v "\$volume:/target" alpine:3.20 sh -c 'rm -rf /target/* /target/.[!.]* /target/..?* 2>/dev/null || true'
  docker run --rm -v "\$volume:/target" -v "$BACKUP:/backup:ro" alpine:3.20 sh -c "cd /target && tar xzf /backup/\$archive"
}
echo '[rollback] restaurando memoria-data'
restore_volume "$MEMORIA_VOLUME" memoria-data.tgz
echo '[rollback] restaurando server-data'
restore_volume "$SERVER_VOLUME" server-data.tgz
docker compose build --no-cache memoria bdr-explorer server
docker compose up -d
for i in $(seq 1 60); do
  if curl -fsS --max-time 3 "$HEALTH_URL" >/tmp/memoria-rollback-health.json 2>/dev/null; then
    echo '[rollback] health OK'
    cat /tmp/memoria-rollback-health.json; echo
    exit 0
  fi
  sleep 3
done
echo '[rollback] ERRO: health nao voltou'
docker compose ps
docker compose logs --tail=300 memoria bdr-explorer server || true
exit 1
EOF
chmod +x "$ROLLBACK_SCRIPT"

echo "[3/8] Atualizando codigo do servidor para candidato exato..."
git fetch origin
git checkout --detach "$TARGET_SERVER"
[ "$(git rev-parse HEAD)" = "$TARGET_SERVER" ] || { echo "ERRO: server HEAD incorreto"; exit 1; }

echo "[4/8] Fixando runtime Memoria.ia e BDR sem apagar dados..."
python3 - "$TARGET_MEMORIA" "$TARGET_BDR" <<'PY'
from pathlib import Path
import sys
p=Path('.env')
text=p.read_text() if p.exists() else ''
vals={'MEMORIA_COMMIT':sys.argv[1], 'BDR_COMMIT':sys.argv[2]}
out=[]; seen=set()
for line in text.splitlines():
    key=line.split('=',1)[0].strip() if '=' in line and not line.lstrip().startswith('#') else None
    if key in vals:
        out.append(f'{key}={vals[key]}'); seen.add(key)
    else:
        out.append(line)
for key,val in vals.items():
    if key not in seen: out.append(f'{key}={val}')
p.write_text('\n'.join(out)+'\n')
PY
grep -q "^MEMORIA_COMMIT=$TARGET_MEMORIA$" .env
grep -q "^BDR_COMMIT=$TARGET_BDR$" .env

echo "[5/8] Reconstruindo componentes alterados..."
docker compose build --no-cache memoria bdr-explorer server

echo "[6/8] Subindo stack com os volumes preservados..."
docker compose up -d

OK=0
for i in $(seq 1 60); do
  if curl -fsS --max-time 3 "$HEALTH_URL" > "$BACKUP/health-after.json" 2>/dev/null; then
    OK=1
    echo "HEALTH: OK na tentativa $i"
    cat "$BACKUP/health-after.json"; echo
    break
  fi
  sleep 3
done
if [ "$OK" -ne 1 ]; then
  echo "ERRO: health nao voltou. Rollback disponivel em: $ROLLBACK_SCRIPT"
  docker compose ps
  docker compose logs --tail=300 memoria bdr-explorer server || true
  exit 1
fi

echo "[7/8] Validando runtime paginado sem escrever nem formatar..."
docker compose exec -T memoria python - <<'PY' > "$BACKUP/memoria-page.json"
import json, os
from urllib.request import Request, urlopen
key=os.environ.get('MEMORIA_API_KEY','')
headers={'X-Memoria-Key':key} if key else {}
with urlopen(Request('http://127.0.0.1:8080/api/v1/episodes/history?limit=5000',headers=headers),timeout=10) as r:
    body=json.load(r)
assert body.get('schema') == 'memoria-episode-history/v1', body
assert isinstance(body.get('count'), int), body
print(json.dumps(body,ensure_ascii=False))
PY
cat "$BACKUP/memoria-page.json"
TOTAL="$(python3 - "$BACKUP/memoria-page.json" <<'PY'
import json,sys
print(int(json.load(open(sys.argv[1])).get('count') or 0))
PY
)"
OFFSET=0
if [ "$TOTAL" -gt 64 ]; then OFFSET=$((TOTAL-64)); fi
docker compose exec -T bdr-explorer python - "$OFFSET" <<'PY' > "$BACKUP/explorer-window.json"
import json,sys
from urllib.request import urlopen
offset=int(sys.argv[1])
with urlopen(f'http://127.0.0.1:8765/api/snapshot?offset={offset}&limit=64',timeout=10) as r:
    body=json.load(r)
assert body.get('schema') == 'bdr-explorer-snapshot/v0.2', body
assert int(body.get('window',{}).get('count') or 0) >= int(body.get('window',{}).get('returned') or 0)
assert len(body.get('nodes') or []) <= 64
print(json.dumps(body.get('window',{}),ensure_ascii=False))
PY
cat "$BACKUP/explorer-window.json"

echo "[8/8] Validando interface/Inspector/formatador sem executar FORMATAR..."
docker compose exec -T server sh -c "grep -q 'diagnostics-fix.js' /app/apps/memoria-admin/static/index.html"
docker compose exec -T bdr-explorer sh -c "grep -q 'id=\"format-bdr\"' /app/explorer/static/index.html"
docker compose exec -T bdr-explorer sh -c "grep -q 'time-older' /app/explorer/static/index.html"
docker compose exec -T bdr-explorer sh -c "grep -q 'showNode(node, group)' /app/explorer/static/app.js"
docker compose exec -T bdr-explorer sh -c "grep -q '.filter((v) => visible(v.p))' /app/explorer/static/app.js"

echo
echo "==============================================="
echo " TEMPORAL EXPLORER PATCH ATIVO"
echo "==============================================="
echo "server_commit=$TARGET_SERVER"
echo "memoria_commit=$TARGET_MEMORIA"
echo "bdr_commit=$TARGET_BDR"
echo "episodios_fisicos=$TOTAL"
echo "backup_memoria=$BACKUP/memoria-data.tgz"
echo "backup_server=$BACKUP/server-data.tgz"
echo "rollback=$ROLLBACK_SCRIPT"
echo
echo "O script NAO executou Formatar BDR."
echo "A entrada bruta continua sem filtros/regex."
echo "Teste agora: zoom temporal, selecao/Inspector e depois, somente se desejar, Formatar BDR."
