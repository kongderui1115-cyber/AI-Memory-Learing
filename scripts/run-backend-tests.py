"""Run all backend suites with an explicitly isolated PostgreSQL test database."""

import json
import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]


def main():
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    local = ROOT / ".local-test"
    if "TEST_DATABASE_URL" not in env and (local / "test.env").exists():
        env.update(
            dict(
                line.split("=", 1)
                for line in (local / "test.env").read_text().splitlines()
                if "=" in line
            )
        )
    if "TEST_DATABASE_URL" not in env:
        raise RuntimeError(
            "Configure TEST_DATABASE_URL or run scripts/init-local-db.py --migrate first"
        )
    if "TEST_APP_DATABASE_URL" not in env and (local / "local-db.json").exists():
        state = json.loads((local / "local-db.json").read_text())
        env["TEST_APP_DATABASE_URL"] = (
            make_url(env["TEST_DATABASE_URL"])
            .set(username="memory_app", password=state["app_password"])
            .render_as_string(hide_password=False)
        )
    for name in ("tests_backend", "tests_ai", "tests_notif"):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                f"backend/{name}",
                "-q",
            ],
            cwd=ROOT,
            env=env,
        )
        if result.returncode:
            raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
