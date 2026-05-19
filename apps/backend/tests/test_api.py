from app.main import app
from fastapi.testclient import TestClient


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_websocket_ready() -> None:
    with TestClient(app) as client:
        with client.websocket_connect("/ws/interview") as websocket:
            message = websocket.receive_json()
            assert message["type"] == "session.ready"
            assert message["sessionId"]


def test_session_end_requires_session_id() -> None:
    with TestClient(app) as client:
        response = client.post("/api/session/end", json={})
    assert response.status_code == 400


def test_settings_update_runtime_config() -> None:
    with TestClient(app) as client:
        response = client.post("/api/settings", json={"provider": "openai", "model": "gpt-4o"})
        assert response.status_code == 200
        assert app.state.runtime.settings.default_provider == "openai"
        assert app.state.runtime.settings.default_model == "gpt-4o"


def test_websocket_rejects_invalid_message_without_disconnect() -> None:
    with TestClient(app) as client:
        with client.websocket_connect("/ws/interview") as websocket:
            websocket.receive_json()
            websocket.send_json({"type": "audio.chunk", "sessionId": "missing", "payloadBase64": "not-base64"})
            message = websocket.receive_json()
            assert message["type"] == "assistant.error"
