"""Generic careers-page scraper powered by Playwright (for JS-heavy sites without an API).

Respect each site's terms of service and robots.txt. Sites like LinkedIn/Indeed prohibit
automated scraping - use their official alerts/exports instead.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from ..models import Job

BROWSER_HINT = "Install browser extras: pip install -e '.[browser]' && playwright install chromium"


def scrape(site: dict[str, Any]) -> list[Job]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(BROWSER_HINT) from exc

    url = site["url"]
    jobs: list[Job] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=site.get("headless", True))
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        for item in page.query_selector_all(site.get("item", "a")):
            title_el = item.query_selector(site["title"]) if site.get("title") else item
            link_el = item.query_selector(site["link"]) if site.get("link") else item
            loc_el = item.query_selector(site["location"]) if site.get("location") else None
            title = (title_el.inner_text() if title_el else "").strip()
            href = link_el.get_attribute("href") if link_el else None
            if not title or not href:
                continue
            jobs.append(Job(title=title, company=site.get("name", url), url=urljoin(url, href), source="browser",
                            location=(loc_el.inner_text().strip() if loc_el else "")))
        if site.get("fetch_details"):
            for job in jobs:
                page.goto(job.url, wait_until="domcontentloaded")
                job.description = page.inner_text(site.get("detail", "body"))
        browser.close()
    return jobs
