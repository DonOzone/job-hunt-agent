"""Explicit contract metadata and titles identify short-term opportunities."""

from __future__ import annotations

import re

from .models import Job

PROJECT_TAGS = {"contract", "contractor", "temporary", "freelance", "short-term", "short term", "project-based"}
PROJECT_TITLE = re.compile(r"\b(?:freelance|contract(?:or)?|temporary|short[- ]term|project[- ]based)\b", re.I)
DURATION = re.compile(r"\b(?:duration|contract length)\s*[:=-]?\s*(\d{1,2}\s+(?:weeks?|months?))\b", re.I)


def classify(job: Job) -> Job:
    if (
        job.opportunity_type == "project"
        or PROJECT_TAGS.intersection(t.lower() for t in job.tags)
        or PROJECT_TITLE.search(job.title)
    ):
        if job.id == job.default_id("job"):
            job.id = job.default_id("project")
        job.opportunity_type = "project"
        if not job.duration and (match := DURATION.search(job.description)):
            job.duration = match.group(1)
    return job


def select(jobs: list[Job], kind: str = "all") -> list[Job]:
    if kind not in ("all", "job", "project"):
        raise ValueError("opportunity type must be all, job or project")
    return [j for j in jobs if kind == "all" or classify(j).opportunity_type == kind]
