#!/usr/bin/env sh
set -eu
bash scripts/prepare-env.sh
docker compose build --pull
docker compose up -d --remove-orphans
docker compose ps
