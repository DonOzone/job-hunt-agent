from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
 profile TEXT NOT NULL, cv_text TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS sessions (
 digest TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS items (
 owner TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, kind TEXT NOT NULL,
 id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 PRIMARY KEY(owner,kind,id)
);
CREATE INDEX IF NOT EXISTS items_owner_kind ON items(owner,kind);
CREATE TABLE IF NOT EXISTS limits (bucket TEXT NOT NULL, ts TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS limits_bucket ON limits(bucket,ts);
CREATE TABLE IF NOT EXISTS source_cache (key TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.directory = directory
        self.path = directory / "app.db"
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
        finally:
            db.close()

    def items(self, owner: str, kind: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM items WHERE owner=? AND kind=? ORDER BY created_at DESC", (owner, kind)
            ).fetchall()
        return [
            json.loads(r["payload"]) | {"id": r["id"], "created_at": r["created_at"], "updated_at": r["updated_at"]}
            for r in rows
        ]

    def item(self, owner: str, kind: str, item_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT * FROM items WHERE owner=? AND kind=? AND id=?", (owner, kind, item_id)).fetchone()
        if row is None:
            raise KeyError("Record not found")
        return json.loads(row["payload"]) | {
            "id": row["id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def put(self, owner: str, kind: str, payload: dict, item_id: str | None = None) -> dict:
        item_id = item_id or uuid4().hex
        text = json.dumps({k: v for k, v in payload.items() if k not in ("id", "created_at", "updated_at")})
        with self.connect() as db:
            db.execute(
                "INSERT INTO items VALUES (?,?,?,?,?,?) ON CONFLICT(owner,kind,id) "
                "DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at",
                (owner, kind, item_id, text, now(), now()),
            )
            db.commit()
        return self.item(owner, kind, item_id)

    def delete(self, owner: str, kind: str, item_id: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM items WHERE owner=? AND kind=? AND id=?", (owner, kind, item_id))
            db.commit()

    def allow(self, bucket: str, maximum: int, seconds: int) -> bool:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat(timespec="seconds")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "DELETE FROM limits WHERE ts<?",
                ((datetime.now(timezone.utc) - timedelta(days=2)).isoformat(timespec="seconds"),),
            )
            count = db.execute("SELECT COUNT(*) FROM limits WHERE bucket=? AND ts>=?", (bucket, cutoff)).fetchone()[0]
            if count >= maximum:
                return False
            db.execute("INSERT INTO limits VALUES (?,?)", (bucket, now()))
            db.commit()
        return True

    def claim(self) -> tuple[str, dict] | None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cutoff = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(timespec="seconds")
            db.execute(
                "UPDATE items SET payload=json_set(payload,'$.status','failed','$.error',"
                "'Worker interrupted or timed out; retry explicitly'), updated_at=? "
                "WHERE kind='run' AND json_extract(payload,'$.status')='running' AND updated_at<?",
                (now(), cutoff),
            )
            row = db.execute(
                "SELECT owner,id,payload FROM items WHERE kind='run' "
                "AND json_extract(payload,'$.status')='queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is None:
                db.commit()
                return None
            payload = json.loads(row["payload"]) | {"status": "running"}
            db.execute(
                "UPDATE items SET payload=?,updated_at=? WHERE owner=? AND kind='run' AND id=?",
                (json.dumps(payload), now(), row["owner"], row["id"]),
            )
            db.commit()
        return row["owner"], payload | {"id": row["id"]}
