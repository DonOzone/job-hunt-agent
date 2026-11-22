"""Build text-only skill ZIPs using an allowlist and Git's ignored-file rules."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = PurePosixPath("packaging/job-hunt-agent")
REQUIRED = {
    "AGENTS.md", "README.md", "LICENSE", ".gitignore", "pyproject.toml", "uv.lock",
    "src/jobhunt/cli.py", "src/jobhunt/data/templates/profile.example.yaml",
    "src/jobhunt/data/templates/sites.example.yaml", "src/jobhunt/data/templates/env.example",
    ".github/skills/job-search/SKILL.md",
}


def allowed(name: str) -> bool:
    """Exclude personal state, binaries, build output and unrelated host settings."""
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in ("..", "me", "workspace", "__pycache__") for part in path.parts):
        return False
    if name in {
        "AGENTS.md", "CLAUDE.md", "GEMINI.md", "README.md", "LICENSE", ".gitignore",
        ".github/copilot-instructions.md", "pyproject.toml", "uv.lock", ".env.example",
    }:
        return True
    if path.parts[:2] == ("src", "jobhunt"):
        return path.suffix in {".py", ".yaml"} or name in {
            "src/jobhunt/data/templates/env.example",
        }
    if path.parts[:2] == (".github", "skills"):
        return len(path.parts) == 4 and path.name == "SKILL.md"
    if path.parts[:1] == ("docs",):
        return len(path.parts) == 2 and path.suffix == ".md"
    if path.parts[:1] == ("config",):
        return name in {"config/profile.example.yaml", "config/sites.example.yaml"}
    if path.parts[:1] == ("examples",):
        return name in {"examples/sample_cv.md", "examples/learning-resources.example.yaml"}
    return name == "imports/saved_jobs.example.csv"


def version(root: Path) -> str:
    project = root.joinpath("pyproject.toml").read_text(encoding="utf-8").split("[project]\n", 1)[1].split("\n[", 1)[0]
    match = re.search(r'^version = "(\d+\.\d+\.\d+)"$', project, re.MULTILINE)
    if not match:
        raise ValueError("Expected a stable major.minor.patch project version.")
    result = match[1]
    module = root.joinpath("src/jobhunt/__init__.py").read_text(encoding="utf-8")
    if not re.search(rf'^__version__ = "{re.escape(result)}"$', module, re.MULTILINE):
        raise ValueError("pyproject.toml and jobhunt.__version__ must agree.")
    return result


def read_file(root: Path, name: str) -> bytes:
    path = root.joinpath(*PurePosixPath(name).parts)
    if any(parent.is_symlink() for parent in (path, *path.parents) if parent != root.parent):
        raise ValueError(f"Refusing symlink: {name}")
    if not path.is_file():
        raise ValueError(f"Missing release input: {name}")
    data = path.read_bytes()
    if b"\0" in data:
        raise ValueError(f"Binary release input: {name}")
    # Normalize checkout line endings for identical ZIPs on Windows and Linux.
    return data.decode("utf-8").replace("\r\n", "\n").encode("utf-8")


def payload(root: Path, tracked: list[str]) -> dict[str, bytes]:
    selected = sorted(name for name in tracked if allowed(name))
    missing = REQUIRED - set(selected)
    if missing:
        raise ValueError(f"Missing release inputs: {', '.join(sorted(missing))}")
    files = {f"scripts/app/{name}": read_file(root, name) for name in selected}
    files["LICENSE"] = read_file(root, "LICENSE")
    for name in sorted(tracked):
        path = PurePosixPath(name)
        if path.is_relative_to(SKILL) and path.suffix == ".md":
            files[str(path.relative_to(SKILL))] = read_file(root, name)
    if "SKILL.md" not in files or "references/setup.md" not in files:
        raise ValueError("Missing skill entry or setup reference.")
    for name, data in files.items():
        if not name.endswith("SKILL.md"):
            continue
        text = data.decode("utf-8")
        if not text.startswith("---\n") or "\n---\n" not in text[4:]:
            raise ValueError(f"Invalid skill frontmatter: {name}")
        metadata = yaml.safe_load(text.split("---\n", 2)[1])
        if not isinstance(metadata, dict) or any(
            not isinstance(metadata.get(key), str) or not metadata[key].strip()
            for key in ("name", "description")
        ):
            raise ValueError(f"Skill requires a name and description: {name}")
        expected = "job-hunt-agent" if name == "SKILL.md" else PurePosixPath(name).parent.name
        if metadata["name"] != expected:
            raise ValueError(f"Skill name does not match directory: {name}")
    return files


def build(root: Path, output: Path, *, expected_version: str | None = None) -> list[Path]:
    release_version = version(root)
    if expected_version is not None and expected_version != release_version:
        raise ValueError(f"Release tag version {expected_version} does not match project version {release_version}.")
    tracked = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root, check=True, capture_output=True,
    ).stdout.decode("utf-8").rstrip("\0").split("\0")
    files = payload(root, tracked)
    manifest = {
        "name": "job-hunt-agent",
        "version": release_version,
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
    }
    files["manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    output.mkdir(parents=True, exist_ok=True)
    archives = []
    for layout, prefix in (("skill", ""), ("bundle", "job-hunt-agent/")):
        archive = output / f"job-hunt-agent-{release_version}-{layout}.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as handle:
            for name, data in sorted(files.items()):
                info = zipfile.ZipInfo(prefix + name, date_time=(2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                handle.writestr(info, data)
        archives.append(archive)
    return archives


def checksums(output: Path) -> Path:
    artifacts = sorted(
        path for path in output.iterdir()
        if path.is_file() and (path.suffix in {".zip", ".whl"} or path.name.endswith(".tar.gz"))
    )
    if not artifacts:
        raise ValueError("No distribution artifacts found.")
    result = output / "SHA256SUMS"
    result.write_text("".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in artifacts
    ), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--expected-version", help="Release tag without the leading v")
    args = parser.parse_args()
    for path in build(ROOT, args.output, expected_version=args.expected_version):
        print(path)
    print(checksums(args.output))


if __name__ == "__main__":
    main()
