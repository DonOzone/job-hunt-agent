"""Import jobs you saved manually - the compliant way to use LinkedIn, Indeed, Glassdoor, recruiter emails, etc.

CSV columns / JSON keys (only title + company are required):
    title, company, url, location, description, salary, remote, posted_at
See imports/saved_jobs.example.csv.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from ..models import Job

TRUE = {"1", "true", "yes", "y", "remote"}


def read_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else data.get("jobs", [])
    with path.open(newline="", encoding="utf-8-sig") as fh:  # utf-8-sig handles Excel-exported CSVs
        return list(csv.DictReader(fh))


def load(site: dict[str, Any]) -> list[Job]:
    jobs: list[Job] = []
    for raw in site.get("paths") or []:
        path = Path(raw).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"import file not found: {path}")
        for r in read_rows(path):
            r = {str(k).strip().lower(): (v or "") for k, v in r.items() if k}
            if not r.get("title") or not r.get("company"):
                continue
            desc = str(r.get("description", ""))
            if r.get("salary"):
                desc = f"Salary: {r['salary']}\n{desc}"
            jobs.append(Job(
                title=str(r["title"]).strip(), company=str(r["company"]).strip(), url=str(r.get("url", "")).strip(),
                source="file", location=str(r.get("location", "")), description=desc,
                remote=str(r.get("remote", "")).strip().lower() in TRUE, posted_at=str(r.get("posted_at", "")) or None))
    return jobs
