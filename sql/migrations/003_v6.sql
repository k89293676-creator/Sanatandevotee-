-- v6 data model delta
create table if not exists llm_usage (
  id serial primary key,
  ts timestamptz default now(),
  model text,
  purpose text,
  prompt_tokens int,
  completion_tokens int,
  status text,
  latency_ms int
);
create table if not exists llm_cache (
  key_sha256 text primary key,
  model text,
  response_json jsonb,
  created_at timestamptz default now()
);
create table if not exists knowledge_cards (
  id serial primary key,
  element text unique,
  notes text,
  confidence real,
  source_url text,
  created_at timestamptz default now()
);
create table if not exists unit_cards (
  unit_id int,
  card_id int,
  primary key (unit_id, card_id)
);
create table if not exists glossary (
  id serial primary key,
  unit_id int,
  word text,
  meaning_hi text
);
create table if not exists script_scores (
  script_id int primary key,
  total int,
  hook int,
  faithfulness int,
  clarity int,
  language int,
  structure int,
  uniqueness int,
  hard_gates_json jsonb,
  reasons_json jsonb,
  judge_model text
);
create table if not exists gen_failures (
  id serial primary key,
  ts timestamptz default now(),
  verse_id int,
  format text,
  reason text,
  http_status int
);