import logging
import os
from supabase import create_client, Client

logger = logging.getLogger(__name__)

url: str | None = os.environ.get("SUPABASE_URL")
key: str | None = os.environ.get("SUPABASE_KEY")
if not url:
    raise ValueError("Supabase URL not found.")
if not key:
    raise ValueError("Supabase key not found.")
logger.info("Connecting to Supabase at %s", url)
supabase: Client = create_client(url, key)
logger.info("Supabase client initialized")
