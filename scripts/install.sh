#!/usr/bin/env sh
set -eu

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required. Install Docker Engine and the Compose plugin first." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "The Docker Compose plugin is required." >&2
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
  if command -v openssl >/dev/null 2>&1; then
    generated_key="$(openssl rand -hex 32)"
  else
    generated_key="$(head -c 48 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  fi
  sed -i "s/change-me-with-a-long-random-secret/${generated_key}/" .env
  echo "Created .env with a random administrator API key."
else
  echo "Using the existing .env file."
fi

docker compose build
docker compose up -d
docker compose ps

port="$(sed -n 's/^MEMORIA_SERVER_PORT=//p' .env | tail -n 1)"
port="${port:-8780}"
echo "Memoria.ia Server started at http://127.0.0.1:${port}"
echo "Place it behind HTTPS before exposing it publicly."
