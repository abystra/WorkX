#!/usr/bin/env bash
# Prints the SQL that creates the WorkX database roles (same as scripts/dev/pg.sh). For CI or a hosted
# PostgreSQL: scripts/dev/pg-roles.sql.sh | psql -U postgres
cat <<'SQL'
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'workx_owner') THEN
    CREATE ROLE workx_owner LOGIN PASSWORD 'workx_owner_dev' CREATEDB;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'workx_app') THEN
    CREATE ROLE workx_app LOGIN PASSWORD 'workx_app_dev' NOSUPERUSER NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'workx_broker') THEN
    CREATE ROLE workx_broker LOGIN PASSWORD 'workx_broker_dev' NOSUPERUSER NOBYPASSRLS;
  END IF;
END $$;
GRANT workx_app TO workx_owner;
GRANT workx_broker TO workx_owner;
GRANT workx_app TO workx_broker;
SQL
