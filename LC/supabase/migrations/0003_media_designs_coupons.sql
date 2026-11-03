-- Laraib Creative — site media, design catalog, coupons, rate limiting

-- ───────── Site media (hero, services, about…) managed from Admin → Site media ─────────
create table site_media (
  key text primary key,                 -- e.g. 'hero.main', 'service.party'
  url text not null,
  alt text not null default '',
  updated_by uuid references profiles,
  updated_at timestamptz not null default now()
);
alter table site_media enable row level security;
create policy "public read site_media" on site_media for select using (true);
create policy "staff all site_media" on site_media for all using (is_staff()) with check (is_staff());

-- ───────── Design catalog ("Lookbook") ─────────
alter table designs add column occasion text not null default 'everyday';  -- everyday | party | formal | bridal | eid
alter table designs add column description text;
alter table designs add column images text[] not null default '{}';
alter table designs add column options jsonb not null default '{}';          -- preset neckline/sleeves/daman/trouser
alter table designs add column featured boolean not null default false;
alter table designs add column sort int not null default 0;

-- ───────── Coupons ─────────
create table coupons (
  code text primary key,                -- stored upper-case
  description text,
  kind text not null check (kind in ('percent', 'flat')),
  value int not null check (value > 0),
  min_order int not null default 0,
  max_discount int,
  starts_on date,
  ends_on date,
  usage_limit int,
  used_count int not null default 0,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);
alter table coupons enable row level security;
create policy "finance all coupons" on coupons for all using (is_finance()) with check (is_finance());

alter table orders add column coupon_code text references coupons (code);

-- Atomically claims one use of a coupon; returns false when exhausted.
create or replace function claim_coupon(p_code text) returns boolean
language plpgsql security definer set search_path = public as $$
begin
  update coupons set used_count = used_count + 1
  where code = p_code and is_active
    and (usage_limit is null or used_count < usage_limit);
  return found;
end $$;
revoke execute on function claim_coupon(text) from public, anon, authenticated;

-- ───────── Rate limiting for public forms ─────────
create table rate_limits (
  id bigint generated always as identity primary key,
  bucket text not null,                  -- e.g. 'order:ip:1.2.3.4'
  created_at timestamptz not null default now()
);
create index rate_limits_bucket_idx on rate_limits (bucket, created_at desc);
alter table rate_limits enable row level security;  -- service role only

-- Records a hit and returns true while under `max_hits` within `window_seconds`.
create or replace function hit_rate_limit(p_bucket text, p_max int, p_window_seconds int) returns boolean
language plpgsql security definer set search_path = public as $$
declare hits int;
begin
  delete from rate_limits where created_at < now() - interval '1 day';
  select count(*) into hits from rate_limits
  where bucket = p_bucket and created_at > now() - make_interval(secs => p_window_seconds);
  if hits >= p_max then return false; end if;
  insert into rate_limits (bucket) values (p_bucket);
  return true;
end $$;
revoke execute on function hit_rate_limit(text, int, int) from public, anon, authenticated;
