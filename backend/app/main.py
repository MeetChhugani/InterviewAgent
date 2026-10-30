from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List
import uuid
import os
from livekit.api import AccessToken, VideoGrants
from dotenv import load_dotenv
import logging

load_dotenv()
logging.basicConfig(level=logging.INFO)
AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "interviewer").strip() or "interviewer"

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
    topics: List[str] = Field(min_length=1, max_length=20)
    num_questions: int = Field(ge=1, le=10)


sessions = {}


@app.post("/api/interview/session")
async def create_session(setup: InterviewSetup):
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "id": session_id,
        "setup": setup.model_dump(),
        "status": "created",
        "questions_asked": 0,
        "evaluations": [],
        "report": None,
    }

    import json
    from livekit import api
    import logging
    logger = logging.getLogger("api")

    try:
        url = os.getenv("LIVEKIT_URL")
        key = os.getenv("LIVEKIT_API_KEY")
        secret = os.getenv("LIVEKIT_API_SECRET")
        logger.info(f"Connecting to LiveKit API at {url}")

        async with api.LiveKitAPI(url=url, api_key=key, api_secret=secret) as lkapi:
            dispatch = await lkapi.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name=AGENT_NAME,
                    room=session_id,
                    metadata=json.dumps(setup.model_dump()),
                )
            )
            logger.info(
                "DISPATCHING INTERVIEWER: agent_name=%s room=%s",
                AGENT_NAME,
                session_id,
            )
            logger.info(f"dispatch_id={dispatch.id}")
    except Exception as e:
        logger.error(f"Failed to dispatch agent: {e}", exc_info=True)

    return sessions[session_id]


@app.get("/api/interview/session/{session_id}")
async def get_session(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return sessions[session_id]


@app.get("/api/interview/session/{session_id}/token")
async def get_token(session_id: str, participant_name: str = "Candidate"):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

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
        .with_name(participant_name)
    )

    token = access_token.to_jwt()
    return {"token": token, "livekit_url": os.getenv("LIVEKIT_URL")}


@app.post("/api/interview/session/{session_id}/complete")
async def complete_session(session_id: str, report: dict):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    sessions[session_id]["status"] = "completed"
    sessions[session_id]["report"] = report
    return sessions[session_id]
