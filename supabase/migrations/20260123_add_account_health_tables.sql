-- Account health + reporting tables for dashboard/analytics

create table if not exists accounts (
  id uuid primary key default gen_random_uuid(),
  account_name text unique not null,
  display_name text,
  status text default 'unknown',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists account_health (
  account_name text primary key references accounts(account_name) on delete cascade,
  current_status text not null default 'unknown',
  last_success_at timestamptz,
  last_failure_at timestamptz,
  last_failure_reason text,
  captcha_count_7d int default 0,
  rate_limit_count_7d int default 0,
  consecutive_failures int default 0,
  last_status_change_at timestamptz,
  updated_at timestamptz default now()
);

create table if not exists account_status_events (
  id bigint generated always as identity primary key,
  account_name text not null references accounts(account_name) on delete cascade,
  status text not null,
  reason text,
  source text,
  detected_at timestamptz default now()
);

create table if not exists session_runs (
  id bigint generated always as identity primary key,
  run_id text not null,
  account_name text references accounts(account_name) on delete set null,
  mode text,
  start_at timestamptz,
  end_at timestamptz,
  duration_s int,
  status text,
  error text,
  actions_summary jsonb,
  created_at timestamptz default now()
);

create index if not exists idx_session_runs_account on session_runs(account_name);

create table if not exists session_actions (
  id bigint generated always as identity primary key,
  run_id text not null,
  account_name text references accounts(account_name) on delete set null,
  votes int default 0,
  saves int default 0,
  follows int default 0,
  posts_viewed int default 0,
  subreddits_browsed int default 0,
  scroll_events int default 0,
  click_failures int default 0,
  created_at timestamptz default now()
);

create index if not exists idx_session_actions_run on session_actions(run_id);

create table if not exists scan_summary (
  id bigint generated always as identity primary key,
  run_id text not null,
  account_name text references accounts(account_name) on delete set null,
  subreddit text not null,
  scanned_count int default 0,
  matched_count int default 0,
  elapsed_ms int,
  created_at timestamptz default now()
);

create index if not exists idx_scan_summary_run on scan_summary(run_id);

create table if not exists scan_matches (
  id bigint generated always as identity primary key,
  run_id text not null,
  account_name text references accounts(account_name) on delete set null,
  subreddit text not null,
  post_id_hash text not null,
  matched_keywords text[],
  match_ts timestamptz default now()
);

create index if not exists idx_scan_matches_run on scan_matches(run_id);

create table if not exists ci_runs (
  id bigint generated always as identity primary key,
  run_id text,
  workflow text,
  job text,
  commit_sha text,
  started_at timestamptz,
  ended_at timestamptz,
  exit_code int,
  logs_path text,
  created_at timestamptz default now()
);

create table if not exists config_snapshots (
  id bigint generated always as identity primary key,
  config_hash text not null,
  source_file text,
  summary jsonb,
  created_at timestamptz default now()
);
