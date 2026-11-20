#!/usr/bin/env bash
# Stops the local Postgres instance started by scripts/start-db.sh.
set -euo pipefail

PGBIN="${OPSPILOT_PGBIN:-$HOME/.local/share/opspilot-pg/pg/pgserver/pginstall/bin}"
PGDATA="${OPSPILOT_PGDATA:-$HOME/.local/share/opspilot-pg/data}"

"$PGBIN/pg_ctl" -D "$PGDATA" -m fast -w stop
