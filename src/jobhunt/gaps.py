"""Rank CV skill gaps across found jobs and recommend courses/certifications."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import quote_plus

from .config import load_data
from .cv import match_job, skill_counts, taxonomy
from .models import Job


@dataclass
class Gap:
    skill: str
    category: str
    importance: float  # 0-100
    jobs: int
    share: float  # fraction of jobs that ask for it
    courses: list[dict] = field(default_factory=list)


def course_links(skill: str) -> list[dict]:
    catalog = load_data("courses.yaml")
    entries = list(catalog.get(skill, []))
    q = quote_plus(skill)
    entries += [
        {"name": f"Search Coursera for {skill}", "provider": "Coursera", "type": "search",
         "url": f"https://www.coursera.org/search?query={q}"},
        {"name": f"Search edX for {skill}", "provider": "edX", "type": "search",
         "url": f"https://www.edx.org/search?q={q}"},
    ]
    return entries


DECISION_WEIGHT = {"shortlist": 1.5, "preparing": 2.0, "applied": 2.0, "skip": 0.0, "closed": 0.0}


def decision_weights(records: dict[str, dict]) -> dict[str, float]:
    """Job id -> weight from your reviewed-jobs memory decisions."""
    return {jid: DECISION_WEIGHT[r["decision"]] for jid, r in records.items() if r.get("decision") in DECISION_WEIGHT}


def analyse(jobs: list[Job], cv_skills: set[str], weights: dict[str, float] | None = None,
            ) -> tuple[list[Gap], list[tuple[str, int]]]:
    """Return (ranked gaps, strengths). Importance blends frequency, job rank, mention depth and skill weight.

    `weights` (job id -> multiplier) lets your decisions steer the plan: jobs you shortlisted or applied to count
    more, jobs you skipped count zero (see `decision_weights`).
    """
    weights = weights or {}
    jobs = [j for j in jobs if weights.get(j.id, 1.0) > 0]
    if not jobs:
        return [], []
    tax = taxonomy()
    score: dict[str, float] = defaultdict(float)
    count: dict[str, int] = defaultdict(int)
    strengths: dict[str, int] = defaultdict(int)
    for job in jobs:
        match_job(cv_skills, job)
        rank_weight = weights.get(job.id, 1.0) / (1 + 0.05 * ((job.rank or 1) - 1))  # top-ranked jobs matter more
        mentions = skill_counts(f"{job.title}\n{job.description}")
        for skill in job.skills:
            if skill in cv_skills:
                strengths[skill] += 1
                continue
            in_title = 2.0 if skill in mentions and skill.lower() in job.title.lower() else 1.0
            depth = min(mentions.get(skill, 1), 3)
            score[skill] += rank_weight * in_title * (1 + 0.25 * (depth - 1)) * tax[skill].get("weight", 1.0)
            count[skill] += 1
    top = max(score.values(), default=1.0)
    gaps = [Gap(skill=s, category=tax[s].get("category", "other"), importance=round(100 * v / top, 1),
                jobs=count[s], share=round(count[s] / len(jobs), 2), courses=course_links(s))
            for s, v in score.items()]
    gaps.sort(key=lambda g: (-g.importance, -g.jobs, g.skill))
    return gaps, sorted(strengths.items(), key=lambda kv: -kv[1])


def render_markdown(gaps: list[Gap], strengths: list[tuple[str, int]], total_jobs: int, limit: int = 15) -> str:
    lines = ["# Skill gap report", "", f"Analysed **{total_jobs}** jobs.", "", "## Your strengths", ""]
    lines += [f"- {s} (asked by {n} jobs)" for s, n in strengths[:15]] or ["- (no overlap found)"]
    lines += ["", "## Gaps ranked by importance", "",
              "| Rank | Skill | Category | Importance | % of jobs |", "|---|---|---|---|---|"]
    for i, g in enumerate(gaps[:limit], 1):
        lines.append(f"| {i} | {g.skill} | {g.category} | {g.importance:.0f} | {g.share:.0%} |")
    lines += ["", "## How to bridge the gaps", ""]
    for i, g in enumerate(gaps[:limit], 1):
        lines.append(f"### {i}. {g.skill}")
        for c in g.courses:
            extra = f" — {c['type']}" if c.get("type") else ""
            lines.append(f"- [{c['name']}]({c['url']}) ({c.get('provider', '')}{extra})")
        lines.append("")
    return "\n".join(lines)
