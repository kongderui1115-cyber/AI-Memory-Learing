"""Create an isolated loopback PostgreSQL development and test instance."""

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from urllib.parse import quote

import psycopg
from app.secret_files import write_private
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]


def run(command, *, cwd=None, env=None, detached=False):
    if detached:
        with (ROOT / ".local-test" / "setup.log").open("a", encoding="utf-8") as output:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                stdout=output,
                stderr=output,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        if result.returncode:
            raise RuntimeError("PostgreSQL startup failed. See .local-test/setup.log")
        return ""
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-bin", type=Path, required=True)
    parser.add_argument("--port", type=int, default=55433)
    parser.add_argument("--migrate", action="store_true")
    args = parser.parse_args()
    local = ROOT / ".local-test"
    local.mkdir(exist_ok=True)
    state_file = local / "local-db.json"
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
        if state["port"] != args.port:
            raise RuntimeError("Existing local database uses a different port")
    else:
        state = {
            "port": args.port,
            "owner_password": secrets.token_hex(32),
            "app_password": secrets.token_hex(32),
            "secret_key": secrets.token_hex(64),
        }
        write_private(state_file, json.dumps(state))
    data = local / "postgres-data"
    suffix = ".exe" if os.name == "nt" else ""
    binary = lambda name: str(args.pg_bin / (name + suffix))
    if not (data / "PG_VERSION").exists():
        password_file = local / "bootstrap-password.txt"
        write_private(password_file, state["owner_password"])
        try:
            run(
                [
                    binary("initdb"),
                    "-D",
                    str(data),
                    "-U",
                    "memory_owner",
                    "-A",
                    "scram-sha-256",
                    "--pwfile=" + str(password_file),
                    "--encoding=UTF8",
                    "--locale=C",
                ]
            )
        finally:
            password_file.unlink(missing_ok=True)
    status = subprocess.run(
        [binary("pg_ctl"), "status", "-D", str(data)],
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if status.returncode:
        run(
            [
                binary("pg_ctl"),
                "start",
                "-D",
                str(data),
                "-l",
                str(local / "postgres.log"),
                "-o",
                f"-h 127.0.0.1 -p {args.port}",
                "-w",
            ],
            detached=True,
        )
    owner = {
        "host": "127.0.0.1",
        "port": args.port,
        "user": "memory_owner",
        "password": state["owner_password"],
    }
    with psycopg.connect(**owner, dbname="postgres", autocommit=True) as connection:
        if not connection.execute(
            "SELECT 1 FROM pg_roles WHERE rolname='memory_app'"
        ).fetchone():
            connection.execute(
                sql.SQL("CREATE ROLE memory_app LOGIN PASSWORD {}").format(
                    sql.Literal(state["app_password"])
                )
            )
        for name in ("memory_os_dev", "memory_os_test"):
            if not connection.execute(
                "SELECT 1 FROM pg_database WHERE datname=%s", (name,)
            ).fetchone():
                connection.execute(
                    sql.SQL("CREATE DATABASE {} OWNER memory_owner").format(
                        sql.Identifier(name)
                    )
                )

    def url(user, password, database):
        return f"postgresql+psycopg://{user}:{quote(password, safe='')}@127.0.0.1:{args.port}/{database}"

    backend_env = ROOT / "backend" / ".env"
    if not backend_env.exists():
        write_private(
            backend_env,
            "DATABASE_URL="
            + url("memory_app", state["app_password"], "memory_os_dev")
            + "\n"
            + "SECRET_KEY="
            + state["secret_key"]
            + "\nACCESS_TOKEN_EXPIRE_MINUTES=60\n"
            + "APP_HOST=127.0.0.1\nAPP_PORT=8000\nAI_BILLING_APPROVED=false\n"
            + "CORS_ORIGINS=http://127.0.0.1:3030,http://localhost:3030,http://127.0.0.1:3000\n",
        )
    test_env = local / "test.env"
    if not test_env.exists():
        write_private(
            test_env,
            "TEST_DATABASE_URL="
            + url("memory_owner", state["owner_password"], "memory_os_test")
            + "\n",
        )
    if args.migrate:
        for name in ("memory_os_dev", "memory_os_test"):
            env = dict(
                os.environ,
                DATABASE_URL=url("memory_owner", state["owner_password"], name),
                SECRET_KEY=state["secret_key"],
            )
            run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=ROOT / "backend",
                env=env,
            )
            with psycopg.connect(**owner, dbname=name, autocommit=True) as connection:
                connection.execute("GRANT USAGE ON SCHEMA public TO memory_app")
                connection.execute(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO memory_app"
                )
                connection.execute(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE memory_owner IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO memory_app"
                )
                connection.execute(
                    "REVOKE UPDATE, DELETE ON review_history, audit_events, raw_notes FROM memory_app"
                )
                connection.execute("REVOKE ALL ON alembic_version FROM memory_app")
                connection.execute("GRANT SELECT ON alembic_version TO memory_app")
    print(
        f"PostgreSQL ready on 127.0.0.1:{args.port}; development and test databases configured."
    )
    print("Private configuration saved to backend/.env and .local-test/test.env.")


if __name__ == "__main__":
    main()
