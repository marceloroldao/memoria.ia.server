#!/usr/bin/env sh
set -eu
docker compose ps
docker compose exec -T server python -c "import json,urllib.request; print(json.dumps(json.load(urllib.request.urlopen('http://127.0.0.1:8780/api/server/v1/health', timeout=5)), indent=2))"
