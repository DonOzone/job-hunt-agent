"""Local JSON store for the latest collected/ranked jobs."""
from __future__ import annotations

import json
from pathlib import Path

from .config import workspace_dir
from .models import Job


def jobs_path() -> Path:
    return workspace_dir() / "jobs.json"


def save_jobs(jobs: list[Job]) -> Path:
    path = jobs_path()
    path.write_text(json.dumps([j.to_dict() for j in jobs], indent=2), encoding="utf-8")
    return path


def mark_new(jobs: list[Job]) -> int:
    """Carry first_seen over from the previous search and flag jobs that are new. Returns the new-job count."""
    from . import memory
    from .tracker import now

    previous = {j.id: j.first_seen for j in load_jobs()}
    previous.update({k: v.get("first_reviewed") for k, v in memory.records().items() if k not in previous})
    ts = now()
    for job in jobs:
        job.first_seen = previous.get(job.id) or ts
        job.is_new = job.id not in previous
    return sum(j.is_new for j in jobs)


def load_jobs() -> list[Job]:
    path = jobs_path()
    if not path.exists():
        return []
    return [Job.from_dict(d) for d in json.loads(path.read_text(encoding="utf-8"))]


def find_job(job_id: str) -> Job:
    from . import memory

    for job in load_jobs():
        if job.id == job_id or (job.rank is not None and str(job.rank) == job_id):
            return job
    for job in memory.my_jobs():
        if job.id == job_id:
            return job
    raise KeyError(f"Job {job_id!r} not found - run `jobhunt search` or `jobhunt add` first "
                   "(you can pass an id or a rank number)")
