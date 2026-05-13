create table if not exists public.scheduler_jobs (
    id              uuid primary key default gen_random_uuid(),
    symposium_id    uuid not null references public.symposiums(id) on delete cascade,
    status          text not null default 'pending'
                        check (status in ('pending', 'running', 'completed', 'failed')),
    result          jsonb,
    error           text,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create index if not exists scheduler_jobs_symposium_id_idx on public.scheduler_jobs (symposium_id);
create index if not exists scheduler_jobs_created_at_idx   on public.scheduler_jobs (created_at);
