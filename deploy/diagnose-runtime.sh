#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="${MEMORIA_SERVER_DIR:-$HOME/memoria.ia.server}"
cd "$PROJECT"

echo "==============================================="
echo " M.IA.SERVER - Runtime diagnostic"
echo " modo: somente leitura"
echo "==============================================="

echo
echo "[1/7] Estado dos servicos"
docker compose ps

echo
echo "[2/7] Pins ativos"
grep -E '^(MEMORIA_COMMIT|BDR_COMMIT)=' .env || true

echo
echo "[3/7] Inspect do container Memoria.ia"
MEMORIA_ID="$(docker compose ps -q memoria)"
if [ -z "$MEMORIA_ID" ]; then
  echo "ERRO: container memoria nao localizado"
  exit 1
fi
docker inspect "$MEMORIA_ID" --format '
container={{.Name}}
image={{.Image}}
restart_count={{.RestartCount}}
state={{.State.Status}}
running={{.State.Running}}
restarting={{.State.Restarting}}
exit_code={{.State.ExitCode}}
oom_killed={{.State.OOMKilled}}
error={{.State.Error}}
started_at={{.State.StartedAt}}
finished_at={{.State.FinishedAt}}
health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}
'

echo
echo "[4/7] Health agregado do Server"
python3 - <<'PY'
import json, urllib.request, urllib.error
for path in ("/api/server/v1/health", "/api/server/v1/ready"):
    url="http://127.0.0.1"+path
    try:
        with urllib.request.urlopen(url,timeout=5) as r:
            print(path, r.status)
            print(json.dumps(json.load(r),ensure_ascii=False,indent=2))
    except urllib.error.HTTPError as exc:
        print(path, exc.code)
        try:
            print(json.dumps(json.load(exc),ensure_ascii=False,indent=2))
        except Exception:
            print(exc.read().decode("utf-8","replace"))
    except Exception as exc:
        print(path, "ERROR", repr(exc))
PY

echo
echo "[5/7] Ultimos logs da Memoria.ia"
docker compose logs --no-color --tail=220 memoria || true

echo
echo "[6/7] Logs recentes relacionados no Server e BDR Explorer"
docker compose logs --no-color --tail=120 server bdr-explorer || true

echo
echo "[7/7] Recursos do host"
df -h /
docker system df || true

echo
echo "DIAGNOSTICO CONCLUIDO"
echo "Nenhum container foi reiniciado, parado, reconstruido ou modificado por este script."
