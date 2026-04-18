create index if not exists departments_symposium_id_idx            on public.departments        (symposium_id);
create index if not exists classes_department_id_idx               on public.classes            (department_id);
create index if not exists professors_class_id_idx                 on public.professors         (class_id);
create index if not exists students_class_id_idx                   on public.students           (class_id);
create index if not exists students_presentation_id_idx            on public.students           (presentation_id);
create index if not exists presentations_class_id_idx              on public.presentations      (class_id);
create index if not exists presenting_students_presentation_id_idx on public.presenting_students (presentation_id);
create index if not exists presenting_students_student_id_idx      on public.presenting_students (student_id);
create index if not exists requests_student_id_idx                 on public.requests           (student_id);

create index if not exists timeframes_linked_id_idx                on public.timeframes         (linked_id);
