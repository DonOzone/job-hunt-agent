"""Long-term memory of jobs YOU added and jobs that have been reviewed.

workspace/memory/my-jobs.json        jobs you added by hand (`jobhunt add`) - kept across searches
workspace/memory/reviewed-jobs.json  one record per reviewed job: fit, gates, decision, notes, generated files
workspace/reviewed-jobs.md           human-readable view (regenerated on every change)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import workspace_dir
from .models import Job
from .tracker import now

DECISIONS = ("new", "shortlist", "preparing", "applied", "skip", "closed")


def _dir() -> Path:
    d = workspace_dir() / "memory"
    d.mkdir(exist_ok=True)
    return d


def _read(name: str, default: Any) -> Any:
    path = _dir() / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write(name: str, data: Any) -> None:
    (_dir() / name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# --------------------------------------------------------------------------- jobs you added
def my_jobs() -> list[Job]:
    return [Job.from_dict(d) for d in _read("my-jobs.json", [])]


def save_my_job(job: Job) -> None:
    jobs = [j for j in my_jobs() if j.id != job.id]
    jobs.append(job)
    _write("my-jobs.json", [j.to_dict() for j in jobs])


# --------------------------------------------------------------------------- reviewed jobs
def records() -> dict[str, dict]:
    return _read("reviewed-jobs.json", {})


def get(job_id: str) -> dict | None:
    return records().get(job_id)


def remember(job: Job, **fields: Any) -> dict:
    """Create/update the memory record for a job. `outputs` and `notes` are merged, not replaced."""
    data = records()
    rec = data.get(job.id) or {"id": job.id, "title": job.title, "company": job.company, "url": job.url,
                               "source": job.source, "first_reviewed": now(), "decision": "new",
                               "notes": [], "outputs": {}, "history": []}
    rec.update(title=job.title, company=job.company, url=job.url, last_reviewed=now())
    note = fields.pop("note", None)
    if note:
        rec["notes"].append({"ts": now(), "text": note})
    rec["outputs"].update(fields.pop("outputs", {}) or {})
    if "decision" in fields and fields["decision"] != rec.get("decision"):
        if fields["decision"] not in DECISIONS:
            raise ValueError(f"decision must be one of {DECISIONS}")
        rec["history"].append({"ts": now(), "decision": fields["decision"]})
    rec.update({k: v for k, v in fields.items() if v is not None})
    data[job.id] = rec
    _write("reviewed-jobs.json", data)
    render_markdown()
    return rec


def skipped_ids() -> set[str]:
    return {k for k, v in records().items() if v.get("decision") in ("skip", "closed")}


def render_markdown() -> Path:
    recs = sorted(records().values(), key=lambda r: r.get("last_reviewed", ""), reverse=True)
    out = ["# Reviewed jobs (memory)", "", f"{len(recs)} jobs reviewed. Updated {now()}.", "",
           "| Job | Company | Source | Fit | Decision | Last reviewed | Notes |", "|---|---|---|---|---|---|---|"]
    for r in recs:
        fit = r.get("fit") or {}
        note = (r["notes"][-1]["text"] if r.get("notes") else "").replace("|", "/")[:60]
        out.append(f"| [{r['title']}]({r.get('url') or '#'}) `{r['id']}` | {r['company']} | {r.get('source', '')} "
                   f"| {fit.get('overall', '-')} | {r.get('decision')} | {r.get('last_reviewed', '')[:16]} | {note} |")
    out += ["", "## Files generated per job", ""]
    for r in recs:
        if r.get("outputs"):
            out.append(f"- **{r['title']} @ {r['company']}**: "
                       + ", ".join(f"[{k}]({v})" for k, v in r["outputs"].items()))
    path = workspace_dir() / "reviewed-jobs.md"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path
