"""Start a local embedded PostgreSQL (with pgvector) for development without Docker.

Usage::

    uv run python scripts/dev_db.py            # start, create DB + roles, print env vars
    uv run python scripts/dev_db.py --stop     # stop the server

The data directory is ``backend/.pgdata`` (git-ignored). Two roles are created:

* ``postgres`` (superuser) — used only for migrations
* ``retrieva_app`` (no superuser, no BYPASSRLS) — used by the API and workers so that
  Row-Level Security policies are enforced
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / ".pgdata"
APP_ROLE = "retrieva_app"
APP_PASSWORD = "retrieva_app_dev"  # local development only  # noqa: S105


def ensure_database(server, name: str) -> None:  # type: ignore[no-untyped-def]
    exists = server.psql(f"SELECT 1 FROM pg_database WHERE datname = '{name}';")
    if "(1 row)" not in exists:
        server.psql(f'CREATE DATABASE "{name}";')


def ensure_app_role(server) -> None:  # type: ignore[no-untyped-def]
    server.psql(
        "DO $$ BEGIN "
        f"IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN "
        f"CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{APP_PASSWORD}' NOSUPERUSER NOBYPASSRLS; "
        "END IF; END $$;"
    )


def main() -> int:
    import pgserver

    parser = argparse.ArgumentParser()
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--database", default="retrieva")
    parser.add_argument(
        "--no-write-env",
        dest="write_env",
        action="store_false",
        help="only print the URLs, do not touch .env",
    )
    args = parser.parse_args()

    server = pgserver.get_server(DATA_DIR, cleanup_mode=None)
    if args.stop:
        server.cleanup()
        print("stopped")
        return 0

    ensure_app_role(server)
    ensure_database(server, args.database)
    admin_uri = server.get_uri(args.database).replace("postgresql://", "postgresql+psycopg://")
    host_part = admin_uri.split("@", 1)[1]
    app_uri = f"postgresql+psycopg://{APP_ROLE}:{APP_PASSWORD}@{host_part}"
    values = {"MIGRATION_DATABASE_URL": admin_uri, "DATABASE_URL": app_uri}
    if args.write_env:
        update_env_file(ENV_FILE, values)
        print(f"updated {ENV_FILE}")
    for key, value in values.items():
        print(f"{key}={value}")
    return 0


ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def update_env_file(path: Path, values: dict[str, str]) -> None:
    """Set ``values`` in a dotenv file, keeping every other line untouched."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(values)
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(line)
    out.extend(f"{key}={value}" for key, value in remaining.items())
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
