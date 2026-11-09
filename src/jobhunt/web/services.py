from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict

from .. import assessment, gaps, ranking, tailor
from ..config import Profile, Requirement
from ..cv import extract_skills, match_job
from ..fit import evaluate, render
from ..models import Job
from .db import Database

_NO_GENERATED_APPLICATIONS = re.compile(
    r"\b(?:do not|don't|must not|please avoid)\s+(?:use|submit)\s+(?:any\s+)?"
    r"(?:AI|artificial intelligence|ChatGPT)\b[^.\n]{0,140}"
    r"\b(?:applications?|cover letters?|application answers?|application responses?)\b"
    r"|\b(?:AI|ChatGPT)[ -](?:generated|written|assisted)\s+"
    r"(?:applications?|cover letters?|application answers?|application responses?)\b"
    r"[^.\n]{0,100}\b(?:not allowed|prohibited|not accepted|will be rejected|are forbidden)\b",
    re.IGNORECASE,
)


class DraftingRestricted(ValueError):
    pass


def ensure_drafting_allowed(job: Job) -> None:
    if _NO_GENERATED_APPLICATIONS.search(job.description):
        raise DraftingRestricted(
            "This posting explicitly restricts generated application materials. "
            "Write the application yourself and verify the employer's exact policy; "
            "matching, learning and tracking remain available."
        )


def profile(db: Database, owner: str) -> dict:
    with db.connect() as conn:
        row = conn.execute("SELECT profile,cv_text FROM users WHERE id=?", (owner,)).fetchone()
    if row is None:
        raise KeyError("Account not found")
    return json.loads(row["profile"]) | {"cv_text": row["cv_text"]}


def domain_profile(data: dict) -> Profile:
    return Profile(
        name=data["name"],
        location=data["location"],
        home_country=data["home_country"],
        work_authorization=data["work_authorization"],
        prefer_remote=data["prefer_remote"],
        open_to_relocation=False,
        requirement=Requirement(roles=data["roles"]),
    )


def jobs(db: Database, owner: str) -> list[Job]:
    return [Job.from_dict(j) for j in db.items(owner, "opportunity")]


def ranked(db: Database, owner: str) -> list[dict]:
    data = profile(db, owner)
    found = jobs(db, owner)
    for job in found:
        match_job(set(extract_skills(data["cv_text"])), job)
    return [
        j.to_dict()
        for j in ranking.rank_jobs(
            found, domain_profile(data), order=("remote", "region", "match", "salary", "relocation")
        )
    ]


def match(db: Database, owner: str, job_id: str) -> dict:
    job = Job.from_dict(db.item(owner, "opportunity", job_id))
    data = profile(db, owner)
    report = evaluate(job, domain_profile(data), data["cv_text"])
    return {
        "score": report.overall,
        "matched": report.matched,
        "missing": report.missing,
        "report": render(report)
        + "\n\nHeuristic assessment, not verified geographic eligibility or a hiring probability.",
    }


def gap_report(db: Database, owner: str) -> list[dict]:
    data = profile(db, owner)
    found, _ = gaps.analyse([Job.from_dict(j) for j in ranked(db, owner)], set(extract_skills(data["cv_text"])))
    return [asdict(g) for g in found[:20]]


def draft(db: Database, owner: str, application_id: str) -> dict:
    application = db.item(owner, "application", application_id)
    job = Job.from_dict(db.item(owner, "opportunity", application["opportunity_id"]))
    ensure_drafting_allowed(job)
    data = profile(db, owner)
    suggestions = tailor.cv_suggestions(job, data["cv_text"])
    return {
        "cv": data["cv_text"],
        "cover_letter": tailor.cover_letter(job, domain_profile(data), data["cv_text"]),
        "suggestions": suggestions,
        "warning": "Unedited draft, not submission-ready. Keep actual titles and "
        "ownership; confirm work rights, salary and missing facts. Nothing is submitted. Respect employer AI rules.",
    }


def make_cards(skill: str) -> list[dict]:
    bank = assessment.question_bank().get(skill, [])
    if not bank:
        return [
            {
                "topic": skill,
                "kind": "technical",
                "front": f"Explain {skill}, its trade-offs, and a real example.",
                "options": [],
                "back": "Use your own evidence. Explain limitations, testing and failure modes.",
                "answer": None,
            }
        ]
    return [
        {
            "topic": skill,
            "kind": "knowledge",
            "front": q["q"],
            "options": q["options"],
            "answer": chr(97 + q["answer"]),
            "back": q["options"][q["answer"]] + (" - " + q["why"] if q.get("why") else ""),
        }
        for q in bank[:10]
    ]


def dashboard(db: Database, owner: str) -> dict:
    applications = db.items(owner, "application")
    learning = db.items(owner, "learning")
    attempts = db.items(owner, "attempt")
    feedback = db.items(owner, "feedback")
    opportunities = db.items(owner, "opportunity")
    return {
        "opportunities": len(opportunities),
        "projects": sum(j["opportunity_type"] == "project" for j in opportunities),
        "applications": len(applications),
        "application_statuses": dict(Counter(a["status"] for a in applications)),
        "learning_completed": sum(i["status"] == "completed" for i in learning),
        "learning_total": len(learning),
        "study_attempts": sum(a["correct"] is not None for a in attempts),
        "study_correct": sum(a["correct"] is True for a in attempts),
        "feedback_received": len(feedback),
        "feedback_unreviewed": sum(not f["analysis"] for f in feedback),
        "pending_tasks": sum(t["status"] == "pending" for t in db.items(owner, "task")),
    }
