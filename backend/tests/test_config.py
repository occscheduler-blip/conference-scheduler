"""Tests for app.config – Settings loading and CORS parsing."""

import os
from unittest.mock import patch

import pytest

from app.config import Settings


class TestSettings:
    def test_default_values(self):
        with patch.dict(os.environ, {}, clear=True):
            s = Settings(
                _env_file=None,
                backend_api_key="k",
                supabase_url="https://x.supabase.co",
                supabase_key="k",
            )
        assert s.app_name == "Conference Scheduler API"
        assert s.app_env == "development"
        assert s.app_port == 8000
        assert s.supabase_events_table == "events"

    def test_cors_origins_single(self):
        s = Settings(
            _env_file=None,
            backend_cors_origins="http://localhost:3000",
            backend_api_key="k",
            supabase_url="u",
            supabase_key="k",
        )
        assert s.cors_origins == ["http://localhost:3000"]

    def test_cors_origins_multiple(self):
        s = Settings(
            _env_file=None,
            backend_cors_origins="http://a.com, http://b.com ,http://c.com",
            backend_api_key="k",
            supabase_url="u",
            supabase_key="k",
        )
        assert s.cors_origins == ["http://a.com", "http://b.com", "http://c.com"]

    def test_cors_origins_strips_empty(self):
        s = Settings(
            _env_file=None,
            backend_cors_origins="http://a.com,,  ,http://b.com",
            backend_api_key="k",
            supabase_url="u",
            supabase_key="k",
        )
        assert s.cors_origins == ["http://a.com", "http://b.com"]
