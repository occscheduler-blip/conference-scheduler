import logging
import os

from supabase import create_client, Client

logger = logging.getLogger("supabase_io.client")

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

try:
    supabase: Client = create_client(url, key)
    logger.info("Supabase client initialised (url=%s)", url)
except Exception as exc:
    logger.error("Failed to initialise Supabase client: %s", exc)
    raise
