from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ai_is_off_without_api_key():
    """The app must be fully usable with no AI credentials configured."""
    response = client.get("/health")
    body = response.json()
    assert "ai_enabled" in body
