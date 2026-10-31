#!/usr/bin/env bash
# Local PostgreSQL 16 cluster for development and tests (no container daemon needed).
#   scripts/dev/pg.sh start | stop | status | url | reset
# Creates two roles, matching production (docs/architecture/11-DATA-API-EVENTS.md, RLS):
#   workx_owner  owns the schema and runs migrations
#   workx_app    used by every service at runtime; not the table owner and NOBYPASSRLS, so RLS applies
# Override with WORKX_PG_BIN, WORKX_PG_DATA, WORKX_PG_PORT. On macOS/others, any PostgreSQL 16 works:
# create the same roles and export WORKX_DATABASE_URL / WORKX_MIGRATION_DATABASE_URL yourself.
set -euo pipefail

PG_BIN="${WORKX_PG_BIN:-$(ls -d /usr/lib/postgresql/16/bin 2>/dev/null || dirname "$(command -v pg_ctl)")}"
PG_DATA="${WORKX_PG_DATA:-/var/lib/postgresql/workx-dev}"
PG_PORT="${WORKX_PG_PORT:-54329}"
OWNER_PW="workx_owner_dev"
APP_PW="workx_app_dev"

as_pg() {
  if [ "$(id -u)" = "0" ] && id postgres >/dev/null 2>&1; then runuser -u postgres -- "$@"; else "$@"; fi
}
psql_admin() { as_pg "$PG_BIN/psql" -h /tmp -p "$PG_PORT" -U postgres -v ON_ERROR_STOP=1 -qAt "$@"; }

init() {
  if [ ! -f "$PG_DATA/PG_VERSION" ]; then
    mkdir -p "$PG_DATA"
    [ "$(id -u)" = "0" ] && chown postgres:postgres "$PG_DATA"
    as_pg "$PG_BIN/initdb" -D "$PG_DATA" -U postgres --auth=trust --encoding=UTF8 --locale=C.UTF-8 >/dev/null
    {
      echo "listen_addresses = '127.0.0.1'"
      echo "port = $PG_PORT"
      echo "unix_socket_directories = '/tmp'"
      echo "max_connections = 200"
      echo "fsync = off"
      echo "synchronous_commit = off"
    } | as_pg tee -a "$PG_DATA/postgresql.conf" >/dev/null
  fi
}

roles() {
  psql_admin -d postgres <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'workx_owner') THEN
    CREATE ROLE workx_owner LOGIN PASSWORD '$OWNER_PW' CREATEDB;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'workx_app') THEN
    CREATE ROLE workx_app LOGIN PASSWORD '$APP_PW' NOSUPERUSER NOBYPASSRLS;
  END IF;
END \$\$;
SQL
  # Test databases are created by workx_owner, which must be able to grant to workx_app.
  psql_admin -d postgres -c "GRANT workx_app TO workx_owner" >/dev/null
  if [ "$(psql_admin -d postgres -c "SELECT 1 FROM pg_database WHERE datname = 'workx'")" != "1" ]; then
    psql_admin -d postgres -c "CREATE DATABASE workx OWNER workx_owner" >/dev/null
  fi
}

case "${1:-start}" in
  start)
    init
    if ! as_pg "$PG_BIN/pg_ctl" -D "$PG_DATA" status >/dev/null 2>&1; then
      as_pg "$PG_BIN/pg_ctl" -D "$PG_DATA" -l "$PG_DATA/server.log" -w start >/dev/null
    fi
    roles
    echo "PostgreSQL running on 127.0.0.1:$PG_PORT ($PG_DATA)"
    ;;
  stop) as_pg "$PG_BIN/pg_ctl" -D "$PG_DATA" -m fast stop ;;
  status) as_pg "$PG_BIN/pg_ctl" -D "$PG_DATA" status ;;
  reset)
    as_pg "$PG_BIN/pg_ctl" -D "$PG_DATA" -m fast stop 2>/dev/null || true
    rm -rf "$PG_DATA"
    exec "$0" start
    ;;
  url)
    echo "export WORKX_DATABASE_URL=postgresql+psycopg://workx_app:$APP_PW@127.0.0.1:$PG_PORT/workx"
    echo "export WORKX_MIGRATION_DATABASE_URL=postgresql+psycopg://workx_owner:$OWNER_PW@127.0.0.1:$PG_PORT/workx"
    ;;
  *) echo "usage: $0 start|stop|status|reset|url" >&2; exit 2 ;;
esac
