"""CV review & targeted rewrite.

Reviews a CV against one job (or the top-N / role-filtered jobs from your latest search) and produces:
  * a review report: ATS keyword score, missing skills ranked by importance, terminology to mirror,
    "buried" skills, bullet-by-bullet wording fixes, section/contact/length checks and a targeted summary;
  * a DRAFT tailored CV (markdown, optional .docx) with improved bullets, re-ordered skills and a new summary.

Golden rule: nothing is invented or inflated. Missing skills are listed for you to add *only if true*; bullets
without a number are listed for you to quantify; weak verbs are flagged but never upgraded (contributed != led).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from .config import load_data, workspace_dir
from .cv import _patterns, extract_skills, match_job, taxonomy, years_of_experience
from .models import Job
from .tracker import now

BULLET_RE = re.compile(r"^(\s*(?:[-*•▪●◦–]|\d+[.)])\s+)(.*)$")
METRIC_RE = re.compile(r"\d|%|\$|€|£|\bx\d|\b(double|triple|halv)", re.I)
PASSIVE_RE = re.compile(r"\b(was|were|been|being|is|are)\s+\w+(ed|en)\b", re.I)
FIRST_PERSON_RE = re.compile(r"\b(I|me|my|myself)\b")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
METRIC_PLACEHOLDER = " [+ metric: by X% / for N users / saving N hrs]"


@lru_cache(maxsize=1)
def rules() -> dict:
    return load_data("cv_wording.yaml")


@lru_cache(maxsize=1)
def _weak_re() -> re.Pattern:
    return re.compile(r"^(?:" + "|".join(rules()["weak_openers"]) + r")\b\s*", re.I)


# --------------------------------------------------------------------------- parsing
def section_of(line: str) -> str | None:
    """Return the canonical section name if `line` is a heading, else None."""
    raw = line.strip()
    if not raw or len(raw) > 45:
        return None
    is_md = raw.startswith("#")
    if raw.startswith("###"):  # employer / sub-area lines inside a section
        return None
    name = re.sub(r"^[#\s]+|[*_:]+", "", raw).strip().lower()
    for canon, aliases in rules()["sections"].items():
        if name in aliases:
            return canon
    if is_md or (raw.isupper() and len(raw.split()) <= 4):
        return "other"
    return None


@dataclass
class Line:
    no: int
    text: str
    section: str | None
    bullet_prefix: str | None = None

    @property
    def body(self) -> str:
        m = BULLET_RE.match(self.text)
        return m.group(2) if m else self.text


def parse(text: str) -> list[Line]:
    lines, current = [], None
    for i, raw in enumerate(text.splitlines()):
        sec = section_of(raw)
        if sec:
            current = sec
            lines.append(Line(i, raw, "heading"))
            continue
        m = BULLET_RE.match(raw)
        lines.append(Line(i, raw, current, m.group(1) if m else None))
    return lines


# --------------------------------------------------------------------------- wording
def _past_tense(word: str) -> str:
    low = word.lower()
    irregular = rules()["irregular"]
    if low in irregular:
        out = irregular[low]
    elif low.endswith("ing") and len(low) > 5:
        stem = low[:-3]
        if len(stem) > 2 and stem[-1] == stem[-2] and stem[-1] not in "ls":  # running -> run(ned)
            stem = stem[:-1]
        out = stem + ("d" if stem.endswith("e") else "ed")
    else:
        return word
    return out.capitalize()


@dataclass
class BulletReview:
    line_no: int
    original: str
    issues: list[str] = field(default_factory=list)
    rewrite: str | None = None


LABEL_RE = re.compile(r"^([A-Z][\w/&,' -]{1,40}):\s+(?=\S)")


def review_bullet(line_no: int, text: str) -> BulletReview:
    """Flag wording problems. Only *safe* rewrites are proposed (dropping I/my, "-ing"/"Responsible for doing"
    to past tense) - a weaker verb is never upgraded to a stronger claim (e.g. "contributed" never becomes "led")."""
    text = text.strip().rstrip(".")
    r = BulletReview(line_no, text)
    label_m = LABEL_RE.match(text)
    label = label_m.group(0) if label_m and len(label_m.group(1).split()) <= 5 else ""
    body = text[len(label):]
    if FIRST_PERSON_RE.search(body):
        r.issues.append("first person - drop I/my")
        body = re.sub(r"^(I|We)\s+", "", body)
    weak = _weak_re().match(body)
    if weak:
        rest = body[weak.end():]
        first, _, tail = rest.partition(" ")
        if first.lower().endswith("ing") and len(first) > 5:
            r.issues.append(f"weak opener \"{weak.group(0).strip()}\" - lead with the action verb")
            body = f"{_past_tense(first)} {tail}".strip()
        else:
            r.issues.append(f"weak opener \"{weak.group(0).strip()}\" - say exactly what YOU did with an accurate "
                            "verb (e.g. built / implemented / partnered on) - never overstate your role")
    elif not label and body.split(" ", 1)[0].lower().endswith("ing") and len(body.split(" ", 1)[0]) > 5:
        first, _, tail = body.partition(" ")
        r.issues.append("starts with -ing - use past tense for impact")
        body = f"{_past_tense(first)} {tail}".strip()
    if PASSIVE_RE.search(body):
        r.issues.append("passive voice - say who did what")
    for c in rules()["cliches"]:
        if found := re.search(rf"\b{c}\b", body, re.I):
            r.issues.append(f"cliché \"{found.group(0)}\" - replace with evidence")
    words = len(body.split())
    if words > 32:
        r.issues.append(f"{words} words - split or trim to ≤ 2 lines")
    elif words < 6:
        r.issues.append("too vague - add what, how and the result")
    if not METRIC_RE.search(body):
        r.issues.append("no measurable result - add one if true (e.g. by X%, for N users, saving N hrs)")
    body = label + (body if label else body[:1].upper() + body[1:])
    if body != text:
        r.rewrite = body
    return r


# --------------------------------------------------------------------------- skills / exposure
def _surface_forms(skill: str, text: str) -> Counter:
    pat = dict(_patterns())[skill]
    return Counter(m.group(0) for m in pat.finditer(text))


def _same_term(a: str, b: str) -> bool:
    """True for spellings of one thing (Postgres/PostgreSQL, golang/Go, k8s/Kubernetes), not related concepts."""
    x, y = (re.sub(r"[^a-z0-9#+]", "", t.lower()) for t in (a, b))
    known = {frozenset(p) for p in (("k8s", "kubernetes"), ("js", "javascript"), ("ts", "typescript"),
                                    ("csharp", "c#"), ("dotnet", "net"), ("gcp", "googlecloud"))}
    return (x.startswith(y) or y.startswith(x) or frozenset((x, y)) in known
            or SequenceMatcher(None, x, y).ratio() >= 0.75)


@dataclass
class Review:
    target: str
    titles: list[str]
    score: float
    weights: dict[str, float]
    matched: list[str]
    missing: list[tuple[str, float]]  # (skill, points gained if truthfully added)
    terminology: list[tuple[str, str, str]]  # (skill, your wording, their wording)
    buried: list[str]
    skills_order: list[str]
    bullets: list[BulletReview]
    checks: list[tuple[bool, str]]
    summary: str
    cliches: list[str]
    previous_score: float | None = None


def _target_title(jobs: list[Job]) -> str:
    cleaned = [re.sub(r"\s*[\(\[,\-–|].*$", "", j.title).strip() for j in jobs]
    cleaned = [re.sub(r"^(senior|sr\.?|junior|jr\.?|lead|staff|principal)\s+", "", t, flags=re.I) for t in cleaned]
    return Counter(cleaned).most_common(1)[0][0] if cleaned else "Professional"


def review(cv_text: str, jobs: list[Job], target: str) -> Review:
    tax = taxonomy()
    lines = parse(cv_text)
    cv_skills = set(extract_skills(cv_text))
    freq: Counter = Counter()
    job_text = ""
    for job in jobs:
        match_job(cv_skills, job)
        freq.update(job.skills)
        job_text += f"\n{job.title}\n{job.description}"
    weights = {s: n * tax[s].get("weight", 1.0) for s, n in freq.items()}
    total = sum(weights.values()) or 1.0
    matched = sorted((s for s in weights if s in cv_skills), key=lambda s: -weights[s])
    missing = sorted(((s, round(100 * w / total, 1)) for s, w in weights.items() if s not in cv_skills),
                     key=lambda x: -x[1])
    score = round(sum(weights[s] for s in matched) / total, 3)

    terminology = []
    for s in matched:
        yours, theirs = _surface_forms(s, cv_text), _surface_forms(s, job_text)
        if yours and theirs:
            y, t = yours.most_common(1)[0][0], theirs.most_common(1)[0][0]
            if y.lower() != t.lower() and _same_term(y, t) and t.lower() not in cv_text.lower():
                terminology.append((s, y, t))

    evidence_text = "\n".join(ln.text for ln in lines if ln.section not in ("skills", "heading"))
    evidence = set(extract_skills(evidence_text))
    buried = [s for s in matched if s not in evidence]

    others = sorted(cv_skills - set(matched), key=lambda s: -tax[s].get("weight", 1.0))
    skills_order = matched + others

    bullets = [review_bullet(ln.no, ln.body) for ln in lines
               if ln.bullet_prefix and ln.section not in ("skills", "education", "certifications", "additional")]
    bullets = [b for b in bullets if b.issues]

    sections = {ln.section for ln in lines} | {section_of(ln.text) for ln in lines if ln.section == "heading"}
    words = len(cv_text.split())
    title = _target_title(jobs)
    head = cv_text[:600]
    years = years_of_experience(cv_text)
    max_words = 1400 if (years or 0) >= 10 else 1000
    placeholders = [p for p in dict.fromkeys(re.findall(r"\[[^\]\n]{3,80}\]", re.sub(r"<!--.*?-->", "", cv_text,
                                                                                        flags=re.S)))]
    checks = [
        ("experience" in sections, "Has an Experience section with a standard heading"),
        ("skills" in sections, "Has a Skills section with a standard heading"),
        ("education" in sections or "certifications" in sections, "Has Education/Certifications"),
        ("summary" in sections, "Has a Summary/Profile tuned to the role"),
        (bool(EMAIL_RE.search(head)), "Email in the header"),
        (bool(PHONE_RE.search(head)), "Phone in the header"),
        ("linkedin" in cv_text.lower(), "LinkedIn URL"),
        (all(w.lower() in cv_text.lower() for w in title.split()[:3]), f"Target title \"{title}\" appears in CV"),
        (250 <= words <= max_words, f"Length {words} words (aim 400-{max_words} ≈ "
                                    f"{'1-2' if max_words <= 1000 else '2'} pages)"),
        (not placeholders, "No unfilled [placeholders]" + (f": {', '.join(placeholders[:3])}" if placeholders else "")),
        (score >= 0.6, f"ATS keyword coverage {score:.0%} (aim ≥ 60-70%)"),
    ]
    found_cliches = sorted({m.group(0).lower() for c in rules()["cliches"]
                            for m in re.finditer(rf"\b{c}\b", cv_text, re.I)})

    top = matched[:3]
    # The posting's title is a target, not evidence that the candidate has held that title or worked in production.
    summary = (("Experience with " + (', '.join(top[:-1]) + ' and ' + top[-1] if len(top) > 1 else top[0]) + ". ")
               if top else "") + "[Your relevant experience and headline achievement, with a real number if available.]"

    return Review(target, sorted({j.title for j in jobs}), score, weights, matched, missing, terminology, buried,
                  skills_order, bullets, checks, summary, found_cliches)


# --------------------------------------------------------------------------- outputs
def render_report(r: Review, limit: int = 25) -> str:
    out = [f"# CV review — {r.target}", "", f"Reviewed against: {', '.join(r.titles[:6])}"
           + (" …" if len(r.titles) > 6 else ""), ""]
    trend = f" (previous: {r.previous_score:.0%})" if r.previous_score is not None else ""
    out += [f"## ATS keyword score: **{r.score:.0%}**{trend}", ""]
    out += ["## Exposure checklist", ""] + [f"- {'✅' if ok else '❌'} {msg}" for ok, msg in r.checks] + [""]
    out += ["## Suggested summary / headline", "", f"> {r.summary}", ""]
    out += ["## Skills", "", f"**Lead with (job order):** {', '.join(r.skills_order[:12]) or '-'}", ""]
    if r.missing:
        out += ["**Missing keywords — add ONLY if you genuinely have the experience** (pts = score gain):", ""]
        out += [f"- {s} (+{pts} pts)" for s, pts in r.missing[:12]] + [""]
    if r.terminology:
        out += ["**Mirror their wording** (ATS matches exact terms):", ""]
        out += [f"- {s}: you write \"{y}\" → they write \"{t}\" — use \"{t}\" (keep yours in brackets)"
                for s, y, t in r.terminology] + [""]
    if r.buried:
        out += ["**Buried skills** — only in your skills list; prove each in a bullet:", ""]
        out += [f"- {s}" for s in r.buried] + [""]
    if r.cliches:
        out += [f"**Clichés to replace with evidence:** {', '.join(r.cliches)}", ""]
    wording = [b for b in r.bullets if b.rewrite or any(not i.startswith("no measurable") for i in b.issues)]
    metric_only = [b for b in r.bullets if b not in wording]
    out += [f"## Bullet wording ({len(wording)} to improve)", ""]
    for b in wording[:limit]:
        out += [f"- **Line {b.line_no + 1}:** {b.original}", f"  - Issues: {'; '.join(b.issues)}"]
        if b.rewrite:
            out.append(f"  - Suggested: {b.rewrite}")
    if metric_only:
        out += ["", f"## Add a number where you honestly can ({len(metric_only)} bullets)", "",
                "Scale (users, tenants, requests/day), speed (latency, time saved), money (cost, revenue) or "
                "quality (errors, incidents). Skip it if you can't back it up.", ""]
        out += [f"- Line {b.line_no + 1}: {b.original[:110]}{'…' if len(b.original) > 110 else ''}"
                for b in metric_only[:limit]]
    out += ["", "Formula for every bullet: **Action verb + what you did + tool/skill + measurable result.**", ""]
    return "\n".join(out)


def draft_cv(cv_text: str, r: Review) -> str:
    """Tailored draft that keeps your layout. A strong existing summary is kept (the suggestion goes in a comment)."""
    lines = cv_text.splitlines()
    parsed = parse(cv_text)
    rewrites = {b.line_no: b.rewrite for b in r.bullets if b.rewrite}
    upper = any(ln.startswith("## ") and ln[3:].strip().isupper() for ln in lines)
    summary_heading = "## PROFESSIONAL SUMMARY" if upper else "## Summary"
    original = " ".join(ln.text.strip() for ln in parsed if ln.section == "summary" and ln.text.strip())
    keep_summary = len(original.split()) >= 40
    out: list[str] = [f"<!-- DRAFT tailored for {r.target} — generated {now()}. Review EVERY line. "
                      "Replace [placeholders] with real facts; delete anything untrue. -->"]
    if r.missing:
        out.append("<!-- Missing keywords (add only if true): "
                   + ", ".join(s for s, _ in r.missing[:10]) + " -->")
    inserted_summary = any(section_of(ln) == "summary" for ln in lines)
    key_skills_done = False
    in_summary = False
    for p in parsed:
        line = lines[p.no]
        if p.section == "heading":
            sec = section_of(line)
            in_summary = sec == "summary"
            if not inserted_summary and sec in ("experience", "skills"):
                out += [summary_heading, r.summary, ""]
                inserted_summary = True
            out.append(line)
            if in_summary:
                if keep_summary:
                    out.append(f"<!-- suggested opener for this role: {r.summary} -->")
                else:
                    out.append(r.summary)
            if sec == "skills" and not key_skills_done:
                keys = r.matched[:10] if len(r.matched) >= 5 else r.skills_order[:10]
                out.append(f"- **Key skills for this role:** {', '.join(keys)}")
                key_skills_done = True
            continue
        if in_summary and not keep_summary and p.section == "summary":
            out.append(f"<!-- original summary: {line.strip()} -->" if line.strip() else line)
            continue
        if p.no in rewrites:
            out.append(f"{p.bullet_prefix}{rewrites[p.no]}{'.' if line.rstrip().endswith('.') else ''}")
            continue
        out.append(line)
    if not inserted_summary:
        first = next((i for i, ln in enumerate(out) if ln.startswith("## ")), len(out))
        out[first:first] = [summary_heading, r.summary, ""]
    text = "\n".join(out) + "\n"
    for _, yours, theirs in r.terminology:
        text = re.sub(rf"(?<![\w+#.]){re.escape(yours)}(?![\w+#])", f"{theirs} ({yours})", text, count=1)
    return text


def to_docx(markdown: str, path: Path) -> Path:
    """Word version in the house CV format (see cv_format.py)."""
    from .cv_format import markdown_to_docx

    return markdown_to_docx(markdown, path)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "cv"


def history_path() -> Path:
    d = workspace_dir() / "cv-versions"
    d.mkdir(exist_ok=True)
    return d / "history.jsonl"


def history(target: str | None = None) -> list[dict]:
    path = history_path()
    if not path.exists():
        return []
    items = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [i for i in items if target is None or i["target"] == target]


def save(cv_text: str, cv_path: str, r: Review, docx: bool = False) -> dict[str, Path]:
    prev = history(r.target)
    r.previous_score = prev[-1]["score"] if prev else None
    out_dir = workspace_dir() / "cv-review"
    out_dir.mkdir(exist_ok=True)
    slug = _slug(r.target)
    report = out_dir / f"{slug}-review.md"
    report.write_text(render_report(r), encoding="utf-8")
    draft_text = draft_cv(cv_text, r)
    draft = out_dir / f"{slug}-cv-draft.md"
    draft.write_text(draft_text, encoding="utf-8")
    stamp = now().replace(":", "").replace("+0000", "Z")
    version = history_path().parent / f"{stamp}-{slug}.md"
    version.write_text(draft_text, encoding="utf-8")
    with history_path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": now(), "target": r.target, "cv": cv_path, "score": r.score,
                             "missing": [s for s, _ in r.missing[:10]], "bullets_flagged": len(r.bullets),
                             "draft": str(version)}) + "\n")
    paths = {"report": report, "draft": draft, "version": version}
    if docx:
        paths["docx"] = to_docx(draft_text, out_dir / f"{slug}-cv-draft.docx")
    return paths
