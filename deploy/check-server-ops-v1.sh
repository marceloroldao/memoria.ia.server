#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="${MEMORIA_SERVER_DIR:-$HOME/memoria.ia.server}"
cd "$PROJECT"

echo "==============================================="
echo " M.IA.SERVER - Server Ops V1 smoke test"
echo " modo: somente leitura"
echo "==============================================="

if [ ! -f .env ]; then
  echo "ERRO: .env nao encontrado em $PROJECT"
  exit 1
fi

docker compose ps

docker compose exec -T server python - <<'PY'
import http.cookiejar
import json
import os
from pathlib import Path
from urllib.request import HTTPCookieProcessor, Request, build_opener

BASE="http://127.0.0.1:8780"

def open_json(opener, path, *, method="GET", payload=None, authenticated=True):
    data=None
    headers={"Accept":"application/json"}
    if payload is not None:
        data=json.dumps(payload).encode("utf-8")
        headers["Content-Type"]="application/json"
    req=Request(BASE+path,data=data,headers=headers,method=method)
    with opener.open(req,timeout=10) as response:
        body=json.load(response)
        return response.status, body

jar=http.cookiejar.CookieJar()
opener=build_opener(HTTPCookieProcessor(jar))

user=os.environ.get("MEMORIA_SERVER_ADMIN_USER","admin")
password=os.environ["MEMORIA_SERVER_ADMIN_PASSWORD"]

status, health = open_json(opener,"/api/server/v1/health")
assert status==200, status
assert health.get("shell",{}).get("status")=="online", health
assert health.get("status")=="online", health
for component_name, component in (health.get("components") or {}).items():
    assert component.get("status")=="online", (component_name, component, health)

status, ready = open_json(opener,"/api/server/v1/ready")
assert status==200, status
assert ready.get("ready") is True, ready

status, authority = open_json(opener,"/api/server/v1/device-auth/authority")
assert status==200, status
assert authority.get("algorithm")=="Ed25519", authority
assert str(authority.get("public_key","")).startswith("ed25519:"), authority

status, _login = open_json(
    opener,
    "/api/server/v1/login",
    method="POST",
    payload={"username":user,"password":password},
)
assert status==200, status

status, capabilities = open_json(opener,"/api/server/v1/capabilities")
assert status==200, status
expected_true = [
    "device_registry_v1",
    "device_heartbeat_v1",
    "device_auth_v1",
    "device_certificates_v1",
    "device_permissions_v1",
    "device_enrollment_v1",
    "audit_log_v1",
    "server_identity_v1",
]
for key in expected_true:
    assert capabilities.get(key) is True, (key, capabilities)
assert capabilities.get("format_bdr") is False, capabilities

status, identity = open_json(opener,"/api/server/v1/server/identity")
assert status==200, status
server_id=identity.get("server_id")
assert isinstance(server_id,str) and server_id.startswith("srv-"), identity
assert health.get("shell",{}).get("server_id")==server_id, (health, identity)
assert authority.get("server_id")==server_id, (authority, identity)

status, devices = open_json(opener,"/api/server/v1/devices")
assert status==200, status
assert isinstance(devices.get("devices"),list), devices
assert devices.get("count")==len(devices["devices"]), devices

status, enrollments = open_json(opener,"/api/server/v1/enrollments")
assert status==200, status
assert isinstance(enrollments.get("invitations"),list), enrollments
assert enrollments.get("count")==len(enrollments["invitations"]), enrollments

status, audit = open_json(opener,"/api/server/v1/audit?limit=10")
assert status==200, status
assert isinstance(audit.get("events"),list), audit

for path in ("/devices","/devices.js"):
    req=Request(BASE+path,method="GET")
    with opener.open(req,timeout=10) as response:
        body=response.read()
        assert response.status==200, (path,response.status)
        assert body, path

data_dir=Path(os.environ.get("MEMORIA_SERVER_DATA_DIR","/data"))
identity_file=data_dir/"server-identity.json"
authority_file=data_dir/"device-authority.json"
assert identity_file.exists(), identity_file
assert authority_file.exists(), authority_file

print(json.dumps({
    "schema":"memoria-server-ops-smoke/v1",
    "status":"ok",
    "server_id":server_id,
    "authority_fingerprint":authority.get("public_key_fingerprint"),
    "devices":devices.get("count"),
    "enrollments":enrollments.get("count"),
    "audit_events_returned":len(audit.get("events") or []),
    "capabilities_checked":expected_true,
    "format_bdr":capabilities.get("format_bdr"),
    "writes_performed":False,
},ensure_ascii=False,indent=2))
PY

echo
echo "SMOKE TEST: PASS"
echo "Nenhum dispositivo, convite, episodio ou registro BDR foi criado/alterado."
