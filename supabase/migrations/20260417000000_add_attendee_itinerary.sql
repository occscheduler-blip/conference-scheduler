create table if not exists public.attendee_itinerary (
    attendee_id     uuid not null references public.attendees(id) on delete cascade,
    presentation_id uuid not null references public.presentations(id) on delete cascade,
    created_at      timestamptz not null default now(),
    primary key (attendee_id, presentation_id)
);

create index if not exists attendee_itinerary_attendee_idx on public.attendee_itinerary (attendee_id);
