-- Relay schema (Supabase Postgres)
create table if not exists relay_queue (
  id uuid primary key default gen_random_uuid(),
  series_day int,
  format text,
  verse_ref text,
  caption text,
  first_comment text,
  hashtags text[],
  video_url text,
  cover_url text,
  yt_title text,
  yt_description text,
  duration_s real,
  scheduled_at timestamptz not null,
  is_reserve boolean default false,
  status text not null default 'scheduled',
  claimed_by text,
  claimed_at timestamptz,
  ig_container_id text,
  ig_media_id text,
  permalink text,
  yt_video_id text,
  yt_status text,
  attempts int default 0,
  last_error text,
  hook_style text,
  visual_style text,
  voice text,
  slot_label text,
  published_at timestamptz
);

create table if not exists relay_comments (
  ig_comment_id text primary key,
  media_id text not null,
  username text,
  text text,
  lang text,
  received_at timestamptz default now(),
  status text not null default 'new',
  reply_after timestamptz,
  reply_text text,
  replied_at timestamptz,
  skip_reason text
);

create table if not exists relay_insights (
  media_id text not null,
  fetched_at timestamptz default now(),
  hours_since_post real,
  views int,
  reach int,
  likes int,
  comments int,
  shares int,
  saves int,
  avg_watch_ms real,
  total_watch_ms real,
  completion_ratio real,
  raw jsonb
);

create table if not exists relay_account (
  day date primary key,
  followers int,
  yt_subscribers int,
  yt_views_90d int
);

create table if not exists relay_state (
  key text primary key,
  value jsonb not null,
  updated_at timestamptz default now()
);

create table if not exists relay_events (
  ts timestamptz default now(),
  level text,
  component text,
  message text
);

-- claim function
create or replace function claim_due_reel(worker text)
returns setof relay_queue as $$
declare r relay_queue;
begin
  -- re-claim stuck rows over 20 min
  update relay_queue set status='scheduled', claimed_by=null, claimed_at=null
  where status='claimed' and claimed_at < now() - interval '20 minutes';
  -- claim one due row
  select * into r from relay_queue
  where status='scheduled' and scheduled_at <= now()
  order by scheduled_at asc
  for update skip locked
  limit 1;
  if r.id is not null then
    update relay_queue set status='claimed', claimed_by=worker, claimed_at=now()
    where id=r.id;
    select * into r from relay_queue where id=r.id;
  end if;
  return next r;
end;
$$ language plpgsql;