-- Temporary timeframes: draft schedule before it is published to the live timeframes table.
-- symposium_id is stored directly so the whole draft for a symposium can be cleared efficiently.
create table if not exists public.temporary_timeframes (
    id           uuid primary key,
    linked_id    uuid not null,
    start_time   timestamp not null,
    end_time     timestamp not null,
    symposium_id uuid not null references public.symposiums(id) on delete cascade
);

-- Draft room assignment (mirrors presentations.room but only updated by the scheduler draft flow).
alter table public.presentations
    add column if not exists temporary_room smallint;
