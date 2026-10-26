"""Job sources. Each source turns a site config entry into a list of Job objects.

Site config example (config/sites.yaml):
    - type: greenhouse   # board token, e.g. boards.greenhouse.io/<token>
      company: stripe
    - type: lever
      company: netflix
    - type: ashby
      company: linear
    - type: remoteok
    - type: arbeitnow
    - type: remotive
      queries: [backend engineer]
    - type: file          # CSV/JSON you saved manually (e.g. from LinkedIn/Indeed)
      paths: [imports/saved_jobs.csv]
    - type: browser      # any site, scraped with Playwright + CSS selectors
      url: https://example.com/careers
      item: ".job"
      title: ".job-title"
      link: "a"
      location: ".job-location"
"""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

from ..enrich import enrich
from ..models import Job
from . import api_sources, browser_source, file_import

log = logging.getLogger(__name__)

SOURCES: dict[str, Callable[[dict[str, Any]], list[Job]]] = {
    "greenhouse": api_sources.greenhouse,
    "lever": api_sources.lever,
    "ashby": api_sources.ashby,
    "remoteok": api_sources.remoteok,
    "arbeitnow": api_sources.arbeitnow,
    "remotive": api_sources.remotive,
    "file": file_import.load,
    "browser": browser_source.scrape,
}


def _dedupe_key(job: Job) -> tuple[str, str]:
    return re.sub(r"\W+", "", job.company.lower()), re.sub(r"\W+", "", job.title.lower())


def dedupe(jobs: list[Job]) -> list[Job]:
    """The same posting often appears on several boards - keep the most detailed copy."""
    best: dict[tuple[str, str], Job] = {}
    for job in jobs:
        key = _dedupe_key(job)
        if key not in best or len(job.description) > len(best[key].description):
            best[key] = job
    return list(best.values())


def collect(sites: list[dict[str, Any]]) -> list[Job]:
    jobs: dict[str, Job] = {}
    for site in sites:
        kind = site.get("type", "")
        fetch = SOURCES.get(kind)
        if not fetch:
            log.warning("Unknown source type %r - skipping", kind)
            continue
        try:
            found = fetch(site)
        except Exception as exc:  # one broken site must not stop the run
            log.warning("Source %s (%s) failed: %s", kind, site.get("company") or site.get("url"), exc)
            continue
        for job in found:
            jobs.setdefault(job.id, enrich(job))
        log.info("%s %s: %d jobs", kind, site.get("company", ""), len(found))
    return dedupe(list(jobs.values()))
