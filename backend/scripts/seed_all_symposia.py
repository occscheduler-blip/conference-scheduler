#!/usr/bin/env python3
"""Regenerate every seeded symposium.

Wipes existing data once, then runs each size-specific seed script in turn
(plus the debug-scenario seed). Run from the backend/ directory:

    python scripts/seed_all_symposia.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from supabase import create_client

SCRIPTS_DIR = Path(__file__).resolve().parent

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

SEED_SCRIPTS: list[str] = [
    "seed_debug_symposium.py",
    "seed_small_symposium.py",
    "seed_medium_symposium.py",
    "seed_large_symposium.py",
    "seed_massive_symposium.py",
    "seed_uniform_symposium.py"
]


def delete_all() -> None:
    """Delete all rows in dependency order (children before parents)."""
    print("Deleting all existing data...")
    tables = [
        "presenting_students",
        "requests",
        "timeframes",
        "students",
        "presentations",
        "professors",
        "classes",
        "departments",
        "symposiums",
    ]
    for table in tables:
        resp = supabase.table(table).delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        count = len(resp.data) if resp.data else 0
        print(f"  Deleted {count} rows from {table}")
    print("All existing data deleted.\n")


def run(script: str) -> None:
    print(f"\n=== Running {script} ===", flush=True)
    result = subprocess.run([sys.executable, str(SCRIPTS_DIR / script)])
    if result.returncode != 0:
        sys.exit(f"FAILED: {script} exited with {result.returncode}")


def main() -> None:
    delete_all()
    for script in SEED_SCRIPTS:
        run(script)
    print("\nAll symposia regenerated.")


if __name__ == "__main__":
    main()
