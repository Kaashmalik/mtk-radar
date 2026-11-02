-- CRM v2: deals, activity timeline, one inbox for live chat + WhatsApp + email,
-- visitor locations, push alerts and shared rate limits.
--
-- Safe to re-run. Apply after 0001-0003 in the Supabase SQL editor.
-- Every table keeps RLS on with no policies: only the server (secret key) can touch it.

-- ---------------------------------------------------------------------------
-- Leads: deals, priority, location and conversation state
-- ---------------------------------------------------------------------------

alter table public.leads
  add column if not exists source            text not null default 'scraper',
  add column if not exists starred           boolean not null default false,
  add column if not exists tags              text[] not null default '{}',
  add column if not exists deal_stage        text not null default 'none',
  add column if not exists deal_value        numeric(14, 2),
  add column if not exists deal_currency     text not null default 'PKR',
  add column if not exists last_inbound_at   timestamptz,
  add column if not exists last_outbound_at  timestamptz,
  add column if not exists unread_count      integer not null default 0,
  add column if not exists city              text not null default '',
  add column if not exists region            text not null default '',
  add column if not exists country           text not null default '',
  add column if not exists timezone          text not null default '',
  add column if not exists preferred_channel text not null default '',
  add column if not exists contact_token     text unique;

alter table public.leads drop constraint if exists leads_deal_stage_check;
alter table public.leads add constraint leads_deal_stage_check
  check (deal_stage in ('none', 'discovery', 'proposal', 'negotiation', 'in_progress', 'review', 'delivered', 'on_hold'));

create index if not exists leads_starred_idx on public.leads (starred) where starred;
create index if not exists leads_deal_stage_idx on public.leads (deal_stage) where deal_stage <> 'none';
create index if not exists leads_unread_idx on public.leads (unread_count) where unread_count > 0;
create index if not exists leads_last_inbound_idx on public.leads (last_inbound_at desc nulls last);
create index if not exists leads_email_lower_idx on public.leads (lower(email)) where email <> '';

-- ---------------------------------------------------------------------------
-- Activity timeline: every send, reply, status move, note and deal change
-- ---------------------------------------------------------------------------

create table if not exists public.lead_activities (
  id         bigserial primary key,
  lead_id    text not null references public.leads (id) on delete cascade,
  kind       text not null check (kind in (
               'created', 'import', 'status', 'note', 'followup', 'deal',
               'message_out', 'message_in', 'opt_out', 'edit')),
  summary    text not null default '',
  meta       jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists lead_activities_lead_idx on public.lead_activities (lead_id, created_at desc);
create index if not exists lead_activities_kind_idx on public.lead_activities (kind, created_at desc);

alter table public.lead_activities enable row level security;

-- Backfill one "message_out" per lead that was already contacted, so history
-- and the "sent per day" chart include sends made before this migration.
insert into public.lead_activities (lead_id, kind, summary, meta, created_at)
select l.id, 'message_out', 'First WhatsApp message sent (before activity log)',
       jsonb_build_object('channel', 'whatsapp', 'backfill', true),
       (coalesce(l.first_contacted, l.last_contacted)::timestamp + interval '12 hours') at time zone 'Asia/Karachi'
from public.leads l
where coalesce(l.first_contacted, l.last_contacted) is not null
  and not exists (select 1 from public.lead_activities a where a.lead_id = l.id and a.kind = 'message_out');

-- ---------------------------------------------------------------------------
-- Website live chat sessions
-- ---------------------------------------------------------------------------

create table if not exists public.chat_sessions (
  id                uuid primary key default gen_random_uuid(),
  token_hash        text not null unique,          -- sha256 of the visitor's secret token
  lead_id           text references public.leads (id) on delete set null,
  name              text not null default '',
  email             text not null default '',
  phone             text not null default '',
  preferred_channel text not null default '',
  page              text not null default '',
  referrer          text not null default '',
  device            text not null default '',
  city              text not null default '',
  region            text not null default '',
  country           text not null default '',
  timezone          text not null default '',
  lat               numeric(5, 1),
  lng               numeric(5, 1),
  status            text not null default 'open' check (status in ('open', 'closed')),
  unread_admin      integer not null default 0,
  last_seen_at      timestamptz not null default now(),
  visitor_typing_at timestamptz,
  admin_typing_at   timestamptz,
  last_message_at   timestamptz,
  last_notified_at  timestamptz,
  created_at        timestamptz not null default now()
);

create index if not exists chat_sessions_last_message_idx on public.chat_sessions (last_message_at desc nulls last);
create index if not exists chat_sessions_lead_idx on public.chat_sessions (lead_id);

alter table public.chat_sessions enable row level security;

-- ---------------------------------------------------------------------------
-- Messages for every channel (one inbox)
--   thread_key: 'web:<session uuid>' | 'wa:<digits>' | 'email:<address>'
-- ---------------------------------------------------------------------------

create table if not exists public.messages (
  id          bigserial primary key,
  lead_id     text references public.leads (id) on delete set null,
  channel     text not null check (channel in ('web', 'whatsapp', 'email')),
  thread_key  text not null,
  direction   text not null check (direction in ('in', 'out')),
  sender      text not null default '' check (sender in ('', 'customer', 'agent', 'bot')),
  msg_type    text not null default 'text',
  subject     text not null default '',
  body        text not null default '',
  external_id text unique,                 -- wamid / Resend email id, dedupes webhooks
  status      text not null default 'sent'
              check (status in ('received', 'sent', 'delivered', 'read', 'failed')),
  error       text not null default '',
  meta        jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now()
);

create index if not exists messages_thread_idx on public.messages (thread_key, created_at desc);
create index if not exists messages_lead_idx on public.messages (lead_id, created_at desc);
create index if not exists messages_created_idx on public.messages (created_at desc);

alter table public.messages enable row level security;

-- ---------------------------------------------------------------------------
-- Owner alerts: Web Push subscriptions for the installed admin app
-- ---------------------------------------------------------------------------

create table if not exists public.push_subscriptions (
  endpoint   text primary key,
  p256dh     text not null,
  auth       text not null,
  user_agent text not null default '',
  created_at timestamptz not null default now()
);

alter table public.push_subscriptions enable row level security;

-- Small key/value store (admin presence for the chat widget).
create table if not exists public.app_state (
  key        text primary key,
  value      jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.app_state enable row level security;

-- ---------------------------------------------------------------------------
-- Shared fixed-window rate limits (login, contact form, chat)
-- ---------------------------------------------------------------------------

create table if not exists public.rate_limits (
  key      text primary key,
  count    integer not null,
  reset_at timestamptz not null
);

alter table public.rate_limits enable row level security;

-- Counts one hit and returns true when the caller is over the limit.
create or replace function public.rate_limit_hit(p_key text, p_window_seconds integer, p_max integer)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  hits integer;
begin
  insert into public.rate_limits as r (key, count, reset_at)
  values (p_key, 1, now() + make_interval(secs => p_window_seconds))
  on conflict (key) do update set
    count    = case when r.reset_at < now() then 1 else r.count + 1 end,
    reset_at = case when r.reset_at < now() then excluded.reset_at else r.reset_at end
  returning count into hits;

  -- Opportunistic cleanup keeps the table tiny.
  if random() < 0.02 then
    delete from public.rate_limits where reset_at < now() - interval '1 day';
  end if;

  return hits > p_max;
end;
$$;

revoke all on function public.rate_limit_hit(text, integer, integer) from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- Analytics: city-level location for live visitors and the map
-- (city, region code, timezone and coordinates rounded to ~10 km)
-- ---------------------------------------------------------------------------

alter table public.page_views
  add column if not exists city     text not null default '',
  add column if not exists region   text not null default '',
  add column if not exists timezone text not null default '',
  add column if not exists lat      numeric(5, 1),
  add column if not exists lng      numeric(5, 1);

create or replace function public.analytics_summary()
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
with bounds as (
  select
    (date_trunc('day', now() at time zone 'Asia/Karachi') at time zone 'Asia/Karachi') as today_start,
    now() - interval '5 minutes' as live_start,
    now() - interval '24 hours' as day_start,
    now() - interval '7 days' as week_start,
    now() - interval '30 days' as month_start
),
live as (
  select count(distinct p.visitor_id)::int as visitors,
         count(*) filter (where p.kind = 'view')::int as views
  from public.page_views p, bounds b
  where p.created_at >= b.live_start
),
last24 as (
  select count(distinct p.visitor_id)::int as visitors,
         count(*) filter (where p.kind = 'view')::int as views
  from public.page_views p, bounds b
  where p.created_at >= b.day_start
),
today as (
  select count(distinct p.visitor_id)::int as visitors,
         count(*) filter (where p.kind = 'view')::int as views
  from public.page_views p, bounds b
  where p.created_at >= b.today_start
),
yesterday as (
  select count(distinct p.visitor_id)::int as visitors,
         count(*) filter (where p.kind = 'view')::int as views
  from public.page_views p, bounds b
  where p.created_at >= b.today_start - interval '1 day'
    and p.created_at < b.today_start
),
week as (
  select count(distinct p.visitor_id)::int as visitors,
         count(*) filter (where p.kind = 'view')::int as views
  from public.page_views p, bounds b
  where p.created_at >= b.week_start
),
month as (
  select count(distinct p.visitor_id)::int as visitors,
         count(*) filter (where p.kind = 'view')::int as views
  from public.page_views p, bounds b
  where p.created_at >= b.month_start
),
hourly as (
  select date_trunc('hour', p.created_at) as bucket,
         count(distinct p.visitor_id)::int as visitors,
         count(*) filter (where p.kind = 'view')::int as views
  from public.page_views p, bounds b
  where p.created_at >= b.day_start
  group by 1
),
daily as (
  select (p.created_at at time zone 'Asia/Karachi')::date as day,
         count(distinct p.visitor_id)::int as visitors,
         count(*) filter (where p.kind = 'view')::int as views
  from public.page_views p, bounds b
  where p.created_at >= b.today_start - interval '13 days'
  group by 1
),
pages as (
  select p.path,
         count(distinct p.visitor_id)::int as visitors,
         count(*)::int as views
  from public.page_views p, bounds b
  where p.created_at >= b.month_start and p.kind = 'view'
  group by 1
  order by views desc
  limit 8
),
referrers as (
  select coalesce(nullif(p.referrer_host, ''), 'direct') as source,
         count(distinct p.visitor_id)::int as visitors,
         count(*)::int as views
  from public.page_views p, bounds b
  where p.created_at >= b.month_start and p.kind = 'view'
  group by 1
  order by views desc
  limit 6
),
countries as (
  select coalesce(nullif(p.country, ''), 'Unknown') as country,
         count(distinct p.visitor_id)::int as visitors
  from public.page_views p, bounds b
  where p.created_at >= b.month_start and p.kind = 'view'
  group by 1
  order by visitors desc
  limit 8
),
cities as (
  select p.city, p.region, p.country,
         count(distinct p.visitor_id)::int as visitors
  from public.page_views p, bounds b
  where p.created_at >= b.month_start and p.kind = 'view' and p.city <> ''
  group by 1, 2, 3
  order by visitors desc
  limit 10
),
devices as (
  select p.device,
         count(distinct p.visitor_id)::int as visitors
  from public.page_views p, bounds b
  where p.created_at >= b.month_start and p.kind = 'view'
  group by 1
  order by visitors desc
),
-- Each visitor active in the last 5 minutes, with their latest page and place.
live_visitors as (
  select distinct on (p.visitor_id)
         p.visitor_id as id, p.path, p.city, p.region, p.country, p.timezone,
         p.device, p.lat, p.lng, p.created_at as last_seen
  from public.page_views p, bounds b
  where p.created_at >= b.live_start
  order by p.visitor_id, p.created_at desc
),
map_points as (
  select p.lat, p.lng, max(p.city) as city, max(p.country) as country,
         count(distinct p.visitor_id)::int as visitors
  from public.page_views p, bounds b
  where p.created_at >= b.day_start and p.lat is not null and p.lng is not null
  group by 1, 2
  order by visitors desc
  limit 300
),
recent as (
  select p.path, p.country, p.city, p.region, p.device, p.created_at
  from public.page_views p, bounds b
  where p.created_at >= b.week_start and p.kind = 'view'
  order by p.created_at desc
  limit 10
)
select jsonb_build_object(
  'live',          (select to_jsonb(x) from live x),
  'last24h',       (select to_jsonb(x) from last24 x),
  'today',         (select to_jsonb(x) from today x),
  'yesterday',     (select to_jsonb(x) from yesterday x),
  'week',          (select to_jsonb(x) from week x),
  'month',         (select to_jsonb(x) from month x),
  'hourly',        coalesce((select jsonb_agg(to_jsonb(h) order by h.bucket) from hourly h), '[]'::jsonb),
  'daily',         coalesce((select jsonb_agg(to_jsonb(d) order by d.day) from daily d), '[]'::jsonb),
  'pages',         coalesce((select jsonb_agg(to_jsonb(p)) from pages p), '[]'::jsonb),
  'referrers',     coalesce((select jsonb_agg(to_jsonb(r)) from referrers r), '[]'::jsonb),
  'countries',     coalesce((select jsonb_agg(to_jsonb(c)) from countries c), '[]'::jsonb),
  'cities',        coalesce((select jsonb_agg(to_jsonb(c)) from cities c), '[]'::jsonb),
  'devices',       coalesce((select jsonb_agg(to_jsonb(v)) from devices v), '[]'::jsonb),
  'live_visitors', coalesce((select jsonb_agg(to_jsonb(lv) order by lv.last_seen desc) from live_visitors lv), '[]'::jsonb),
  'map',           coalesce((select jsonb_agg(to_jsonb(m)) from map_points m), '[]'::jsonb),
  'recent',        coalesce((select jsonb_agg(to_jsonb(rc)) from recent rc), '[]'::jsonb),
  'generated_at',  now()
);
$$;

revoke all on function public.analytics_summary() from public, anon, authenticated;
