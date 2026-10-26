from pathlib import Path

import pytest
import yaml

from jobhunt import cli, cv_format, cv_review, memory, profiles, rampup, review
from jobhunt.apply import ApplyAssistant, ApplyResult
from jobhunt.config import Profile, default_profile_path, person_scope, workspace_dir
from jobhunt.store import load_jobs
from jobhunt.tracker import Tracker

SAMPLE = (Path(__file__).resolve().parents[1] / "examples" / "sample_cv.md").read_text()


def test_cv_contacts_only():
    fields = profiles.from_cv(SAMPLE)
    assert fields == {
        "name": "JANE WANJIKU DOE", "email": "jane.doe@example.com", "phone": "+254 700 000 000",
        "location": "Nairobi, Kenya", "linkedin": "https://linkedin.com/in/janedoe-example",
        "github": "https://github.com/janedoe-example",
    }
    assert "salary" not in fields and "work_authorization" not in fields and "home_country" not in fields
    fields = profiles.from_cv("Alex Example\nPhone: +1 555 123 4567\n\nEXPERIENCE\n"
                              "Contact an employer at hr@company.example\n")
    assert fields["name"] == "Alex Example"
    assert fields["phone"] == "+1 555 123 4567"
    assert "email" not in fields
    assert profiles.from_cv("") == {}


def test_populate_preserves_confirmed_fields(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text("email: confirmed@example.com\nrequirement:\n  roles: [engineer]\nanswers:\n  notice: 2 weeks\n")
    filled, conflicts = profiles.populate(path, SAMPLE, Path("my-cv.md"))
    data = yaml.safe_load(path.read_text())
    assert "name" in filled and conflicts == ["email"]
    assert data["email"] == "confirmed@example.com"
    assert data["requirement"]["roles"] == ["engineer"] and data["answers"]["notice"] == "2 weeks"
    assert data["cv_path"] == "my-cv.md"


def test_named_person_storage_and_notification_scope(tmp_home, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("JOBHUNT_NTFY_TOPIC", "default-user-channel")
    path = tmp_path / "p.yaml"
    path.write_text("name: Example\n")
    with person_scope("one"):
        assert workspace_dir() == tmp_home / "people" / "one"
        assert str(default_profile_path()) == "me/profiles/one/profile.yaml"
        assert not Profile.load(path).notify
        with person_scope("two"):
            assert workspace_dir() == tmp_home / "people" / "two"
        assert workspace_dir() == tmp_home / "people" / "one"
    assert workspace_dir() == tmp_home
    assert Profile.load(path).notify["ntfy_topic"] == "default-user-channel"
    with pytest.raises(ValueError, match="--person"):
        with person_scope("../escape"):
            pass


def test_multiple_people_full_application_workflow(tmp_path, tmp_home, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    cv = tmp_path / "original.docx"
    cv_format.markdown_to_docx(SAMPLE, cv)
    posting = tmp_path / "job.txt"
    posting.write_text("Senior Backend Engineer\nAcme\nRemote anywhere.\nPython, AWS and Rust required.")
    baselines = []
    for person in ("jane", "alex"):
        cli.main(["--person", person, "init"])
        profile_path = tmp_path / "me" / "profiles" / person / "profile.yaml"
        initial = yaml.safe_load(profile_path.read_text())
        assert not initial.get("name") and not initial.get("cv_path")
        assert not initial.get("answers") and not initial.get("work_authorization")
        # The same source may be deliberately imported for two people, but baselines and all state are separate.
        source = tmp_path / f"{person}.md"
        source.write_text(SAMPLE if person == "jane" else SAMPLE.replace("JANE WANJIKU DOE", "ALEX EXAMPLE")
                          .replace("jane.doe@example.com", "alex@example.com"))
        cli.main(["cv-import", str(cv if person == "jane" else source), "--person", person, "--populate-profile"])
        data = yaml.safe_load(profile_path.read_text())
        assert data["name"] == ("JANE WANJIKU DOE" if person == "jane" else "ALEX EXAMPLE")
        baseline = Path(data["cv_path"])
        before = baseline.read_bytes()
        baselines.append(baseline)
        cli.main(["--person", person, "add", "--file", str(posting), "--title", "Senior Backend Engineer",
                  "--company", "Acme", "--remote"])
        cli.main(["application", "1", "--person", person, "-y"])
        home = tmp_home / "people" / person
        folder = next((home / "applications").iterdir())
        assert (folder / "cv-draft.docx").is_file() and (folder / "cover-letter.docx").is_file()
        assert "Rust" in (folder / "requirements.md").read_text()
        assert "Not found" in (folder / "requirements.md").read_text()
        assert "Rust" not in review.prose((folder / "cv-draft.md").read_text())
        letter = (folder / "cover-letter.md").read_text()
        assert data["name"] in letter and "Acme" in letter
        assert "---" in (folder / "cv-changes.diff").read_text()
        assert baseline.read_bytes() == before
        with person_scope(person):
            assert len(load_jobs()) == 1
            assert next(iter(memory.records().values()))["decision"] == "preparing"
            tracker = Tracker()
            assert tracker.summary()["total"] == 1
            tracker.close()
        # A second preparation must not replace user-approved final files.
        final = folder / "cv-final.md"
        final.write_text("A manually reviewed final CV")
        cli.main(["--person", person, "application", "1", "-y", "--no-docx"])
        assert final.read_text() == "A manually reviewed final CV"
        resources = tmp_path / "me" / "profiles" / person / "learning-resources.yaml"
        resources.write_text(f"resources:\n  - {{skill: Python, name: {person}'s own course}}\n")
        with person_scope(person):
            assert rampup.load_user_resources()[0].name == f"{person}'s own course"
    assert baselines[0] != baselines[1]
    assert not (tmp_path / "me" / "cv").exists() and not (tmp_path / "config" / "profile.yaml").exists()
    assert not (tmp_home / "tracker.db").exists()
    cli.main(["profiles"])
    assert "jane" in capsys.readouterr().out
    cli.main(["journal", "log", "Default workspace only"])
    assert "Default workspace only" in (tmp_home / "journal.md").read_text()
    assert "Default workspace only" not in (tmp_home / "people" / "jane" / "journal.md").read_text()


def test_profile_from_cv_and_explicit_upload_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cv = tmp_path / "source.md"
    cv.write_text(SAMPLE)
    cli.main(["--person", "jane", "profile-from-cv", str(cv)])
    p = yaml.safe_load((tmp_path / "me" / "profiles" / "jane" / "profile.yaml").read_text())
    assert p["email"] == "jane.doe@example.com"
    assert not p["open_to_relocation"]
    posting = tmp_path / "job.txt"
    posting.write_text("Backend Engineer\nPython. Remote.")
    cli.main(["--person", "jane", "add", "--file", str(posting), "--title", "Backend Engineer", "--remote"])
    final = cv_format.markdown_to_docx(SAMPLE, tmp_path / "final.docx")
    seen = []

    def capture(self, job, **kwargs):
        seen.append(self.profile.cv_path)
        return ApplyResult(job.id, 1, "saved")

    monkeypatch.setattr(ApplyAssistant, "apply", capture)
    cli.main(["--person", "jane", "apply", "1", "--cv", str(final), "--dry-run"])
    assert seen == [str(final)]
    assert yaml.safe_load((tmp_path / "me/profiles/jane/profile.yaml").read_text())["cv_path"] == str(cv)


def test_cv_import_invalid_options_have_no_side_effects(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit, match="cannot be combined"):
        cli.main(["cv-import", "missing.md", "--populate-profile", "--no-profile"])
    assert not (tmp_path / "me").exists()


def test_target_title_does_not_become_a_candidate_claim():
    from jobhunt.models import Job

    job = Job(title="Staff Production Engineer", company="Example", description="Python", url="", source="manual")
    report = cv_review.review("# Alex Example\n\n## Skills\nPython\n", [job], "Example role")
    assert "Staff" not in report.summary and "production" not in report.summary.lower()
    assert "Python" in report.summary
