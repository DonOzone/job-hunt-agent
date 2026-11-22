from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import tempfile
import threading
from contextlib import asynccontextmanager
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .. import gaps
from ..cv import read_cv, taxonomy
from ..enrich import enrich, strip_html
from ..guard import check
from ..models import Job
from ..tracker import STATUSES
from . import ai, auth, services
from .db import Database

log = logging.getLogger(__name__)
User = Annotated[dict, Depends(auth.current_user)]
Kind = Literal["all", "job", "project"]


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            await self.app(scope, receive, send)
            return
        messages: list[Message] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > 4 * 1024 * 1024:
                await JSONResponse({"detail": "Request must be at most 4 MB"}, status_code=413)(scope, receive, send)
                return
            messages.append(message)
            if not message.get("more_body", False):
                break
        iterator = iter(messages)

        async def replay() -> Message:
            message = next(iterator, None)
            return message if message is not None else await receive()

        await self.app(scope, replay, send)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AuthInput(Input):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=12, max_length=1024)

    @field_validator("email")
    @classmethod
    def lower_email(cls, value: str) -> str:
        return value.lower()


class ProfileInput(Input):
    name: str = Field(default="", max_length=200)
    location: str = Field(default="", max_length=200)
    home_country: str = Field(default="", max_length=100)
    work_authorization: list[str] = Field(default_factory=list, max_length=30)
    roles: list[str] = Field(default_factory=list, max_length=30)
    prefer_remote: bool = True
    cv_text: str = Field(default="", max_length=200000)

    @field_validator("roles", "work_authorization")
    @classmethod
    def short_values(cls, values: list[str]) -> list[str]:
        if any(len(v) > 100 for v in values):
            raise ValueError("Each value must be at most 100 characters")
        return values


class OpportunityInput(Input):
    title: str = Field(min_length=1, max_length=250)
    company: str = Field(min_length=1, max_length=200)
    url: str = Field(default="", max_length=2000)
    location: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=40000)
    remote: bool = False
    opportunity_type: Literal["job", "project"] = "job"
    duration: str = Field(default="", max_length=100)

    @field_validator("url")
    @classmethod
    def safe_url(cls, value: str) -> str:
        if value and (
            urlsplit(value).scheme not in ("http", "https")
            or not urlsplit(value).hostname
            or urlsplit(value).username
            or urlsplit(value).password
        ):
            raise ValueError("Use an HTTP(S) posting link without credentials")
        return value


class SiteInput(Input):
    type: Literal["ashby", "greenhouse", "lever", "remoteok", "remotive"]
    company: str = Field(default="", max_length=80, pattern=r"^[a-zA-Z0-9_-]*$")
    name: str = Field(default="", max_length=200)


class SearchInput(Input):
    sites: list[SiteInput] = Field(min_length=1, max_length=3)
    kind: Kind = "all"


class ApplicationInput(Input):
    opportunity_id: str = Field(max_length=64)


class ApplicationUpdate(Input):
    status: str
    next_action: str = Field(default="", max_length=2000)

    @field_validator("status")
    @classmethod
    def known_status(cls, value: str) -> str:
        if value not in STATUSES:
            raise ValueError("Unknown application status")
        return value


class FeedbackInput(Input):
    application_id: str = Field(max_length=64)
    subject: str = Field(default="", max_length=300)
    body: str = Field(min_length=1, max_length=20000)


class LearningInput(Input):
    skill: str = Field(min_length=1, max_length=80)


class LearningUpdate(Input):
    status: Literal["planned", "learning", "completed"]
    hours: float = Field(default=0, ge=0, le=100000)
    evidence: str = Field(default="", max_length=5000)


class CardsInput(LearningInput):
    opportunity_id: str | None = Field(default=None, max_length=64)


class AnswerInput(Input):
    answer: str = Field(min_length=1, max_length=20)


class TaskInput(Input):
    feedback_id: str = Field(max_length=64)
    title: str = Field(default="Review received response with my authorized LLM", max_length=250)


class TaskUpdate(Input):
    result: str = Field(default="", max_length=20000)
    status: Literal["pending", "completed"] = "completed"


class AiInput(Input):
    provider: Literal["openai", "anthropic", "gemini"]
    model: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.:-]+$")
    api_key: str = Field(min_length=1, max_length=1000, pattern=r"^[\x21-\x7e]+$")


class GenerateInput(Input):
    kind: Literal["match", "draft", "feedback", "study"]
    opportunity_id: str | None = Field(default=None, max_length=64)
    feedback_id: str | None = Field(default=None, max_length=64)
    skill: str = Field(default="", max_length=80)
    consent: bool
    preview_digest: str = ""


def public_run(run: dict) -> dict:
    return {k: run[k] for k in ("id", "kind", "status", "result", "error", "created_at")}


def preview_digest(prompt: str, settings: dict) -> str:
    approved = {"prompt": prompt, **{k: settings[k] for k in ("provider", "model", "key")}}
    return hashlib.sha256(json.dumps(approved, sort_keys=True).encode()).hexdigest()


def ai_prompt(
    db: Database, owner: str, kind: str, opportunity_id: str | None, feedback_id: str | None, skill: str
) -> str:
    if kind == "study":
        if not skill.strip():
            raise HTTPException(400, "Choose a study topic")
        return f"Suggest reviewable study cards with answer explanations and verification sources for {skill}."
    if kind == "feedback":
        if not feedback_id:
            raise HTTPException(400, "Choose received feedback")
        feedback = db.item(owner, "feedback", feedback_id)
        application = db.item(owner, "application", feedback["application_id"])
        opportunity_id = application["opportunity_id"]
        received = feedback["subject"] + "\n" + feedback["body"]
    else:
        received = ""
    if not opportunity_id:
        raise HTTPException(400, "Choose an opportunity")
    job = db.item(owner, "opportunity", opportunity_id)
    if kind == "draft":
        services.ensure_drafting_allowed(Job.from_dict(job))
    data = services.profile(db, owner)
    return json.dumps(
        {
            "request": kind,
            "instructions": ai.SYSTEM,
            "posting_data": {
                "title": job["title"],
                "company": job["company"],
                "description": job["description"][:12000],
            },
            "confirmed_profile": {k: data[k] for k in ("location", "home_country", "work_authorization")},
            "cv_excerpt": data["cv_text"][:16000],
            "received_feedback": received[:20000],
        },
        ensure_ascii=False,
    )


def create_app(data_dir: str | Path | None = None, start_worker: bool = True) -> FastAPI:
    directory = Path(data_dir or os.environ.get("JOBHUNT_WEB_HOME", "workspace/web"))
    db = Database(directory)
    encryption = ai.cipher(directory)
    origins = [
        v.strip()
        for v in os.environ.get(
            "JOBHUNT_WEB_ORIGINS",
            "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:5174,http://localhost:5174",
        ).split(",")
        if v.strip()
    ]
    if "*" in origins:
        raise ValueError("Use exact JOBHUNT_WEB_ORIGINS, not a wildcard")
    stop = threading.Event()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from .worker import work

        thread = threading.Thread(target=work, args=(db, encryption, stop), daemon=True)
        if start_worker:
            thread.start()
        try:
            yield
        finally:
            stop.set()
            if start_worker:
                thread.join(timeout=2)

    app = FastAPI(title="Job Hunt", lifespan=lifespan)
    app.state.db, app.state.encryption, app.state.origins = db, encryption, origins
    hosts = {"localhost", "127.0.0.1", "testserver"}
    hosts.update(urlsplit(o).hostname for o in origins if urlsplit(o).hostname)
    hosts.update(h.strip() for h in os.environ.get("JOBHUNT_WEB_HOSTS", "").split(",") if h.strip())
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=sorted(hosts))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )
    app.add_middleware(BodyLimitMiddleware)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        length = request.headers.get("content-length", "0")
        if not length.isdigit() or int(length) > 4 * 1024 * 1024:
            return JSONResponse({"detail": "Request is too large or has invalid length"}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self' https: http://localhost:* http://127.0.0.1:*; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.exception_handler(KeyError)
    async def missing(request: Request, exc: KeyError):
        return JSONResponse({"detail": "Record not found"}, status_code=404)

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError):
        message = "; ".join(".".join(str(v) for v in e["loc"]) + ": " + e["msg"] for e in exc.errors())
        return JSONResponse({"detail": message}, status_code=422)

    @app.exception_handler(services.DraftingRestricted)
    async def restricted_draft(request: Request, exc: services.DraftingRestricted):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.get("/api/health")
    def health():
        with db.connect() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "ok"}

    def signed_in(response: Response, user: dict) -> dict:
        token = auth.session(db, user["id"])
        response.set_cookie(
            "jobhunt_session",
            token,
            httponly=True,
            samesite="lax",
            max_age=604800,
            secure=os.environ.get("JOBHUNT_WEB_SECURE_COOKIES") == "1",
        )
        return {"user": user, "token": token}

    def auth_limit(request: Request):
        auth.check_origin(request)
        host = request.client.host if request.client else "unknown"
        if not db.allow("auth:" + host, 30, 3600):
            raise HTTPException(429, "Too many authentication attempts; try again later")

    @app.post("/api/auth/register")
    def register(body: AuthInput, request: Request, response: Response):
        auth_limit(request)
        try:
            user = auth.create_user(db, body.email, body.password)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Email is already registered") from None
        return signed_in(response, user)

    @app.post("/api/auth/login")
    def login(body: AuthInput, request: Request, response: Response):
        auth_limit(request)
        return signed_in(response, auth.login(db, body.email, body.password))

    @app.get("/api/auth/me")
    def me(user: User):
        return user

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response, user: User):
        with db.connect() as conn:
            conn.execute(
                "DELETE FROM sessions WHERE digest=? AND owner=?",
                (auth.digest(auth.request_token(request)), user["id"]),
            )
            conn.commit()
        response.delete_cookie("jobhunt_session")
        return {"status": "signed_out"}

    @app.get("/api/profile")
    def get_profile(user: User):
        return services.profile(db, user["id"])

    @app.put("/api/profile")
    def put_profile(body: ProfileInput, user: User):
        data = body.model_dump()
        cv_text = data.pop("cv_text")
        with db.connect() as conn:
            conn.execute("UPDATE users SET profile=?,cv_text=? WHERE id=?", (json.dumps(data), cv_text, user["id"]))
            conn.commit()
        db.put(user["id"], "cv_version", {"text": cv_text})
        return services.profile(db, user["id"])

    async def read_upload(file: UploadFile) -> bytes:
        content = await file.read(2 * 1024 * 1024 + 1)
        if len(content) > 2 * 1024 * 1024:
            raise HTTPException(413, "Upload must be at most 2 MB")
        return content

    @app.post("/api/cv")
    async def import_cv(user: User, file: Annotated[UploadFile, File()]):
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in (".txt", ".md", ".pdf", ".docx"):
            raise HTTPException(400, "Upload TXT, Markdown, PDF or unprotected DOCX")
        content = await read_upload(file)
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            path = Path(temporary) / ("cv" + suffix)
            path.write_bytes(content)
            try:
                text = read_cv(path)
            except ImportError:
                raise HTTPException(400, "PDF support is not installed; install the docs extra") from None
            except Exception:
                log.warning("CV parsing failed for %s", suffix, exc_info=True)
                raise HTTPException(
                    400, "Could not read this CV; protected documents need an authorized export"
                ) from None
        if not text.strip() or len(text) > 200000:
            raise HTTPException(400, "CV must contain readable text of at most 200,000 characters")
        data = services.profile(db, user["id"]) | {"cv_text": text}
        return put_profile(ProfileInput(**data), user)

    @app.get("/api/dashboard")
    def dashboard(user: User):
        return services.dashboard(db, user["id"])

    @app.get("/api/opportunities")
    def opportunities(user: User, kind: Kind = "all"):
        return [j for j in services.ranked(db, user["id"]) if kind == "all" or j["opportunity_type"] == kind]

    @app.post("/api/opportunities")
    def add_opportunity(body: OpportunityInput, user: User):
        result = check(body.description, body.url, body.company)
        job = enrich(Job(**(body.model_dump() | {"description": result.cleaned}), source="manual"))
        return db.put(user["id"], "opportunity", job.to_dict(), job.id)

    @app.get("/api/opportunities/{job_id}/match")
    def match(job_id: str, user: User):
        return services.match(db, user["id"], job_id)

    @app.get("/api/gaps")
    def gap_report(user: User):
        return services.gap_report(db, user["id"])

    def queue(owner: str, kind: str, inputs: dict) -> dict:
        active = [r for r in db.items(owner, "run") if r["status"] in ("queued", "running")]
        if len(active) >= 3:
            raise HTTPException(429, "Finish existing tasks before starting another")
        return public_run(
            db.put(owner, "run", {"kind": kind, "status": "queued", "inputs": inputs, "result": "", "error": ""})
        )

    @app.post("/api/search")
    def search(body: SearchInput, user: User):
        if any(s.type in ("ashby", "lever", "greenhouse") and not s.company for s in body.sites):
            raise HTTPException(400, "An official board identifier is required")
        if not db.allow(user["id"] + ":search", 6, 86400):
            raise HTTPException(429, "Daily search limit reached; public feeds are shared and cached")
        return queue(user["id"], "search", body.model_dump())

    @app.get("/api/runs")
    def runs(user: User):
        return [public_run(r) for r in db.items(user["id"], "run")]

    @app.get("/api/applications")
    def applications(user: User):
        return db.items(user["id"], "application")

    @app.post("/api/applications")
    def create_application(body: ApplicationInput, user: User):
        job = db.item(user["id"], "opportunity", body.opportunity_id)
        for item in db.items(user["id"], "application"):
            if item["opportunity_id"] == job["id"]:
                return item
        return db.put(
            user["id"],
            "application",
            {
                "opportunity_id": job["id"],
                "title": job["title"],
                "company": job["company"],
                "opportunity_type": job["opportunity_type"],
                "status": "saved",
                "next_action": "",
            },
        )

    @app.patch("/api/applications/{item_id}")
    def update_application(item_id: str, body: ApplicationUpdate, user: User):
        existing = db.item(user["id"], "application", item_id)
        updated = db.put(user["id"], "application", existing | body.model_dump(), item_id)
        db.put(user["id"], "application_event", {"application_id": item_id, **body.model_dump()})
        return updated

    @app.get("/api/applications/{item_id}/draft")
    def application_draft(item_id: str, user: User):
        return services.draft(db, user["id"], item_id)

    @app.get("/api/feedback")
    def feedback(user: User):
        return db.items(user["id"], "feedback")

    @app.post("/api/feedback")
    def add_feedback(body: FeedbackInput, user: User):
        db.item(user["id"], "application", body.application_id)
        return db.put(user["id"], "feedback", body.model_dump() | {"analysis": ""})

    @app.post("/api/feedback/import")
    async def import_feedback(user: User, application_id: Annotated[str, Form()], file: Annotated[UploadFile, File()]):
        db.item(user["id"], "application", application_id)
        content = await read_upload(file)
        if Path(file.filename or "").suffix.lower() == ".eml":
            message = BytesParser(policy=policy.default).parsebytes(content)
            part = message.get_body(preferencelist=("plain", "html"))
            text = part.get_content() if part else ""
            if not isinstance(text, str):
                raise HTTPException(400, "Email contains no readable body")
            if part and part.get_content_type() == "text/html":
                text = strip_html(text)
            subject = str(message.get("subject", ""))[:300]
        elif Path(file.filename or "").suffix.lower() == ".txt":
            text, subject = content.decode("utf-8", errors="replace"), file.filename or ""
        else:
            raise HTTPException(400, "Import an EML or TXT file; no mailbox access is performed")
        return add_feedback(FeedbackInput(application_id=application_id, subject=subject, body=text[:20000]), user)

    @app.get("/api/skills")
    def skills(user: User):
        return sorted(taxonomy())

    @app.get("/api/learning")
    def learning(user: User):
        return db.items(user["id"], "learning")

    @app.post("/api/learning")
    def add_learning(body: LearningInput, user: User):
        for item in db.items(user["id"], "learning"):
            if item["skill"] == body.skill:
                return item
        return db.put(
            user["id"],
            "learning",
            {
                "skill": body.skill,
                "status": "planned",
                "hours": 0,
                "evidence": "",
                "resources": gaps.course_links(body.skill),
            },
        )

    @app.patch("/api/learning/{item_id}")
    def update_learning(item_id: str, body: LearningUpdate, user: User):
        existing = db.item(user["id"], "learning", item_id)
        return db.put(user["id"], "learning", existing | body.model_dump(), item_id)

    def public_card(card: dict) -> dict:
        return {k: card[k] for k in ("id", "topic", "kind", "front", "options")}

    @app.get("/api/cards")
    def cards(user: User):
        return [public_card(c) for c in db.items(user["id"], "card")]

    @app.post("/api/cards")
    def create_cards(body: CardsInput, user: User):
        if body.opportunity_id:
            db.item(user["id"], "opportunity", body.opportunity_id)
        existing = {c["front"]: c for c in db.items(user["id"], "card") if c["topic"] == body.skill}
        result = []
        for card in services.make_cards(body.skill):
            saved = existing.get(card["front"]) or db.put(user["id"], "card", card)
            result.append(public_card(saved))
        return result

    @app.post("/api/cards/{item_id}/reveal")
    def reveal_card(item_id: str, user: User):
        return {"back": db.item(user["id"], "card", item_id)["back"]}

    @app.post("/api/cards/{item_id}/answer")
    def answer_card(item_id: str, body: AnswerInput, user: User):
        card = db.item(user["id"], "card", item_id)
        answer = body.answer.strip().lower()
        if card["answer"] is not None and answer not in [chr(97 + i) for i in range(len(card["options"]))]:
            raise HTTPException(400, "Choose an available answer")
        if card["answer"] is None and answer not in ("know", "dont-know"):
            raise HTTPException(400, "Use know or dont-know for a self-rating")
        correct = answer == card["answer"] if card["answer"] is not None else None
        db.put(
            user["id"], "attempt", {"card_id": item_id, "topic": card["topic"], "answer": answer, "correct": correct}
        )
        return {"correct": correct, "back": card["back"]}

    @app.get("/api/tasks")
    def tasks(user: User):
        return db.items(user["id"], "task")

    @app.post("/api/tasks")
    def create_task(body: TaskInput, user: User):
        feedback = db.item(user["id"], "feedback", body.feedback_id)
        application = db.item(user["id"], "application", feedback["application_id"])
        prompt = ai.SYSTEM + "\n\nReview only this received response. Summarize facts, uncertainties and proposed "
        prompt += "next steps. Do not read other emails, send a reply or change status. Ask the user before acting.\n"
        prompt += json.dumps(
            {
                "role": application["title"],
                "company": application["company"],
                "untrusted_received_response": {"subject": feedback["subject"], "body": feedback["body"]},
            },
            ensure_ascii=False,
        )
        return db.put(
            user["id"],
            "task",
            {"title": body.title, "feedback_id": body.feedback_id, "prompt": prompt, "status": "pending", "result": ""},
        )

    @app.patch("/api/tasks/{item_id}")
    def update_task(item_id: str, body: TaskUpdate, user: User):
        task = db.item(user["id"], "task", item_id)
        if body.status == "completed" and not body.result.strip():
            raise HTTPException(400, "Paste the reviewed result before completing this handoff")
        task = db.put(user["id"], "task", task | body.model_dump(), item_id)
        if body.status == "completed":
            received = db.item(user["id"], "feedback", task["feedback_id"])
            db.put(user["id"], "feedback", received | {"analysis": body.result}, received["id"])
        return task

    @app.get("/api/ai")
    def get_ai(user: User):
        settings = db.items(user["id"], "ai")
        return {
            "provider": settings[0]["provider"] if settings else "",
            "model": settings[0]["model"] if settings else "",
            "configured": bool(settings),
        }

    @app.put("/api/ai")
    def put_ai(body: AiInput, user: User):
        db.put(
            user["id"],
            "ai",
            {"provider": body.provider, "model": body.model, "key": encryption.encrypt(body.api_key.encode()).decode()},
            "connection",
        )
        return get_ai(user)

    @app.delete("/api/ai")
    def delete_ai(user: User):
        db.delete(user["id"], "ai", "connection")
        return get_ai(user)

    @app.get("/api/ai/preview")
    def preview_ai(
        user: User,
        kind: Literal["match", "draft", "feedback", "study"],
        opportunity_id: str | None = None,
        feedback_id: str | None = None,
        skill: str = "",
    ):
        try:
            settings = db.item(user["id"], "ai", "connection")
        except KeyError:
            raise HTTPException(400, "Connect an API provider, or use the manual logged-in LLM handoff") from None
        prompt = ai_prompt(db, user["id"], kind, opportunity_id, feedback_id, skill)
        return {
            "provider": settings["provider"],
            "model": settings["model"],
            "configured": True,
            "prompt": prompt,
            "preview_digest": preview_digest(prompt, settings),
            "notice": "Only the displayed data is sent. CV/posting excerpts may be truncated. "
            "This uses API billing, not subscription login, and returns a draft only.",
        }

    @app.post("/api/ai/generate")
    def generate_ai(body: GenerateInput, user: User):
        preview = preview_ai(user, body.kind, body.opportunity_id, body.feedback_id, body.skill)
        if not body.consent or body.preview_digest != preview["preview_digest"]:
            raise HTTPException(400, "Preview the current data and explicitly approve it before sending")
        if not db.allow(user["id"] + ":ai", 10, 86400):
            raise HTTPException(429, "Daily AI request limit reached; basic mode remains available")
        settings = db.item(user["id"], "ai", "connection")
        if preview_digest(preview["prompt"], settings) != body.preview_digest:
            raise HTTPException(400, "AI connection changed; preview and approve the current destination again")
        return queue(
            user["id"],
            "ai",
            {
                "prompt": preview["prompt"],
                "connection_key": settings["key"],
                "provider": settings["provider"],
                "model": settings["model"],
            },
        )

    packaged = Path(__file__).parent / "static"
    source_ui = Path(__file__).resolve().parents[3] / "apps" / "web" / "dist"
    ui = (
        Path(os.environ["JOBHUNT_UI_DIR"])
        if os.environ.get("JOBHUNT_UI_DIR")
        else (packaged if (packaged / "index.html").exists() else source_ui)
    )
    if (ui / "index.html").exists():
        app.mount("/", StaticFiles(directory=ui, html=True), name="ui")
    else:

        @app.get("/")
        def no_ui():
            return {"status": "API ready", "ui": "Run npm install && npm run build to build the UI"}

    return app
