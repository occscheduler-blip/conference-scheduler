from dotenv import load_dotenv
import pandas as pd

from app.routers import schemas
from supabase_io import write
from app.routers.events import add_symposium, remove_symposium

def test_delete_symposium() -> None:
    symposium_id = 1
    name = "symposium_test"
    remove_symposium(symposium_id, name)



def test_add_symposium() -> None:
    load_dotenv(".env")

    symposium_payload = {
        "id": 1,
        "name": "test",
        "departments": [],
    }

    add_symposium(symposium_payload)

    print(f"Created/rewrote table public.symposium_test")

def main():
    test_delete_symposium()

if __name__ == "__main__":
    main()
