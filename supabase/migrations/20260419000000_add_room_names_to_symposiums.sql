alter table if exists public.symposiums
    add column if not exists room_names text[];

notify pgrst, 'reload schema';
