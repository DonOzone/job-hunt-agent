"""Filter collected jobs against the user's requirement."""
from __future__ import annotations

import re
from datetime import date, timedelta

from .config import Requirement
from .enrich import salary_usd
from .models import Job


def _has(phrase: str, text: str) -> bool:
    return re.search(rf"(?<![\w+#]){re.escape(phrase.lower())}(?![\w+#])", text.lower()) is not None


def title_matches(title: str, roles: list[str]) -> bool:
    """A role matches when every word of it appears in the title (order-independent)."""
    if not roles:
        return True
    return any(all(_has(word, title) for word in role.split()) for role in roles)


def matches(job: Job, req: Requirement, fx: dict[str, float] | None = None) -> bool:
    text = f"{job.title}\n{job.description}\n{' '.join(job.tags)}"
    if not title_matches(job.title, req.roles):
        return False
    if any(_has(x, job.title) for x in req.exclude):
        return False
    if any(not _has(m, text) for m in req.must_have):
        return False
    if req.include_any and not any(_has(m, text) for m in req.include_any):
        return False
    if any(_has(x, text) for x in req.exclude_text):
        return False
    if req.needs_visa_sponsorship and job.visa_sponsorship is False and not job.remote:
        return False
    if req.max_age_days and job.posted_at:
        try:
            if date.fromisoformat(job.posted_at[:10]) < date.today() - timedelta(days=int(req.max_age_days)):
                return False
        except ValueError:
            pass
    if req.remote_only and not job.remote:
        return False
    if req.locations and not job.remote:
        loc = f"{job.location} {job.region}"
        if not any(_has(place, loc) for place in req.locations):
            return False
    if req.min_salary_usd and job.salary_mid:
        if salary_usd(job, fx or {}) < req.min_salary_usd:
            return False
    return True


def filter_jobs(jobs: list[Job], req: Requirement, fx: dict[str, float] | None = None) -> list[Job]:
    return [j for j in jobs if matches(j, req, fx)]
