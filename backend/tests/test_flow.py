import os
from fastapi.testclient import TestClient
from app.main import app
from unittest import mock

client = TestClient(app)

def test_flow():
    # Test missing keys
    with mock.patch.dict(os.environ, {}, clear=True):
        response = client.post("/api/interview/session", json={
            "domain": "AI",
            "role": "Engineer",
            "difficulty": "Intermediate",
            "topics": ["ML"],
            "num_questions": 5
        })
        assert response.status_code == 200
        session_id = response.json()["id"]
        
        response_token_fail = client.get(f"/api/interview/session/{session_id}/token")
        assert response_token_fail.status_code == 500

    # Test invalid session
    response_invalid = client.get(f"/api/interview/session/invalid/token")
    assert response_invalid.status_code == 404

    # Test valid flow
    with mock.patch.dict(os.environ, {"LIVEKIT_API_KEY": "devkey", "LIVEKIT_API_SECRET": "secret", "LIVEKIT_URL": "wss://test"}, clear=True):
        response_token = client.get(f"/api/interview/session/{session_id}/token")
        assert response_token.status_code == 200
        data = response_token.json()
        assert "token" in data
        assert isinstance(data["token"], str)
        assert data["token"].count(".") == 2 # basic JWT structure check
        assert "livekit_url" in data
        assert data["livekit_url"] == "wss://test"
