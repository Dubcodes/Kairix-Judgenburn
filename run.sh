#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed or is not available on PATH. Install Docker Engine or Docker Desktop, then run this again." >&2
  exit 1
fi

if [ ! -f ".env" ]; then
  cp ".env.example" ".env"
  echo "Created .env from .env.example. Change POSTGRES_PASSWORD before event day."
fi

HOST_PORT="$(awk -F= '/^[[:space:]]*HOST_PORT[[:space:]]*=/{gsub(/[[:space:]]/, "", $2); print $2}' .env | tail -n 1)"
HOST_PORT="${HOST_PORT:-7080}"

echo "Building and starting Kairix on port $HOST_PORT..."
docker compose up -d --build

HEALTH_URL="http://localhost:$HOST_PORT/api/health"
READY=0
i=0
while [ "$i" -lt 60 ]; do
  if command -v curl >/dev/null 2>&1 && curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    READY=1
    break
  fi
  i=$((i + 1))
  sleep 1
done

if [ "$READY" -eq 1 ]; then
  echo "Kairix is running."
else
  echo "Kairix is still starting. Check logs with: docker compose logs -f web"
fi

echo "Home:        http://localhost:$HOST_PORT/"
echo "Admin:       http://localhost:$HOST_PORT/admin"
echo "Judge:       http://localhost:$HOST_PORT/judge"
echo "Public:      http://localhost:$HOST_PORT/public"
echo "Queue:       http://localhost:$HOST_PORT/queue"
echo "OBS overlay: http://localhost:$HOST_PORT/obs-overlay"
