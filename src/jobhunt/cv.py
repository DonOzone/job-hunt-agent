"""Read a CV and extract skills using the bundled taxonomy (data/skills.yaml)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .config import load_data
from .models import Job


@lru_cache(maxsize=1)
def taxonomy() -> dict[str, dict]:
    """skill -> {category, aliases, weight}"""
    return load_data("skills.yaml")


@lru_cache(maxsize=1)
def _patterns() -> list[tuple[str, re.Pattern]]:
    pats = []
    for skill, meta in taxonomy().items():
        ci = list(meta.get("aliases", []))
        cs = list(meta.get("cs_aliases", []))
        (cs if meta.get("case_sensitive") else ci).append(skill)
        parts = []
        if ci:
            parts.append("(?i:" + "|".join(re.escape(n) for n in sorted(ci, key=len, reverse=True)) + ")")
        if cs:
            parts.append("|".join(re.escape(n) for n in sorted(cs, key=len, reverse=True)))
        pats.append((skill, re.compile(rf"(?<![\w+#.])(?:{'|'.join(parts)})(?![\w+#])")))
    return pats


def read_cv(path: str | Path) -> str:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader  # optional: pip install -e '.[docs]'
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    if suffix == ".docx":
        from .cv_format import docx_to_markdown

        return docx_to_markdown(path)
    return path.read_text(encoding="utf-8", errors="ignore")


def extract_skills(text: str) -> list[str]:
    return [skill for skill, pat in _patterns() if pat.search(text or "")]


def skill_counts(text: str) -> dict[str, int]:
    return {skill: n for skill, pat in _patterns() if (n := len(pat.findall(text or "")))}


def years_of_experience(text: str) -> int | None:
    found = [int(m) for m in re.findall(r"(\d{1,2})\+?\s*(?:years|yrs)", text or "", re.I)]
    return max(found) if found else None


@dataclass
class CVMatch:
    job_id: str
    score: float
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    years_required: int | None = None


def match_job(cv_skills: set[str], job: Job) -> CVMatch:
    job.skills = job.skills or extract_skills(f"{job.title}\n{job.description}\n{' '.join(job.tags)}")
    required = set(job.skills)
    if not required:
        job.match_score = 0.0
        return CVMatch(job.id, 0.0)
    weights = {s: taxonomy()[s].get("weight", 1.0) for s in required}
    matched = sorted(required & cv_skills)
    score = sum(weights[s] for s in matched) / sum(weights.values())
    job.match_score = round(score, 3)
    return CVMatch(job.id, job.match_score, matched, sorted(required - cv_skills),
                   years_of_experience(job.description))
