# import argparse
# from ortools.sat.python import cp_model
# from app.supabase_io import read, write
# from uuid import UUID
# from typing import cast


# def get_data(symposium_id: UUID) -> None:
#     data: dict[str,object] = {}

#     # Get departments in the symposium
#     dept_resp = cast(list[dict[str, object]], read.get_departments(symposium_id).data)
#     depts = [dept["id"] for dept in dept_resp]

#     # Get classes in each department
#     for dept in depts:
#         pass


# def schedule_presentations(symposium_id=UUID("3a9189b1-fb8c-47cc-990f-1b796fb4b75a")) -> None:
#     get_data(symposium_id)


# def main() -> None:
#     parser = argparse.ArgumentParser(
#         description="Run the conference scheduling algorithm."
#     )
#     parser.add_argument(
#         "-s", dest="symposium_id", type=UUID, help="UUID of the symposium to schedule"
#     )
#     args = parser.parse_args()
#     if args.symposium_id:
#         schedule_presentations(None, args.symposium_id)
#     else:
#         schedule_presentations(None)


# if __name__ == "__main__":
#     main()
