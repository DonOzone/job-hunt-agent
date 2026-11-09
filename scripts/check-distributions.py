"""Reject private state and missing packaged UI in release distributions."""

from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path, PurePosixPath


def check_members(names: list[str], *, wheel: bool) -> None:
    has_ui = False
    for name in names:
        path = PurePosixPath(name.replace("\\", "/"))
        parts = tuple(part.lower() for part in path.parts)
        if (
            path.is_absolute()
            or ".." in parts
            or any(part in {"me", "workspace", ".git", ".venv", "node_modules"} for part in parts)
            or any(part == ".env" or part.startswith(".env.") for part in parts)
            or any(
                parts[index:index + 2] in {
                    ("config", "profile.yaml"), ("config", "sites.yaml")
                }
                for index in range(len(parts) - 1)
            )
            or path.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".pem", ".key"}
        ):
            raise ValueError(f"Distribution contains forbidden state/credential path: {name}")
        expected = ("jobhunt", "web", "static", "index.html")
        if parts[-4:] == expected:
            has_ui = True
    if not has_ui:
        kind = "wheel" if wheel else "source distribution"
        raise ValueError(f"The {kind} is missing jobhunt/web/static/index.html; build and package the React UI first.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", default="dist")
    args = parser.parse_args()
    directory = Path(args.directory)
    wheels = list(directory.glob("*.whl"))
    sources = list(directory.glob("*.tar.gz"))
    if not wheels or not sources:
        raise SystemExit("Expected a Python wheel and source distribution.")
    for artifact in wheels + sources:
        if artifact.suffix == ".whl":
            with zipfile.ZipFile(artifact) as archive:
                check_members(archive.namelist(), wheel=True)
        else:
            with tarfile.open(artifact, "r:gz") as archive:
                check_members(archive.getnames(), wheel=False)
        print(f"Distribution privacy/UI check passed: {artifact.name}")


if __name__ == "__main__":
    main()
