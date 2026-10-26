"""Application kit: everything needed to apply to ONE job you picked, in one folder.

workspace/applications/<company>_<role>/
  posting.md        exact posting text (archived - jobs get taken down) + link + integrity verdict
  fit.md            gates + 5-dimension fit score
  cv-review.md      wording / keyword / exposure review for this job
  cv-draft.md       DRAFT tailored CV (fill the [placeholders] with real facts)
  cv-changes.diff   baseline -> draft changes (baseline is unchanged)
  requirements.md  recognised requirements mapped to baseline evidence + manual checks
  cover-letter.md   cover-letter draft (Word snapshot also generated with docx=True)
  form-answers.md   copy-paste answers for the usual form questions (+ what is still missing)
  interview-prep.md prep pack for this job
  checklist.md      step-by-step: verify -> finalise -> submit -> track -> follow up
  review.md         hiring-manager-style review of the kit (re-run `jobhunt review <job>` after editing)
Company notes are shared across applications: workspace/company-research/<company>.md
"""
from __future__ import annotations

import re
from difflib import unified_diff
from pathlib import Path

from . import cv_review, fit, interview, research, review, tailor
from .apply import EXPECTED_FLOWS, detect_ats, profile_values
from .config import Profile, workspace_dir
from .cv import extract_skills
from .cv_format import COMMENT_RE, markdown_to_docx
from .enrich import salary_usd
from .models import Job
from .tracker import now


def folder(job: Job) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", f"{job.company}_{job.title}".lower()).strip("-")[:60]
    path = workspace_dir() / "applications" / f"{slug}-{job.id[:6]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def form_answers(job: Job, profile: Profile, report: fit.Fit, cv_text: str = "") -> str:
    vals = profile_values(profile)
    top = report.matched[:3]
    pay = salary_usd(job, profile.fx_to_usd)
    salary = (f"Based on the role and market, I'm targeting around USD {profile.target_salary_usd:,.0f} per year, "
              "and I'm flexible on the overall package." if profile.target_salary_usd
              else "I'd like to understand the full scope first; I'm sure we can agree on a fair package.")
    lines = [f"# Form answers: {job.title} @ {job.company}", "",
             "Copy-paste helpers. Edit to sound like you. `jobhunt apply` auto-fills the profile fields.", "",
             "## Profile fields", ""]
    for key in ("name", "email", "phone", "location", "linkedin", "github", "website"):
        lines.append(f"- **{key}**: {vals.get(key) or '❗ missing - add to config/profile.yaml'}")
    lines += ["", "## Common questions", "",
              "**Why do you want this role?**",
              f"> The {job.title} role lines up with what I do best"
              + (f" - {', '.join(top)}" if top else "")
              + f". <One specific thing about {job.company}: product, mission, recent news.>", "",
              "**Why are you a good fit?**",
              "> " + next(iter(tailor.best_achievements(job, profile, cv_text, 1)),
                          "<Your strongest quantified achievement relevant to this role.>"), "",
              f"**Salary expectation?** {'(posting: ~USD ' + format(pay, ',.0f') + '/yr)' if pay else ''}",
              f"> {salary}", "",
              "**Do you require visa sponsorship?**",
              "> " + ("No." if report.logistics.reason in ("remote", "in your home country")
                      else "<Yes/No - answer honestly; check the eligibility gate in fit.md.>"), "",
              "**Willing to relocate?**",
              "> " + ("Yes." if profile.open_to_relocation else "No, I'm looking for remote or local roles."), ""]
    if report.missing:
        lines += ["**If asked about a skill you lack** (" + ", ".join(report.missing[:3]) + "):",
                  "> I haven't used it in production yet; I've <started course/project>, and I picked up "
                  "<similar skill> quickly in <context>.", ""]
    saved = profile.answers or {}
    if saved:
        lines += ["## Your saved answers (profile.answers)", ""] + [f"- **{q}**: {a}" for q, a in saved.items()]
    return "\n".join(lines) + "\n"


def requirements(job: Job, cv_text: str, report: fit.Fit) -> str:
    """Map recognised posting skills to baseline lines, keeping unsupported requirements visible."""
    baseline = COMMENT_RE.sub(lambda m: "\n" * m.group().count("\n"), cv_text)
    parsed = cv_review.parse(baseline)
    lines = ["# Requirements and CV evidence", "",
             "Keyword coverage is not a promise of eligibility or a perfect match. "
             "Check the full posting in posting.md, including requirements outside the skill taxonomy.", "",
             "| Posting skill | Baseline evidence | Action |", "|---|---|---|"]
    for skill in report.matched + report.missing:
        mentions = [p for p in parsed if skill in extract_skills(p.body)]
        evidence = next((p for p in mentions if p.section in ("experience", "projects")), None)
        if evidence:
            snippet = evidence.body.replace("|", "/").replace("\n", " ")
            lines.append(f"| {skill} | L{evidence.no + 1}: {snippet} | Surface this existing evidence |")
        elif mentions:
            lines.append(f"| {skill} | Listed on baseline, no experience/project evidence found | "
                         "Explain where you used it, only if true |")
        else:
            lines.append(f"| {skill} | Not found | Do not claim it; confirm experience or use ramp-up |")
    if not report.matched and not report.missing:
        lines.append("| No taxonomy skills detected | Manual review needed | Read the full posting |")
    lines += ["", "## Eligibility and logistics", ""]
    for gate in [*report.gates, report.logistics]:
        lines.append(f"- {gate.name}: {gate.verdict} - {gate.reason}")
    lines += ["", "## Manual requirement check", "",
              "- [ ] Read every requirement in posting.md (credentials, domain knowledge, years, "
              "languages, location and work rights may need manual verification).",
              "- [ ] Confirm each skill claim, employer, date, metric and level of ownership.",
              "- [ ] Resolve gaps honestly; a course is not production experience.",
              "- [ ] Review cv-changes.diff; the baseline CV has not been modified.", ""]
    return "\n".join(lines)


def checklist(job: Job, report: fit.Fit, app_id: int | None) -> str:
    ats = detect_ats(job.url)
    steps = [
        f"Verify the posting is genuine: {report.integrity.verdict()}",
        "Read fit.md - resolve any ⛔/⚠️/❔ gate (e.g. confirm work rights on the careers page)",
        "Open cv-draft.md: replace every [placeholder] with a REAL number, delete anything untrue",
        "Read requirements.md and cv-changes.diff; confirm the evidence and every proposed change",
        "Re-run `jobhunt cv-review " + job.id + " --cv <your edited CV>` and aim for ≥ 70% keyword coverage",
        "Export the CV to PDF (or use --docx) - simple layout, no tables/columns for ATS parsing",
        f"Research {job.company}: fill 2+ sections of {research.path_for(job.company)}",
        "Personalise cover-letter.md (why this company + the problem you'd solve first)",
        f"Run `jobhunt review {job.id}` until there are no ⛔/⚠️ items",
        "Look for a referral: 1-2 people at " + job.company + " on LinkedIn - a referral beats a cold apply",
        f"Apply: `jobhunt apply {job.id}` (browser assistant) or apply manually via {job.url or 'the posting'}",
        f"Then: `jobhunt track update {app_id or '<app id>'} applied` (the assistant does this for you)",
        "Follow up after 7 days if no reply: `jobhunt track followups`",
        "Start interview-prep.md now - don't wait for the invite",
    ]
    return "\n".join([f"# Checklist: {job.title} @ {job.company}", "", f"Prepared {now()}", "",
                      f"**Expected flow:** {EXPECTED_FLOWS.get(ats, EXPECTED_FLOWS['generic'])}", ""]
                     + [f"- [ ] {s}" for s in steps]) + "\n"


def build(job: Job, profile: Profile, cv_text: str, cv_path: str, report: fit.Fit | None = None,
          app_id: int | None = None, docx: bool = False) -> dict[str, Path]:
    out = folder(job)
    cv_skills = set(extract_skills(cv_text))
    report = report or fit.evaluate(job, profile, cv_text, cv_skills)
    files: dict[str, Path] = {}

    def put(name: str, text: str) -> None:
        files[name] = out / name
        files[name].write_text(text, encoding="utf-8")

    put("posting.md", f"# {job.title} @ {job.company}\n\n- Link: {job.url or 'n/a'}\n- Location: {job.location}\n"
                      f"- Archived: {now()}\n- Integrity: {report.integrity.verdict()}\n\n---\n\n"
                      f"{report.integrity.cleaned or job.description}\n")
    put("fit.md", fit.render(report))
    rev = cv_review.review(cv_text, [job], f"{job.company} {job.title}")
    put("cv-review.md", cv_review.render_report(rev))
    draft = cv_review.draft_cv(cv_text, rev)
    put("cv-draft.md", draft)
    put("requirements.md", requirements(job, cv_text, report))
    put("cv-changes.diff", "".join(unified_diff(cv_text.splitlines(keepends=True), draft.splitlines(keepends=True),
                                              fromfile=cv_path, tofile="cv-draft.md")))
    if docx:
        files["cv-draft.docx"] = cv_review.to_docx(draft, out / "cv-draft.docx")
    put("cover-letter.md", tailor.cover_letter(job, profile, cv_text) + "\n")
    if docx:
        files["cover-letter.docx"] = markdown_to_docx(files["cover-letter.md"].read_text(encoding="utf-8"),
                                                    out / "cover-letter.docx")
    put("form-answers.md", form_answers(job, profile, report, cv_text))
    put("interview-prep.md", interview.build_pack(job, cv_skills))
    put("checklist.md", checklist(job, report, app_id))
    files["company-research"] = research.brief(job)
    put("review.md", review.render(review.review_kit(job, out, profile, cv_text)))
    return files
