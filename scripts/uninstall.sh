#!/usr/bin/env sh
set -eu
echo "Stopping Memoria.ia Server. Persistent memory data will be preserved."
docker compose down
echo "To permanently remove stored data, run: docker compose down --volumes"
