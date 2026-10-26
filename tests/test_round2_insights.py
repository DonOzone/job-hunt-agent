"""Round-2 ideas adapted from ai-job-search: application reviewer, company research, follow-ups/sweep,
funnel dashboard, decision-weighted gaps, robots.txt, grounded cover letters."""
import sqlite3
from pathlib import Path

import pytest

from jobhunt import cli, dashboard, gaps, research, review, tailor
from jobhunt.config import Profile
from jobhunt.cv import extract_skills
from jobhunt.models import Job
from jobhunt.sources import robots
from jobhunt.tracker import Tracker

SAMPLE = (Path(__file__).resolve().parents[1] / "examples" / "sample_cv.md").read_text()


def job(desc="Python, Go, Kafka, PostgreSQL and Kubernetes. AWS a plus.", **kw):
    j = Job(title=kw.pop("title", "Senior Backend Engineer"), company=kw.pop("company", "Acme Payments"),
            url=kw.pop("url", "https://boards.greenhouse.io/acme/jobs/1"), source="manual", description=desc, **kw)
    j.skills = extract_skills(f"{j.title}\n{desc}")
    return j


def kit_folder(tmp_path, cv=SAMPLE, letter=None):
    folder = tmp_path / "kit"
    folder.mkdir()
    (folder / "cv-draft.md").write_text(cv)
    (folder / "cover-letter.md").write_text(letter or (
        "Dear Acme Payments hiring team,\n\nI'm applying for the Senior Backend Engineer role. "
        + "I built payment routing in Go and Kafka for 3M+ transactions per day. " * 12 + "\n\nBest regards,\nJane"))
    return folder


# --------------------------------------------------------------------------- application reviewer
def test_review_flags_placeholders_unsupported_claims_and_cliches(tmp_path):
    p = Profile(name="Jane", email="jane.doe@example.com", writing_style={"avoid_words": ["ninja"]})
    cv = SAMPLE.replace("Python", "Python, Rust", 1) + "\n- Grew revenue by 300% [add metric source]\n"
    letter = ("Dear team,\n\nI am writing to apply. I'm a passionate about payments ninja and a team player. "
              "<Why this company>\nI cut costs by 55%.\n")
    r = review.review_kit(job(), kit_folder(tmp_path, cv, letter), p, SAMPLE)
    text = review.render(r)
    blockers = [f.message for f in r.findings if f.severity == "blocker"]
    assert any("[add metric source]" in m for m in blockers) and any("<Why this company>" in m for m in blockers)
    assert "Rust" in text and "300%" in text and "55%" in text  # not in the baseline CV
    assert "Doesn't mention Acme Payments" in text
    assert "“ninja”" in text and "team player" in text and "i am writing to apply" in text.lower()
    assert r.verdict.startswith("Not ready") and r.score < 60


def test_review_clean_kit_with_research_is_ready(tmp_path):
    j = job()
    path = research.brief(j)
    path.write_text(path.read_text()
                    .replace("## What they do\n\n", "## What they do\n\nPayments for merchants (about page).\n")
                    .replace("## People\n\n", "## People\n\nRecruiter: A. Example.\n"))
    assert research.is_filled(path)
    r = review.review_kit(j, kit_folder(tmp_path), Profile(email="jane.doe@example.com"), SAMPLE)
    assert not [f for f in r.findings if f.severity != "tip"], review.render(r)
    assert r.verdict == "Ready to send"


def test_review_prefers_cv_final_and_ignores_comments(tmp_path):
    folder = kit_folder(tmp_path)
    (folder / "cv-final.md").write_text(SAMPLE + "\n<!-- [placeholder in a note] -->\n")
    r = review.review_kit(job(), folder, Profile(), SAMPLE)
    assert not any("placeholder" in f.message for f in r.findings)


# --------------------------------------------------------------------------- company research
def test_research_brief_is_cached_and_extended():
    a, b = job(), job(title="Staff Engineer", url="https://boards.greenhouse.io/acme/jobs/2")
    path = research.brief(a)
    path.write_text(path.read_text().replace("## Culture & values\n\n", "## Culture & values\n\nMy note.\n"))
    assert research.brief(b) == path
    text = path.read_text()
    assert "My note." in text and "Staff Engineer" in text and "Senior Backend Engineer" in text
    assert "glassdoor" in text.lower() and not research.is_filled(path)


# --------------------------------------------------------------------------- grounded cover letter
def test_cover_letter_is_grounded():
    j = job(desc="Python, Go, Kafka, Rust")
    letter = tailor.cover_letter(j, Profile(name="Jane", writing_style={"sign_off": "Kind regards"}), SAMPLE)
    assert "actively deepening" not in letter  # no unverified claims
    assert "<Optional, only if true" in letter and "Kind regards," in letter
    wins = tailor.best_achievements(j, Profile(), SAMPLE)
    assert all(not w.startswith(("Cloud and DevOps", "Languages")) for w in wins)  # skills lines aren't wins
    assert any("3M+" in w for w in wins)


# --------------------------------------------------------------------------- gaps steered by decisions
def test_gap_weights_follow_decisions():
    keep, skipped = job("Kafka and Terraform"), job("Rust and Haskell", company="Other")
    weights = gaps.decision_weights({skipped.id: {"decision": "skip"}, keep.id: {"decision": "applied"}})
    found, _ = gaps.analyse([keep, skipped], {"Python"}, weights)
    names = {g.skill for g in found}
    assert "Kafka" in names and "Rust" not in names


# --------------------------------------------------------------------------- tracker: follow-ups, sweep, funnel
def _backdate(db_path, days_ago="2026-01-01T00:00:00+00:00"):
    db = sqlite3.connect(db_path)
    db.execute("UPDATE applications SET updated_at=?, created_at=?", (days_ago, days_ago))
    db.execute("UPDATE events SET ts=?", (days_ago,))
    db.commit()
    db.close()


def test_followups_sent_and_funnel(tmp_home):
    tmp_home.mkdir(parents=True, exist_ok=True)
    tr = Tracker()
    a = tr.add(job(), "saved")
    tr.update(a, "applied")
    b = tr.add(job(company="Beta", url="https://x/b"), "saved")
    tr.update(b, "applied")
    tr.update(b, "interview")
    tr.update(b, "rejected")
    c = tr.add(job(company="Draft Co", url="https://x/c"), "applying")
    _backdate(tr.path)
    assert [r["id"] for r in tr.stale(7)] == [a]  # rejected and never-sent are not follow-ups
    tr.log_event(a, "follow-up sent")
    assert tr.stale(7) == [] and tr.followups_sent(a) == 1 and tr.get(a)["status"] == "applied"
    assert tr.funnel() == {"submitted": 2, "responded": 1, "interview": 1, "offer": 0}
    html = dashboard.render(tr)
    assert "Job hunt dashboard" in html and "Draft Co" in html and "50%" in html and "<script" not in html
    tr.close()
    assert c


def test_cli_followups_sweep_dashboard(tmp_home, capsys):
    tmp_home.mkdir(parents=True, exist_ok=True)
    tr = Tracker()
    a = tr.add(job(), "saved")
    tr.update(a, "applied")
    path = tr.path
    tr.close()
    _backdate(path)
    cli.main(["track", "followups", "--profile", "missing.yaml"])
    drafts = list((tmp_home / "followups").glob("*.md"))
    assert drafts and "following up" in drafts[0].read_text()
    cli.main(["track", "sent", str(a)])
    cli.main(["track", "sweep", "-y"])  # follow-up just sent -> nothing quiet for 60 days
    assert "No open applications" in capsys.readouterr().out
    _backdate(path)
    cli.main(["track", "sweep", "-y"])
    with _open() as t:
        assert t.get(a)["status"] == "ghosted"
    cli.main(["track", "dashboard"])
    assert (tmp_home / "dashboard.html").exists()


def _open():
    from jobhunt.tracker import open_tracker

    return open_tracker()


# --------------------------------------------------------------------------- robots.txt
class _Resp:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text


@pytest.mark.parametrize("status,text,url,ok", [
    (200, "User-agent: *\nDisallow: /private/\n", "https://ex.com/private/job", False),
    (200, "User-agent: *\nDisallow: /private/\n", "https://ex.com/jobs/1", True),
    (404, "", "https://ex.com/anything", True),
    (403, "", "https://ex.com/anything", False),
])
def test_robots(monkeypatch, status, text, url, ok):
    robots._parser.cache_clear()
    monkeypatch.setattr(robots.requests, "get", lambda *a, **k: _Resp(status, text))
    assert robots.allowed(url) is ok
    if not ok:
        with pytest.raises(PermissionError):
            robots.require(url)


def test_robots_network_error_allows(monkeypatch):
    robots._parser.cache_clear()

    def boom(*a, **k):
        raise robots.requests.ConnectionError("offline")

    monkeypatch.setattr(robots.requests, "get", boom)
    assert robots.allowed("https://ex.com/x")
