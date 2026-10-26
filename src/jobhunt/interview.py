"""Interview preparation pack generated from a found job + your CV."""
from __future__ import annotations

import re
from pathlib import Path

from .config import load_data, workspace_dir
from .cv import match_job
from .models import Job


def bank() -> dict:
    return load_data("interview_bank.yaml")


def _behavioural(job: Job, data: dict) -> list[str]:
    text = job.description.lower()
    qs = []
    for theme, meta in data.get("behavioural", {}).items():
        if any(k in text for k in meta.get("keywords", [])) or theme == "core":
            qs += [f"[{theme}] {q}" for q in meta["questions"]]
    return qs


def _seniority(title: str) -> str:
    t = title.lower()
    if re.search(r"\b(staff|principal|lead|head|director|architect)\b", t):
        return "lead"
    if re.search(r"\b(senior|sr\.?)\b", t):
        return "senior"
    if re.search(r"\b(junior|jr\.?|graduate|intern|entry)\b", t):
        return "junior"
    return "mid"


def build_pack(job: Job, cv_skills: set[str]) -> str:
    data = bank()
    m = match_job(cv_skills, job)
    seniority = _seniority(job.title)
    lines = [f"# Interview prep: {job.title} @ {job.company}", "",
             f"- Link: {job.url}", f"- Location: {job.location or 'n/a'} ({job.region}, "
             f"{'remote' if job.remote else 'onsite/hybrid'})", f"- Seniority signal: **{seniority}**",
             f"- CV match: **{m.score:.0%}** — strengths: {', '.join(m.matched) or 'none detected'}",
             f"- Gaps to address honestly: {', '.join(m.missing) or 'none detected'}", ""]

    lines += ["## 1. Company research checklist", ""] + [f"- [ ] {c}" for c in data["research"]] + [""]

    lines += ["## 2. Technical questions (by skill in the posting)", ""]
    tech = data.get("technical", {})
    for skill in m.matched + m.missing:
        qs = tech.get(skill) or [f"Walk me through a project where you used {skill}. What trade-offs did you make?",
                                 f"What are common pitfalls with {skill} and how do you avoid them?"]
        tag = "✅ strength" if skill in m.matched else "⚠️ gap — prepare a learning story"
        lines += [f"### {skill} ({tag})"] + [f"- {q}" for q in qs] + [""]

    if seniority in ("senior", "lead"):
        lines += ["### System design / leadership", ""] + [f"- {q}" for q in data["senior"]] + [""]

    lines += ["## 3. Behavioural questions (answer with STAR: Situation, Task, Action, Result + metric)", ""]
    lines += [f"- {q}" for q in _behavioural(job, data)] + [""]

    lines += ["## 4. Your stories bank", "", "Prepare 5-6 STAR stories that map to the strengths above:", ""]
    lines += [f"- [ ] Story showing **{s}** — Situation / Task / Action / Result (number!)" for s in m.matched[:6]]
    lines += [f"- [ ] Story showing how you learn fast (use it for gap: **{s}**)" for s in m.missing[:2]] + [""]

    lines += ["## 5. Questions to ask them", ""] + [f"- {q}" for q in data["ask_them"]] + [""]
    lines += ["## 6. Practice schedule", ""] + [f"- [ ] {s}" for s in data["schedule"]] + [""]
    return "\n".join(lines)


def write_pack(job: Job, cv_skills: set[str]) -> Path:
    out = workspace_dir() / "interview-prep"
    out.mkdir(exist_ok=True)
    path = out / f"{job.id}-{re.sub(r'[^a-z0-9]+', '-', job.company.lower()).strip('-')}.md"
    path.write_text(build_pack(job, cv_skills), encoding="utf-8")
    return path
