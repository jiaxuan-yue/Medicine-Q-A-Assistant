from fastapi.testclient import TestClient

from app.main import app
from app.services.store import store


def test_auth_and_me():
    store.reset()
    with TestClient(app) as client:
        login_response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        assert login_response.status_code == 200
        access_token = login_response.json()["data"]["access_token"]

        me_response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me_response.status_code == 200
        assert me_response.json()["data"]["username"] == "admin"


def test_register_and_refresh():
    store.reset()
    with TestClient(app) as client:
        register_response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "new_user",
                "email": "new_user@tcm.local",
                "password": "secret123",
            },
        )
        assert register_response.status_code == 200
        refresh_token = register_response.json()["data"]["refresh_token"]

        refresh_response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert refresh_response.status_code == 200
        assert refresh_response.json()["data"]["access_token"]


def test_chat_session_lifecycle_and_stream():
    store.reset()
    with TestClient(app) as client:
        login_response = client.post(
            "/api/v1/auth/login",
            json={"username": "demo", "password": "demo123"},
        )
        access_token = login_response.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        create_response = client.post("/api/v1/chats", headers=headers)
        assert create_response.status_code == 200
        session_id = create_response.json()["data"]["session_id"]

        with client.stream(
            "POST",
            f"/api/v1/chats/{session_id}/stream",
            json={"query": "失眠口苦怎么理解"},
            headers=headers,
        ) as response:
            body = "".join(response.iter_text())
        assert "event: start" in body
        assert "event: chunk" in body
        assert "event: citation" in body
        assert "event: done" in body

        messages_response = client.get(f"/api/v1/chats/{session_id}/messages", headers=headers)
        assert messages_response.status_code == 200
        messages = messages_response.json()["data"]
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"


def test_documents_and_admin_dashboard():
    store.reset()
    with TestClient(app) as client:
        login_response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        access_token = login_response.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        documents_response = client.get("/api/v1/documents", headers=headers)
        assert documents_response.status_code == 200
        assert documents_response.json()["data"]["total"] >= 1

        dashboard_response = client.get("/api/v1/admin/dashboard", headers=headers)
        assert dashboard_response.status_code == 200
        assert dashboard_response.json()["data"]["total_users"] >= 4
