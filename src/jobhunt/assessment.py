"""Skill evaluation (quizzes / self-assessment), job eligibility and a study plan."""
from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

from .config import load_data
from .cv import match_job, taxonomy
from .gaps import Gap
from .models import Job

CV_ONLY_PROFICIENCY = 0.6  # a skill listed on the CV but never assessed
SELF_RATING_GUIDE = [
    "0 - never used it",
    "1 - read about it / followed a tutorial",
    "2 - used it in a small project with help",
    "3 - used it independently at work or in a real project",
    "4 - can design solutions with it and debug hard problems",
    "5 - could teach it / recognised expert",
]


def question_bank() -> dict[str, list[dict]]:
    return load_data("question_bank.yaml")


def export_quiz(skill: str, n: int = 5, seed: int | None = None) -> list[dict]:
    """Questions without answers - lets an AI agent run the quiz conversationally, then score with --answers."""
    bank = question_bank().get(skill, [])
    qs = random.Random(seed).sample(bank, min(n, len(bank)))
    return [{"q": q["q"], "options": q["options"]} for q in qs]


def run_quiz(skill: str, n: int = 5, ask: Callable[[str], str] = input, say: Callable[[str], None] = print,
             seed: int | None = None) -> tuple[float, str]:
    """Multiple-choice quiz. Returns (score 0-1, detail)."""
    bank = question_bank().get(skill, [])
    if not bank:
        return self_assess(skill, ask, say)
    qs = random.Random(seed).sample(bank, min(n, len(bank)))
    correct = 0
    for i, q in enumerate(qs, 1):
        say(f"\nQ{i}. {q['q']}")
        for j, opt in enumerate(q["options"]):
            say(f"   {chr(97 + j)}) {opt}")
        ans = ask("Your answer: ").strip().lower()[:1]
        right = chr(97 + q["answer"])
        if ans == right:
            correct += 1
            say("   ✅ correct")
        else:
            say(f"   ❌ answer: {right}) {q['options'][q['answer']]}" + (f" — {q['why']}" if q.get("why") else ""))
    score = correct / len(qs)
    return score, f"quiz {correct}/{len(qs)}"


def self_assess(skill: str, ask: Callable[[str], str] = input, say: Callable[[str], None] = print) -> tuple[float, str]:
    """Structured self-rating with evidence questions (used when no quiz exists)."""
    say(f"\nSelf-assessment: {skill}")
    for line in SELF_RATING_GUIDE:
        say(f"   {line}")
    try:
        rating = max(0, min(5, int(ask("Rating 0-5: ").strip() or 0)))
    except ValueError:
        rating = 0
    evidence = ask("Evidence (project/link/metric) - leave empty if none: ").strip()
    score = rating / 5 * (1.0 if evidence else 0.8)  # unverified claims are discounted
    return round(score, 2), f"self {rating}/5" + (f"; evidence: {evidence}" if evidence else "")


def level(score: float) -> str:
    return "expert" if score >= 0.85 else "proficient" if score >= 0.65 else "working" if score >= 0.4 else "beginner"


@dataclass
class Eligibility:
    job_id: str
    score: float
    verdict: str
    per_skill: dict[str, float] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)


def eligibility(job: Job, cv_skills: set[str], proficiency: dict[str, float]) -> Eligibility:
    match_job(cv_skills, job)
    tax = taxonomy()
    if not job.skills:
        return Eligibility(job.id, 0.0, "Unknown — no recognisable skills in the posting; read it manually")
    per_skill, total, weight_sum = {}, 0.0, 0.0
    for skill in job.skills:
        p = proficiency.get(skill, CV_ONLY_PROFICIENCY if skill in cv_skills else 0.0)
        w = tax[skill].get("weight", 1.0)
        per_skill[skill] = round(p, 2)
        total += p * w
        weight_sum += w
    score = round(total / weight_sum, 2)
    blockers = sorted((s for s, p in per_skill.items() if p < 0.4 and tax[s].get("weight", 1.0) >= 1.5),
                      key=lambda s: -tax[s].get("weight", 1.0))
    if score >= 0.7 and not blockers:
        verdict = "Strong match — apply now"
    elif score >= 0.45:
        verdict = "Stretch — apply and upskill in parallel (most hiring managers accept ~60-70% fit)"
    else:
        verdict = "Not yet — study the blockers first, then re-assess"
    return Eligibility(job.id, score, verdict, per_skill, blockers)


def study_plan(gaps: list[Gap], hours_per_week: int = 6, max_skills: int = 5, start: date | None = None) -> str:
    start = start or date.today()
    lines = ["# Study plan", "", f"{hours_per_week} h/week • starts {start.isoformat()}", ""]
    week = 0
    for i, g in enumerate(gaps[:max_skills], 1):
        weeks = 3 if g.importance >= 70 else 2
        begin = start + timedelta(weeks=week)
        end = begin + timedelta(weeks=weeks) - timedelta(days=1)
        course = g.courses[0] if g.courses else {"name": "search", "url": ""}
        lines += [f"## {i}. {g.skill} ({begin} → {end})",
                  f"- Why: asked by {g.share:.0%} of matching jobs (importance {g.importance:.0f}/100)",
                  f"- Learn: [{course['name']}]({course['url']})",
                  f"- Build: a small public project that uses {g.skill}; add it to your CV/GitHub",
                  f"- Check-in: `jobhunt assess \"{g.skill}\"` on {end} (target ≥ 65%)", ""]
        week += weeks
    return "\n".join(lines)
