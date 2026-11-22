import hashlib
import importlib.util
import json
import subprocess
import zipfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_release", ROOT / "tools" / "build_release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
spec = importlib.util.spec_from_file_location("smoke_release", ROOT / "tools" / "smoke_release.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


@pytest.fixture
def release_root(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    for name in release.REQUIRED | {
        "src/jobhunt/__init__.py",
        "packaging/job-hunt-agent/SKILL.md",
        "packaging/job-hunt-agent/references/setup.md",
    }:
        source = ROOT / name
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
    return root


def test_both_zip_layouts_are_complete_and_deterministic(release_root, tmp_path):
    first = release.build(release_root, tmp_path / "first")
    second = release.build(release_root, tmp_path / "second")
    for left, right in zip(first, second, strict=True):
        assert left.read_bytes() == right.read_bytes()
        prefix = "" if left.name.endswith("-skill.zip") else "job-hunt-agent/"
        with zipfile.ZipFile(left) as archive:
            metadata = yaml.safe_load(archive.read(prefix + "SKILL.md").decode().split("---\n", 2)[1])
            assert metadata["name"] == "job-hunt-agent"
            assert metadata["description"].strip()
            assert prefix + "references/setup.md" in archive.namelist()
            assert prefix + "scripts/app/pyproject.toml" in archive.namelist()
            manifest = json.loads(archive.read(prefix + "manifest.json"))
            assert set(archive.namelist()) == {
                prefix + name for name in manifest["files"]
            } | {prefix + "manifest.json"}
            for name, digest in manifest["files"].items():
                assert hashlib.sha256(archive.read(prefix + name)).hexdigest() == digest
    sums = release.checksums(tmp_path / "first").read_text(encoding="utf-8")
    assert all(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}" in sums for path in first)


def test_private_files_and_unexpected_binaries_are_excluded(release_root, tmp_path):
    for name in (
        ".env", "config/profile.yaml", "config/sites.yaml", "me/cv.md",
        "workspace/session.json", "examples/sample_cv.docx", "src/jobhunt/__pycache__/cli.pyc",
        ".github/skills/job-hunt-agent/SKILL.md", "docs/ci.yml",
    ):
        target = release_root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("PRIVATE", encoding="utf-8")
    with (release_root / ".gitignore").open("a", encoding="utf-8") as handle:
        handle.write("\n.github/skills/job-hunt-agent/\n")
    with zipfile.ZipFile(release.build(release_root, tmp_path / "out")[0]) as archive:
        assert all(b"PRIVATE" not in archive.read(name) for name in archive.namelist())


@pytest.mark.parametrize("problem", ["version", "tag", "frontmatter", "missing", "binary"])
def test_invalid_release_inputs_fail_before_creating_artifacts(release_root, tmp_path, problem):
    kwargs = {}
    if problem == "version":
        (release_root / "src/jobhunt/__init__.py").write_text('__version__ = "9.9.9"\n', encoding="utf-8")
    elif problem == "tag":
        kwargs["expected_version"] = "9.9.9"
    elif problem == "frontmatter":
        (release_root / "packaging/job-hunt-agent/SKILL.md").write_text(
            "---\nname: job-hunt-agent\ndescription: ''\n---\n", encoding="utf-8")
    elif problem == "missing":
        (release_root / "AGENTS.md").unlink()
    else:
        (release_root / "src/jobhunt/cli.py").write_bytes(b"\0binary")
    with pytest.raises(ValueError):
        release.build(release_root, tmp_path / "out", **kwargs)
    assert not (tmp_path / "out").exists()


def test_symlink_input_is_rejected(release_root, tmp_path):
    target = release_root / "src/jobhunt/cli.py"
    target.unlink()
    outside = tmp_path / "private.py"
    outside.write_text("private", encoding="utf-8")
    try:
        target.symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks is unavailable on this host")
    with pytest.raises(ValueError, match="symlink"):
        release.build(release_root, tmp_path / "out")


@pytest.mark.parametrize("problem", ["tampered", "unlisted", "traversal"])
def test_archive_validation_fails_before_extraction(tmp_path, problem):
    archive = tmp_path / "bad.zip"
    content = b"original"
    manifest = {"files": {"SKILL.md": hashlib.sha256(content).hexdigest()}}
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("manifest.json", json.dumps(manifest))
        handle.writestr("SKILL.md", b"changed" if problem == "tampered" else content)
        if problem != "tampered":
            handle.writestr("extra.txt" if problem == "unlisted" else "../outside.txt", b"unexpected")
    with pytest.raises(ValueError):
        smoke.verify_archive(archive, tmp_path / "extracted", "")
    assert not (tmp_path / "extracted").exists()
