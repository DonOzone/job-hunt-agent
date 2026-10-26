"""SQLite application tracker with a timestamped event history."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import workspace_dir
from .models import Job

PENDING = {"saved", "applying", "applied"}
PASSED = {"screening", "assessment", "interview", "final", "offer", "accepted"}
FAILED = {"rejected", "failed", "ghosted", "withdrawn", "declined"}
STATUSES = PENDING | PASSED | FAILED | {"skipped"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT UNIQUE, title TEXT, company TEXT, url TEXT, source TEXT,
    status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    next_action TEXT, next_action_due TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id INTEGER NOT NULL REFERENCES applications(id),
    ts TEXT NOT NULL, status TEXT NOT NULL, note TEXT
);
CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill TEXT NOT NULL, score REAL NOT NULL, method TEXT NOT NULL, ts TEXT NOT NULL, detail TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def outcome(status: str) -> str:
    if status in PASSED:
        return "passed"
    if status in FAILED:
        return "failed"
    return "pending"


class Tracker:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else workspace_dir() / "tracker.db"
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    # --- applications -------------------------------------------------------
    def add(self, job: Job, status: str = "saved", note: str = "") -> int:
        row = self.db.execute("SELECT id FROM applications WHERE job_id=?", (job.id,)).fetchone()
        if row:
            return row["id"]
        ts = now()
        cur = self.db.execute(
            "INSERT INTO applications(job_id,title,company,url,source,status,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (job.id, job.title, job.company, job.url, job.source, status, ts, ts))
        self.db.execute("INSERT INTO events(app_id,ts,status,note) VALUES(?,?,?,?)",
                        (cur.lastrowid, ts, status, note or "added"))
        self.db.commit()
        return int(cur.lastrowid)

    def update(self, app_id: int, status: str, note: str = "", next_action: str | None = None,
               due_in_days: int | None = None) -> None:
        if status not in STATUSES:
            raise ValueError(f"Unknown status {status!r}. Use one of: {', '.join(sorted(STATUSES))}")
        ts = now()
        due = (datetime.now(timezone.utc) + timedelta(days=due_in_days)).date().isoformat() if due_in_days else None
        with self.db:
            n = self.db.execute(
                "UPDATE applications SET status=?, updated_at=?, next_action=COALESCE(?,next_action),"
                " next_action_due=COALESCE(?,next_action_due) WHERE id=?",
                (status, ts, next_action, due, app_id)).rowcount
            if not n:
                raise KeyError(f"Application {app_id} not found")
            self.db.execute("INSERT INTO events(app_id,ts,status,note) VALUES(?,?,?,?)", (app_id, ts, status, note))

    def get(self, app_id: int) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()

    def by_job(self, job_id: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM applications WHERE job_id=?", (job_id,)).fetchone()

    def list(self, status: str | None = None) -> list[sqlite3.Row]:
        if status in ("passed", "failed", "pending"):
            group = {"passed": PASSED, "failed": FAILED, "pending": PENDING}[status]
            q = f"SELECT * FROM applications WHERE status IN ({','.join('?' * len(group))}) ORDER BY updated_at DESC"
            return self.db.execute(q, tuple(group)).fetchall()
        if status:
            return self.db.execute("SELECT * FROM applications WHERE status=? ORDER BY updated_at DESC",
                                   (status,)).fetchall()
        return self.db.execute("SELECT * FROM applications ORDER BY updated_at DESC").fetchall()

    def history(self, app_id: int) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM events WHERE app_id=? ORDER BY id", (app_id,)).fetchall()

    def stale(self, days: int = 7) -> list[sqlite3.Row]:
        """Applications sitting in 'applied' (or a passed stage) with no update for N days -> follow up."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        active = tuple(({"applied"} | PASSED) - {"accepted"})
        q = f"SELECT * FROM applications WHERE status IN ({','.join('?' * len(active))}) AND updated_at < ?"
        return self.db.execute(q, (*active, cutoff)).fetchall()

    def summary(self) -> dict:
        rows = self.list()
        counts = {"total": len(rows), "passed": 0, "failed": 0, "pending": 0}
        by_status: dict[str, int] = {}
        for r in rows:
            by_status[r["status"]] = by_status.get(r["status"], 0) + 1
            if r["status"] != "skipped":
                counts[outcome(r["status"])] += 1
        submitted = sum(v for k, v in by_status.items() if k not in ("saved", "applying", "skipped"))
        counts["by_status"] = by_status
        counts["submitted"] = submitted
        counts["response_rate"] = round(counts["passed"] / submitted, 2) if submitted else 0.0
        counts["interview_rate"] = round(
            sum(by_status.get(s, 0) for s in ("interview", "final", "offer", "accepted")) / submitted, 2
        ) if submitted else 0.0
        return counts

    # --- assessments --------------------------------------------------------
    def record_assessment(self, skill: str, score: float, method: str, detail: str = "") -> None:
        with self.db:
            self.db.execute("INSERT INTO assessments(skill,score,method,ts,detail) VALUES(?,?,?,?,?)",
                            (skill, score, method, now(), detail))

    def proficiency(self) -> dict[str, float]:
        rows = self.db.execute("SELECT skill, score FROM assessments ORDER BY id").fetchall()
        return {r["skill"]: r["score"] for r in rows}  # latest wins

    # --- reporting ----------------------------------------------------------
    def report_markdown(self) -> str:
        s = self.summary()
        lines = [f"# Application report ({now()})", "",
                 f"- Total: **{s['total']}** | Submitted: **{s['submitted']}**",
                 f"- Passed a stage: **{s['passed']}** | Failed: **{s['failed']}** | Pending: **{s['pending']}**",
                 f"- Response rate: **{s['response_rate']:.0%}** | Interview rate: **{s['interview_rate']:.0%}**", ""]
        for title, group in (("✅ Passed", PASSED), ("❌ Failed", FAILED), ("⏳ Pending", PENDING)):
            rows = [r for r in self.list() if r["status"] in group]
            lines += [f"## {title} ({len(rows)})", ""]
            for r in rows:
                lines.append(f"### #{r['id']} {r['title']} @ {r['company']} — `{r['status']}`")
                if r["next_action"]:
                    lines.append(f"Next: {r['next_action']} (due {r['next_action_due'] or 'n/a'})")
                lines += [f"- `{e['ts']}` **{e['status']}** {e['note'] or ''}" for e in self.history(r["id"])]
                lines.append("")
        return "\n".join(lines)


def open_tracker() -> closing[Tracker]:
    return closing(Tracker())
