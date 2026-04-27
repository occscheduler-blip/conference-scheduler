create table if not exists public.presentation_professors (
    id              uuid primary key default gen_random_uuid(),
    presentation_id uuid not null references public.presentations(id) on delete cascade,
    professor_id    uuid not null references public.professors(id) on delete cascade,
    unique (presentation_id, professor_id)
);

create index if not exists presentation_professors_presentation_id_idx
    on public.presentation_professors (presentation_id);

create index if not exists presentation_professors_professor_id_idx
    on public.presentation_professors (professor_id);
