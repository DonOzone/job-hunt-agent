"""Timestamped local journal of progress and learnings (markdown + JSONL)."""
from __future__ import annotations

import json
from pathlib import Path

from .config import workspace_dir
from .tracker import now

KINDS = ("progress", "learning", "feedback", "win", "setback")


def _paths() -> tuple[Path, Path]:
    ws = workspace_dir()
    return ws / "journal.md", ws / "journal.jsonl"


def log(text: str, kind: str = "progress", tags: list[str] | None = None) -> dict:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    entry = {"ts": now(), "kind": kind, "text": text, "tags": tags or []}
    md, jl = _paths()
    if not md.exists():
        md.write_text("# Job hunt journal\n\n", encoding="utf-8")
    with md.open("a", encoding="utf-8") as fh:
        tag_str = f" `{' '.join('#' + t for t in entry['tags'])}`" if entry["tags"] else ""
        fh.write(f"- **{entry['ts']}** [{kind}]{tag_str} {text}\n")
    with jl.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return entry


def entries(kind: str | None = None, limit: int | None = None) -> list[dict]:
    _, jl = _paths()
    if not jl.exists():
        return []
    items = [json.loads(line) for line in jl.read_text(encoding="utf-8").splitlines() if line.strip()]
    if kind:
        items = [e for e in items if e["kind"] == kind]
    return items[-limit:] if limit else items
