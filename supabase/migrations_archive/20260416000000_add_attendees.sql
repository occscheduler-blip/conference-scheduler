create table if not exists public.attendees (
    id         uuid primary key default gen_random_uuid(),
    email      text not null unique,
    created_at timestamptz not null default now()
);

create index if not exists attendees_email_idx on public.attendees (email);
