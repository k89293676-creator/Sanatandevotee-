-- v4 additive migration
alter table relay_queue add column if not exists handed_off_at timestamptz;
alter table relay_queue add column if not exists acked_at timestamptz;
alter table relay_queue add column if not exists ack_status text;
alter table relay_queue add column if not exists make_run_note text;
-- extend status allowed values (app-level): handed_off, failed_in_make, unknown
alter table relay_state add column if not exists value jsonb;
-- local reels columns handled in sqlite separately