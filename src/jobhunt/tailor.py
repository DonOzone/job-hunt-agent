"""Tailoring helpers: truthful CV keyword suggestions and a cover-letter draft (always edit before sending)."""
from __future__ import annotations

import re

from .config import Profile
from .cv import match_job, skill_counts
from .models import Job


def cv_suggestions(job: Job, cv_text: str) -> list[str]:
    cv_skills = set(skill_counts(cv_text))
    m = match_job(cv_skills, job)
    counts = skill_counts(cv_text)
    tips = []
    weak = [s for s in m.matched if counts.get(s, 0) == 1]
    if weak:
        tips.append(f"You have these but mention them only once - move them into your summary/first bullets "
                    f"with a metric: {', '.join(weak)}.")
    if m.missing:
        tips.append(f"Asked for but not on your CV: {', '.join(m.missing)}. Add them only if you have real "
                    "experience; otherwise address the gap in your cover letter.")
    tips.append(f"Mirror the job title wording (\"{job.title}\") in your headline if it honestly matches.")
    tips.append("Lead each bullet with an outcome: 'Did X, measured by Y, by doing Z'.")
    if m.years_required:
        tips.append(f"The posting mentions ~{m.years_required}+ years - make your relevant years easy to spot.")
    return tips


def best_achievements(job: Job, profile: Profile, cv_text: str, n: int = 2) -> list[str]:
    """Profile achievements first, then the CV's own quantified bullets that mention the most job skills."""
    wins = list(profile.achievements or [])[:n]
    if len(wins) < n:
        job_skills = set(match_job(set(skill_counts(cv_text)), job).matched)
        bullets = [re.sub(r"^\s*[-*\u2022]\s*", "", ln).strip() for ln in cv_text.splitlines()
                   if re.match(r"^\s*[-*\u2022]\s+", ln) and re.search(r"\d", ln)]
        bullets.sort(key=lambda b: -len(job_skills & set(skill_counts(b))))
        wins += [b.rstrip(".") + "." for b in bullets if b not in wins][: n - len(wins)]
    return wins


def cover_letter(job: Job, profile: Profile, cv_text: str) -> str:
    m = match_job(set(skill_counts(cv_text)), job)
    top = m.matched[:3]
    wins = best_achievements(job, profile, cv_text)
    wins += ["<one quantified achievement>", "<another quantified achievement>"][len(wins):]
    gap = m.missing[:1]
    return "\n".join(x for x in [
        f"Dear {job.company} hiring team,",
        "",
        f"I'm applying for the {job.title} role."
        + (f" My hands-on experience with {', '.join(top)} maps directly to what you're looking for." if top else ""),
        "",
        "A couple of results I'm proud of:",
        f"- {wins[0]}",
        f"- {wins[1]}",
        "",
        f"<One sentence on why {job.company} specifically - product, mission or a recent launch.>",
        (f"I'm actively deepening my {gap[0]} skills and can share a recent project." if gap else None),
        "",
        "I'd welcome the chance to discuss how I can help the team.",
        "",
        "Best regards,",
        profile.name or "<Your name>",
        " · ".join(x for x in (profile.email, profile.linkedin) if x),
    ] if x is not None)


def render(job: Job, profile: Profile, cv_text: str) -> str:
    lines = [f"# Tailoring: {job.title} @ {job.company}", "", f"Link: {job.url}", "", "## CV suggestions", ""]
    lines += [f"- {t}" for t in cv_suggestions(job, cv_text)]
    lines += ["", "## Cover letter draft (edit before sending - never send unedited)", "", "```text",
              cover_letter(job, profile, cv_text), "```", ""]
    return "\n".join(lines)
