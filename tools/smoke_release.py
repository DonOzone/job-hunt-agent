"""Verify release contents and install both ZIP layouts, wheel and sdist in isolation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def run(*command: str, cwd: Path, env: dict[str, str]) -> None:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        result.check_returncode()


def verify_archive(archive: Path, destination: Path, prefix: str) -> Path:
    with zipfile.ZipFile(archive) as handle:
        names = handle.namelist()
        if len(names) != len(set(names)):
            raise ValueError(f"Duplicate ZIP members: {archive.name}")
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
                raise ValueError(f"Unsafe ZIP member: {name}")
            if not name.startswith(prefix):
                raise ValueError(f"Unexpected ZIP layout: {name}")
        manifest = json.loads(handle.read(prefix + "manifest.json"))
        expected = {prefix + name for name in manifest["files"]} | {prefix + "manifest.json"}
        if set(names) != expected:
            raise ValueError(f"Manifest does not cover every ZIP member: {archive.name}")
        for name, digest in manifest["files"].items():
            if hashlib.sha256(handle.read(prefix + name)).hexdigest() != digest:
                raise ValueError(f"Checksum mismatch: {name}")
        handle.extractall(destination)
    return destination / prefix / "scripts" / "app"


def environment(path: Path, root: Path, env: dict[str, str], installer: str) -> Path:
    if installer == "uv":
        run("uv", "venv", str(path), cwd=root, env=env)
    else:
        run(sys.executable, "-m", "venv", str(path), cwd=root, env=env)
    return path / "Scripts" / "python.exe" if os.name == "nt" else path / "bin" / "python"


def install(python: Path, package: Path, root: Path, env: dict[str, str], installer: str) -> None:
    if installer == "uv":
        run("uv", "pip", "install", "--python", str(python), str(package), cwd=root, env=env)
    else:
        run(str(python), "-m", "pip", "install", "--quiet", str(package), cwd=root, env=env)


def smoke(output: Path, installer: str = "uv") -> None:
    for line in (output / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        if Path(name).name != name or hashlib.sha256((output / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Distribution checksum mismatch: {name}")
    wheels = list(output.glob("*.whl"))
    sources = list(output.glob("*.tar.gz"))
    archives = list(output.glob("*.zip"))
    if len(wheels) != 1 or len(sources) != 1 or len(archives) != 2:
        raise ValueError("Expected one wheel, one source distribution and both skill ZIP layouts.")
    with tempfile.TemporaryDirectory(prefix="jobhunt-release-") as temporary:
        root = Path(temporary)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.pop("VIRTUAL_ENV", None)
        env.pop("UV_PROJECT_ENVIRONMENT", None)
        env["PYTHONUTF8"] = "1"
        env["JOBHUNT_HOME"] = str(root / "workspace")
        for label, distribution in (("wheel", wheels[0]), ("source", sources[0])):
            data = root / label
            data.mkdir()
            python = environment(root / f"{label}-env", root, env, installer)
            install(python, distribution, root, env, installer)
            run(str(python), "-I", "-m", "jobhunt", "--help", cwd=data, env=env)
            run(str(python), "-I", "-m", "jobhunt",
                "--person", "release-check", "init", cwd=data, env=env)
            run(str(python), "-I", "-c",
                "from jobhunt.config import load_data; assert load_data('skills.yaml'); "
                "assert load_data('courses.yaml')", cwd=data, env=env)
            print(f"Installed and checked {label}: {distribution.name}")
        for archive in sorted(archives):
            prefix = "" if archive.name.endswith("-skill.zip") else "job-hunt-agent/"
            app = verify_archive(archive, root / archive.stem, prefix)
            if installer == "uv":
                run("uv", "sync", "--locked", "--no-dev", cwd=app, env=env)
                command = ("uv", "run", "--locked", "--no-dev", "jobhunt")
            else:
                python = environment(app / ".venv", root, env, installer)
                install(python, app, root, env, installer)
                command = (str(python), "-I", "-m", "jobhunt")
            run(*command, "--help", cwd=app, env=env)
            run(*command, "--person", "release-check", "init", cwd=app, env=env)
            run(*command, "agent-install", cwd=app, env=env)
            profile = app / "me" / "profiles" / "release-check" / "profile.yaml"
            if "name: ''" not in profile.read_text(encoding="utf-8"):
                raise ValueError("Named-person setup did not produce a blank profile.")
            print(f"Extracted, installed and checked {archive.name}")
    print(f"Release smoke checks passed using {installer}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "dist")
    parser.add_argument("--installer", choices=["uv", "pip"], default="uv")
    args = parser.parse_args()
    smoke(args.output.resolve(), args.installer)
