"""Integration tests for OTP sign-in flow (/api/auth/otp/*)."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from tests.db_helper import DbHelper

# Fixed OTP used across all tests (patched into generate_otp)
_TEST_OTP = "123456"

# ── Helpers ────────────────────────────────────────────────────────────────

TF_1 = {"start_time": "2026-04-20T09:00:00Z", "end_time": "2026-04-20T12:00:00Z"}


def _seed_professor(client: TestClient, h: dict[str, str]) -> dict[str, str]:
    """Create symposium → department → class → professor; return professor info."""
    resp = client.post(
        "/api/events/add_symposium",
        json={"symposium_name": "OTP Symp", "rooms_available": 1, "default_buffer": 0, "timeframes": [TF_1]},
        headers=h,
    )
    sym_id = resp.json()["symposium_id"]

    resp = client.post(
        "/api/events/add_department",
        json={
            "symposium_id": sym_id,
            "department_name": "CS",
            "department_head_name": "Dr. Head",
            "email": "head@hamilton.edu",
        },
        headers=h,
    )
    dept_id = resp.json()["department_id"]

    resp = client.post(
        "/api/events/add_class",
        json={
            "name": "CS101",
            "department_id": dept_id,
            "professors": [{"name": "Prof. OTP", "email": "prof@hamilton.edu"}],
        },
        headers=h,
    )
    class_id = resp.json()["class_id"]

    return {"email": "prof@hamilton.edu", "class_id": class_id}


def _seed_student(client: TestClient, h: dict[str, str], class_id: str) -> dict[str, str]:
    """Add a student to the given class; return student info."""
    resp = client.post(
        "/api/events/add_students",
        json={
            "class_id": class_id,
            "students": [{"name": "Stu OTP", "email": "stu@hamilton.edu"}],
        },
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    return {"email": "stu@hamilton.edu"}


# ── /auth/otp/request ─────────────────────────────────────────────────────


class TestOTPRequest:
    def test_request_success_professor(self, client: TestClient, h: dict[str, str]) -> None:
        _seed_professor(client, h)
        with patch("app.routers.auth.generate_otp", return_value=_TEST_OTP), \
             patch("app.routers.auth.send_otp_email") as mock_send:
            resp = client.post(
                "/api/auth/otp/request",
                json={"email": "prof@hamilton.edu", "role": "professor"},
            )
        assert resp.status_code == 200
        assert resp.json()["detail"] == "OTP sent to your email address."
        mock_send.assert_called_once_with("prof@hamilton.edu", _TEST_OTP)

    def test_request_success_student(self, client: TestClient, h: dict[str, str]) -> None:
        prof = _seed_professor(client, h)
        _seed_student(client, h, prof["class_id"])
        with patch("app.routers.auth.generate_otp", return_value=_TEST_OTP), \
             patch("app.routers.auth.send_otp_email"):
            resp = client.post(
                "/api/auth/otp/request",
                json={"email": "stu@hamilton.edu", "role": "student"},
            )
        assert resp.status_code == 200

    def test_request_success_department_head(self, client: TestClient, h: dict[str, str]) -> None:
        _seed_professor(client, h)  # also creates dept with head@hamilton.edu
        with patch("app.routers.auth.generate_otp", return_value=_TEST_OTP), \
             patch("app.routers.auth.send_otp_email"):
            resp = client.post(
                "/api/auth/otp/request",
                json={"email": "head@hamilton.edu", "role": "department_head"},
            )
        assert resp.status_code == 200

    def test_request_invalid_role(self, client: TestClient) -> None:
        resp = client.post(
            "/api/auth/otp/request",
            json={"email": "anyone@hamilton.edu", "role": "admin"},
        )
        assert resp.status_code == 400

    def test_request_email_not_found(self, client: TestClient) -> None:
        resp = client.post(
            "/api/auth/otp/request",
            json={"email": "nobody@hamilton.edu", "role": "professor"},
        )
        assert resp.status_code == 404


# ── /auth/otp/verify ──────────────────────────────────────────────────────


class TestOTPVerify:
    def _request_otp(self, client: TestClient, email: str, role: str) -> None:
        """Request an OTP with generate_otp patched to return _TEST_OTP."""
        with patch("app.routers.auth.generate_otp", return_value=_TEST_OTP), \
             patch("app.routers.auth.send_otp_email"):
            resp = client.post(
                "/api/auth/otp/request",
                json={"email": email, "role": role},
            )
            assert resp.status_code == 200

    def test_verify_success_returns_jwt(self, client: TestClient, h: dict[str, str]) -> None:
        _seed_professor(client, h)
        self._request_otp(client, "prof@hamilton.edu", "professor")

        resp = client.post(
            "/api/auth/otp/verify",
            json={"email": "prof@hamilton.edu", "role": "professor", "otp": _TEST_OTP},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["role"] == "professor"
        assert "access_token" in body
        assert "entity_id" in body

    def test_verify_jwt_contains_correct_claims(self, client: TestClient, h: dict[str, str]) -> None:
        _seed_professor(client, h)
        self._request_otp(client, "prof@hamilton.edu", "professor")

        resp = client.post(
            "/api/auth/otp/verify",
            json={"email": "prof@hamilton.edu", "role": "professor", "otp": _TEST_OTP},
        )
        from app.auth.jwt_utils import decode_jwt
        claims = decode_jwt(resp.json()["access_token"])
        assert claims.role == "professor"
        assert claims.email == "prof@hamilton.edu"

    def test_verify_wrong_otp(self, client: TestClient, h: dict[str, str]) -> None:
        _seed_professor(client, h)
        self._request_otp(client, "prof@hamilton.edu", "professor")

        resp = client.post(
            "/api/auth/otp/verify",
            json={"email": "prof@hamilton.edu", "role": "professor", "otp": "000000"},
        )
        assert resp.status_code == 401

    def test_verify_otp_used_twice(self, client: TestClient, h: dict[str, str]) -> None:
        """An OTP can only be consumed once."""
        _seed_professor(client, h)
        self._request_otp(client, "prof@hamilton.edu", "professor")

        first = client.post(
            "/api/auth/otp/verify",
            json={"email": "prof@hamilton.edu", "role": "professor", "otp": _TEST_OTP},
        )
        assert first.status_code == 200

        second = client.post(
            "/api/auth/otp/verify",
            json={"email": "prof@hamilton.edu", "role": "professor", "otp": _TEST_OTP},
        )
        assert second.status_code == 401

    def test_verify_expired_otp(self, client: TestClient, h: dict[str, str]) -> None:
        """An OTP past its TTL should be rejected."""
        from datetime import datetime, timedelta, timezone
        _seed_professor(client, h)
        self._request_otp(client, "prof@hamilton.edu", "professor")

        # Manually expire the token by pushing expires_at into the past
        from app.supabase_io.client import supabase
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        supabase.table("otp_tokens").update({"expires_at": past}).eq(
            "email", "prof@hamilton.edu"
        ).eq("used", False).execute()

        resp = client.post(
            "/api/auth/otp/verify",
            json={"email": "prof@hamilton.edu", "role": "professor", "otp": _TEST_OTP},
        )
        assert resp.status_code == 401

    def test_verify_invalid_role(self, client: TestClient) -> None:
        resp = client.post(
            "/api/auth/otp/verify",
            json={"email": "prof@hamilton.edu", "role": "admin", "otp": _TEST_OTP},
        )
        assert resp.status_code == 400

    def test_new_request_invalidates_old_otp(self, client: TestClient, h: dict[str, str]) -> None:
        """Requesting a new OTP should invalidate any previous unused OTP."""
        _seed_professor(client, h)

        # First OTP
        with patch("app.routers.auth.generate_otp", return_value="111111"), \
             patch("app.routers.auth.send_otp_email"):
            client.post(
                "/api/auth/otp/request",
                json={"email": "prof@hamilton.edu", "role": "professor"},
            )

        # Second OTP (invalidates the first)
        with patch("app.routers.auth.generate_otp", return_value="222222"), \
             patch("app.routers.auth.send_otp_email"):
            client.post(
                "/api/auth/otp/request",
                json={"email": "prof@hamilton.edu", "role": "professor"},
            )

        # First OTP should no longer work
        resp = client.post(
            "/api/auth/otp/verify",
            json={"email": "prof@hamilton.edu", "role": "professor", "otp": "111111"},
        )
        assert resp.status_code == 401

        # Second OTP should work
        resp = client.post(
            "/api/auth/otp/verify",
            json={"email": "prof@hamilton.edu", "role": "professor", "otp": "222222"},
        )
        assert resp.status_code == 200


# ── Cleanup / deletion tests ────────────────────────────────────────────


class TestOTPCleanup:
    def _request_otp(self, client: TestClient, email: str, role: str, code: str = _TEST_OTP) -> None:
        with patch("app.routers.auth.generate_otp", return_value=code), \
             patch("app.routers.auth.send_otp_email"):
            resp = client.post(
                "/api/auth/otp/request",
                json={"email": email, "role": role},
            )
            assert resp.status_code == 200

    def test_used_otp_is_deleted(self, client: TestClient, h: dict[str, str], db: DbHelper) -> None:
        """Verifying an OTP should delete the row from the database."""
        _seed_professor(client, h)
        self._request_otp(client, "prof@hamilton.edu", "professor")
        assert db.count("otp_tokens") == 1

        client.post(
            "/api/auth/otp/verify",
            json={"email": "prof@hamilton.edu", "role": "professor", "otp": _TEST_OTP},
        )
        assert db.count("otp_tokens") == 0

    def test_expired_otps_deleted_on_new_request(self, client: TestClient, h: dict[str, str], db: DbHelper) -> None:
        """Requesting a new OTP should delete any expired rows."""
        from datetime import datetime, timedelta, timezone
        from app.supabase_io.client import supabase

        _seed_professor(client, h)
        self._request_otp(client, "prof@hamilton.edu", "professor")
        assert db.count("otp_tokens") == 1

        # Manually expire the existing token
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        supabase.table("otp_tokens").update({"expires_at": past}).eq(
            "email", "prof@hamilton.edu"
        ).eq("used", False).execute()

        # Requesting a new OTP should clean up the expired one
        self._request_otp(client, "prof@hamilton.edu", "professor", code="999999")

        # Only the new OTP should remain
        assert db.count("otp_tokens") == 1
        rows = db.rows("otp_tokens")
        assert rows[0]["used"] is False
        expires_at = rows[0]["expires_at"]
        assert expires_at > datetime.now(timezone.utc)

    def test_old_unused_otp_deleted_on_new_request(self, client: TestClient, h: dict[str, str], db: DbHelper) -> None:
        """Requesting a new OTP should delete (not just mark used) the previous unused OTP."""
        _seed_professor(client, h)
        self._request_otp(client, "prof@hamilton.edu", "professor", code="111111")
        assert db.count("otp_tokens") == 1

        self._request_otp(client, "prof@hamilton.edu", "professor", code="222222")

        # Old OTP should be deleted, only the new one remains
        assert db.count("otp_tokens") == 1
