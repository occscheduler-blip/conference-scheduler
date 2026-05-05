"""Per-symposium Postgres advisory locks via psycopg.

Used to serialize multi-step writes that are not safe under concurrency
(scheduler runs, manual schedule edits, publish, atomic delete-then-insert
of timeframes / presenting_students).

The lock is held for the duration of a psycopg transaction on a dedicated
connection; released automatically on COMMIT / ROLLBACK / connection drop.
No janitor needed on crash.

Yielding the connection lets callers run additional writes inside the same
transaction for true atomicity (e.g. delete-then-insert of timeframes).
Callers that only need mutual exclusion can ignore the yielded value and
do their writes through supabase-py as usual.
"""
from __future__ import annotations

import contextlib
import hashlib
import logging
import os
from typing import Iterator
from uuid import UUID

import psycopg
from fastapi import HTTPException

logger = logging.getLogger(__name__)

_DEFAULT_DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


def _db_url() -> str:
    return os.environ.get("SUPABASE_DB_URL") or _DEFAULT_DB_URL


def _key_for(symposium_id: str | UUID) -> int:
    """Map a symposium identifier to a stable signed-bigint advisory-lock key."""
    digest = hashlib.blake2b(str(symposium_id).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


@contextlib.contextmanager
def symposium_lock(
    symposium_id: str | UUID,
    *,
    lock_timeout_ms: int = 5000,
) -> Iterator[psycopg.Connection]:
    """Hold a per-symposium advisory lock for the duration of a transaction.

    Raises HTTPException(423) if another holder doesn't release within
    ``lock_timeout_ms``.
    """
    key = _key_for(symposium_id)
    timeout_value = max(0, int(lock_timeout_ms))
    conn = psycopg.connect(_db_url())
    try:
        with conn.cursor() as cur:
            # SET cannot use bind parameters in Postgres, so format the int
            # ourselves — the value is always an int from our own code.
            cur.execute(f"SET LOCAL lock_timeout = '{timeout_value}ms'")
            try:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (key,))
            except psycopg.errors.LockNotAvailable as exc:
                conn.rollback()
                logger.warning(
                    "symposium_lock timed out: symposium_id=%s key=%s",
                    symposium_id,
                    key,
                )
                raise HTTPException(
                    status_code=423,
                    detail={
                        "code": "symposium_busy",
                        "message": "Another operation is in progress for this symposium. Please retry.",
                    },
                ) from exc
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()


@contextlib.contextmanager
def maybe_symposium_lock(
    symposium_id: str | UUID | None,
    *,
    lock_timeout_ms: int = 5000,
) -> Iterator[psycopg.Connection | None]:
    """Same as ``symposium_lock`` but a no-op when ``symposium_id`` is None.

    Useful for cascade-delete endpoints where the entity may already be gone
    (idempotent delete) — there's nothing to protect, so we skip the lock.
    """
    if symposium_id is None:
        yield None
        return
    with symposium_lock(symposium_id, lock_timeout_ms=lock_timeout_ms) as conn:
        yield conn
