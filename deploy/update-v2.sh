#!/usr/bin/env bash
set -euo pipefail

COMMIT="c43214a777b268f887f83fb574bed6fe0dd59c56"
PROJECT="${MEMORIA_SERVER_DIR:-$HOME/memoria.ia.server}"
HEALTH_URL="http://127.0.0.1:8780/api/server/v1/health"

echo "========================================"
echo " Memoria.ia Server - Update V2 Candidate"
echo " Commit: $COMMIT"
echo "========================================"
cd "$PROJECT"

echo
echo "[1/7] Verificando repositorio..."
git status --short
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERRO: existem alteracoes locais versionadas. Nada sera sobrescrito."
  git status
  exit 1
fi

echo
echo "[2/7] Buscando atualizacoes..."
git fetch origin

echo
echo "[3/7] Fixando candidato exato..."
git checkout --detach "$COMMIT"
CURRENT="$(git rev-parse HEAD)"
[ "$CURRENT" = "$COMMIT" ] || { echo "ERRO: HEAD=$CURRENT esperado=$COMMIT"; exit 1; }

echo
echo "[4/7] Parando containers..."
docker compose down

echo
echo "[5/7] Reconstruindo server..."
docker compose build --no-cache server

echo
echo "[6/7] Iniciando servicos..."
docker compose up -d

echo
echo "[7/7] Aguardando health (ate 90s)..."
HEALTH_OK=0
for attempt in $(seq 1 30); do
  if curl -fsS --max-time 2 "$HEALTH_URL" >/tmp/memoria-health.json 2>/dev/null; then
    HEALTH_OK=1
    echo "HEALTH: OK na tentativa $attempt"
    cat /tmp/memoria-health.json; echo
    break
  fi
  printf '.'; sleep 3
done
if [ "$HEALTH_OK" -ne 1 ]; then
  echo; echo "ERRO: servidor nao ficou saudavel em 90s."
  docker compose ps
  docker compose logs --tail=200 server
  exit 1
fi

echo
echo "========================================"
echo " V2 CANDIDATE ATIVA"
echo "========================================"
echo "Commit ativo: $(git rev-parse HEAD)"
echo "Os dados persistentes em /data nao sao zerados pelo script."
echo "CTRL+C encerra somente a visualizacao dos logs."
echo

docker compose logs -f --tail=150 server | grep -E --line-buffered 'trajectory_guidance|epistemic_target|trajectory_deferred|topic:|evidence:|learning|stagnation|error|HTTP 500|health'
