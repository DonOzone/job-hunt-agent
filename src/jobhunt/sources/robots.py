"""robots.txt check before fetching a page we don't have an API for.

Only HTML pages are checked (posting URLs, browser-scraped career pages); official JSON APIs are meant for programs.
If robots.txt can't be read (network error / 5xx) we treat it as unknown and allow, as most crawlers do; a 401/403
on robots.txt itself means "disallow everything" per RFC 9309.
"""
from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

from .api_sources import UA

AGENT = "job-hunt-agent"


@lru_cache(maxsize=256)
def _parser(origin: str) -> RobotFileParser | None:
    rp = RobotFileParser()
    try:
        resp = requests.get(f"{origin}/robots.txt", headers=UA, timeout=10)
    except requests.RequestException:
        return None
    if resp.status_code in (401, 403):
        rp.disallow_all = True
    elif resp.status_code >= 400:
        rp.allow_all = True
    else:
        rp.parse(resp.text.splitlines())
    return rp


def allowed(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return True
    rp = _parser(f"{parts.scheme}://{parts.netloc}")
    return True if rp is None else rp.can_fetch(AGENT, url)


def require(url: str) -> None:
    if not allowed(url):
        raise PermissionError(f"{urlsplit(url).netloc} disallows automated access to this page (robots.txt). "
                              "Open it in your browser and use `jobhunt add <url> --paste` instead.")
