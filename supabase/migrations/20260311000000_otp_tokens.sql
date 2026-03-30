create table if not exists public.otp_tokens (
    id          uuid        primary key default gen_random_uuid(),
    email       text        not null,
    token_hash  text        not null,  -- SHA-256 hex digest of the 6-digit code
    role        text        not null,  -- 'department_head' | 'professor' | 'student'
    expires_at  timestamptz not null,
    used        boolean     not null default false,
    created_at  timestamptz not null default now()
);

create index if not exists otp_tokens_email_role_idx on public.otp_tokens (email, role);
