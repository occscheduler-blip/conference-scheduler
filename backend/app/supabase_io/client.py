import os
from supabase import create_client, Client

url: str | None = os.environ.get("SUPABASE_URL")
key: str | None = os.environ.get("SUPABASE_KEY")
if not url:
    raise ValueError("Supabase URL not found.")
if not key:
    raise ValueError("Supabase key not found.")
supabase: Client = create_client(url, key)
