from datetime import date

import pytest

from jobhunt import assessment, gaps, insights, interview, journal
from jobhunt.cv import extract_skills, match_job, years_of_experience
from jobhunt.enrich import enrich
from jobhunt.tracker import Tracker

CV = "Backend engineer, 5 years. Python, FastAPI, Docker, AWS, PostgreSQL, Git."


def test_extract_skills():
    skills = set(extract_skills(CV))
    assert {"Python", "FastAPI", "Docker", "AWS", "SQL", "Git"} <= skills
    assert "Go" not in extract_skills("Let's go to the market")  # case-sensitive-ish false positive guard
    assert years_of_experience(CV) == 5


def test_match_and_gaps(jobs):
    cv = set(extract_skills(CV))
    jobs = [enrich(j) for j in jobs[:3]]
    for i, j in enumerate(jobs, 1):
        j.rank = i
    m = match_job(cv, jobs[0])
    assert "Python" in m.matched and "Kubernetes" in m.missing and 0 < m.score < 1
    found, strengths = gaps.analyse(jobs, cv)
    names = [g.skill for g in found]
    assert names[0] in ("Kubernetes", "Terraform", "Go")
    assert found[0].importance == 100
    assert any(c["type"] == "cert" for c in next(g for g in found if g.skill == "Kubernetes").courses)
    assert ("Docker", 1) in strengths
    md = gaps.render_markdown(found, strengths, 3)
    assert "CKA" in md


def test_tracker_lifecycle():
    from jobhunt.models import Job
    tr = Tracker()
    job = Job(title="BE", company="Acme", url="u", source="s")
    app = tr.add(job)
    assert tr.add(job) == app  # idempotent
    tr.update(app, "applied", "sent", next_action="follow up", due_in_days=7)
    tr.update(app, "interview", "recruiter call")
    hist = tr.history(app)
    assert [e["status"] for e in hist] == ["saved", "applied", "interview"]
    assert all(e["ts"] for e in hist)
    s = tr.summary()
    assert s["passed"] == 1 and s["interview_rate"] == 1.0
    assert tr.list("passed")[0]["id"] == app
    assert "✅ Passed (1)" in tr.report_markdown()
    with pytest.raises(ValueError):
        tr.update(app, "bogus")
    tr.close()


def test_stale_followups():
    from jobhunt.models import Job
    tr = Tracker()
    app = tr.add(Job(title="BE", company="Old", url="u", source="s"), "applied")
    tr.db.execute("UPDATE applications SET updated_at='2000-01-01T00:00:00+00:00' WHERE id=?", (app,))
    assert tr.stale(7) == []  # the 'added' event is recent activity
    tr.db.execute("UPDATE events SET ts='2000-01-01T00:00:00+00:00' WHERE app_id=?", (app,))
    assert [r["id"] for r in tr.stale(7)] == [app]
    tr.close()


def test_journal(tmp_home):
    journal.log("Applied to 3 jobs")
    journal.log("Learned k8s probes", kind="learning", tags=["k8s"])
    assert len(journal.entries()) == 2
    assert journal.entries("learning")[0]["text"] == "Learned k8s probes"
    assert "#k8s" in (tmp_home / "journal.md").read_text()
    with pytest.raises(ValueError):
        journal.log("x", kind="nope")


def test_insights_contextual():
    tips = insights.contextual_tips({"submitted": 12, "response_rate": 0.0, "failed": 4, "by_status": {}}, 2, ["Go"])
    titles = [t["title"] for t in tips]
    assert "Follow up" in titles and "Move with the cheese" in titles
    assert insights.daily_principle(seed=1)["title"]
    assert "🧀" in insights.render(tips)


def test_quiz_and_self_assess():
    answers = iter(["a"] * 10)
    bank = assessment.question_bank()["SQL"]
    score, detail = assessment.run_quiz("SQL", n=len(bank), ask=lambda _: next(answers), say=lambda _: None, seed=1)
    assert 0 <= score <= 1 and detail.startswith("quiz")
    replies = iter(["4", "github.com/me/proj"])
    score, detail = assessment.run_quiz("Unknown Skill", ask=lambda _: next(replies), say=lambda _: None)
    assert score == 0.8 and "self 4/5" in detail


def test_eligibility_and_study_plan(jobs):
    cv = set(extract_skills(CV))
    job = enrich(jobs[0])
    weak = assessment.eligibility(job, cv, {})
    strong = assessment.eligibility(job, cv, {"Kubernetes": 0.9, "Python": 0.9, "AWS": 0.9})
    assert strong.score > weak.score
    assert "Kubernetes" in weak.blockers and strong.verdict.startswith("Strong")
    found, _ = gaps.analyse([enrich(j) for j in jobs[:3]], cv)
    plan = assessment.study_plan(found, start=date(2026, 1, 5))
    assert "2026-01-05" in plan and "jobhunt assess" in plan


def test_interview_pack(jobs):
    cv = set(extract_skills(CV))
    job = enrich(jobs[0])
    text = interview.build_pack(job, cv)
    assert "Seniority signal: **senior**" in text
    assert "System design / leadership" in text and "Kubernetes (⚠️ gap" in text
    path = interview.write_pack(job, cv)
    assert path.exists() and path.name.endswith("-acme.md")
