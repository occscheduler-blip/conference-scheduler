 create table if not exists public.admins (
     id            uuid primary key default gen_random_uuid(),
     email         text not null unique,
     password_hash text not null,       -- bcrypt
     created_at    timestamptz not null default (now() AT TIME ZONE 'est'::text)
 );
