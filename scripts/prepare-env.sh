#!/usr/bin/env sh
set -eu

if [ ! -f .env ]; then
  cp .env.example .env
fi

random_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 24
  else
    head -c 36 /dev/urandom | od -An -tx1 | tr -d ' \n'
  fi
}

if grep -q '^MEMORIA_API_KEY=change-me-with-a-long-random-secret$' .env; then
  generated_api_key="$(random_secret)"
  sed -i "s/^MEMORIA_API_KEY=.*/MEMORIA_API_KEY=${generated_api_key}/" .env
fi

if ! grep -q '^MEMORIA_SERVER_ADMIN_USER=' .env; then
  printf '\nMEMORIA_SERVER_ADMIN_USER=admin\n' >> .env
fi

if grep -q '^MEMORIA_SERVER_ADMIN_PASSWORD=change-me-with-a-random-login-password
if ! grep -q '^MEMORIA_SERVER_SESSION_HOURS=' .env; then
  printf 'MEMORIA_SERVER_SESSION_HOURS=8\n' >> .env
fi

if ! grep -q '^MEMORIA_SERVER_COOKIE_SECURE=' .env; then
  printf 'MEMORIA_SERVER_COOKIE_SECURE=false\n' >> .env
fi
 .env; then
  generated_password="$(random_secret)"
  sed -i "s/^MEMORIA_SERVER_ADMIN_PASSWORD=.*/MEMORIA_SERVER_ADMIN_PASSWORD=${generated_password}/" .env
  echo "Generated a new server login password in .env."
elif ! grep -q '^MEMORIA_SERVER_ADMIN_PASSWORD=' .env; then
  generated_password="$(random_secret)"
  printf 'MEMORIA_SERVER_ADMIN_PASSWORD=%s\n' "${generated_password}" >> .env
  echo "Generated a new server login password in .env."
fi

if ! grep -q '^MEMORIA_SERVER_SESSION_HOURS=' .env; then
  printf 'MEMORIA_SERVER_SESSION_HOURS=8\n' >> .env
fi

if ! grep -q '^MEMORIA_SERVER_COOKIE_SECURE=' .env; then
  printf 'MEMORIA_SERVER_COOKIE_SECURE=false\n' >> .env
fi
