"""Ramp-up plan: turn missing skills into a ranked learning path using your own list plus open materials."""
from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from math import ceil
from pathlib import Path
from urllib.parse import quote_plus

from .config import load_data, load_yaml, personal_dir
from .cv import taxonomy
from .gaps import Gap

URL_RE = re.compile(r"https?://\S+")


@dataclass
class Resource:
    skill: str
    name: str
    url: str = ""
    kind: str = "course"
    free: bool | None = None
    hours: float | None = None
    provider: str = ""
    note: str = ""
    origin: str = "open"  # yours | curated | open


@dataclass
class Step:
    skill: str
    category: str
    importance: float
    jobs: int
    resources: list[Resource] = field(default_factory=list)
    practice: str = ""
    hours: float = 0.0


def _canon(skill: str) -> str:
    """Match a user-typed skill to the taxonomy spelling (case-insensitive), else keep it as typed."""
    low = skill.strip().lower()
    for known in taxonomy():
        if known.lower() == low:
            return known
    return skill.strip()


def _to_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        hours = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Learning resource hours must be numeric, got {value!r}") from exc
    if not math.isfinite(hours) or hours <= 0:
        raise ValueError("Learning resource hours must be positive and finite")
    return hours


def _from_row(row: dict) -> Resource:
    skill = str(row.get("skill") or "").strip()
    name = str(row.get("name") or row.get("title") or "").strip()
    url = str(row.get("url") or row.get("link") or "").strip()
    if not skill or not (name or url):
        raise ValueError("Each learning resource needs a skill and a name/title or URL")
    kind = str(row.get("kind") or row.get("type") or "course").strip().lower()
    free = row.get("free")
    if isinstance(free, str):
        value = free.strip().lower()
        if value not in ("1", "true", "yes", "free", "0", "false", "no", "paid"):
            raise ValueError("Learning resource free must be true or false")
        free = value in ("1", "true", "yes", "free")
    elif free is not None and not isinstance(free, bool):
        raise ValueError("Learning resource free must be true or false")
    return Resource(skill=_canon(skill), name=name or url, url=url, kind=kind, free=free,
                    hours=_to_float(row.get("hours")), provider=str(row.get("provider") or ""),
                    note=str(row.get("note") or ""), origin="yours")


def _from_text(text: str) -> list[Resource]:
    """`Skill | Title | URL | hours` lines (markdown bullets, tables and CSV also work). `#` lines are ignored."""
    out: list[Resource] = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("-*• ").strip()
        if not line or line.startswith("#") or set(line) <= set("|-: "):
            continue
        if "|" in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
        else:
            cells = next(csv.reader(io.StringIO(line)))
        cells = [c.strip() for c in cells]
        if cells and cells[0].lower() == "skill":
            continue
        url = next((c for c in cells if URL_RE.fullmatch(c)), "")
        # Text format is positional: Skill | Title | URL | optional hours.
        if len(cells) < 2 or len(cells) > 4:
            raise ValueError("Learning list lines must be Skill | Title | URL | optional hours")
        hours = _to_float(cells[3]) if len(cells) == 4 else None
        title = cells[1] if cells[1] != url else ""
        res = _from_row({"skill": cells[0] if cells else "", "name": title, "url": url, "hours": hours})
        out.append(res)
    return out


def load_user_resources(path: str | Path | None = None) -> list[Resource]:
    """Your own list. YAML: a list of {skill, name, url, hours, free}; or `Skill | Title | URL | hours` text/CSV/MD."""
    candidates = [Path(path)] if path else [personal_dir() / f"learning-resources.{ext}"
                                          for ext in ("yaml", "csv", "md")]
    for p in candidates:
        if not p.exists():
            if path:
                raise FileNotFoundError(f"Learning list not found: {p}")
            continue
        if p.suffix.lower() in (".yaml", ".yml"):
            raw = load_yaml(p)
            if isinstance(raw, dict) and raw and "resources" not in raw:
                raise ValueError(f"{p}: expected a 'resources' list")
            rows = raw.get("resources", []) if isinstance(raw, dict) else raw
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError(f"{p}: expected a resources list containing skill/name/URL mappings")
            return [_from_row(row) for row in rows]
        return _from_text(p.read_text(encoding="utf-8"))
    return []


def open_resources(skill: str, free_only: bool = False) -> list[Resource]:
    """Curated courses (courses.yaml) first, then search links on open platforms (no scraping, no accounts)."""
    out = [
        Resource(skill=skill, name=c["name"], url=c["url"], provider=c.get("provider", ""),
                 kind="cert" if c.get("type") == "cert" else "course",
                 free=c.get("type", "").startswith("free") or c.get("type") == "free", origin="curated")
        for c in load_data("courses.yaml").get(skill, [])
    ]
    q = quote_plus(skill)
    for s in load_data("learning_sources.yaml")["sources"]:
        out.append(Resource(skill=skill, name=s["name"], url=s["url"].format(q=q), provider=s.get("provider", ""),
                            kind=s.get("kind", "course"), free=s.get("free"), note=s.get("note", ""), origin="open"))
    return [r for r in out if not (free_only and r.free is False)]


def practice_for(skill: str) -> str:
    cat = taxonomy().get(skill, {}).get("category", "other")
    table = load_data("learning_sources.yaml")["practice_by_category"]
    return table.get(cat, table["other"])


def build(gaps: list[Gap], user: list[Resource], extra_skills: list[str] | None = None, max_skills: int = 5,
          free_only: bool = False, per_skill: int = 6) -> list[Step]:
    """Your resources come first for each skill, then curated, then open sources."""
    steps: list[Step] = []
    seen: set[str] = set()
    for skill in [_canon(s) for s in extra_skills or []]:  # skills you named always lead
        if skill in seen:
            continue
        seen.add(skill)
        steps.append(Step(skill=skill, category=taxonomy().get(skill, {}).get("category", "other"),
                          importance=100.0, jobs=0))
    for g in gaps:
        if g.skill not in seen:
            seen.add(g.skill)
            steps.append(Step(skill=g.skill, category=g.category, importance=g.importance, jobs=g.jobs))
    steps = steps[:max_skills]
    for st in steps:
        mine = [r for r in user if r.skill == st.skill and not (free_only and r.free is False)]
        mine_urls = {r.url for r in mine}
        rest = [r for r in open_resources(st.skill, free_only) if r.url not in mine_urls]
        st.resources = (mine + rest)[: max(per_skill, len(mine))]
        st.practice = practice_for(st.skill)
        st.hours = sum(r.hours for r in mine if r.hours) or (20.0 if st.importance >= 70 else 12.0)
    return steps


def unused_user_skills(user: list[Resource], steps: list[Step]) -> list[str]:
    used = {s.skill for s in steps}
    return sorted({r.skill for r in user} - used)


def render(steps: list[Step], hours_per_week: int = 6, start: date | None = None, user_count: int = 0,
           leftover: list[str] | None = None) -> str:
    if hours_per_week <= 0:
        raise ValueError("hours_per_week must be positive")
    start = start or date.today()
    lines = ["# Ramp-up plan", "",
             f"{hours_per_week} h/week - starts {start.isoformat()} - "
             f"{user_count} resource(s) from your own list" if user_count else
             f"{hours_per_week} h/week - starts {start.isoformat()} - no personal list found "
             "(add one: see `examples/learning-resources.example.yaml`)", "",
             "Rule: only add a skill to your CV once you have used it for real. "
             "Log it with `jobhunt ramp-up log <skill>` and prove it with `jobhunt assess <skill>`.", ""]
    cursor = start
    for i, st in enumerate(steps, 1):
        end = cursor + timedelta(weeks=max(1, ceil(st.hours / hours_per_week))) - timedelta(days=1)
        why = f"asked by {st.jobs} matching job(s), importance {st.importance:.0f}/100" if st.jobs else "added by you"
        lines += [f"## {i}. {st.skill} ({cursor} -> {end}, ~{st.hours:.0f} h)", f"- Why: {why}", "- Learn:"]
        for r in st.resources:
            tags = [t for t in (r.provider, r.kind, "free" if r.free else ("paid" if r.free is False else ""),
                                f"{r.hours:g} h" if r.hours else "", "YOUR LIST" if r.origin == "yours" else "") if t]
            note = f" - {r.note}" if r.note else ""
            link = f"[{r.name}]({r.url})" if r.url else r.name
            lines.append(f"  - {link} ({', '.join(tags)}){note}")
        lines += [f"- Build (public proof): {st.practice}",
                  f"- Check: `jobhunt assess \"{st.skill}\"` on {end} (target >= 65%)",
                  f"- Done? `jobhunt ramp-up log \"{st.skill}\" --hours 10 --note \"what I built\"`", ""]
        cursor = end + timedelta(days=1)
    if leftover:
        lines += ["## In your list but not a current gap", "", ", ".join(leftover), ""]
    return "\n".join(lines)
