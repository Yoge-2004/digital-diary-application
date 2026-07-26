from __future__ import annotations

import tempfile

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def build_client():
    tmp = tempfile.TemporaryDirectory()
    settings = Settings(
        database_url=f"sqlite:///{tmp.name}/test.db",
        secret_key="dev-secret-key-with-32-chars-minimum!!",
    )
    app = create_app(settings)
    client = TestClient(app)
    return client, tmp


def test_web_auth_and_diary_flow():
    client, tmp = build_client()
    with client, tmp:
        response = client.get("/register")
        assert response.status_code == 200

        csrf_token = client.cookies.get("csrf_token")
        response = client.post(
            "/register",
            data={
                "username": "alice",
                "email": "alice@example.com",
                "password": "password123",
                "confirm_password": "password123",
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/dashboard"

        csrf_token = client.cookies.get("csrf_token")
        response = client.post(
            "/diaries/new",
            data={
                "title": "First entry",
                "content": "Hello from the diary",
                "mood": "happy",
                "visibility": "private",
                "tags": "life, work",
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

        response = client.get("/diaries")
        assert response.status_code == 200
        assert "First entry" in response.text


def test_api_diary_listing_and_filtering():
    client, tmp = build_client()
    with client, tmp:
        response = client.post(
            "/api/auth/register",
            json={
                "username": "bob",
                "email": "bob@example.com",
                "password": "password123",
            },
        )
        assert response.status_code == 201

        response = client.post(
            "/api/diaries",
            json={
                "title": "Study notes",
                "content": "Worked through FastAPI and SQLAlchemy.",
                "mood": "focused",
                "visibility": "private",
                "tags": ["study", "coding"],
            },
        )
        assert response.status_code == 201

        response = client.get("/api/diaries?tag=study")
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["title"] == "Study notes"

        response = client.get("/api/stats/dashboard")
        assert response.status_code == 200
        assert response.json()["total_entries"] == 1
