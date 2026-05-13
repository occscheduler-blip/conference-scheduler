alter table public.departments add column if not exists emailed boolean not null default false;
alter table public.professors  add column if not exists emailed boolean not null default false;
alter table public.students    add column if not exists emailed boolean not null default false;
