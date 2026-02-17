from app.supabase_io.client import supabase
from uuid import UUID
from app.supabase_io import read


def delete_student(student_id: UUID | list[UUID]):
    # TODO: Make sure that if the last student is deleted from a presentation, the presentation is deleted as well.
    del_stu_query = supabase.table("students").delete()
    del_presenting_student_query = supabase.table("presenting_students").delete()
    del_prof_request_query = supabase.table("prof_requests").delete()

    if isinstance(student_id, UUID):
        del_stu_query = del_stu_query.eq("id", student_id)
        del_presenting_student_query = del_presenting_student_query.eq(
            "student_id", student_id
        )
        del_prof_request_query = del_prof_request_query.eq("student_id", student_id)
    elif isinstance(student_id, list[UUID]):
        del_stu_query = del_stu_query.in_("id", student_id)
        del_presenting_student_query = del_presenting_student_query.in_(
            "student_id", student_id
        )
        del_prof_request_query = del_prof_request_query.in_("student_id", student_id)

    del_stu_resp = del_stu_query.execute()
    del_presenting_student_resp = del_presenting_student_query.execute()
    del_prof_request_resp = del_prof_request_query.execute()


def delete_professor(prof_id: UUID | list[UUID]):
    # TODO: What to do when the last professor in a class/presentation is removed?
    del_prof_query = supabase.table("students").delete()
    del_prof_request_query = supabase.table("prof_requests").delete()

    if isinstance(prof_id, UUID):
        del_prof_query = del_prof_query.eq("id", prof_id)
        del_prof_request_query = del_prof_request_query.eq("professor_id", prof_id)
    elif isinstance(prof_id, list[UUID]):
        del_prof_query = del_prof_query.in_("id", prof_id)
        del_prof_request_query = del_prof_request_query.in_("professor_id", prof_id)

    del_prof_resp = del_prof_query.execute()
    del_prof_request_resp = del_prof_request_query.execute()


def delete_presentation(presentation_id: UUID | list[UUID]):
    del_pres_query = supabase.table("presentations").delete()
    del_presenting_student_query = supabase.table("presenting_students").delete()

    if isinstance(presentation_id, UUID):
        del_pres_query = del_pres_query.eq("id", presentation_id)
        del_presenting_student_query = del_presenting_student_query.eq(
            "presentation_id", presentation_id
        )
    elif isinstance(presentation_id, list[UUID]):
        del_pres_query = del_pres_query.in_("id", presentation_id)
        del_presenting_student_query = del_presenting_student_query.in_(
            "presentation_id", presentation_id
        )

    del_pres_resp = del_pres_query.execute()
    del_presenting_student_resp = del_presenting_student_query.execute()


def delete_multiple_classes(class_ids: list[UUID]):
    for class_id in class_ids:
        delete_class(class_id)


def delete_class(class_id: UUID | list[UUID]):
    if isinstance(class_id, list[UUID]):
        delete_multiple_classes(class_id)

    student_list = read.get_students(class_id=class_id).data
    for student in student_list:
        delete_student(student_id=student["id"])

    prof_list = read.get_professors(class_id=class_id).data
    for professor in prof_list:
        delete_professor(professor["id"])
    pres_list = read.get_presentations(class_id=class_id).data
    for presentation in pres_list:
        delete_presentation(presentation_id=presentation["id"])

    del_class_resp = supabase.table("classes").delete().eq("id", class_id).execute()
