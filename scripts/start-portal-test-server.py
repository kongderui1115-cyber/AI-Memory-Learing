"""Start the explicit browser-test API against an isolated PostgreSQL database only."""

import json
import os
import runpy
import sys
from pathlib import Path

from sqlalchemy.engine import make_url


def main():
    root = Path(__file__).resolve().parents[1]
    raw_url = os.environ.get("TEST_DATABASE_URL", "")
    env_file = root / ".local-test" / "test.env"
    if not raw_url and env_file.exists():
        values = dict(
            line.split("=", 1)
            for line in env_file.read_text().splitlines()
            if "=" in line
        )
        raw_url = values.get("TEST_DATABASE_URL", "")
    if not raw_url:
        raise RuntimeError("Configure a dedicated TEST_DATABASE_URL first")
    url = make_url(raw_url)
    if not url.drivername.startswith("postgresql") or not (url.database or "").endswith(
        "_test"
    ):
        raise RuntimeError(
            "Browser tests require a PostgreSQL database whose name ends with _test"
        )
    app_url = os.environ.get("TEST_APP_DATABASE_URL", "")
    state_file = root / ".local-test" / "local-db.json"
    if not app_url and state_file.exists() and url.database == "memory_os_test":
        state = json.loads(state_file.read_text())
        app_url = url.set(
            username="memory_app", password=state["app_password"]
        ).render_as_string(hide_password=False)
    target = make_url(app_url or raw_url)
    if (target.host, target.port, target.database) != (
        url.host,
        url.port,
        url.database,
    ):
        raise RuntimeError(
            "Test application connection must target the same isolated database"
        )
    os.environ.update(
        DATABASE_URL=target.render_as_string(hide_password=False),
        SECRET_KEY=os.environ.get(
            "PORTAL_TEST_SECRET_KEY", "browser-ui-isolated-secret-" * 4
        ),
        APP_ENV="test",
        BACKGROUND_TASKS_ENABLED="false",
        AI_BILLING_APPROVED="false",
        PORTAL_TEST_PORT=os.environ.get("PORTAL_TEST_PORT", "8001"),
        CORS_ORIGINS=os.environ.get("PORTAL_TEST_ORIGIN", "http://127.0.0.1:3031"),
    )
    sys.path.insert(0, str(root / "backend" / "tests_backend"))
    os.chdir(root)
    runpy.run_path(
        str(root / "backend" / "tests_backend" / "portal_server.py"),
        run_name="__main__",
    )


if __name__ == "__main__":
    main()
