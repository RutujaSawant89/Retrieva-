#!/bin/sh
# Creates the runtime role used by the API and workers. It is deliberately not a superuser and
# has no BYPASSRLS, so PostgreSQL Row-Level Security policies apply to every query it runs.
# Table privileges are granted by the Alembic migrations (run as the owner role).
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_password="$APP_DB_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE retrieva_app LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'retrieva_app')
\gexec
GRANT CONNECT ON DATABASE retrieva TO retrieva_app;
CREATE EXTENSION IF NOT EXISTS vector;
SQL
