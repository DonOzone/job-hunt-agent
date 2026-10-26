"""Normalise raw postings: strip HTML, detect region, remote, relocation and salary."""
from __future__ import annotations

import html
import re

from .models import Job

REGION_KEYWORDS: dict[str, list[str]] = {
    "NA": ["united states", "usa", "u.s.", " us", "canada", "new york", "san francisco", "seattle", "austin",
           "boston", "toronto", "vancouver", "chicago", "los angeles", "denver", "montreal", "north america"],
    "UK": ["united kingdom", " uk", "london", "manchester", "edinburgh", "glasgow", "bristol", "cambridge",
           "england", "scotland", "wales"],
    "EU": ["germany", "berlin", "munich", "hamburg", "france", "paris", "netherlands", "amsterdam", "spain",
           "madrid", "barcelona", "ireland", "dublin", "portugal", "lisbon", "poland", "warsaw", "sweden",
           "stockholm", "denmark", "copenhagen", "finland", "helsinki", "italy", "milan", "austria", "vienna",
           "belgium", "brussels", "switzerland", "zurich", "europe", "emea", "czech", "prague", "norway", "oslo"],
    "APAC": ["india", "bangalore", "bengaluru", "singapore", "australia", "sydney", "melbourne", "japan",
             "tokyo", "hong kong", "new zealand", "philippines", "indonesia", "vietnam", "apac", "asia"],
    "LATAM": ["brazil", "são paulo", "sao paulo", "mexico", "argentina", "buenos aires", "colombia", "bogota",
              "chile", "latam", "latin america"],
    "MEA": ["nigeria", "lagos", "kenya", "nairobi", "south africa", "cape town", "johannesburg", "egypt",
            "uae", "dubai", "israel", "tel aviv", "saudi", "qatar", "africa", "middle east", "ghana", "accra"],
}

REMOTE_RE = re.compile(r"\b(remote|work from home|wfh|distributed|anywhere)\b", re.I)
HYBRID_RE = re.compile(r"\bhybrid\b", re.I)
RELOCATION_RE = re.compile(
    r"(relocation (support|assistance|package|bonus|stipend|provided|available|offered)"
    r"|(help|support|assist)(s)? (you )?(with )?relocat"
    r"|relocation is (offered|provided|available)|we (will )?relocate)",
    re.I)
NO_RELOCATION_RE = re.compile(r"(no relocation|relocation (is )?not (offered|provided|available)"
                              r"|unable to (offer|provide) (visa|relocation))", re.I)
VISA_YES_RE = re.compile(r"(visa sponsorship (is )?(available|provided|offered)|(we|will|can) sponsor"
                         r"|sponsor(ship)? (for )?(your |a )?(work )?visa|visa support)", re.I)
VISA_NO_RE = re.compile(r"(no (visa )?sponsorship|(unable|not able|cannot|can't|do not|don't|will not) (to )?sponsor"
                        r"|without (the need for )?(visa )?sponsorship"
                        r"|must (already )?(be|have) (legally )?(authori[sz]ed|eligible|the right) to work)", re.I)

FX_CODES = "USD|EUR|GBP|CAD|AUD|CHF|INR|KES|NGN|ZAR|SEK|PLN|AED"
CURRENCY_SYMBOLS = {"US$": "USD", "$": "USD", "C$": "CAD", "CA$": "CAD", "A$": "AUD", "€": "EUR", "£": "GBP",
                    "₹": "INR", "₦": "NGN", "KSH": "KES", "KSHS": "KES"}
_CUR = rf"US\$|CA\$|C\$|A\$|\$|€|£|₹|₦|KShs?|{FX_CODES}"
_NUM = r"\d{1,3}(?:[,.\s]\d{3})+|\d+(?:\.\d+)?"
SALARY_PRE_RE = re.compile(rf"(?P<cur>{_CUR})\s?(?P<lo>{_NUM})\s?(?P<lok>[kK])?"
                           rf"(?:\s*(?:-|–|—|to)\s*(?:{_CUR})?\s?(?P<hi>{_NUM})\s?(?P<hik>[kK])?)?")
SALARY_POST_RE = re.compile(rf"(?P<lo>{_NUM})\s?(?P<lok>[kK])?(?:\s*(?:-|–|—|to)\s*(?P<hi>{_NUM})\s?(?P<hik>[kK])?)?"
                            rf"\s?(?P<cur>{FX_CODES})\b")
SALARY_CONTEXT_RE = re.compile(r"salary|compensation|pay|base|OTE|range|package|per (year|annum|month|hour)", re.I)
ANNUALISE = {"year": 1, "month": 12, "day": 260, "hour": 2080}


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    text = html.unescape(html.unescape(text))
    text = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def detect_region(location: str, description: str = "") -> str:
    hay = f" {location.lower()} "
    for region, words in REGION_KEYWORDS.items():
        if any(w in hay for w in words):
            return region
    if REMOTE_RE.search(location) and ("worldwide" in hay or "anywhere" in hay or location.strip().lower() == "remote"):
        return "GLOBAL"
    hay = f" {description[:600].lower()} "
    for region, words in REGION_KEYWORDS.items():
        if any(w in hay for w in words):
            return region
    return "GLOBAL" if REMOTE_RE.search(location) else "UNKNOWN"


def _num(raw: str) -> float:
    raw = raw.strip()
    if re.fullmatch(r"\d{1,3}(?:[,.\s]\d{3})+", raw):  # 120,000 / 60.000 / 60 000
        raw = re.sub(r"[,.\s]", "", raw)
    return float(raw)


def _period(after: str) -> str:
    a = after.lower()
    if re.match(r"\W{0,3}(per |/|an |a )?\s?(hour|hr\b|h\b)", a) or "hourly" in a[:25]:
        return "hour"
    if re.match(r"\W{0,3}(per |/|a )?\s?(month|mo\b|pm\b|p\.m\.)", a) or "monthly" in a[:25]:
        return "month"
    if re.match(r"\W{0,3}(per |/|a )?\s?day", a) or "daily" in a[:25]:
        return "day"
    return "year"


def parse_salary(text: str) -> tuple[float | None, float | None, str | None]:
    """Find the most salary-like amount and return an ANNUAL (min, max, currency)."""
    text = text or ""
    best: tuple | None = None
    for rx in (SALARY_PRE_RE, SALARY_POST_RE):
        for m in rx.finditer(text):
            raw = m.group("cur")
            cur = CURRENCY_SYMBOLS.get(raw.upper(), CURRENCY_SYMBOLS.get(raw, raw.upper()))
            try:
                lo = _num(m.group("lo")) * (1000 if m.group("lok") else 1)
                hi = _num(m.group("hi")) * (1000 if m.group("hik") else 1) if m.group("hi") else None
            except ValueError:
                continue
            if m.group("hik") and not m.group("lok") and hi and lo < 1000:  # "$120-150k"
                lo *= 1000
            if hi is not None and hi < lo:
                lo, hi = hi, lo
            factor = ANNUALISE[_period(text[m.end(): m.end() + 30])]
            lo, hi = lo * factor, (hi * factor if hi else None)
            if lo < 3_000 or lo > 1e9:  # "3 years", "$5" style noise (raw currency units)
                continue
            ctx = 1 if SALARY_CONTEXT_RE.search(text[max(0, m.start() - 80): m.start()]) else 0
            rank = (ctx, 1 if hi else 0)
            if best is None or rank > best[0]:
                best = (rank, lo, hi, cur)
    return (best[1], best[2], best[3]) if best else (None, None, None)


def visa_sponsorship(text: str) -> bool | None:
    """True = offered, False = explicitly not offered, None = not stated."""
    if VISA_NO_RE.search(text):
        return False
    if VISA_YES_RE.search(text):
        return True
    return None


def enrich(job: Job) -> Job:
    from .guard import HIDDEN_BLOCK_RE, ZERO_WIDTH_RE

    raw = job.description or ""
    visible = ZERO_WIDTH_RE.sub("", HIDDEN_BLOCK_RE.sub(" ", raw))
    if visible != raw and "integrity:hidden-removed" not in job.tags:
        job.tags.append("integrity:hidden-removed")
    job.description = strip_html(visible)
    text = f"{job.title}\n{job.location}\n{job.description}"
    if not job.remote:
        job.remote = bool(REMOTE_RE.search(job.location) or REMOTE_RE.search(job.title)
                          or (REMOTE_RE.search(job.description[:1500]) and not HYBRID_RE.search(job.location)))
    if job.visa_sponsorship is None:
        job.visa_sponsorship = visa_sponsorship(text)
    if not job.relocation:
        job.relocation = (bool(RELOCATION_RE.search(text)) or job.visa_sponsorship is True) \
            and not NO_RELOCATION_RE.search(text)
    if job.salary_min is None and job.salary_max is None:
        job.salary_min, job.salary_max, cur = parse_salary(text)
        job.currency = job.currency or cur
    if job.region in ("", "UNKNOWN"):
        job.region = detect_region(job.location, job.description)
    return job


def salary_usd(job: Job, fx: dict[str, float]) -> float:
    mid = job.salary_mid
    if not mid:
        return 0.0
    return mid * fx.get((job.currency or "USD").upper(), 1.0)
