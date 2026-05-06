"""CLI tool to create a new super admin or promote an existing admin to super admin."""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import os

os.environ.setdefault("SUPABASE_URL", os.environ.get("SUPABASE_URL", ""))
os.environ.setdefault("SUPABASE_KEY", os.environ.get("SUPABASE_KEY", ""))

from app.auth.password import hash_password
from app.supabase_io.client import supabase


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or promote a super admin user.")
    parser.add_argument("--email", required=True, help="Admin email (@hamilton.edu)")
    parser.add_argument("--password", default=None, help="Password (prompted if omitted; ignored when --promote-existing is set)")
    parser.add_argument(
        "--promote-existing",
        action="store_true",
        help="Promote an existing admin account to super admin instead of creating a new one",
    )
    args = parser.parse_args()

    if not args.email.endswith("@hamilton.edu"):
        print("Error: email must end with @hamilton.edu", file=sys.stderr)
        sys.exit(1)

    if args.promote_existing:
        resp = (
            supabase.table("admins")
            .update({"is_superadmin": True})
            .eq("email", args.email)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            print(f"Error: no admin found with email {args.email}", file=sys.stderr)
            sys.exit(1)
        print(f"Super admin promoted: {rows[0]['id']}  ({args.email})")
    else:
        password = args.password or getpass.getpass("Password: ")
        if not password:
            print("Error: password cannot be empty", file=sys.stderr)
            sys.exit(1)

        password_hash = hash_password(password)
        resp = (
            supabase.table("admins")
            .insert({"email": args.email, "password_hash": password_hash, "is_superadmin": True})
            .execute()
        )
        rows = resp.data or []
        if not rows:
            print("Error: insert returned no data", file=sys.stderr)
            sys.exit(1)
        print(f"Super admin created: {rows[0]['id']}  ({args.email})")


if __name__ == "__main__":
    main()
