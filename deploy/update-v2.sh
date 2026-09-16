#!/usr/bin/env bash
set -euo pipefail

COMMIT="4c1be255130a5775ae9c6bfefe7a486cdc6a8c86"
PROJECT="${MEMORIA_SERVER_DIR:-$HOME/memoria.ia.server}"
HEALTH_URL="${MEMORIA_SERVER_HEALTH_URL:-http://127.0.0.1/api/server/v1/health}"

echo "========================================"
echo " Memoria.ia Server - Update V2 Hotfix"
echo " Commit: $COMMIT"
echo "========================================"
cd "$PROJECT"

echo; echo "[1/7] Verificando repositorio..."
git status --short
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERRO: existem alteracoes locais versionadas. Nada sera sobrescrito."
  git status
  exit 1
fi

echo; echo "[2/7] Buscando atualizacoes..."
git fetch origin

echo; echo "[3/7] Fixando candidato exato..."
git checkout --detach "$COMMIT"
CURRENT="$(git rev-parse HEAD)"
[ "$CURRENT" = "$COMMIT" ] || { echo "ERRO: HEAD=$CURRENT esperado=$COMMIT"; exit 1; }

echo; echo "[4/7] Parando containers..."
docker compose down

echo; echo "[5/7] Reconstruindo server..."
docker compose build --no-cache server

echo; echo "[6/7] Iniciando servicos..."
docker compose up -d

echo; echo "[7/7] Aguardando health pela porta publicada (ate 120s)..."
HEALTH_OK=0
for attempt in $(seq 1 40); do
  if curl -fsS --max-time 3 "$HEALTH_URL" >/tmp/memoria-health.json 2>/dev/null; then
    HEALTH_OK=1
    echo "HEALTH: OK na tentativa $attempt"
    cat /tmp/memoria-health.json; echo
    break
  fi
  printf '.'; sleep 3
done
if [ "$HEALTH_OK" -ne 1 ]; then
  echo; echo "ERRO: servidor nao respondeu em $HEALTH_URL."
  docker compose ps
  docker compose logs --tail=200 server
  exit 1
fi

echo; echo "Validando arquivos da interface dentro do container..."
# /admin/memoria pode redirecionar para /login sem sessao; portanto a validacao
# de deploy deve verificar os assets efetivamente copiados para a imagem.
docker compose exec -T server sh -c "grep -q 'diagnostics-fix.js' /app/apps/memoria-admin/static/index.html" || { echo 'ERRO: index.html da imagem nao referencia diagnostics-fix.js'; exit 1; }
docker compose exec -T server sh -c "test -s /app/apps/memoria-admin/static/diagnostics-fix.js && grep -q 'Baixar relatório TXT' /app/apps/memoria-admin/static/diagnostics-fix.js" || { echo 'ERRO: modulo diagnostics-fix.js ausente na imagem'; exit 1; }
docker compose exec -T server sh -c "grep -q 'Do not reload BDR history here' /app/apps/memoria-admin/static/history-fix.js" || { echo 'ERRO: hotfix resiliente do chat ausente na imagem'; exit 1; }
echo "INTERFACE: OK - TXT + chat hotfix presentes na imagem"

echo; echo "========================================"
echo " V2 HOTFIX ATIVA"
echo "========================================"
echo "Commit ativo: $(git rev-parse HEAD)"
echo "Correcoes: chat resiliente a falha BDR + TXT restaurado + health porta 80."
echo "Dados persistentes nao sao zerados pelo script."
echo "CTRL+C encerra somente os logs."
echo

docker compose logs -f --tail=150 server | grep -E --line-buffered 'trajectory_guidance|epistemic_target|topic:|evidence:|learning|stagnation|error|HTTP 500|health'
