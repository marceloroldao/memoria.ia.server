#!/usr/bin/env bash
set -Eeuo pipefail

# Memoria.ia Server - atualização controlada para o runtime estrutural V2
# - preserva volumes/dados
# - fixa Memoria.ia + Resolutive-DB em commits compatíveis
# - mantém o container antigo se o build falhar
# - faz rollback automático se o novo container não ficar healthy
# - valida a rota /api/v1/structural/text/resolve

REPO_DIR="${REPO_DIR:-$HOME/memoria.ia.server}"
MEMORIA_COMMIT="bd33b9cfcfa78f0e3850fb5e298cbf4cbdc360b9"
BDR_COMMIT="d09914b85646353d8fd004ccf99e96a94fab9eef"
WAIT_SECONDS="${WAIT_SECONDS:-180}"
TS="$(date +%Y%m%d-%H%M%S)"
LOG_DIR="${REPO_DIR}/deploy-logs"
BUILD_LOG="${LOG_DIR}/memoria-v2-build-${TS}.log"
ENV_BACKUP="${REPO_DIR}/.env.backup-${TS}"
ROLLBACK_TAG="memoria-ia-server-memoria:rollback-${TS}"

say() { printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
die() { printf '\nERRO: %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "docker não encontrado"
docker compose version >/dev/null 2>&1 || die "docker compose não disponível"
[[ -d "$REPO_DIR/.git" ]] || die "repositório não encontrado em $REPO_DIR"

cd "$REPO_DIR"
mkdir -p "$LOG_DIR"

say "1/9 Atualizando memoria.ia.server"
if ! git diff --quiet || ! git diff --cached --quiet; then
  die "há alterações locais no repositório. Faça commit/stash antes de continuar."
fi
# O servidor pode estar em detached HEAD após deploy por SHA. Volte para main
# apenas se a árvore estiver limpa (checado acima), preserve o estado remoto e
# então avance por fast-forward.
git fetch origin main
current_branch="$(git symbolic-ref --quiet --short HEAD || true)"
if [[ "$current_branch" != "main" ]]; then
  git switch main 2>/dev/null || git switch -c main --track origin/main
fi
git pull --ff-only origin main

say "2/9 Salvando backup do .env"
[[ -f .env ]] || die ".env não encontrado em $REPO_DIR"
cp -a .env "$ENV_BACKUP"
echo "Backup: $ENV_BACKUP"

set_env() {
  local key="$1" value="$2"
  if grep -q "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env
  else
    printf '\n%s=%s\n' "$key" "$value" >> .env
  fi
}

set_env MEMORIA_COMMIT "$MEMORIA_COMMIT"
set_env BDR_COMMIT "$BDR_COMMIT"

say "3/9 Confirmando pins efetivos"
RESOLVED="$(docker compose config | grep -E 'MEMORIA_COMMIT:|BDR_COMMIT:' || true)"
echo "$RESOLVED"
grep -q "MEMORIA_COMMIT: ${MEMORIA_COMMIT}" <<<"$RESOLVED" || die "MEMORIA_COMMIT efetivo não é o esperado"
grep -q "BDR_COMMIT: ${BDR_COMMIT}" <<<"$RESOLVED" || die "BDR_COMMIT efetivo não é o esperado"

OLD_CID="$(docker compose ps -q memoria || true)"
OLD_IMAGE_ID=""
if [[ -n "$OLD_CID" ]]; then
  OLD_IMAGE_ID="$(docker inspect -f '{{.Image}}' "$OLD_CID")"
  docker tag "$OLD_IMAGE_ID" "$ROLLBACK_TAG"
  say "Imagem atual preservada para rollback: $ROLLBACK_TAG"
fi

say "4/9 Compilando Memoria.ia V2 + BDR compatível"
if ! docker compose build --no-cache memoria 2>&1 | tee "$BUILD_LOG"; then
  echo
  echo "Build falhou. O container atual NÃO foi substituído."
  echo "Log: $BUILD_LOG"
  exit 2
fi

say "5/9 Substituindo somente o serviço memoria (volumes preservados)"
docker compose up -d --no-deps --force-recreate memoria

wait_healthy() {
  local service="$1" timeout="$2" elapsed=0 cid status
  while (( elapsed < timeout )); do
    cid="$(docker compose ps -q "$service" || true)"
    if [[ -n "$cid" ]]; then
      status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null || true)"
      printf '\r  %s: %s (%ss/%ss)' "$service" "${status:-desconhecido}" "$elapsed" "$timeout"
      if [[ "$status" == "healthy" ]]; then
        echo
        return 0
      fi
      if [[ "$status" == "exited" || "$status" == "dead" ]]; then
        echo
        return 1
      fi
    fi
    sleep 3
    elapsed=$((elapsed+3))
  done
  echo
  return 1
}

rollback() {
  echo
  echo "Novo runtime não ficou saudável. Iniciando rollback..."
  if [[ -z "$OLD_IMAGE_ID" ]]; then
    echo "Não havia imagem anterior registrada para rollback automático." >&2
    return 1
  fi
  docker tag "$OLD_IMAGE_ID" memoria-ia-server-memoria:latest
  docker compose up -d --no-deps --force-recreate memoria
  wait_healthy memoria 120 || true
  echo "Rollback aplicado. Backup do .env: $ENV_BACKUP"
}

say "6/9 Aguardando saúde do novo runtime"
if ! wait_healthy memoria "$WAIT_SECONDS"; then
  docker compose logs --tail=120 memoria || true
  rollback
  exit 3
fi

say "7/9 Verificando se a rota estrutural V2 existe dentro do container"
MEM_CID="$(docker compose ps -q memoria)"
if ! docker exec "$MEM_CID" sh -c 'grep -R "structural/text/resolve" -n /app/src/memoria_resolutiva >/dev/null 2>&1'; then
  echo "Rota V2 ausente no container novo."
  rollback
  exit 4
fi
echo "Rota V2 encontrada."

say "8/9 Testando Server -> Memoria.ia V2 com a chave interna"
docker compose exec -T server python - <<'PY'
import json, os, urllib.request, urllib.error
u = os.environ["MEMORIA_API_URL"].rstrip("/") + "/api/v1/structural/text/resolve"
payload = json.dumps({
    "query": "teste",
    "hierarchy_id": "diagnostico-deploy-v2",
    "limit": 1,
    "max_scan": 1,
}).encode()
req = urllib.request.Request(
    u,
    data=payload,
    headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Memoria-Key": os.environ["MEMORIA_API_KEY"],
    },
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        body = r.read().decode()
        print("HTTP", r.status)
        print(body)
        if r.status != 200:
            raise SystemExit(5)
except urllib.error.HTTPError as e:
    print("HTTP", e.code)
    print(e.read().decode(errors="replace"))
    raise SystemExit(5)
PY

say "9/9 Reavaliando o shell do servidor"
docker compose restart server >/dev/null
sleep 3
docker compose ps

echo
echo "============================================================"
echo "OK: Memoria.ia V2 estrutural está implantada e respondendo."
echo "Memoria commit: $MEMORIA_COMMIT"
echo "BDR commit:     $BDR_COMMIT"
echo "Build log:      $BUILD_LOG"
echo "Backup .env:    $ENV_BACKUP"
echo "Próximo passo: no OFF.IA, toque em 'Testar memory.sync'."
echo "============================================================"
