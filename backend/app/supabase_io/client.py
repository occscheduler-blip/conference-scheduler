import logging
import os
import threading
from typing import Any, cast
from supabase import create_client, Client

logger = logging.getLogger(__name__)

_url: str = os.environ.get("SUPABASE_URL") or ""
_key: str = os.environ.get("SUPABASE_KEY") or ""
if not _url:
    raise ValueError("Supabase URL not found.")
if not _key:
    raise ValueError("Supabase key not found.")
logger.info("Connecting to Supabase at %s", _url)

_local = threading.local()


def get_client() -> Client:
    """Return a thread-local supabase client, creating one on first use per thread."""
    if not hasattr(_local, "client"):
        _local.client = create_client(_url, _key)
    return cast(Client, _local.client)


class _ThreadLocalProxy:
    """Proxy that forwards all attribute access to the thread-local client.

    This keeps the existing ``from app.supabase_io.client import supabase``
    import pattern working everywhere while ensuring each thread gets its
    own httpx connection pool — preventing HTTP/2 stream-state corruption
    when background threads and request-handler threads share the same client.
    """

    def __getattr__(self, name: str) -> object:
        return getattr(get_client(), name)


supabase: Client = _ThreadLocalProxy()  # type: ignore[assignment]
logger.info("Supabase thread-local client proxy initialized")
