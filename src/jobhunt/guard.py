"""Posting integrity: job postings are untrusted input.

* strips hidden text (HTML comments, display:none blocks, zero-width characters) that may try to steer an AI agent;
* flags instruction-like lines ("ignore previous instructions", "include the word ... in your cover letter");
* verifies the source host (known ATS / job board vs unverified - with look-alike protection);
* flags common recruitment-scam signals (fees, WhatsApp/Telegram-only contact, crypto/cheque payments).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

ATS_HOSTS = ("greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com", "workday.com", "smartrecruiters.com",
             "workable.com", "bamboohr.com", "recruitee.com", "teamtailor.com", "breezy.hr", "jobvite.com",
             "icims.com", "personio.de", "personio.com", "successfactors.com", "taleo.net", "oraclecloud.com")
BOARD_HOSTS = ("linkedin.com", "indeed.com", "glassdoor.com", "remoteok.com", "remotive.com", "arbeitnow.com",
               "weworkremotely.com", "wellfound.com", "otta.com", "welcometothejungle.com", "stackoverflow.com",
               "brightermonday.co.ke", "fuzu.com", "myjobmag.co.ke", "careerjet.co.ke", "jobberman.com",
               "builtin.com", "dice.com", "hired.com", "eurobrussels.com", "reliefweb.int", "devex.com",
               "unjobs.org", "careers.un.org", "himalayas.app", "workingnomads.com", "jobicy.com")

HIDDEN_BLOCK_RE = re.compile(
    r"<!--.*?-->|<(\w+)[^>]*style\s*=\s*[\"'][^\"']*(display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0"
    r"|opacity\s*:\s*0(?:\.0+)?\b)[^\"']*[\"'][^>]*>.*?</\1>|<(\w+)\s[^>]*?(?<![-\w])hidden(?=[\s>=])[^>]*>.*?</\3>",
    re.I | re.S)
ZERO_WIDTH_RE = re.compile("[\u200b-\u200f\u2060-\u2064\ufeff\u00ad]")
INSTRUCTION_RE = re.compile(
    r"(ignore (all |any )?(previous|prior|above|earlier) (instructions|prompts)|disregard (the|all|previous)"
    r"|you are (an?|the) (ai|assistant|language model|llm|chatbot)|as an ai\b|system prompt|\bprompt injection"
    r"|(if|when) you are an? (ai|llm|language model|bot)|(chatgpt|gpt-?\d|claude|copilot|gemini|llm)s?\b.{0,40}"
    r"(must|should|include|mention|write|say)|(include|mention|use) the (word|phrase|code)\b"
    r"|in your (cover letter|application|response),? (include|mention|write|say))",
    re.I)
SCAM_PATTERNS = {
    "asks for a fee/payment": r"(application|processing|registration|training|interview|placement|medical)\s+fee"
                              r"|pay (a |the )?(fee|deposit)|send (money|payment)|mpesa .*(fee|pay)",
    "contact only via WhatsApp/Telegram/Signal": r"\b(whatsapp|telegram|signal)\b.{0,40}(contact|reach|message|text|"
                                                 r"apply|interview)|(contact|apply|interview).{0,40}"
                                                 r"\b(whatsapp|telegram)\b",
    "crypto/cheque/gift-card payment": r"\b(bitcoin|usdt|crypto(currency)?|gift ?cards?|cashier'?s? cheque|"
                                       r"check deposit)\b",
    "too-good-to-be-true pay": r"earn (up to )?\$?\d[\d,]*\s*(per|a|/)\s*(day|week)|no experience (needed|required)"
                               r".{0,60}(earn|\$|per (day|week))",
    "personal email for hiring": r"(apply|send|email)[^.\n]{0,40}@(gmail|yahoo|hotmail|outlook|aol)\.com",
    "asks for sensitive documents early": r"(send|provide|upload).{0,30}(passport|national id|bank (details|account)"
                                         r"|social security|ssn)",
}


@dataclass
class Integrity:
    host: str
    host_kind: str  # ats | board | company | unverified | none
    cleaned: str
    hidden_removed: list[str] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    scam_signals: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.hidden_removed or self.instructions or self.scam_signals)

    def verdict(self) -> str:
        if self.ok and self.host_kind != "unverified":
            return f"✅ clean ({self.host_kind}: {self.host or 'no URL'})"
        bits = []
        if self.host_kind == "unverified":
            bits.append(f"⚠ unverified host {self.host} - confirm on the employer's own careers page")
        if self.hidden_removed:
            bits.append(f"⚠ {len(self.hidden_removed)} hidden block(s) removed")
        if self.instructions:
            bits.append(f"⚠ {len(self.instructions)} instruction-like line(s) ignored")
        if self.scam_signals:
            bits.append("🚩 scam signals: " + ", ".join(self.scam_signals))
        return "; ".join(bits)

    def to_dict(self) -> dict:
        return {"host": self.host, "host_kind": self.host_kind, "verdict": self.verdict(),
                "instructions": self.instructions, "scam_signals": self.scam_signals,
                "hidden_removed": len(self.hidden_removed)}


def _matches(host: str, apex: str) -> bool:
    return host == apex or host.endswith("." + apex)


def verify_host(url: str, company: str = "") -> tuple[str, str]:
    """Classify a URL's host. Look-alikes (evil-greenhouse.io, greenhouse.io.evil.com, user@host) are unverified."""
    if not url:
        return "", "none"
    parts = urlsplit(url if "://" in url else f"https://{url}")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host or "@" in parts.netloc or parts.scheme not in ("http", "https"):
        return host or url, "unverified"
    if any(_matches(host, apex) for apex in ATS_HOSTS):
        return host, "ats"
    if any(_matches(host, apex) for apex in BOARD_HOSTS):
        return host, "board"
    slug = re.sub(r"[^a-z0-9]", "", company.lower())
    if slug and len(slug) >= 3 and slug in re.sub(r"[^a-z0-9.]", "", host).replace(".", ""):
        return host, "company"
    return host, "unverified"


def check(text: str, url: str = "", company: str = "") -> Integrity:
    hidden = [m.group(0)[:200] for m in HIDDEN_BLOCK_RE.finditer(text or "")]
    cleaned = HIDDEN_BLOCK_RE.sub(" ", text or "")
    zero_width = len(ZERO_WIDTH_RE.findall(cleaned))
    cleaned = ZERO_WIDTH_RE.sub("", cleaned)
    if zero_width:
        hidden.append(f"{zero_width} zero-width character(s)")
    instructions, kept = [], []
    for line in cleaned.splitlines():
        if INSTRUCTION_RE.search(line):
            instructions.append(line.strip()[:200])
        else:
            kept.append(line)
    cleaned = "\n".join(kept)
    scams = [name for name, pat in SCAM_PATTERNS.items() if re.search(pat, cleaned, re.I | re.S)]
    host, kind = verify_host(url, company)
    return Integrity(host, kind, cleaned.strip(), hidden, instructions, scams)
