#!/usr/bin/env bash
set -u
cd "${MEMORIA_SERVER_DIR:-$HOME/memoria.ia.server}" || exit 1
OUT="/tmp/memoria-bdr-diagnostic-$(date +%Y%m%d-%H%M%S).txt"
exec > >(tee "$OUT") 2>&1

echo "MEMORIA.IA BDR DIAGNOSTIC v1"
echo "time=$(date -Is)"
echo "head=$(git rev-parse HEAD 2>/dev/null || true)"
echo

echo "== containers =="
docker compose ps || true

echo
 echo "== health =="
curl -sS http://127.0.0.1/api/server/v1/health || true; echo

echo
 echo "== BDR files / mounts (read only) =="
docker compose exec -T memoria sh -c 'echo "PWD=$PWD"; find /app /data /var/lib -maxdepth 4 -type f \( -name "*.db" -o -name "*.sqlite*" -o -name "*.json" -o -name "*.bdr" \) -printf "%p %s bytes\n" 2>/dev/null | sort' || true

echo
 echo "== recent persistence traceback/errors =="
docker compose logs --no-color --tail=500 memoria 2>&1 | grep -Ei -C 8 'traceback|exception|error|500|save|persist|episode' | tail -n 220 || true

echo
 echo "== episode history count =="
HIST="$(curl -sS 'http://127.0.0.1/api/v1/episodes/history?limit=5000' 2>/dev/null || true)"
python3 - "$HIST" <<'PY'
import json,sys
try:
 d=json.loads(sys.argv[1]); rows=d if isinstance(d,list) else d.get('episodes') or d.get('items') or d.get('history') or []
 print('episodes_history_count=',len(rows))
 if rows: print('last_episode=',json.dumps(rows[-1],ensure_ascii=False)[:1000])
except Exception as e: print('history_parse_error=',repr(e))
PY

echo
 echo "== SAFE single write probe on CURRENT BDR =="
ID="diag-$(date +%s)-$RANDOM"
BODY=$(printf '{"episode_id":"%s","role":"user","text":"BDR diagnostic boundary probe","session_id":"diagnostic:bdr","order":1,"timestamp":"%s","event_type":"diagnostic_probe","topics":["bdr","boundary-256"]}' "$ID" "$(date -u +%Y-%m-%dT%H:%M:%SZ)")
CODE=$(curl -sS -o /tmp/bdr-probe-response.txt -w '%{http_code}' -H 'Content-Type: application/json' -d "$BODY" http://127.0.0.1/api/v1/episodes || true)
echo "probe_http=$CODE episode_id=$ID"
echo "probe_response:"; cat /tmp/bdr-probe-response.txt 2>/dev/null || true; echo

echo
 echo "== traceback immediately after probe =="
docker compose logs --no-color --tail=180 memoria 2>&1 | tail -n 180 || true

echo
 echo "== interpretation =="
if [ "$CODE" = "201" ]; then
  echo "CURRENT_WRITE=PASS: banco atual aceita escrita; 256 nao e bloqueio absoluto."
else
  echo "CURRENT_WRITE=FAIL: banco atual reproduziu a falha. Use traceback acima para separar schema legado, serializacao, indice ou limite."
fi
echo "NOTE: este diagnostico NAO apaga, migra ou recria o BDR. Ele faz somente uma tentativa de episodio diagnostico no banco atual."
echo "NOTE: o teste destrutivo/isolado de 300 registros deve rodar apenas em storage temporario separado; nao foi executado contra producao."
echo
echo "RELATORIO=$OUT"
