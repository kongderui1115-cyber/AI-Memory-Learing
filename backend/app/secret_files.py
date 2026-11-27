"""Restrict local credential files to their operating-system owner."""

import csv
import io
import os
from pathlib import Path
import subprocess


def restrict_file(path: Path):
    if os.name == "nt":
        result = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            check=True,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        sid = next(csv.reader(io.StringIO(result.stdout.strip())))[1]
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"*{sid}:(F)", "*S-1-5-18:(F)"],
            check=True,
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        path.chmod(0o600)


def write_private(path: Path, value: str):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        restrict_file(path)
        output.write(value)
