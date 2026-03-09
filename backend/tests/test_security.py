"""Tests for API key authentication middleware (app.security)."""

import pytest
from fastapi import HTTPException

from app.security import require_api_key


class TestRequireApiKey:
    def test_valid_key(self):
        """No exception when the correct key is provided."""
        result = require_api_key(x_api_key="test-api-key")
        assert result is None

    def test_missing_key(self):
        with pytest.raises(HTTPException) as exc_info:
            require_api_key(x_api_key=None)
        assert exc_info.value.status_code == 401

    def test_wrong_key(self):
        with pytest.raises(HTTPException) as exc_info:
            require_api_key(x_api_key="wrong-key")
        assert exc_info.value.status_code == 401

    def test_unconfigured_backend_key(self, monkeypatch):
        """500 when BACKEND_API_KEY is empty on the server."""
        from app.config import get_settings
        get_settings.cache_clear()
        monkeypatch.setenv("BACKEND_API_KEY", "")
        try:
            with pytest.raises(HTTPException) as exc_info:
                require_api_key(x_api_key="any")
            assert exc_info.value.status_code == 500
        finally:
            monkeypatch.setenv("BACKEND_API_KEY", "test-api-key")
            get_settings.cache_clear()
