create table if not exists public.symposiums (
    id              uuid primary key default gen_random_uuid(),
    created_at      timestamptz not null default now(),
    name            text,
    rooms_available smallint not null,
    default_buffer  smallint not null default 0
);

create table if not exists public.departments (
    id                   uuid primary key default gen_random_uuid(),
    department_name      text not null,
    department_head_name text not null,
    email                text not null,
    symposium_id         uuid references public.symposiums(id)
);

create table if not exists public.classes (
    id            uuid primary key default gen_random_uuid(),
    name          text,
    department_id uuid references public.departments(id)
);

create table if not exists public.presentations (
    id         uuid primary key default gen_random_uuid(),
    title      text,
    class_id   uuid references public.classes(id),
    minutes    smallint not null,
    buffer     smallint not null,
    start_time timestamptz,
    end_time   timestamptz
);

create table if not exists public.professors (
    id       uuid primary key default gen_random_uuid(),
    name     text,
    email    text,
    class_id uuid references public.classes(id)
);

create table if not exists public.students (
    id              uuid primary key default gen_random_uuid(),
    name            text,
    email           text,
    class_id        uuid references public.classes(id),
    presentation_id uuid references public.presentations(id)
);

create table if not exists public.presenting_students (
    id              uuid primary key default gen_random_uuid(),
    presentation_id uuid references public.presentations(id),
    student_id      uuid references public.students(id)
);

create table if not exists public.timeframes (
    id         uuid primary key default gen_random_uuid(),
    linked_id  uuid not null,
    start_time timestamptz not null,
    end_time   timestamptz not null
);

create table if not exists public.requests (
    id         uuid primary key default gen_random_uuid(),
    name       text,
    email      text,
    student_id uuid references public.students(id)
);
