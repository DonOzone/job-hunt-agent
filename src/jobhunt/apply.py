"""Playwright-powered application assistant.

Safety model: the assistant opens the real application form in a visible browser, pre-fills
what it confidently knows from your profile, uploads your CV, screenshots the result and then
STOPS for you to review. It only clicks "submit" with --auto-submit and when every required
field is filled. Every step is written to the tracker with a timestamp.

Never use it on sites whose terms forbid automation (e.g. LinkedIn Easy Apply).
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .config import Profile, workspace_dir
from .models import Job
from .notify import Notifier
from .tracker import Tracker

# field key -> regexes matched against label/name/id/placeholder/aria-label
FIELD_PATTERNS: list[tuple[str, str]] = [
    ("first_name", r"first[\s_-]?name|given[\s_-]?name|forename"),
    ("last_name", r"last[\s_-]?name|family[\s_-]?name|surname"),
    ("name", r"^(full[\s_-]?)?name$|your name|full name"),
    ("email", r"e-?mail"),
    ("phone", r"phone|mobile|tel"),
    ("linkedin", r"linked\s?in"),
    ("github", r"git\s?hub"),
    ("website", r"website|portfolio|personal (site|url)"),
    ("location", r"^location$|current location|city|where are you (based|located)"),
]

BROWSER_HINT = "Install browser extras: pip install -e '.[browser]' && playwright install chromium"
BLOCKED_HOSTS = ("linkedin.com", "indeed.com", "glassdoor.com")

# What to expect per ATS - shown before the browser opens and again after applying.
EXPECTED_FLOWS = {
    "greenhouse": "Greenhouse: single-page form (name, email, phone, CV, LinkedIn, custom questions, optional EEO "
                  "survey). Confirmation email within minutes; recruiter screen usually 1-2 weeks.",
    "lever": "Lever: single-page form at <posting>/apply (name, email, phone, current company, links, CV). "
             "Recruiter review typically 5-10 business days.",
    "ashby": "Ashby: single-page form, sometimes a CAPTCHA at submit (you solve it). Often an automated "
             "scheduling link for the first call within 1-2 weeks.",
    "workday": "Workday: needs an account per company and a 5-8 page wizard (15-25 min). Status in the candidate "
               "portal; replies can take 2-4 weeks.",
    "smartrecruiters": "SmartRecruiters: multi-step form; CV parsing pre-fills fields - check them carefully.",
    "generic": "Unknown form - fields are filled by their labels; review everything. Expect a confirmation email. "
               "If you hear nothing in 7 days, follow up politely.",
}


def detect_ats(url: str) -> str:
    u = url.lower()
    for name in ("greenhouse", "lever", "ashby", "workday", "smartrecruiters"):
        if name in u or (name == "workday" and "myworkdayjobs" in u):
            return name
    return "generic"


def profile_values(profile: Profile) -> dict[str, str]:
    first, _, last = profile.name.partition(" ")
    vals = {"name": profile.name, "first_name": first, "last_name": last, "email": profile.email,
            "phone": profile.phone, "linkedin": profile.linkedin, "github": profile.github,
            "website": profile.website, "location": profile.location}
    return {k: v for k, v in vals.items() if v}


def classify_field(descriptor: str, answers: dict[str, str] | None = None) -> str | None:
    """Map a form field descriptor (label/name/placeholder) to a profile key or a saved answer key."""
    d = descriptor.strip().lower()
    for key, pattern in FIELD_PATTERNS:
        if re.search(pattern, d):
            return key
    for question in (answers or {}):
        if question.lower() in d:
            return f"answer:{question}"
    return None


@dataclass
class ApplyResult:
    job_id: str
    app_id: int
    status: str
    filled: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    screenshot: str | None = None


class ApplyAssistant:
    def __init__(self, profile: Profile, tracker: Tracker, notifier: Notifier,
                 confirm: Callable[[str], str] = input, headless: bool = False):
        self.headless = headless
        self.profile = profile
        self.tracker = tracker
        self.notifier = notifier
        self.confirm = confirm

    def apply(self, job: Job, auto_submit: bool = False, dry_run: bool = False,
              missing_skills: list[str] | None = None) -> ApplyResult:
        if any(h in job.url for h in BLOCKED_HOSTS):
            raise RuntimeError(f"{job.url} forbids automated applications - apply manually and run "
                               "`jobhunt track update` afterwards.")
        app_id = self.tracker.add(job)
        ats = detect_ats(job.url)
        self.tracker.update(app_id, "applying", f"assistant started ({ats})")
        self.notifier.echo(f"Expected flow - {EXPECTED_FLOWS.get(ats, EXPECTED_FLOWS['generic'])}")
        if dry_run:
            self.tracker.update(app_id, "saved", "dry run - nothing submitted")
            return ApplyResult(job.id, app_id, "saved")

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(BROWSER_HINT) from exc

        shots = workspace_dir() / "screenshots"
        shots.mkdir(exist_ok=True)
        result = ApplyResult(job.id, app_id, "applying")
        with sync_playwright() as pw:
            # Persistent profile keeps your logins/cookies between runs.
            ctx = pw.chromium.launch_persistent_context(str(workspace_dir() / "browser-profile"),
                                                      headless=self.headless)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(job.url + ("/apply" if ats == "lever" and not job.url.rstrip("/").endswith("apply") else ""),
                      wait_until="domcontentloaded")
            self._click_apply_button(page)
            result.filled, result.missing_required = self._fill(page)
            shot = shots / f"{job.id}.png"
            page.screenshot(path=str(shot), full_page=True)
            result.screenshot = str(shot)

            summary = (f"Filled: {', '.join(result.filled) or 'nothing'}\n"
                       f"Needs you: {', '.join(result.missing_required) or 'nothing'}\nScreenshot: {shot}")
            self.notifier.send(f"Review application: {job.title} @ {job.company}", summary)

            if auto_submit and not result.missing_required and self._submit(page):
                status, note = "applied", "auto-submitted by assistant"
            else:
                answer = self.confirm("Review the form in the browser. Type 'y' once YOU submitted it, "
                                      "'s' to skip, anything else to keep as saved: ").strip().lower()
                status, note = {"y": ("applied", "submitted by user"), "s": ("skipped", "skipped by user")}.get(
                    answer, ("saved", "left for later"))
            ctx.close()

        self.tracker.update(app_id, status, note, next_action="Follow up if no reply" if status == "applied" else None,
                            due_in_days=7 if status == "applied" else None)
        result.status = status
        if status == "applied":
            growth = ", ".join((missing_skills or [])[:5]) or "none detected"
            self.notifier.send(f"Applied: {job.title} @ {job.company}",
                               f"Expected flow: {EXPECTED_FLOWS[ats if ats in EXPECTED_FLOWS else 'generic']}\n"
                               f"Room for growth for this role: {growth}\n"
                               f"Run `jobhunt interview-prep {job.id}` to start preparing.")
        return result

    @staticmethod
    def _click_apply_button(page) -> None:
        for sel in ("text=/^apply( now| for this job)?$/i", "a:has-text('Apply')", "button:has-text('Apply')"):
            loc = page.locator(sel).first
            try:
                if loc.is_visible(timeout=1500):
                    loc.click()
                    page.wait_for_load_state("domcontentloaded")
                    return
            except Exception:
                continue

    def _fill(self, page) -> tuple[list[str], list[str]]:
        values = profile_values(self.profile)
        filled, missing = [], []
        for el in page.query_selector_all("input, textarea, select"):
            kind = (el.get_attribute("type") or "").lower()
            if kind in ("hidden", "submit", "button", "checkbox", "radio") or not el.is_visible():
                continue
            descriptor = self._descriptor(page, el)
            required = el.get_attribute("required") is not None or el.get_attribute("aria-required") == "true" \
                or descriptor.strip().endswith("*")
            if kind == "file":
                cv = self.profile.cv_path
                if cv and re.search(r"resume|cv", descriptor, re.I) and Path(cv).exists():
                    el.set_input_files(cv)
                    filled.append("resume")
                elif required:
                    missing.append(descriptor or "file upload")
                continue
            key = classify_field(descriptor, self.profile.answers)
            value = (self.profile.answers.get(key[7:]) if key and key.startswith("answer:") else values.get(key or ""))
            if value and not (el.input_value() if el.evaluate("e => 'value' in e") else ""):
                try:
                    if el.evaluate("e => e.tagName") == "SELECT":
                        el.select_option(label=value)
                    else:
                        el.fill(value)
                    filled.append(key or descriptor)
                    continue
                except Exception:
                    pass
            if required and not value:
                missing.append(descriptor or "unlabelled field")
        return filled, missing

    @staticmethod
    def _descriptor(page, el) -> str:
        el_id = el.get_attribute("id")
        label = ""
        if el_id:
            lab = page.query_selector(f"label[for='{el_id}']")
            label = lab.inner_text() if lab else ""
        if not label:
            label = el.evaluate("e => (e.closest('label') || {}).innerText || ''")
        attrs = ("aria-label", "placeholder", "name")
        parts = [label, *(el.get_attribute(a) for a in attrs), el_id]
        return next((p.strip() for p in parts if p and p.strip()), "")

    @staticmethod
    def _submit(page) -> bool:
        for sel in ("button[type=submit]", "input[type=submit]", "button:has-text('Submit')"):
            loc = page.locator(sel).first
            try:
                if loc.is_visible(timeout=1000):
                    loc.click()
                    page.wait_for_load_state("networkidle")
                    return True
            except Exception:
                continue
        return False
