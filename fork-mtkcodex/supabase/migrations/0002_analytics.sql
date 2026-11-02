-- MTK Codex website analytics: first-party, cookieless page views.
--
-- No cookies and no client storage: the API derives a daily pseudonymous
-- visitor id from IP + user agent + ADMIN_SESSION_SECRET, so the table cannot
-- identify a person and unique counts reset each day (Asia/Karachi).
--
-- Only `kind = 'view'` rows count as page views. `kind = 'ping'` rows are
-- heartbeats from an open tab and keep the "live now" count accurate.
--
-- Apply with the Supabase SQL editor or the Management API. Server-only access.

create table if not exists public.page_views (
  id            bigserial primary key,
  path          text not null,
  referrer_host text not null default '',
  visitor_id    text not null,
  country       text not null default '',
  device        text not null default 'desktop',
  kind          text not null default 'view' check (kind in ('view', 'ping')),
  created_at    timestamptz not null default now()
);

create index if not exists page_views_created_at_idx on public.page_views (created_at desc);
create index if not exists page_views_visitor_idx on public.page_views (visitor_id, created_at desc);
create index if not exists page_views_path_idx on public.page_views (path);
create index if not exists page_views_kind_created_idx on public.page_views (kind, created_at desc);

alter table public.page_views enable row level security;

comment on table public.page_views is
  'First-party website analytics. Pseudonymous daily visitor ids, no cookies. Prune with public.analytics_prune().';

-- Everything the admin dashboard needs in one round trip.
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
  limit 6
),
devices as (
  select p.device,
         count(distinct p.visitor_id)::int as visitors
  from public.page_views p, bounds b
  where p.created_at >= b.month_start and p.kind = 'view'
  group by 1
  order by visitors desc
),
recent as (
  select p.path, p.country, p.device, p.created_at
  from public.page_views p, bounds b
  where p.created_at >= b.week_start and p.kind = 'view'
  order by p.created_at desc
  limit 10
)
select jsonb_build_object(
  'live',      (select to_jsonb(x) from live x),
  'last24h',   (select to_jsonb(x) from last24 x),
  'today',     (select to_jsonb(x) from today x),
  'yesterday', (select to_jsonb(x) from yesterday x),
  'week',      (select to_jsonb(x) from week x),
  'month',     (select to_jsonb(x) from month x),
  'hourly',    coalesce((select jsonb_agg(to_jsonb(h) order by h.bucket) from hourly h), '[]'::jsonb),
  'daily',     coalesce((select jsonb_agg(to_jsonb(d) order by d.day) from daily d), '[]'::jsonb),
  'pages',     coalesce((select jsonb_agg(to_jsonb(p)) from pages p), '[]'::jsonb),
  'referrers', coalesce((select jsonb_agg(to_jsonb(r)) from referrers r), '[]'::jsonb),
  'countries', coalesce((select jsonb_agg(to_jsonb(c)) from countries c), '[]'::jsonb),
  'devices',   coalesce((select jsonb_agg(to_jsonb(v)) from devices v), '[]'::jsonb),
  'recent',    coalesce((select jsonb_agg(to_jsonb(rc)) from recent rc), '[]'::jsonb),
  'generated_at', now()
);
$$;

revoke all on function public.analytics_summary() from public, anon, authenticated;

-- Optional maintenance: delete rows older than p_days (default 180).
create or replace function public.analytics_prune(p_days integer default 180)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  removed integer;
begin
  delete from public.page_views
  where created_at < now() - make_interval(days => greatest(p_days, 7));
  get diagnostics removed = row_count;
  return removed;
end;
$$;

revoke all on function public.analytics_prune(integer) from public, anon, authenticated;
