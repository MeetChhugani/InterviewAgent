"""
Integration smoke-test: creates a session via FastAPI and verifies
that the JWT token endpoint returns a token.
"""
import pytest
from fastapi.testclient import TestClient
import os

# Provide minimal env vars so main.py can import without crashing
os.environ.setdefault("LIVEKIT_URL", "wss://localhost")
os.environ.setdefault("LIVEKIT_API_KEY", "testkey")
os.environ.setdefault("LIVEKIT_API_SECRET", "testsecret")
os.environ.setdefault("GROQ_API_KEY", "testgroq")

from app.main import app, sessions  # noqa: E402

client = TestClient(app)

SETUP_PAYLOAD = {
    "domain": "Software Engineering",
    "role": "Backend Engineer",
    "difficulty": "Intermediate",
    "topics": ["Python", "REST APIs"],
    "num_questions": 5,
}


def test_flow():
    # POST /api/interview/session — dispatch will fail (no real LiveKit) but
    # session is created in memory regardless.
    resp = client.post("/api/interview/session", json=SETUP_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    session_id = data["id"]
    assert session_id in sessions

    # GET session
    resp2 = client.get(f"/api/interview/session/{session_id}")
    assert resp2.status_code == 200
    assert resp2.json()["id"] == session_id

    # GET token
    resp3 = client.get(f"/api/interview/session/{session_id}/token")
    assert resp3.status_code == 200
    assert "token" in resp3.json()
    assert resp3.json()["token"]  # non-empty JWT
