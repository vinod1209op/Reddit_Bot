-- Indexes + dedupe guard for account health tables

-- Prevent duplicate status events (same account/status/source/timestamp)
create unique index if not exists account_status_events_unique
  on public.account_status_events (account_name, status, source, detected_at);

-- Speed up dashboard queries
create index if not exists account_status_events_account_detected
  on public.account_status_events (account_name, detected_at desc);

create index if not exists account_health_updated_at
  on public.account_health (updated_at desc);

create index if not exists scan_runs_account_time
  on public.scan_runs (account, timestamp_utc desc);
