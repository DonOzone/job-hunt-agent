from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet

from ..enrich import enrich
from ..matcher import filter_jobs
from ..models import Job
from ..opportunities import select
from ..sources import SOURCES, dedupe
from . import ai, services
from .db import Database, now

log = logging.getLogger(__name__)


def source_jobs(db: Database, site: dict) -> list[Job]:
    key = json.dumps(site, sort_keys=True)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
    with db.connect() as conn:
        row = conn.execute("SELECT payload FROM source_cache WHERE key=? AND updated_at>?", (key, cutoff)).fetchone()
    if row:
        return [Job.from_dict(j) for j in json.loads(row["payload"])]
    options = {k: v for k, v in site.items() if v}
    if options["type"] == "remotive":
        options["limit"] = 100
    found = [enrich(j) for j in SOURCES[options["type"]](options)][:1500]
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO source_cache VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET "
            "payload=excluded.payload,updated_at=excluded.updated_at",
            (key, json.dumps([j.to_dict() for j in found]), now()),
        )
        conn.commit()
    return found


def execute(db: Database, encryption: Fernet, owner: str, run: dict) -> None:
    try:
        inputs = run["inputs"]
        if run["kind"] == "search":
            found, errors = [], []
            for site in inputs["sites"]:
                try:
                    found.extend(source_jobs(db, site))
                except Exception:
                    log.exception("Official source %s failed", site["type"])
                    errors.append(f"{site['type']} {site.get('company', '')} failed")
            if errors and not found:
                raise RuntimeError("All requested sources failed. " + "; ".join(errors))
            data = services.profile(db, owner)
            found = filter_jobs(dedupe(found), services.domain_profile(data).requirement)
            found = select(found, inputs["kind"])
            for job in found:
                db.put(owner, "opportunity", job.to_dict(), job.id)
            result = (
                f"Saved {len(found)} matching opportunities. Remote labels and keyword scores need manual verification."
            )
            if errors:
                result += "\nPartial results: " + "; ".join(errors)
            status = "partial" if errors else "completed"
        elif run["kind"] == "ai":
            connection = db.item(owner, "ai", "connection")
            if connection["key"] != inputs["connection_key"]:
                raise RuntimeError("AI connection changed after approval; preview and submit again")
            key = encryption.decrypt(connection["key"].encode()).decode()
            result = ai.generate(inputs["provider"], inputs["model"], key, inputs["prompt"])
            status = "completed"
        else:
            raise ValueError("Unsupported task kind")
        db.put(owner, "run", run | {"status": status, "result": result, "error": ""}, run["id"])
    except Exception as exc:
        log.exception("Background %s task failed", run["kind"])
        db.put(owner, "run", run | {"status": "failed", "result": "", "error": str(exc)[:400]}, run["id"])


def work(db: Database, encryption: Fernet, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            claimed = db.claim()
            if claimed:
                execute(db, encryption, *claimed)
            else:
                stop.wait(1)
        except Exception:
            log.exception("Worker could not claim a task")
            stop.wait(5)
