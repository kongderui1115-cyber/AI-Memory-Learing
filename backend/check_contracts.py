"""Dependency-free contract baseline checker. Run: python backend/check_contracts.py"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def fail(message: str) -> None:
    raise AssertionError(message)


def main() -> int:
    required = [ROOT / "ARCHITECTURE.md", ROOT / "DATABASE_SCHEMA.md", ROOT / "API_CONTRACTS.md"]
    required += [BACKEND / "pyproject.toml", BACKEND / "app/contracts/enums.py", BACKEND / "app/contracts/models.py"]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file() or path.stat().st_size == 0]
    if missing:
        fail(f"missing or empty: {missing}")

    with (BACKEND / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]
    if not any(dep.startswith("fastapi") for dep in project["dependencies"]):
        fail("FastAPI dependency missing")
    if not any(dep.startswith("sqlalchemy") for dep in project["dependencies"]):
        fail("SQLAlchemy dependency missing")

    enum_text = (BACKEND / "app/contracts/enums.py").read_text(encoding="utf-8")
    api_text = (ROOT / "API_CONTRACTS.md").read_text(encoding="utf-8")
    tree = ast.parse(enum_text)
    enum_values: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.Assign) and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                    enum_values.add(item.value.value)
    absent = sorted(value for value in enum_values if f"`{value}`" not in api_text)
    if absent:
        fail(f"enum values absent from API_CONTRACTS.md: {absent}")

    for source in (BACKEND / "app/contracts").glob("*.py"):
        compile(source.read_text(encoding="utf-8"), str(source), "exec")

    frs = set(re.findall(r"FR-(\d{2})", (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")))
    expected = {f"{n:02d}" for n in range(1, 13)}
    if frs != expected:
        fail(f"FR coverage mismatch: expected {sorted(expected)}, got {sorted(frs)}")

    print(f"PASS files={len(required)} enum_values={len(enum_values)} fr_coverage=12/12 syntax=ok")
    from app.contracts import models
    print(f'PASS runtime_model_import module={models.__name__}')
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        sys.exit(1)
