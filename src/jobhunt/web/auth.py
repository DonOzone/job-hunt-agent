from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException, Request

from .db import Database, now

DEFAULT_PROFILE = {
    "name": "",
    "location": "",
    "home_country": "",
    "work_authorization": [],
    "roles": [],
    "prefer_remote": True,
}


def password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, maxmem=64 * 1024 * 1024)
    return base64.b64encode(salt).decode() + ":" + base64.b64encode(value).decode()


def password_matches(password: str, encoded: str) -> bool:
    salt = base64.b64decode(encoded.split(":")[0])
    return hmac.compare_digest(password_hash(password, salt), encoded)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def public_user(row) -> dict:
    return {"id": row["id"], "email": row["email"]}


def create_user(db: Database, email: str, password: str) -> dict:
    user_id = uuid4().hex
    encoded = password_hash(password)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO users(id,email,password,profile) VALUES (?,?,?,?)",
            (user_id, email, encoded, json.dumps(DEFAULT_PROFILE)),
        )
        conn.commit()
    return {"id": user_id, "email": email}


def login(db: Database, email: str, password: str) -> dict:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    encoded = row["password"] if row else password_hash("not-an-account-password", b"0" * 16)
    valid = password_matches(password, encoded)
    if row is None or not valid:
        raise HTTPException(401, "Incorrect email or password")
    return public_user(row)


def session(db: Database, owner: str) -> str:
    token = secrets.token_urlsafe(48)
    expires = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(timespec="seconds")
    with db.connect() as conn:
        conn.execute("DELETE FROM sessions WHERE expires<?", (now(),))
        conn.execute("INSERT INTO sessions VALUES (?,?,?)", (digest(token), owner, expires))
        conn.commit()
    return token


def request_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return request.cookies.get("jobhunt_session", "")


def current_user(request: Request) -> dict:
    token = request_token(request)
    with request.app.state.db.connect() as db:
        row = db.execute(
            "SELECT users.id,users.email FROM sessions JOIN users ON users.id=sessions.owner "
            "WHERE digest=? AND expires>?",
            (digest(token), now()),
        ).fetchone()
    if row is None:
        raise HTTPException(401, "Sign in to continue")
    if request.method not in ("GET", "HEAD", "OPTIONS") and not request.headers.get("authorization"):
        check_origin(request, require=True)
    return public_user(row)


def check_origin(request: Request, require: bool = False) -> None:
    origin = request.headers.get("origin")
    own = str(request.base_url).rstrip("/")
    if (require and not origin) or (origin and origin not in request.app.state.origins and origin != own):
        raise HTTPException(403, "This request origin is not allowed")
