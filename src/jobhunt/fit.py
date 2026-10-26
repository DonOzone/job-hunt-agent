"""Fit evaluation for one job: hard gates first, then five scored dimensions.

Gates (run before scoring - a FAIL means "don't spend time drafting", but you can override with --force):
  * Eligibility - citizenship / permanent residency / security clearance / right-to-work wording.
  * Language   - languages the role requires vs the languages in your profile.
Dimensions: skills, experience, career alignment, package (0-100 each) + logistics (PASS / FLAG / FAIL).
Silence is not permission: when a posting says nothing about work rights for an onsite role abroad we
mark it UNVERIFIED so you check the employer's own careers page.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import Profile
from .cv import match_job, years_of_experience
from .enrich import salary_usd
from .guard import Integrity, check
from .matcher import title_matches
from .models import Job
from .ranking import no_move_needed

LANGUAGES = ("English", "French", "German", "Spanish", "Portuguese", "Arabic", "Swahili", "Kiswahili", "Dutch",
             "Italian", "Polish", "Danish", "Swedish", "Norwegian", "Finnish", "Mandarin", "Chinese", "Cantonese",
             "Japanese", "Korean", "Russian", "Turkish", "Hindi", "Amharic", "Somali", "Hebrew", "Greek", "Czech",
             "Romanian", "Hungarian", "Ukrainian", "Vietnamese", "Thai", "Indonesian", "Malay", "Zulu", "Yoruba",
             "Hausa", "Igbo")
LEVELS = {"basic": 1, "a1": 1, "a2": 1, "conversational": 2, "b1": 2, "intermediate": 2, "b2": 3,
          "professional": 3, "business": 3, "working": 3, "proficient": 4, "c1": 4, "fluent": 4, "fluency": 4,
          "c2": 5, "native": 5, "mother tongue": 5, "bilingual": 5}
_LANG = "|".join(LANGUAGES)
_LEVEL = r"native|fluent|fluency|bilingual|proficient|business[- ]level|professional|working|conversational|c1|c2|b1|b2"
LANG_REQ_RE = re.compile(
    rf"(?P<lvl>{_LEVEL})[^.\n]{{0,25}}?\b(?P<lang>{_LANG})\b|\b(?P<lang2>{_LANG})\b[^.\n]{{0,30}}?"
    rf"(?P<lvl2>{_LEVEL}|is required|required|is a must|is mandatory|essential|speaking)",
    re.I)
CITIZEN_RE = re.compile(
    r"(must|required to|need to|should) (be|hold) (an? )?(?P<who>[A-Z][\w.]*(?: [A-Z][\w.]*)?)? ?"
    r"(citizen|national|citizenship)|citizenship (is )?required|(?P<who2>[A-Z][\w.]*(?: [A-Z][\w.]*)?) "
    r"citizens? only|permanent resid(ent|ency)( status)? (is )?required|must be a permanent resident"
    r"|green card (holder )?(required|only)", re.I)
CLEARANCE_RE = re.compile(r"(security|government|top[- ]secret|ts/sci|sc|dv|baseline) clearance|clearance required"
                          r"|(active|current|obtain|eligible for) (a )?(security )?clearance", re.I)
RIGHT_TO_WORK_RE = re.compile(r"(right to work|authori[sz]ed to work|work authori[sz]ation|eligible to work|"
                              r"valid work permit)[^.\n]{0,40}?\bin (the )?(?P<where>[A-Z][\w.]*(?: [A-Z][\w.]*)?)",
                              re.I)
INTERNATIONAL_OK_RE = re.compile(r"international (applicants|candidates) (are )?welcome|visa holders considered|"
                                 r"open to (candidates|applicants) (from )?(anywhere|worldwide|all countries)", re.I)
COUNTRY_ALIASES = {"us": "united states", "u.s.": "united states", "usa": "united states", "u.s": "united states",
                   "american": "united states", "uk": "united kingdom", "british": "united kingdom",
                   "kenyan": "kenya", "canadian": "canada", "australian": "australia", "german": "germany",
                   "eu": "european union", "european": "european union"}


@dataclass
class Gate:
    name: str
    verdict: str  # PASS | FLAG | FAIL | UNVERIFIED
    reason: str
    quote: str = ""

    @property
    def icon(self) -> str:
        return {"PASS": "✅", "FLAG": "⚠️", "FAIL": "⛔", "UNVERIFIED": "❔"}[self.verdict]


@dataclass
class Fit:
    job: Job
    integrity: Integrity
    gates: list[Gate]
    dims: dict[str, tuple[int, str]]  # name -> (score 0-100, explanation)
    logistics: Gate
    overall: int
    recommendation: str
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(g.verdict == "FAIL" for g in [*self.gates, self.logistics])

    def to_dict(self) -> dict:
        return {"overall": self.overall, "recommendation": self.recommendation,
                "gates": {g.name: g.verdict for g in [*self.gates, self.logistics]},
                "dims": {k: v[0] for k, v in self.dims.items()}, "integrity": self.integrity.verdict()}


def _norm_country(text: str) -> str:
    low = text.lower().strip(" .")
    return COUNTRY_ALIASES.get(low, low)


def _authorised(where: str, profile: Profile) -> bool:
    target = _norm_country(where)
    mine = {_norm_country(c) for c in (profile.work_authorization or [])}
    if profile.home_country:
        mine.add(_norm_country(profile.home_country))
    return any(target and (target in m or m in target) for m in mine)


def _quote(text: str, m: re.Match) -> str:
    start = text.rfind("\n", 0, m.start()) + 1
    end = text.find("\n", m.end())
    return text[start: end if end != -1 else None].strip()[:200]


def eligibility_gate(job: Job, profile: Profile, text: str) -> Gate:
    if m := CITIZEN_RE.search(text):
        who = m.group("who") or m.group("who2") or ""
        if who and _authorised(who, profile):
            return Gate("eligibility", "PASS", f"citizenship requirement ({who}) matches your work authorisation",
                        _quote(text, m))
        return Gate("eligibility", "FAIL", "citizenship / permanent-residency requirement", _quote(text, m))
    if (m := CLEARANCE_RE.search(text)) and not profile.security_clearance:
        return Gate("eligibility", "FAIL", "security clearance required (usually citizenship-gated)", _quote(text, m))
    if m := RIGHT_TO_WORK_RE.search(text):
        where = m.group("where")
        if _authorised(where, profile):
            return Gate("eligibility", "PASS", f"you can already work in {where}", _quote(text, m))
        if job.visa_sponsorship:
            return Gate("eligibility", "PASS", f"needs right to work in {where} - sponsorship offered", _quote(text, m))
        return Gate("eligibility", "FAIL" if job.visa_sponsorship is False else "FLAG",
                    f"needs existing right to work in {where}", _quote(text, m))
    if m := INTERNATIONAL_OK_RE.search(text):
        return Gate("eligibility", "PASS", "international applicants explicitly welcome", _quote(text, m))
    if job.visa_sponsorship:
        return Gate("eligibility", "PASS", "visa sponsorship offered")
    if no_move_needed(job, profile):
        return Gate("eligibility", "PASS", "remote or in your home country")
    return Gate("eligibility", "UNVERIFIED", "posting is silent on work rights - silence is not permission; "
                "check the employer's careers/FAQ page")


def language_gate(profile: Profile, text: str) -> Gate:
    mine = {k.lower(): LEVELS.get(str(v).lower(), 4) for k, v in (profile.languages or {"English": "fluent"}).items()}
    if "swahili" in mine:
        mine.setdefault("kiswahili", mine["swahili"])
    if "kiswahili" in mine:
        mine.setdefault("swahili", mine["kiswahili"])
    worst: Gate | None = None
    for m in LANG_REQ_RE.finditer(text):
        lang = (m.group("lang") or m.group("lang2")).lower()
        lvl_word = (m.group("lvl") or m.group("lvl2") or "").lower().replace("-", " ").split(" level")[0]
        needed = LEVELS.get(lvl_word.split()[0] if lvl_word else "", 3)
        if lang not in mine:
            return Gate("language", "FAIL", f"requires {lang.title()}, which is not in your profile languages",
                        _quote(text, m))
        if needed > mine[lang] and worst is None:
            worst = Gate("language", "FLAG", f"{lang.title()} bar may be higher than your declared level",
                         _quote(text, m))
    return worst or Gate("language", "PASS", "no unmet language requirement")


def logistics_gate(job: Job, profile: Profile) -> Gate:
    if job.remote:
        return Gate("logistics", "PASS", "remote")
    if no_move_needed(job, profile):
        return Gate("logistics", "PASS", "in your home country")
    if not profile.open_to_relocation:
        return Gate("logistics", "FAIL", "requires relocation and you are not open to relocating")
    if profile.requirement.needs_visa_sponsorship and job.visa_sponsorship is False:
        return Gate("logistics", "FAIL", "onsite abroad and the posting says no visa sponsorship")
    if job.relocation or job.visa_sponsorship:
        return Gate("logistics", "PASS", "relocation/visa support offered")
    return Gate("logistics", "FLAG", "onsite abroad - relocation and visa support not stated; ask early")


def evaluate(job: Job, profile: Profile, cv_text: str, cv_skills: set[str] | None = None,
             integrity: Integrity | None = None) -> Fit:
    if integrity is None:
        integrity = check(job.description, job.url, job.company)
        # descriptions are stored already cleaned - keep what was found when the job was first added
        if "integrity:hidden-removed" in job.tags and not integrity.hidden_removed:
            integrity.hidden_removed.append("(removed when the job was saved)")
        if "integrity:instructions-removed" in job.tags and not integrity.instructions:
            integrity.instructions.append("(instruction-like lines removed when the job was saved)")
    text = f"{job.title}\n{integrity.cleaned}"
    cv_skills = cv_skills if cv_skills is not None else set()
    m = match_job(cv_skills, job)
    gates = [eligibility_gate(job, profile, text), language_gate(profile, text)]
    logistics = logistics_gate(job, profile)

    skills = round(m.score * 100)
    dims: dict[str, tuple[int, str]] = {
        "skills": (skills, f"{len(m.matched)} of {len(m.matched) + len(m.missing)} detected skills on your CV")}

    have = years_of_experience(cv_text)
    need = m.years_required
    if need is None:
        exp = (70, "no years stated")
    elif have is None:
        exp = (55, f"asks {need}+ yrs - state your years clearly on the CV")
    elif have >= need:
        exp = (90, f"you {have}+ yrs vs {need}+ asked")
    else:
        exp = (max(20, 90 - 20 * (need - have)), f"you {have} yrs vs {need}+ asked - lead with impact, not years")
    dims["experience"] = exp

    low = text.lower()
    role_hit = title_matches(job.title, profile.requirement.roles) if profile.requirement.roles else True
    goals = [g for g in profile.career_goals if g.lower() in low]
    drains = [d for d in profile.avoid if d.lower() in low]
    career = (70 if role_hit else 40) + 10 * min(len(goals), 3) - 15 * min(len(drains), 2)
    note = ("title matches your target roles" if role_hit else "title outside your target roles")
    note += f"; goals hit: {', '.join(goals)}" if goals else ""
    note += f"; drains: {', '.join(drains)}" if drains else ""
    dims["career"] = (max(0, min(100, career)), note)

    pay = salary_usd(job, profile.fx_to_usd)
    target = profile.target_salary_usd or profile.requirement.min_salary_usd
    if not pay:
        dims["package"] = (50, "not stated - research the band (Glassdoor/Levels.fyi) before the first call")
    elif target:
        dims["package"] = (max(0, min(100, round(100 * pay / target))), f"~${pay:,.0f}/yr vs target ${target:,.0f}")
    else:
        dims["package"] = (70, f"~${pay:,.0f}/yr (set target_salary_usd to compare)")

    weights = {"skills": 0.4, "experience": 0.25, "career": 0.2, "package": 0.15}
    overall = round(sum(dims[k][0] * w for k, w in weights.items()))
    if logistics.verdict == "FLAG" or any(g.verdict in ("FLAG", "UNVERIFIED") for g in gates):
        overall -= 5
    if integrity.scam_signals:
        overall = min(overall, 20)
    overall = max(0, min(100, overall))
    fit = Fit(job, integrity, gates, dims, logistics, overall, "", m.matched, m.missing)
    if fit.blocked:
        fit.recommendation = "⛔ not recommended - a gate failed (override with --force if you know better)"
    elif integrity.scam_signals:
        fit.recommendation = "🚩 possible scam - verify the employer independently before sharing any data"
    elif overall >= 75:
        fit.recommendation = "🟢 strong fit - apply, tailor carefully"
    elif overall >= 55:
        fit.recommendation = "🟡 moderate fit - apply if the role excites you; address gaps up front"
    else:
        fit.recommendation = "🔴 weak fit - consider skipping or treat as a stretch/learning target"
    return fit


def render(fit: Fit) -> str:
    j = fit.job
    out = [f"# Fit: {j.title} @ {j.company}", "", f"- Link: {j.url or 'n/a'}",
           f"- Posting integrity: {fit.integrity.verdict()}"]
    for line in fit.integrity.instructions[:5]:
        out.append(f"  - ignored: \"{line}\"")
    out += ["", f"## Overall: **{fit.overall}/100** — {fit.recommendation}", "", "## Gates", ""]
    for g in [*fit.gates, fit.logistics]:
        out.append(f"- {g.icon} **{g.name}** {g.verdict}: {g.reason}" + (f" — \"{g.quote}\"" if g.quote else ""))
    out += ["", "## Dimensions", "", "| Dimension | Score | Why |", "|---|---|---|"]
    out += [f"| {k} | {v[0]} | {v[1]} |" for k, v in fit.dims.items()]
    out += ["", f"**Strengths:** {', '.join(fit.matched) or '-'}", f"**Gaps:** {', '.join(fit.missing) or '-'}", ""]
    return "\n".join(out)
