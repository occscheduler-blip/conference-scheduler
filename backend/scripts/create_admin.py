"""One-time CLI bootstrap for creating the first admin user."""
import argparse
import getpass
import sys
from pathlib import Path

# Ensure the backend package is importable when run from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import os

os.environ.setdefault("SUPABASE_URL", os.environ.get("SUPABASE_URL", ""))
os.environ.setdefault("SUPABASE_KEY", os.environ.get("SUPABASE_KEY", ""))

from app.auth.password import hash_password
from app.supabase_io.client import supabase


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an admin user.")
    parser.add_argument("--email", required=True, help="Admin email (@hamilton.edu)")
    parser.add_argument("--password", default=None, help="Password (prompted if omitted)")
    args = parser.parse_args()

    if not args.email.endswith("@hamilton.edu"):
        print("Error: email must end with @hamilton.edu", file=sys.stderr)
        sys.exit(1)

    password = args.password or getpass.getpass("Password: ")
    if not password:
        print("Error: password cannot be empty", file=sys.stderr)
        sys.exit(1)

    password_hash = hash_password(password)
    resp = (
        supabase.table("admins")
        .insert({"email": args.email, "password_hash": password_hash})
        .execute()
    )
    rows = resp.data or []
    if not rows:
        print("Error: insert returned no data", file=sys.stderr)
        sys.exit(1)

    print(f"Admin created: {rows[0]['id']}")


if __name__ == "__main__":
    main()
