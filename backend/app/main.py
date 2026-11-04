from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List
import uuid
import os
import json
import secrets
import sqlite3
import hashlib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from livekit.api import AccessToken, VideoGrants
from dotenv import load_dotenv
import logging

load_dotenv()
logging.basicConfig(level=logging.INFO)
AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "interviewer").strip() or "interviewer"
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "interviewos.db"))
ADMIN_ACCESS_KEY = os.getenv("ADMIN_ACCESS_KEY", "").strip()
HR_LOGIN_EMAIL = os.getenv("HR_LOGIN_EMAIL", "hr@interviewos.com").strip().lower()
HR_LOGIN_PASSWORD = os.getenv("HR_LOGIN_PASSWORD", "").strip()

app = FastAPI(title="Voice Interviewer API")

production_frontend_origin = "https://interview-agent-ten-umber.vercel.app"
demo_origin = os.getenv("DEMO_FRONTEND_ORIGIN", "").strip()
demo_tunnel_origins = os.getenv("DEMO_ALLOW_TUNNEL_ORIGINS", "").lower() == "true"
allowed_origins = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    production_frontend_origin,
]
if demo_origin and demo_origin.rstrip("/") not in allowed_origins:
    allowed_origins.append(demo_origin.rstrip("/"))

# Vercel assigns a distinct URL to every preview deployment. Restrict the
# wildcard to this project rather than allowing arbitrary Vercel sites.
allowed_origin_patterns = [r"https://interview-agent-[a-z0-9-]+\.vercel\.app"]
if demo_tunnel_origins:
    allowed_origin_patterns.append(r"https://[a-z0-9-]+\.trycloudflare\.com")
allowed_origin_regex = "(?:" + "|".join(allowed_origin_patterns) + ")"

logging.getLogger("api").info("CORS allowed origins configured: %s", allowed_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_origin_regex=allowed_origin_regex,
)


class InterviewSetup(BaseModel):
    domain: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=120)
    difficulty: str = Field(min_length=1, max_length=40)
    topics: List[str] = Field(default_factory=list, max_length=20)
    num_questions: int = Field(ge=1, le=10)


class ScheduledInterviewRequest(BaseModel):
    candidate_name: str = Field(min_length=1, max_length=120)
    candidate_email: str = Field(min_length=3, max_length=254)
    interview_password: str = Field(min_length=8, max_length=128)
    scheduled_at: datetime
    setup: InterviewSetup


class InviteJoinRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class AdminLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None = None) -> str:
    return (value or now_utc()).astimezone(timezone.utc).isoformat()


@contextmanager
def db_connection():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialise_database():
    with db_connection() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS scheduled_interviews (
                id TEXT PRIMARY KEY,
                invite_token TEXT UNIQUE NOT NULL,
                candidate_name TEXT NOT NULL,
                candidate_email TEXT NOT NULL,
                password_hash TEXT,
                scheduled_at TEXT NOT NULL,
                setup_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'scheduled',
                session_id TEXT,
                report_json TEXT,
                report_share_token TEXT UNIQUE,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS interview_sessions (
                id TEXT PRIMARY KEY,
                interview_id TEXT,
                candidate_name TEXT,
                setup_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'created',
                report_json TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_invite_token ON scheduled_interviews(invite_token);
            CREATE TABLE IF NOT EXISTS admin_sessions (
                token TEXT PRIMARY KEY,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        # Existing installations already have the table. Add the lock column
        # once, without invalidating their old interview records.
        columns = {row["name"] for row in db.execute("PRAGMA table_info(scheduled_interviews)")}
        if "password_hash" not in columns:
            db.execute("ALTER TABLE scheduled_interviews ADD COLUMN password_hash TEXT")
        if "report_share_token" not in columns:
            db.execute("ALTER TABLE scheduled_interviews ADD COLUMN report_share_token TEXT")


@app.on_event("startup")
def startup():
    initialise_database()
    if not ADMIN_ACCESS_KEY:
        logging.getLogger("api").warning("ADMIN_ACCESS_KEY is not configured. Admin API routes are disabled.")


def require_admin(x_admin_key: str | None, x_admin_session: str | None):
    # The server-only key remains available for emergency/API administration.
    if ADMIN_ACCESS_KEY and x_admin_key and secrets.compare_digest(x_admin_key, ADMIN_ACCESS_KEY):
        return
    if x_admin_session:
        with db_connection() as db:
            row = db.execute("SELECT expires_at FROM admin_sessions WHERE token = ?", (x_admin_session,)).fetchone()
            if row and datetime.fromisoformat(row["expires_at"]) > now_utc():
                return
            db.execute("DELETE FROM admin_sessions WHERE token = ?", (x_admin_session,))
    if not ADMIN_ACCESS_KEY:
        raise HTTPException(status_code=503, detail="Admin access is not configured")
    raise HTTPException(status_code=401, detail="Please sign in as HR to continue")


@app.post("/api/admin/login")
async def admin_login(request: AdminLoginRequest):
    if not HR_LOGIN_PASSWORD:
        raise HTTPException(status_code=503, detail="HR login is not configured")
    valid_email = secrets.compare_digest(request.email.strip().lower(), HR_LOGIN_EMAIL)
    valid_password = secrets.compare_digest(request.password, HR_LOGIN_PASSWORD)
    if not (valid_email and valid_password):
        raise HTTPException(status_code=401, detail="Incorrect HR email or password")
    token = secrets.token_urlsafe(32)
    expires_at = now_utc() + timedelta(hours=12)
    with db_connection() as db:
        db.execute("DELETE FROM admin_sessions WHERE expires_at <= ?", (iso(),))
        db.execute("INSERT INTO admin_sessions (token, expires_at, created_at) VALUES (?, ?, ?)", (token, iso(expires_at), iso()))
    return {"session_token": token, "expires_at": iso(expires_at)}


def password_digest(password: str, salt: str | None = None) -> str:
    """Store a salted PBKDF2 digest, never the candidate's raw password."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored_digest: str | None) -> bool:
    if not stored_digest or "$" not in stored_digest:
        return False
    salt, _ = stored_digest.split("$", 1)
    return secrets.compare_digest(password_digest(password, salt), stored_digest)


def row_to_session(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"], "candidate_name": row["candidate_name"] or "Candidate",
        "setup": json.loads(row["setup_json"]), "status": row["status"],
        "report": json.loads(row["report_json"]) if row["report_json"] else None,
    }


def create_session_record(setup: dict, candidate_name: str = "Candidate", interview_id: str | None = None) -> dict:
    session_id = str(uuid.uuid4())
    with db_connection() as db:
        db.execute(
            "INSERT INTO interview_sessions (id, interview_id, candidate_name, setup_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, interview_id, candidate_name, json.dumps(setup), iso()),
        )
        row = db.execute("SELECT * FROM interview_sessions WHERE id = ?", (session_id,)).fetchone()
    return row_to_session(row)


async def dispatch_interviewer(session_id: str, setup: dict):
    from livekit import api
    url, key, secret = os.getenv("LIVEKIT_URL"), os.getenv("LIVEKIT_API_KEY"), os.getenv("LIVEKIT_API_SECRET")
    if not url or not key or not secret:
        raise RuntimeError("LiveKit environment variables are not configured")
    async with api.LiveKitAPI(url=url, api_key=key, api_secret=secret) as lkapi:
        await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(agent_name=AGENT_NAME, room=session_id, metadata=json.dumps(setup))
        )


sessions = {}


@app.post("/api/interview/session")
async def create_session(setup: InterviewSetup, x_admin_key: str | None = Header(default=None)):
    # Direct session creation is reserved for HR/admins. Candidates must use
    # their locked invitation endpoint, which also validates schedule/password.
    require_admin(x_admin_key)
    session = create_session_record(setup.model_dump())
    try:
        await dispatch_interviewer(session["id"], session["setup"])
    except Exception:
        logging.getLogger("api").exception("Failed to dispatch interviewer")
        raise HTTPException(status_code=503, detail="Interview service is unavailable")
    return session


@app.get("/api/interview/session/{session_id}")
async def get_session(session_id: str):
    with db_connection() as db:
        row = db.execute("SELECT * FROM interview_sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return row_to_session(row)


@app.get("/api/interview/session/{session_id}/token")
async def get_token(session_id: str, participant_name: str | None = None):
    session = await get_session(session_id)

    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not api_key or not api_secret:
        raise HTTPException(
            status_code=500,
            detail="LiveKit credentials are not configured on the server",
        )

    grant = VideoGrants(room=session_id, room_join=True)
    access_token = (
        AccessToken(api_key, api_secret)
        .with_grants(grant)
        .with_identity(str(uuid.uuid4()))
        .with_name(participant_name or session["candidate_name"])
    )

    token = access_token.to_jwt()
    return {"token": token, "livekit_url": os.getenv("LIVEKIT_URL")}


@app.post("/api/interview/session/{session_id}/complete")
async def complete_session(session_id: str, report: dict):
    with db_connection() as db:
        row = db.execute("SELECT * FROM interview_sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        completed_at = iso()
        db.execute("UPDATE interview_sessions SET status = 'completed', report_json = ?, completed_at = ? WHERE id = ?", (json.dumps(report), completed_at, session_id))
        if row["interview_id"]:
            share_token = secrets.token_urlsafe(24)
            db.execute(
                "UPDATE scheduled_interviews SET status = 'completed', report_json = ?, report_share_token = ?, completed_at = ? WHERE id = ?",
                (json.dumps(report), share_token, completed_at, row["interview_id"]),
            )
        saved = db.execute("SELECT * FROM interview_sessions WHERE id = ?", (session_id,)).fetchone()
    return row_to_session(saved)


@app.post("/api/admin/interviews")
async def schedule_interview(request: ScheduledInterviewRequest, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    require_admin(x_admin_key, x_admin_session)
    if request.scheduled_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="scheduled_at must include a timezone")
    interview_id, token = str(uuid.uuid4()), secrets.token_urlsafe(24)
    with db_connection() as db:
        db.execute(
            "INSERT INTO scheduled_interviews (id, invite_token, candidate_name, candidate_email, password_hash, scheduled_at, setup_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (interview_id, token, request.candidate_name.strip(), request.candidate_email.strip().lower(), password_digest(request.interview_password), iso(request.scheduled_at), json.dumps(request.setup.model_dump()), iso()),
        )
    return {"id": interview_id, "invite_token": token, "scheduled_at": iso(request.scheduled_at), "status": "scheduled"}


@app.get("/api/admin/interviews")
async def list_scheduled_interviews(x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    require_admin(x_admin_key, x_admin_session)
    with db_connection() as db:
        rows = db.execute("SELECT * FROM scheduled_interviews ORDER BY scheduled_at DESC").fetchall()
    return [{
        "id": row["id"], "candidate_name": row["candidate_name"], "candidate_email": row["candidate_email"], "scheduled_at": row["scheduled_at"], "status": row["status"], "session_id": row["session_id"],
        "report": json.loads(row["report_json"]) if row["report_json"] else None, "report_share_token": row["report_share_token"], "setup": json.loads(row["setup_json"]),
    } for row in rows]


@app.get("/api/invitations/{invite_token}")
async def get_invitation(invite_token: str):
    with db_connection() as db:
        row = db.execute("SELECT * FROM scheduled_interviews WHERE invite_token = ?", (invite_token,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Interview invitation not found")
    setup = json.loads(row["setup_json"])
    return {"candidate_name": row["candidate_name"], "scheduled_at": row["scheduled_at"], "status": row["status"], "session_id": row["session_id"], "role": setup["role"], "domain": setup["domain"]}


@app.post("/api/invitations/{invite_token}/join")
async def join_invitation(invite_token: str, request: InviteJoinRequest):
    with db_connection() as db:
        row = db.execute("SELECT * FROM scheduled_interviews WHERE invite_token = ?", (invite_token,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Interview invitation not found")
    if row["status"] == "completed":
        raise HTTPException(status_code=409, detail="This interview has already been completed")
    if not verify_password(request.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect interview password")
    scheduled_at = datetime.fromisoformat(row["scheduled_at"])
    if now_utc() < scheduled_at - timedelta(minutes=10):
        raise HTTPException(status_code=403, detail="This interview opens 10 minutes before its scheduled time")
    if row["session_id"]:
        return {"session_id": row["session_id"]}
    setup = json.loads(row["setup_json"])
    session = create_session_record(setup, row["candidate_name"], row["id"])
    try:
        await dispatch_interviewer(session["id"], setup)
    except Exception:
        logging.getLogger("api").exception("Failed to dispatch scheduled interviewer")
        raise HTTPException(status_code=503, detail="Interview service is unavailable")
    with db_connection() as db:
        db.execute("UPDATE scheduled_interviews SET session_id = ?, status = 'in_progress', started_at = ? WHERE id = ?", (session["id"], iso(), row["id"]))
    return {"session_id": session["id"]}


@app.post("/api/admin/interviews/{interview_id}/share")
async def create_report_share_link(interview_id: str, x_admin_key: str | None = Header(default=None), x_admin_session: str | None = Header(default=None)):
    """Create/retrieve a secret, read-only link for a completed assessment."""
    require_admin(x_admin_key, x_admin_session)
    with db_connection() as db:
        row = db.execute("SELECT report_json, report_share_token FROM scheduled_interviews WHERE id = ?", (interview_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Scheduled interview not found")
        if not row["report_json"]:
            raise HTTPException(status_code=409, detail="A share link is available after the interview report is complete")
        token = row["report_share_token"] or secrets.token_urlsafe(24)
        if not row["report_share_token"]:
            db.execute("UPDATE scheduled_interviews SET report_share_token = ? WHERE id = ?", (token, interview_id))
    return {"share_token": token}


@app.get("/api/shared-reports/{share_token}")
async def get_shared_report(share_token: str):
    with db_connection() as db:
        row = db.execute(
            "SELECT candidate_name, candidate_email, scheduled_at, setup_json, report_json FROM scheduled_interviews WHERE report_share_token = ?",
            (share_token,),
        ).fetchone()
    if not row or not row["report_json"]:
        raise HTTPException(status_code=404, detail="Shared report not found")
    return {
        "candidate_name": row["candidate_name"], "candidate_email": row["candidate_email"],
        "scheduled_at": row["scheduled_at"], "setup": json.loads(row["setup_json"]),
        "report": json.loads(row["report_json"]),
    }
