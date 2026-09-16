#!/usr/bin/env bash
set -euo pipefail

COMMIT="8b18a204643339d84a07d019f0410eefa8407f0c"
PROJECT="${MEMORIA_SERVER_DIR:-$HOME/memoria.ia.server}"

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
echo "[3/7] Fixando commit validado..."
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
echo "Aguardando servidor iniciar..."
sleep 8

echo
echo "========================================"
echo " HEALTH CHECK"
echo "========================================"
if curl -fsS http://127.0.0.1:8780/api/server/v1/health; then
    echo
    echo "HEALTH: OK"
else
    echo
    echo "ERRO: health check falhou."
    docker compose logs --tail=100 server
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

docker compose logs -f --tail=100 server | grep -E --line-buffered 'trajectory_guidance|epistemic_target|topic:|evidence:|learning|stagnation|error'
