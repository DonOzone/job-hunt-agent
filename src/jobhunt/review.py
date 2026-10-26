"""Application reviewer - a hiring-manager-style check of an application kit before you send it.

Reads workspace/applications/<job>/ (your edited files: cv-final.md if present, else cv-draft.md, cover-letter.md,
form-answers.md) and checks them against the posting and your baseline CV. Every finding is grounded:

* Unfilled placeholders ([...] / <...>) that would be embarrassing to send.
* Claims not backed by your baseline CV: skills or numbers that appear in the draft but not in the CV you imported.
* Cover letter: length, names the company and role, the posting's top skills you have, clichés, your avoid-words.
* CV: length for your experience, clichés, contact details.
* Company research done? Posting integrity warnings still open?

It never rewrites anything - it tells you what to fix and why.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from . import research
from .config import Profile, load_data
from .cv import extract_skills, years_of_experience
from .models import Job
from .tracker import now

COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
PLACEHOLDER_RE = re.compile(r"\[(?!x\]|\s\])[^\]\n]{2,80}\](?!\()|<(?!!--|https?:)[A-Za-z][^<>\n]{3,400}>")
NUMBER_RE = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?\s?(?:%|x\b|k\b|m\b|\+)|\$\s?\d[\d,.]*\w?)", re.I)
SEVERITY = {"blocker": "⛔", "fix": "⚠️", "tip": "💡"}
PENALTY = {"blocker": 20, "fix": 7, "tip": 2}


@dataclass
class Finding:
    severity: str  # blocker | fix | tip
    where: str
    message: str


@dataclass
class KitReview:
    job: Job
    folder: Path
    findings: list[Finding] = field(default_factory=list)
    stats: dict[str, int | str] = field(default_factory=dict)

    @property
    def score(self) -> int:
        return max(0, 100 - sum(PENALTY[f.severity] for f in self.findings))

    @property
    def verdict(self) -> str:
        if any(f.severity == "blocker" for f in self.findings):
            return "Not ready - fix the ⛔ items before sending"
        return "Ready to send" if self.score >= 85 else "Almost there - fix the ⚠️ items"

    def add(self, severity: str, where: str, message: str) -> None:
        self.findings.append(Finding(severity, where, message))


@lru_cache(maxsize=1)
def style_rules() -> dict:
    return load_data("writing_style.yaml")


def visible(text: str) -> str:
    return COMMENT_RE.sub("", text)


def prose(text: str) -> str:
    """Visible text without placeholders - what the reader would actually take as a claim."""
    return PLACEHOLDER_RE.sub(" ", visible(text))


def placeholders(text: str) -> list[str]:
    return sorted({m.group(0) for m in PLACEHOLDER_RE.finditer(visible(text))})


def cliches(text: str, extra: list[str] | None = None) -> list[tuple[str, str]]:
    body = visible(text).lower()
    hits = []
    for pattern, advice in style_rules().get("cliches", {}).items():
        m = re.search(pattern, body)
        if m:
            hits.append((m.group(0), advice))
    for word in extra or []:
        if word and re.search(rf"\b{re.escape(word.lower())}\b", body):
            hits.append((word, "On your own avoid-list (profile writing_style.avoid_words)."))
    return hits


def unsupported_numbers(draft: str, baseline: str) -> list[str]:
    base = {re.sub(r"\s", "", n).lower() for n in NUMBER_RE.findall(baseline)}
    return sorted({n for n in NUMBER_RE.findall(prose(draft)) if re.sub(r"\s", "", n).lower() not in base})


def _words(text: str) -> int:
    return len(re.findall(r"[A-Za-z][\w'’-]*", visible(text)))


def _read(folder: Path, *names: str) -> tuple[str, str]:
    for name in names:
        p = folder / name
        if p.exists():
            return name, p.read_text(encoding="utf-8")
    return "", ""


def review_kit(job: Job, folder: Path, profile: Profile, baseline_cv: str) -> KitReview:
    r = KitReview(job=job, folder=folder)
    avoid = list((profile.writing_style or {}).get("avoid_words") or [])
    base_skills = set(extract_skills(baseline_cv))
    job_skills = list(job.skills or extract_skills(f"{job.title}\n{job.description}"))

    # --- CV ---------------------------------------------------------------------------------------------------
    cv_name, cv = _read(folder, "cv-final.md", "cv-draft.md")
    if not cv:
        r.add("blocker", "cv", "No CV in the kit - run `jobhunt prepare` first (or save your final CV as cv-final.md).")
    else:
        for ph in placeholders(cv):
            r.add("blocker", cv_name, f"Unfilled placeholder {ph} - replace with a real fact or delete the line.")
        extra = sorted(set(extract_skills(prose(cv))) - base_skills)
        if extra:
            r.add("fix", cv_name, f"Skills not in your baseline CV: {', '.join(extra)}. Keep them only if true "
                                  "(then add them to your baseline too, so every future CV has them).")
        nums = unsupported_numbers(cv, baseline_cv)
        if nums:
            r.add("fix", cv_name, f"Numbers not in your baseline CV: {', '.join(nums[:8])}. Make sure each is "
                                  "accurate and you can explain how it was measured.")
        words = _words(cv)
        pages = words / style_rules().get("cv", {}).get("words_per_page", 550)
        limit = 2 if (years_of_experience(baseline_cv) or 0) >= 5 else 1
        r.stats.update(cv_words=words, cv_pages=f"{pages:.1f}")
        if pages > limit + 0.3:
            r.add("fix", cv_name, f"~{pages:.1f} pages - aim for ≤ {limit} at your experience level; cut the oldest "
                                  "or least relevant bullets first.")
        for phrase, advice in cliches(cv, avoid):
            r.add("tip", cv_name, f"“{phrase}” - {advice}")
        cv_has = set(extract_skills(visible(cv)))
        buried = [s for s in job_skills[:8] if s in base_skills and s not in cv_has]
        if buried:
            r.add("fix", cv_name, f"You have {', '.join(buried)} (it's in your baseline) but this CV doesn't show "
                                  "it - the posting asks for it.")
        if profile.email and profile.email.lower() not in cv.lower():
            r.add("fix", cv_name, "Your email isn't on the CV.")

    # --- cover letter -------------------------------------------------------------------------------------------
    cl_name, cl = _read(folder, "cover-letter-final.md", "cover-letter.md")
    if cl:
        for ph in placeholders(cl):
            r.add("blocker", cl_name, f"Unfilled placeholder {ph}.")
        words = _words(cl)
        lim = style_rules().get("cover_letter", {})
        r.stats["cover_letter_words"] = words
        if words < lim.get("min_words", 150):
            r.add("fix", cl_name, f"{words} words - a bit thin; add why {job.company} and one more relevant result.")
        elif words > lim.get("max_words", 400):
            r.add("fix", cl_name, f"{words} words - trim to under {lim.get('max_words', 400)}; recruiters skim.")
        if job.company and job.company.lower() not in cl.lower():
            r.add("fix", cl_name, f"Doesn't mention {job.company} - generic letters get skipped.")
        mentioned = set(extract_skills(prose(cl)))
        strong = [s for s in job_skills[:6] if s in base_skills and s not in mentioned]
        if len(strong) >= 2:
            r.add("tip", cl_name, f"Posting asks for {', '.join(strong[:3])} which you have - weave one in "
                                  "with a short example.")
        extra = sorted(mentioned - base_skills)
        if extra:
            r.add("fix", cl_name, f"Mentions {', '.join(extra)} - not in your baseline CV. Keep only if true.")
        nums = unsupported_numbers(cl, baseline_cv)
        if nums:
            r.add("fix", cl_name, f"Numbers not in your CV: {', '.join(nums[:6])} - double-check them.")
        for phrase, advice in cliches(cl, avoid):
            r.add("tip", cl_name, f"“{phrase}” - {advice}")
        if re.search(r"\bI\b", visible(cl)) and len(re.findall(r"(?m)^I\b|\.\s+I\b", visible(cl))) > 6:
            r.add("tip", cl_name, "Many sentences start with “I” - lead some with the result or with them.")

    # --- form answers ---------------------------------------------------------------------------------------------
    fa_name, fa = _read(folder, "form-answers.md")
    if fa:
        if "❗ missing" in fa:
            r.add("fix", fa_name, "Some profile fields are missing (see ❗) - add them to config/profile.yaml.")
        open_ph = [p for p in placeholders(fa) if not p.startswith("<One specific")]
        if open_ph:
            r.add("tip", fa_name, f"{len(open_ph)} answer(s) still have placeholders - finish the ones this form asks.")

    # --- research & integrity -----------------------------------------------------------------------------------
    brief = research.path_for(job.company)
    if not brief.exists() or not research.is_filled(brief):
        r.add("fix", "company-research.md", f"Research {job.company} (2 sections minimum) - it feeds 'why us?' and "
                                            f"interview answers: {brief}")
    if any(t.startswith("integrity:") for t in job.tags):
        r.add("tip", "posting", "The posting had hidden text/instructions removed - verify it on the employer's "
                                "own careers page before sending personal data.")
    order = {"blocker": 0, "fix": 1, "tip": 2}
    r.findings.sort(key=lambda f: order[f.severity])
    return r


def render(r: KitReview) -> str:
    lines = [f"# Application review: {r.job.title} @ {r.job.company}", "",
             f"Reviewed {now()} · **{r.score}/100 - {r.verdict}**", ""]
    if r.stats:
        lines += ["- " + " · ".join(f"{k.replace('_', ' ')}: {v}" for k, v in r.stats.items()), ""]
    if not r.findings:
        lines += ["Nothing to fix. Read it once out loud, then send it. 🚀"]
    for sev in ("blocker", "fix", "tip"):
        group = [f for f in r.findings if f.severity == sev]
        if group:
            title = {"blocker": "Must fix", "fix": "Should fix", "tip": "Polish"}[sev]
            lines += [f"## {SEVERITY[sev]} {title} ({len(group)})", ""]
            lines += [f"- **{f.where}:** {f.message}" for f in group] + [""]
    lines += ["---", "Edit the files in this folder (save your final CV as `cv-final.md` if you like), then re-run "
              f"`jobhunt review {r.job.id}`. Nothing is sent until you apply."]
    return "\n".join(lines) + "\n"
