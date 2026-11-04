-- InterviewOS: Supabase/Postgres schema
-- Run this once in Supabase Dashboard > SQL Editor > New query.

create table if not exists public.scheduled_interviews (
  id uuid primary key,
  invite_token text unique not null,
  candidate_name text not null,
  candidate_email text not null,
  password_hash text not null,
  scheduled_at timestamptz not null,
  setup_json jsonb not null,
  status text not null default 'scheduled',
  session_id uuid,
  report_json jsonb,
  report_share_token text unique,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz
);

create table if not exists public.interview_sessions (
  id uuid primary key,
  interview_id uuid references public.scheduled_interviews(id) on delete set null,
  candidate_name text,
  setup_json jsonb not null,
  status text not null default 'created',
  report_json jsonb,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create table if not exists public.admin_sessions (
  token text primary key,
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);

create index if not exists scheduled_interviews_invite_token_idx on public.scheduled_interviews(invite_token);
create index if not exists scheduled_interviews_share_token_idx on public.scheduled_interviews(report_share_token);
create index if not exists interview_sessions_interview_id_idx on public.interview_sessions(interview_id);
create index if not exists admin_sessions_expiry_idx on public.admin_sessions(expires_at);

-- All client access goes through the FastAPI API. Enable RLS so public
-- browser requests cannot read candidate data directly. The server uses the
-- Supabase secret key and performs its own HR/invitation authorization.
alter table public.scheduled_interviews enable row level security;
alter table public.interview_sessions enable row level security;
alter table public.admin_sessions enable row level security;
