"""Integration tests for /api/auth/* endpoints."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def auth_client(client: TestClient) -> TestClient:
    return client


def _create_admin_direct(email: str, password: str) -> str:
    """Insert admin directly via Supabase SDK; returns admin ID."""
    from app.auth.password import hash_password
    from app.supabase_io.client import supabase

    password_hash = hash_password(password)
    resp = (
        supabase.table("admins")
        .insert({"email": email, "password_hash": password_hash})
        .execute()
    )
    rows = resp.data or []
    return str(rows[0]["id"])


class TestAdminLogin:
    def test_login_success(self, auth_client: TestClient) -> None:
        email = "admin@hamilton.edu"
        password = "correct-password"
        _create_admin_direct(email, password)

        resp = auth_client.post(
            "/api/auth/admin/login",
            json={"email": email, "password": password},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["role"] == "admin"
        assert "access_token" in body
        assert "entity_id" in body

    def test_login_wrong_password(self, auth_client: TestClient) -> None:
        email = "admin@hamilton.edu"
        _create_admin_direct(email, "correct-password")

        resp = auth_client.post(
            "/api/auth/admin/login",
            json={"email": email, "password": "wrong-password"},
        )
        assert resp.status_code == 401

    def test_login_unknown_email(self, auth_client: TestClient) -> None:
        resp = auth_client.post(
            "/api/auth/admin/login",
            json={"email": "nobody@hamilton.edu", "password": "any"},
        )
        assert resp.status_code == 401

    def test_login_same_message_for_both_failures(self, auth_client: TestClient) -> None:
        """Bad email and bad password should return the same error message."""
        _create_admin_direct("admin@hamilton.edu", "password")

        bad_email_resp = auth_client.post(
            "/api/auth/admin/login",
            json={"email": "nobody@hamilton.edu", "password": "anything"},
        )
        bad_pass_resp = auth_client.post(
            "/api/auth/admin/login",
            json={"email": "admin@hamilton.edu", "password": "wrong"},
        )
        assert bad_email_resp.json()["detail"] == bad_pass_resp.json()["detail"]


class TestAdminCreate:
    def _login(self, client: TestClient, email: str, password: str) -> str:
        _create_admin_direct(email, password)
        resp = client.post(
            "/api/auth/admin/login",
            json={"email": email, "password": password},
        )
        return resp.json()["access_token"]

    def test_create_admin_success(self, auth_client: TestClient) -> None:
        token = self._login(auth_client, "admin@hamilton.edu", "password123")

        resp = auth_client.post(
            "/api/auth/admin/create",
            json={"email": "admin2@hamilton.edu", "password": "newpassword"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "admin_id" in resp.json()

    def test_create_admin_no_token(self, auth_client: TestClient) -> None:
        resp = auth_client.post(
            "/api/auth/admin/create",
            json={"email": "admin2@hamilton.edu", "password": "newpassword"},
        )
        assert resp.status_code == 401

    def test_create_admin_invalid_token(self, auth_client: TestClient) -> None:
        resp = auth_client.post(
            "/api/auth/admin/create",
            json={"email": "admin2@hamilton.edu", "password": "newpassword"},
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert resp.status_code == 401


class TestJWTDecode:
    def test_jwt_payload_contains_role_and_entity_id(self, auth_client: TestClient) -> None:
        email = "admin@hamilton.edu"
        password = "password"
        admin_id = _create_admin_direct(email, password)

        resp = auth_client.post(
            "/api/auth/admin/login",
            json={"email": email, "password": password},
        )
        body = resp.json()
        assert body["entity_id"] == admin_id
        assert body["role"] == "admin"

        from app.auth.jwt_utils import decode_jwt
        claims = decode_jwt(body["access_token"])
        assert claims.role == "admin"
        assert claims.sub == admin_id
        assert claims.email == email
