# Citation

The test suite in this directory was written by [Claude](https://claude.ai) (Anthropic), model `claude-sonnet-4-6`.

## Summary

The previous test suite used mocks and an in-memory fake Supabase implementation spread across many files (`fake_supabase.py`, `test_events_api.py`, `test_read.py`, `test_write.py`, `test_delete.py`, `test_security.py`, `test_helpers.py`, `test_integration.py`, etc.). This was replaced with a consolidated real-integration approach:

- **`test_api.py`** — Single test file covering the full API surface: auth, health, and CRUD + cascade delete + nested read tests for every entity (symposiums, departments, classes, students, professors, presentations, requests).
- **`conftest.py`** — Forces `SUPABASE_URL`/`SUPABASE_KEY` to the local Supabase Docker instance, skips the suite automatically if Docker is not running, and provides session-scoped `client`/`db` fixtures plus an autouse `clean_db` fixture that truncates all tables before each test.
- **`db_helper.py`** — Thin psycopg wrapper (`DbHelper`) for direct database inspection (`count`, `rows`) and cleanup (`truncate_all`) without going through the API layer.
