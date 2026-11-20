#!/usr/bin/env bash
# Starts the local Postgres 16 + pgvector instance used by OpsPilot.
# Binaries come from the pgserver wheel; data lives outside the repo.
set -euo pipefail

PGBIN="${OPSPILOT_PGBIN:-$HOME/.local/share/opspilot-pg/pg/pgserver/pginstall/bin}"
PGDATA="${OPSPILOT_PGDATA:-$HOME/.local/share/opspilot-pg/data}"
PORT="${OPSPILOT_PGPORT:-5432}"

if "$PGBIN/pg_isready" -h 127.0.0.1 -p "$PORT" >/dev/null 2>&1; then
  echo "Postgres already accepting connections on 127.0.0.1:$PORT"
  exit 0
fi

"$PGBIN/pg_ctl" -D "$PGDATA" -l "$PGDATA/server.log" \
  -o "-p $PORT -k /tmp -c listen_addresses=127.0.0.1" -w start
"$PGBIN/pg_isready" -h 127.0.0.1 -p "$PORT"
