from pathlib import Path

import pytest
import yaml

from jobhunt import cli
from jobhunt.agent_install import PLATFORMS, install


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    (tmp_path / "AGENTS.md").write_text(
        "# Rules\nNever submit without consent.\nUse --person on every command.\n", encoding="utf-8")
    skill = tmp_path / ".github/skills/job-search/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# Job search\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize("platform", PLATFORMS)
def test_install_native_skill(checkout, platform):
    result = install(checkout, platform)
    path = checkout / PLATFORMS[platform]
    assert result == [(path, "installed")]
    content = path.read_text(encoding="utf-8")
    metadata = yaml.safe_load(content.split("---", 2)[1])
    assert metadata["name"] == "job-hunt-agent"
    assert "job" in metadata["description"]
    assert (checkout / "AGENTS.md").read_text(encoding="utf-8") in content
    assert ".github/skills/<skill>/SKILL.md" in content
    assert "root, never from this skill directory" in content
    assert install(checkout, platform) == [(path, "unchanged")]
    assert not (checkout / "config/profile.yaml").exists()


def test_cli_installs_all_by_default(checkout, capsys):
    cli.main(["agent-install"])
    output = capsys.readouterr().out
    for relative in PLATFORMS.values():
        assert (checkout / relative).is_file()
        assert f"installed: {relative}" in output
    assert "Restart your local assistant" in output


def test_updates_require_explicit_flag(checkout):
    install(checkout, "all")
    path = checkout / PLATFORMS["claude"]
    original = path.read_bytes()
    (checkout / "AGENTS.md").write_text("# Revised rules\n", encoding="utf-8")
    with pytest.raises(ValueError, match="--update"):
        install(checkout, "all")
    assert path.read_bytes() == original
    assert all(status == "updated" for _, status in install(checkout, "all", update=True))
    assert "# Revised rules" in path.read_text(encoding="utf-8")


def test_update_preserves_ownership_when_description_changes(checkout):
    install(checkout, "claude")
    path = checkout / PLATFORMS["claude"]
    previous = path.read_text(encoding="utf-8").replace("Execute local job-hunt-agent", "Older description:")
    path.write_text(previous, encoding="utf-8")
    assert install(checkout, "claude", update=True) == [(path, "updated")]


@pytest.mark.parametrize("update", [False, True])
def test_preflight_preserves_existing_skills(checkout, update):
    conflict = checkout / PLATFORMS["copilot"]
    conflict.parent.mkdir(parents=True)
    conflict.write_text("My custom skill", encoding="utf-8")
    with pytest.raises(ValueError, match="not managed"):
        install(checkout, "all", update=update)
    assert conflict.read_text(encoding="utf-8") == "My custom skill"
    assert not (checkout / PLATFORMS["claude"]).exists()
    assert (checkout / ".github/skills/job-search/SKILL.md").read_text(encoding="utf-8") == "# Job search\n"


def test_wrong_directory_fails_without_creating_files(tmp_path):
    with pytest.raises(ValueError, match="repository root"):
        install(tmp_path, "all")
    assert not list(tmp_path.iterdir())


def test_unknown_platform_fails(checkout):
    with pytest.raises(ValueError, match="Unknown platform"):
        install(checkout, "unknown")


def test_symlink_destination_is_not_followed(checkout, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (checkout / ".agents").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        install(checkout, "all")
    assert not list(outside.iterdir())
    assert not (checkout / PLATFORMS["claude"]).exists()


def test_directory_at_skill_file_is_rejected(checkout):
    path = checkout / PLATFORMS["claude"]
    path.mkdir(parents=True)
    with pytest.raises(ValueError, match="not a file"):
        install(checkout, "all")


def test_cli_reports_invalid_checkout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit, match="repository root"):
        cli.main(["agent-install", "claude"])


def test_cli_reports_io_failure(checkout, monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError("read-only filesystem")

    monkeypatch.setattr(Path, "write_text", denied)
    with pytest.raises(SystemExit, match="cannot install agent skills: read-only filesystem"):
        cli.main(["agent-install", "all"])
