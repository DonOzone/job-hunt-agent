"""Order jobs by region -> remote -> relocation -> offered package (then CV match).

Two modes (profile.ranking_mode or `jobhunt rank --mode`):
  strict   - lexicographic: region first, then remote, relocation, package, CV match
  weighted - blended 0-1 score using profile.ranking_weights (unknown values score 0.4, never guessed)
"""
from __future__ import annotations

from collections import OrderedDict

from .config import Profile
from .enrich import salary_usd
from .models import Job

VISA = {True: "✅", False: "❌", None: "?"}
DEFAULT_ORDER = ("region", "remote", "relocation", "salary", "match")


def _region_key(job: Job, profile: Profile) -> int:
    prefs = [r.upper() for r in profile.preferred_regions]
    region = job.region.upper()
    if region in prefs:
        return prefs.index(region)
    if region == "GLOBAL":  # remote-anywhere roles are reachable from any region
        return len(prefs)
    return len(prefs) + (1 if region != "UNKNOWN" else 2)


def no_move_needed(job: Job, profile: Profile) -> bool:
    home = profile.home_country.lower()
    return job.remote or bool(home and home in job.location.lower())


def component_scores(job: Job, profile: Profile, best_salary: float = 0.0) -> dict[str, float]:
    prefs = [r.upper() for r in profile.preferred_regions]
    region = job.region.upper()
    if region in prefs:
        s_region = 1 - prefs.index(region) / max(len(prefs), 1)
    else:
        s_region = 0.5 if region == "GLOBAL" else 0.4 if region == "UNKNOWN" else 0.0
    s_remote = 1.0 if job.remote == profile.prefer_remote else 0.3
    if no_move_needed(job, profile):
        s_reloc = 1.0
    elif job.relocation and profile.open_to_relocation:
        s_reloc = 0.9
    elif job.visa_sponsorship is False or not profile.open_to_relocation:
        s_reloc = 0.0
    else:
        s_reloc = 0.4
    usd = salary_usd(job, profile.fx_to_usd)
    target = profile.target_salary_usd or best_salary
    s_pkg = min(usd / target, 1.0) if usd and target else 0.4
    return {"region": s_region, "remote": s_remote, "relocation": s_reloc, "package": s_pkg,
            "match": job.match_score or 0.0}


def weighted_score(job: Job, profile: Profile, best_salary: float = 0.0) -> float:
    parts = component_scores(job, profile, best_salary)
    weights = profile.ranking_weights
    total = sum(weights.get(k, 0) for k in parts) or 1.0
    return round(sum(parts[k] * weights.get(k, 0) for k in parts) / total, 3)


def sort_key(job: Job, profile: Profile, order: tuple[str, ...] = DEFAULT_ORDER) -> tuple:
    parts = {
        "region": _region_key(job, profile),
        "remote": 0 if job.remote == profile.prefer_remote else 1,
        "relocation": 0 if (no_move_needed(job, profile) or (job.relocation and profile.open_to_relocation)) else 1,
        "salary": -salary_usd(job, profile.fx_to_usd),
        "match": -(job.match_score or 0.0),
    }
    return tuple(parts[o] for o in order)


def rank_jobs(jobs: list[Job], profile: Profile, order: tuple[str, ...] = DEFAULT_ORDER,
              mode: str | None = None) -> list[Job]:
    mode = mode or profile.ranking_mode
    best = max((salary_usd(j, profile.fx_to_usd) for j in jobs), default=0.0)
    for job in jobs:
        job.score = weighted_score(job, profile, best)
    if mode == "weighted":
        ranked = sorted(jobs, key=lambda j: (-(j.score or 0), sort_key(j, profile, order)))
    else:
        ranked = sorted(jobs, key=lambda j: sort_key(j, profile, order))
    for i, job in enumerate(ranked, 1):
        job.rank = i
    return ranked


def group_by_region(jobs: list[Job]) -> OrderedDict[str, list[Job]]:
    groups: OrderedDict[str, list[Job]] = OrderedDict()
    for job in jobs:
        groups.setdefault(job.region, []).append(job)
    return groups


def render_markdown(jobs: list[Job], profile: Profile) -> str:
    how = ("weighted score (" + ", ".join(f"{k} {v:.0%}" for k, v in profile.ranking_weights.items()) + ")"
           if profile.ranking_mode == "weighted" else "region > remote > relocation > package > CV match")
    lines = ["# Ranked jobs", "", f"Order: {how}. 🆕 = first seen in the latest search.", ""]
    for region, items in group_by_region(jobs).items():
        lines += [f"## {region} ({len(items)})", "",
                  "| # | Role | Company | Location | Remote | Relocation | Visa | Package (USD/yr) | CV match "
                  "| Score |",
                  "|---|------|---------|----------|--------|------------|------|------------------|----------|-------|"]
        for j in items:
            pkg = salary_usd(j, profile.fx_to_usd)
            lines.append(
                f"| {j.rank} | {'🆕 ' if j.is_new else ''}[{j.title}]({j.url}) | {j.company} | {j.location or '-'} "
                f"| {'✅' if j.remote else '—'} | {'✅' if j.relocation else '—'} "
                f"| {VISA[j.visa_sponsorship]} | {f'{pkg:,.0f}' if pkg else '-'} "
                f"| {f'{j.match_score:.0%}' if j.match_score is not None else '-'} "
                f"| {f'{j.score:.2f}' if j.score is not None else '-'} |")
        lines.append("")
    return "\n".join(lines)
