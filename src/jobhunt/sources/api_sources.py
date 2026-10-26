"""Public JSON job-board APIs (no scraping, no login needed)."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import requests

from ..models import Job

UA = {"User-Agent": "job-hunt-agent/0.1 (+https://github.com/DonOzone/job-hunt-agent)"}
TIMEOUT = 30


def get_json(url: str, params: dict[str, Any] | None = None, retries: int = 2) -> Any:
    """GET JSON with polite retries (backs off on HTTP 429 rate limits and transient errors)."""
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, params=params, headers={**UA, "Accept": "application/json"}, timeout=TIMEOUT)
            if resp.status_code == 429 and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.json()
        except (requests.ConnectionError, requests.Timeout):
            if attempt == retries:
                raise
            time.sleep(1 + attempt)
    raise RuntimeError(f"GET {url} kept returning 429 (rate limited)")


def _ts(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        value = value / 1000 if value > 1e11 else value
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    return str(value)


def greenhouse(site: dict[str, Any]) -> list[Job]:
    token = site["company"]
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", {"content": "true"})
    return [
        Job(title=j.get("title", ""), company=site.get("name", token), url=j.get("absolute_url", ""),
            source="greenhouse", location=(j.get("location") or {}).get("name", ""),
            description=j.get("content", ""), posted_at=_ts(j.get("updated_at")))
        for j in data.get("jobs", [])
    ]


def lever(site: dict[str, Any]) -> list[Job]:
    company = site["company"]
    data = get_json(f"https://api.lever.co/v0/postings/{company}", {"mode": "json"})
    jobs = []
    for j in data:
        cats = j.get("categories") or {}
        sal = j.get("salaryRange") or {}
        desc = "\n".join([j.get("descriptionPlain", "")] +
                         [f"{s.get('text', '')}\n{s.get('content', '')}" for s in j.get("lists", [])] +
                         [j.get("additionalPlain", "")])
        jobs.append(Job(
            title=j.get("text", ""), company=site.get("name", company), url=j.get("hostedUrl", ""),
            source="lever", location=cats.get("location", ""), description=desc,
            remote=(j.get("workplaceType") == "remote"), salary_min=sal.get("min"), salary_max=sal.get("max"),
            currency=sal.get("currency"), posted_at=_ts(j.get("createdAt")),
            tags=[t for t in (cats.get("team"), cats.get("commitment")) if t]))
    return jobs


def ashby(site: dict[str, Any]) -> list[Job]:
    org = site["company"]
    data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{org}", {"includeCompensation": "true"})
    jobs = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        comp = (j.get("compensation") or {}).get("summaryComponents") or []
        salary = next((c for c in comp if c.get("compensationType") == "Salary"), {})
        jobs.append(Job(
            title=j.get("title", ""), company=site.get("name", org), url=j.get("jobUrl", ""), source="ashby",
            location=j.get("location", ""), description=j.get("descriptionPlain") or j.get("descriptionHtml", ""),
            remote=bool(j.get("isRemote")), salary_min=salary.get("minValue"), salary_max=salary.get("maxValue"),
            currency=salary.get("currencyCode"), posted_at=_ts(j.get("publishedAt")),
            tags=[t for t in (j.get("department"), j.get("employmentType")) if t]))
    return jobs


def remoteok(site: dict[str, Any]) -> list[Job]:
    data = get_json("https://remoteok.com/api")
    jobs = []
    for j in data:
        if not isinstance(j, dict) or "position" not in j:
            continue  # first element is a legal notice
        jobs.append(Job(
            title=j.get("position", ""), company=j.get("company", ""), url=j.get("url", ""), source="remoteok",
            location=j.get("location") or "Remote", description=j.get("description", ""), remote=True,
            salary_min=j.get("salary_min") or None, salary_max=j.get("salary_max") or None,
            currency="USD" if j.get("salary_min") else None, posted_at=_ts(j.get("date")), tags=j.get("tags") or []))
    return jobs


def arbeitnow(site: dict[str, Any]) -> list[Job]:
    jobs = []
    url: str | None = "https://www.arbeitnow.com/api/job-board-api"
    for _ in range(int(site.get("pages", 2))):
        if not url:
            break
        data = get_json(url)
        for j in data.get("data", []):
            jobs.append(Job(
                title=j.get("title", ""), company=j.get("company_name", ""), url=j.get("url", ""),
                source="arbeitnow", location=j.get("location", ""), description=j.get("description", ""),
                remote=bool(j.get("remote")), posted_at=_ts(j.get("created_at")), tags=j.get("tags") or []))
        url = (data.get("links") or {}).get("next")
    return jobs


def remotive(site: dict[str, Any]) -> list[Job]:
    """Remotive public API (remote jobs). Please respect their rate limits: run at most a few times a day."""
    jobs: dict[str, Job] = {}
    for query in site.get("queries") or [None]:
        params: dict[str, Any] = {"limit": site.get("limit", 100)}
        if query:
            params["search"] = query
        if site.get("category"):
            params["category"] = site["category"]
        for j in get_json("https://remotive.com/api/remote-jobs", params).get("jobs", []):
            desc = j.get("description", "")
            if j.get("salary"):
                desc = f"Salary: {j['salary']}\n{desc}"
            jobs[str(j.get("id"))] = Job(
                title=j.get("title", ""), company=j.get("company_name", ""), url=j.get("url", ""), source="remotive",
                location=j.get("candidate_required_location") or "Remote", description=desc, remote=True,
                posted_at=_ts(j.get("publication_date")), tags=j.get("tags") or [])
    return list(jobs.values())
