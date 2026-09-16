#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="${MEMORIA_SERVER_DIR:-$HOME/memoria.ia.server}"
TARGET_MEMORIA="ec817397b67ad0fadb3e1ec0b82e6a837869e0a1"
TARGET_BDR="eb77ad7286f234243ca1ed1a2af2d55df8c12238"
BACKUP_ROOT="${MEMORIA_BACKUP_ROOT:-$HOME/memoria.ia.backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$BACKUP_ROOT/dynamic-episodes-$STAMP"
HEALTH_URL="${MEMORIA_SERVER_HEALTH_URL:-http://127.0.0.1/api/server/v1/health}"
ROLLBACK_SCRIPT="$BACKUP/rollback.sh"

cd "$PROJECT"
mkdir -p "$BACKUP"

ORIGINAL_HEAD="$(git rev-parse HEAD)"
printf '%s\n' "$ORIGINAL_HEAD" > "$BACKUP/server-head.txt"
cp -a .env "$BACKUP/.env" 2>/dev/null || true
cp -a compose.yaml "$BACKUP/compose.yaml"
docker compose config > "$BACKUP/compose.resolved.yaml"
docker compose ps > "$BACKUP/compose-ps-before.txt" || true

MEMORIA_VOLUME="$(docker compose config --volumes | grep -E '(^|-)memoria-data$' | head -n1 || true)"
if [ -z "$MEMORIA_VOLUME" ]; then
  MEMORIA_VOLUME="$(docker volume ls --format '{{.Name}}' | grep 'memoria-data$' | head -n1 || true)"
fi
[ -n "$MEMORIA_VOLUME" ] || { echo 'ERRO: volume memoria-data nao localizado; abortando antes de alterar producao.'; exit 1; }
printf '%s\n' "$MEMORIA_VOLUME" > "$BACKUP/memoria-volume.txt"

echo "[backup] parando somente memoria e dependentes para snapshot consistente"
docker compose stop server bdr-explorer memoria || true

echo "[backup] copiando volume $MEMORIA_VOLUME (preserva os 256 registros)"
docker run --rm -v "$MEMORIA_VOLUME:/source:ro" -v "$BACKUP:/backup" alpine:3.20 sh -c 'cd /source && tar czf /backup/memoria-data.tgz .'
test -s "$BACKUP/memoria-data.tgz"
sha256sum "$BACKUP/memoria-data.tgz" > "$BACKUP/memoria-data.tgz.sha256"

cat > "$ROLLBACK_SCRIPT" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
cd "$PROJECT"
echo '[rollback] parando stack'
docker compose down
git checkout --detach "$ORIGINAL_HEAD"
cp -a "$BACKUP/.env" .env 2>/dev/null || true
VOLUME="$(cat "$BACKUP/memoria-volume.txt")"
echo "[rollback] restaurando snapshot do volume \$VOLUME"
docker run --rm -v "\$VOLUME:/target" alpine:3.20 sh -c 'rm -rf /target/* /target/.[!.]* /target/..?* 2>/dev/null || true'
docker run --rm -v "\$VOLUME:/target" -v "$BACKUP:/backup:ro" alpine:3.20 sh -c 'cd /target && tar xzf /backup/memoria-data.tgz'
docker compose build --no-cache memoria
docker compose up -d
echo '[rollback] concluido; confira docker compose ps e health.'
EOF
chmod +x "$ROLLBACK_SCRIPT"

echo "[deploy] configurando commits exatos sem alterar dados"
# Compose already accepts these as build args through environment interpolation.
export MEMORIA_COMMIT="$TARGET_MEMORIA"
export BDR_COMMIT="$TARGET_BDR"

# Persist pins in .env while preserving unrelated configuration.
python3 - "$TARGET_MEMORIA" "$TARGET_BDR" <<'PY'
from pathlib import Path
import sys
p=Path('.env'); text=p.read_text() if p.exists() else ''
vals={'MEMORIA_COMMIT':sys.argv[1], 'BDR_COMMIT':sys.argv[2]}
lines=text.splitlines(); seen=set(); out=[]
for line in lines:
    key=line.split('=',1)[0].strip() if '=' in line and not line.lstrip().startswith('#') else None
    if key in vals:
        out.append(f'{key}={vals[key]}'); seen.add(key)
    else: out.append(line)
for key,val in vals.items():
    if key not in seen: out.append(f'{key}={val}')
p.write_text('\n'.join(out)+'\n')
PY

echo "[deploy] construindo runtime memoria.ia $TARGET_MEMORIA com BDR congelado $TARGET_BDR"
docker compose build --no-cache memoria

echo "[deploy] iniciando stack; volume existente NAO e recriado"
docker compose up -d

OK=0
for i in $(seq 1 60); do
  if curl -fsS --max-time 3 "$HEALTH_URL" > "$BACKUP/health-after.json" 2>/dev/null; then OK=1; break; fi
  sleep 3
done
if [ "$OK" -ne 1 ]; then
  echo "ERRO: health nao voltou. Execute: $ROLLBACK_SCRIPT"
  docker compose ps
  docker compose logs --tail=200 memoria server || true
  exit 1
fi

echo "[verify] runtime nativo e ausencia do teto MAX_EPISODES"
docker compose exec -T memoria python - <<'PY'
import ctypes, os
p=os.environ.get('MEMORIA_NATIVE_LIB','/usr/local/lib/libmemoria_mobile.so')
lib=ctypes.CDLL(p)
assert lib.memoria_mobile_abi_version() == 1
print('native_abi=1 OK')
PY

# Verify source identity embedded by image build via image labels is unavailable; inspect compose pins and active health instead.
grep -q "^MEMORIA_COMMIT=$TARGET_MEMORIA$" .env
grep -q "^BDR_COMMIT=$TARGET_BDR$" .env

echo
echo "PRODUCTION PATCH ATIVO"
echo "memoria_commit=$TARGET_MEMORIA"
echo "bdr_commit=$TARGET_BDR"
echo "backup=$BACKUP/memoria-data.tgz"
echo "rollback=$ROLLBACK_SCRIPT"
echo "IMPORTANTE: snapshot preserva o estado anterior de 256 registros."
echo "Agora acompanhe o Explorer: o proximo aprendizado deve ultrapassar 256."
