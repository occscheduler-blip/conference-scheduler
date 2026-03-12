create table if not exists public.user_roles (
    user_id     uuid not null references auth.users(id) on delete cascade,
    role        text not null check (role in ('department_head', 'professor', 'student')),
    entity_id   uuid not null,
    assigned_at timestamptz not null default now(),
    primary key (user_id, role, entity_id)
);
