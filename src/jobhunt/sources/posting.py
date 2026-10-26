"""Turn a job URL or pasted text into a Job (for `jobhunt add`).

URL: reads schema.org JobPosting JSON-LD (used by Greenhouse, Lever, Workday, SmartRecruiters, most career sites),
falling back to the page title + visible text. LinkedIn/Indeed/Glassdoor are never fetched (their terms forbid
automated access) - paste the description instead.
"""
from __future__ import annotations

import html
import json
import re
from typing import Any

import requests

from ..models import Job
from .api_sources import TIMEOUT, UA

NO_FETCH = ("linkedin.com", "indeed.com", "glassdoor.com")
LD_RE = re.compile(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", re.I | re.S)


def _walk(node: Any):
    if isinstance(node, list):
        for item in node:
            yield from _walk(item)
    elif isinstance(node, dict):
        types = node.get("@type")
        if types == "JobPosting" or (isinstance(types, list) and "JobPosting" in types):
            yield node
        for value in node.values():
            if isinstance(value, (list, dict)):
                yield from _walk(value)


def _location(node: dict) -> str:
    locs = node.get("jobLocation") or []
    out = []
    for loc in locs if isinstance(locs, list) else [locs]:
        addr = (loc or {}).get("address") or {}
        if isinstance(addr, str):
            out.append(addr)
            continue
        country = addr.get("addressCountry")
        country = country.get("name") if isinstance(country, dict) else country
        out.append(", ".join(x for x in (addr.get("addressLocality"), addr.get("addressRegion"), country) if x))
    return "; ".join(x for x in out if x)


def from_jsonld(page: str, url: str) -> Job | None:
    for block in LD_RE.findall(page):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        for node in _walk(data):
            org = node.get("hiringOrganization") or {}
            salary = (node.get("baseSalary") or {}) if isinstance(node.get("baseSalary"), dict) else {}
            value = salary.get("value") or {}
            job = Job(title=html.unescape(node.get("title", "")).strip(),
                      company=(org.get("name") if isinstance(org, dict) else str(org)) or "",
                      url=url, source="manual", location=_location(node),
                      description=html.unescape(node.get("description", "")),
                      remote=node.get("jobLocationType") == "TELECOMMUTE",
                      posted_at=node.get("datePosted"))
            if isinstance(value, dict) and (value.get("minValue") or value.get("value")):
                unit = {"HOUR": 2080, "DAY": 260, "WEEK": 52, "MONTH": 12}.get(str(value.get("unitText")).upper(), 1)
                lo = value.get("minValue") or value.get("value")
                hi = value.get("maxValue") or lo
                job.salary_min, job.salary_max = float(lo) * unit, float(hi) * unit
                job.currency = salary.get("currency")
            return job
    return None


def fetch(url: str) -> Job:
    if any(h in url.lower() for h in NO_FETCH):
        raise RuntimeError("LinkedIn/Indeed/Glassdoor can't be fetched automatically - copy the description and "
                           "use `jobhunt add <url> --paste` (or --file description.txt)")
    from .robots import require

    require(url)
    resp = requests.get(url, headers={**UA, "Accept": "text/html"}, timeout=TIMEOUT)
    resp.raise_for_status()
    page = resp.text
    job = from_jsonld(page, url)
    if job and job.title:
        return job
    title = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
    body = re.sub(r"<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", page, flags=re.I | re.S)
    return Job(title=html.unescape(title.group(1)).strip() if title else "", company="", url=url,
               source="manual", description=body)


ATS_COMPANY_RE = re.compile(
    r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/([\w-]+)|jobs(?:\.eu)?\.lever\.co/([\w-]+)"
    r"|jobs\.ashbyhq\.com/([\w-]+)|([\w-]+)\.(?:wd\d+\.)?myworkdayjobs\.com|apply\.workable\.com/([\w-]+)"
    r"|jobs\.smartrecruiters\.com/([\w-]+)|([\w-]+)\.(?:recruitee|teamtailor|bamboohr|breezy)\.\w+", re.I)


def company_from_url(url: str) -> str:
    """Company slug from a well-known ATS URL (boards.greenhouse.io/acme/... -> Acme)."""
    m = ATS_COMPANY_RE.search(url or "")
    if not m:
        return ""
    slug = next(g for g in m.groups() if g)
    return slug.replace("-", " ").replace("_", " ").title()


def from_text(text: str, url: str = "", title: str = "", company: str = "", location: str = "") -> Job:
    """Build a job from pasted text. Title/company are guessed from the first lines if not given."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not title and lines:
        title = lines[0][:100]
        # "Senior Engineer - Acme Corp" / "Senior Engineer at Acme" / "Senior Engineer | Acme"
        m = re.match(r"(.{3,80}?)\s+(?:[-–—|@]|at)\s+([A-Z][\w&.,' ]{1,50})$", title)
        if m:
            title, company = m.group(1).strip(), company or m.group(2).strip()
    if not company:
        company = company_from_url(url)
    if not company:
        m = re.search(r"(?:company|employer|organi[sz]ation)\s*[:\-]\s*(.+)", text, re.I) \
            or re.search(r"\bat\s+([A-Z][\w&.\- ]{1,40}?)(?:[,.(\n]| is | we )", text)
        company = m.group(1).strip() if m else "Unknown company"
    if not location:
        m = re.search(r"location\s*[:\-]\s*(.+)", text, re.I)
        location = m.group(1).strip()[:80] if m else ""
    return Job(title=title, company=company, url=url, source="manual", location=location, description=text)
