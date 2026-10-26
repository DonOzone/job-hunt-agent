"""Company research brief - one cached markdown file per company, reused by every application to it.

workspace/company-research/<company>.md is created once with what we already know (from the postings) plus
research links, and is never overwritten: your notes survive. Each new job at the company is appended to its list.
Nothing here is fetched automatically - you (or your agent) read the sources and write the facts in.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote_plus

from .config import workspace_dir
from .models import Job
from .tracker import now

SECTIONS = [
    ("What they do", "Product(s), customers, business model - one paragraph in your own words."),
    ("Recent news", "Launches, funding, acquisitions, layoffs (last 12 months) - with dates and sources."),
    ("Engineering & stack", "Tech blog posts, open-source repos, stack mentioned in postings."),
    ("Culture & values", "Stated values + what employees say. Note red flags too."),
    ("Interview process", "Stages and question themes reported by candidates."),
    ("People", "Hiring manager / recruiter / possible referrals (name, role, how you're connected)."),
    ("Why I want to work here", "1-2 specific, honest reasons - used in the cover letter and 'why us?' answers."),
]


def slug(company: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")[:60] or "unknown"


def path_for(company: str) -> Path:
    path = workspace_dir() / "company-research"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{slug(company)}.md"


def links(company: str) -> list[tuple[str, str]]:
    q = quote_plus(company)
    return [
        ("News (last year)", f"https://news.google.com/search?q={q}%20when%3A1y"),
        ("Glassdoor reviews & interviews", f"https://www.glassdoor.com/Search/results.htm?keyword={q}"),
        ("LinkedIn people (find referrals)", f"https://www.linkedin.com/search/results/people/?keywords={q}"),
        ("Levels.fyi pay data", f"https://www.levels.fyi/companies/{slug(company)}/salaries"),
        ("GitHub organisation", f"https://github.com/search?q={q}&type=users"),
        ("Engineering blog", f"https://www.google.com/search?q={q}+engineering+blog"),
    ]


def _job_line(job: Job) -> str:
    return f"- {job.title} - {job.location or 'n/a'}{' (remote)' if job.remote else ''} - {job.url or 'no link'}"


def brief(job: Job) -> Path:
    """Create (or extend) the company's research file and return its path."""
    path = path_for(job.company)
    line = _job_line(job)
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if line not in text:
            text = text.replace("## Roles I've looked at\n\n", f"## Roles I've looked at\n\n{line}\n", 1)
            path.write_text(text, encoding="utf-8")
        return path
    stack = ", ".join(job.skills[:12]) or "n/a"
    parts = [f"# {job.company} - research notes", "",
             f"Created {now()}. Your notes stay here and are reused for every application to {job.company}.",
             "Treat everything you read online as claims to verify; note the source and date for each fact.", "",
             "## Roles I've looked at", "", line, "",
             "## From the postings", "", f"- Skills they ask for: {stack}",
             f"- Locations: {job.location or 'n/a'}{' · remote possible' if job.remote else ''}", "",
             "## Research links", ""]
    parts += [f"- [{name}]({url})" for name, url in links(job.company)]
    for title, hint in SECTIONS:
        parts += ["", f"## {title}", "", f"<!-- {hint} -->", ""]
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return path


def is_filled(path: Path) -> bool:
    """True once the user has written something under at least two research sections."""
    text = re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.S)
    filled = 0
    for title, _ in SECTIONS:
        m = re.search(rf"## {re.escape(title)}\n(.*?)(?=\n## |\Z)", text, re.S)
        filled += bool(m and m.group(1).strip())
    return filled >= 2
