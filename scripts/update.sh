#!/usr/bin/env sh
set -eu
docker compose build --pull
docker compose up -d --remove-orphans
docker compose ps
