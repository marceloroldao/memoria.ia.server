#!/usr/bin/env bash
set -euo pipefail

COMMIT="4c54c559c70ca67471b7fe09bc6762b9e60721c2"
PROJECT="${MEMORIA_SERVER_DIR:-$HOME/memoria.ia.server}"
HEALTH_URL="http://127.0.0.1:8780/api/server/v1/health"

echo "========================================"
echo " Memoria.ia Server - Update V2"
echo " Commit: $COMMIT"
echo "========================================"

cd "$PROJECT"

echo
echo "[1/7] Verificando repositorio..."
git status --short
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo
    echo "ERRO: existem alteracoes locais versionadas."
    echo "Nada sera sobrescrito."
    git status
    exit 1
fi

echo
echo "[2/7] Buscando atualizacoes..."
git fetch origin

echo
echo "[3/7] Fixando commit validado/candidato..."
git checkout --detach "$COMMIT"
CURRENT="$(git rev-parse HEAD)"
if [ "$CURRENT" != "$COMMIT" ]; then
    echo "ERRO: HEAD diferente do commit esperado."
    echo "Esperado: $COMMIT"
    echo "Atual:    $CURRENT"
    exit 1
fi
echo "OK: commit correto."

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
echo "[7/7] Estado dos containers..."
docker compose ps

echo
echo "========================================"
echo " HEALTH CHECK"
echo "========================================"
echo "Aguardando ate 90s pelo servidor..."
HEALTH_OK=0
for attempt in $(seq 1 30); do
    if curl -fsS --max-time 2 "$HEALTH_URL" >/tmp/memoria-health.json 2>/dev/null; then
        HEALTH_OK=1
        echo "HEALTH: OK na tentativa $attempt"
        cat /tmp/memoria-health.json
        echo
        break
    fi
    printf '.'
    sleep 3
done
if [ "$HEALTH_OK" -ne 1 ]; then
    echo
    echo "ERRO: health check nao respondeu em ate 90s."
    docker compose ps
    docker compose logs --tail=150 server
    exit 1
fi

echo
echo "========================================"
echo " V2 ATUALIZADA"
echo "========================================"
echo "Commit ativo: $(git rev-parse HEAD)"
echo
echo "Acompanhando trajectory_guidance, epistemic_target, topic, evidence, learning, stagnation e error."
echo "CTRL+C encerra somente a visualizacao; o servidor continua funcionando."
echo

docker compose logs -f --tail=100 server | grep -E --line-buffered 'trajectory_guidance|epistemic_target|trajectory_deferred|topic:|evidence:|learning|stagnation|error'
