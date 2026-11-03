-- Laraib Creative — initial schema
-- Run in Supabase SQL editor or with `supabase db push`.
-- Public writes (orders, inquiries, slips) go through server actions using the
-- service-role key; RLS below protects everything else.

create extension if not exists "pgcrypto";

-- ───────────────────────────── Enums ─────────────────────────────
create type staff_role as enum ('partner', 'admin', 'manager', 'support', 'tailor', 'rider', 'editor', 'accountant');
create type order_status as enum (
  'pending_payment', 'payment_verification', 'confirmed', 'awaiting_fabric', 'fabric_received',
  'cutting', 'stitching', 'finishing', 'quality_check', 'ready', 'dispatched', 'delivered',
  'alteration', 'completed', 'cancelled'
);
create type fabric_method as enum ('rider_pickup', 'courier', 'dropoff');
create type delivery_tier as enum ('standard', 'priority', 'express');
create type measurement_source as enum ('home_visit', 'sample_suit', 'standard_size', 'brand_match', 'self', 'video_call');
create type payment_method as enum ('bank', 'jazzcash', 'easypaisa', 'raast', 'cash_rider', 'cash_shop', 'gateway');
create type payment_status as enum ('pending', 'verified', 'rejected', 'partial');
create type rider_job_type as enum ('pickup', 'delivery', 'measurement', 'alteration_return');
create type rider_job_status as enum ('assigned', 'en_route', 'arrived', 'done', 'failed', 'rescheduled');
create type expense_status as enum ('pending_approval', 'approved', 'rejected');
create type partner_txn_type as enum ('capital', 'drawing', 'reimbursement', 'profit_share', 'loss_share');

-- ───────────────────────────── Staff & helpers ─────────────────────────────
create table profiles (
  id uuid primary key references auth.users on delete cascade,
  full_name text not null,
  phone text,
  role staff_role not null default 'support',
  created_at timestamptz not null default now()
);

create or replace function is_staff() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from profiles where id = auth.uid());
$$;

create or replace function is_finance() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from profiles where id = auth.uid() and role in ('partner', 'admin', 'accountant'));
$$;

-- ───────────────────────────── Customers & measurements ─────────────────────────────
create table customers (
  id uuid primary key default gen_random_uuid(),
  full_name text not null,
  phone text not null unique,
  email text,
  area text,
  address text,
  landmark text,
  lat double precision,
  lng double precision,
  tags text[] not null default '{}',
  created_at timestamptz not null default now()
);

create table standard_sizes (
  id uuid primary key default gen_random_uuid(),
  garment text not null default 'shirt',
  label text not null,                    -- XS..3XL
  data jsonb not null,                    -- { chest, waist, hip, shoulder, ... } inches
  unique (garment, label)
);

create table brand_size_map (
  id uuid primary key default gen_random_uuid(),
  brand_name text not null,
  brand_size text not null,
  standard_size_id uuid not null references standard_sizes on delete cascade,
  fit text not null default 'regular',
  notes text,
  unique (brand_name, brand_size)
);

create table measurement_profiles (
  id uuid primary key default gen_random_uuid(),
  customer_id uuid not null references customers on delete cascade,
  name text not null default 'Me',
  source measurement_source not null,
  standard_size_id uuid references standard_sizes,
  fit text not null default 'regular',
  data jsonb not null default '{}',
  notes text,
  verified boolean not null default false,
  version int not null default 1,
  created_at timestamptz not null default now()
);

-- ───────────────────────────── Catalog ─────────────────────────────
create table garment_types (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  name text not null,
  base_price int not null,
  base_days int not null default 7,
  sort int not null default 0
);

create table designs (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  title text not null,
  garment_type_id uuid references garment_types,
  image_url text,
  price_from int not null,
  tags text[] not null default '{}',
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

-- ───────────────────────────── Logistics ─────────────────────────────
create table delivery_zones (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,             -- A / B / C
  name text not null,
  areas text[] not null,
  fee int not null,
  free_above int,
  fixed_days text[]                      -- e.g. {'tue','fri'} for far zones
);

create table riders (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid references profiles,
  full_name text not null,
  phone text not null,
  cnic text,
  bike_no text,
  zones text[] not null default '{}',
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

-- ───────────────────────────── Orders ─────────────────────────────
create sequence order_no_seq start 1001;

create table orders (
  id uuid primary key default gen_random_uuid(),
  order_no text not null unique default ('LC-' || nextval('order_no_seq')),
  customer_id uuid not null references customers,
  status order_status not null default 'pending_payment',
  tier delivery_tier not null default 'standard',
  fabric_method fabric_method not null,
  zone_code text references delivery_zones (code),
  pickup_date date,
  pickup_slot text,
  promised_date date,
  measurement_profile_id uuid references measurement_profiles,
  subtotal int not null,
  urgency_fee int not null default 0,
  delivery_fee int not null default 0,
  discount int not null default 0,
  total int not null,
  paid int not null default 0,
  showcase_consent boolean not null default false,
  notes text,
  source text not null default 'website',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index orders_status_idx on orders (status);
create index orders_created_idx on orders (created_at desc);

create table order_items (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references orders on delete cascade,
  garment_slug text not null,
  design_id uuid references designs,
  options jsonb not null default '{}',             -- neckline, sleeves, daman, trouser, add-ons
  measurement_snapshot jsonb not null default '{}',
  reference_images text[] not null default '{}',
  price int not null,
  qty int not null default 1
);

create table order_status_history (
  id bigint generated always as identity primary key,
  order_id uuid not null references orders on delete cascade,
  from_status order_status,
  to_status order_status not null,
  note text,
  photo_url text,
  changed_by uuid references profiles,
  created_at timestamptz not null default now()
);

create table rider_jobs (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references orders on delete cascade,
  rider_id uuid references riders,
  type rider_job_type not null,
  scheduled_date date not null,
  slot text,
  status rider_job_status not null default 'assigned',
  otp_hash text,
  proof_photos text[] not null default '{}',
  cash_to_collect int not null default 0,
  cash_collected int not null default 0,
  fail_reason text,
  completed_at timestamptz,
  created_at timestamptz not null default now()
);

-- ───────────────────────────── Payments (manual, slip based) ─────────────────────────────
create table payment_accounts (
  id uuid primary key default gen_random_uuid(),
  type payment_method not null,
  title text not null,
  bank_name text,
  account_no text not null,
  iban text,
  qr_url text,
  is_active boolean not null default true,
  sort int not null default 0
);

create table payments (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references orders on delete cascade,
  method payment_method not null,
  account_id uuid references payment_accounts,
  amount int not null,
  kind text not null default 'advance',   -- advance | balance | full
  txn_id text,
  sender_name text,
  proof_url text,
  submitted_via text not null default 'website', -- website | whatsapp | rider | shop
  status payment_status not null default 'pending',
  reject_reason text,
  verified_by uuid references profiles,
  verified_at timestamptz,
  created_at timestamptz not null default now()
);
create unique index payments_txn_unique on payments (method, txn_id) where txn_id is not null;

-- ───────────────────────────── Social proof & leads ─────────────────────────────
create table reviews (
  id uuid primary key default gen_random_uuid(),
  order_id uuid unique references orders,
  customer_name text not null,
  area text,
  rating int not null check (rating between 1 and 5),
  fit int check (fit between 1 and 5),
  finishing int check (finishing between 1 and 5),
  on_time int check (on_time between 1 and 5),
  body text not null,
  media text[] not null default '{}',
  status text not null default 'pending',  -- pending | published | hidden
  reply text,
  featured boolean not null default false,
  created_at timestamptz not null default now()
);

create table gallery_items (
  id uuid primary key default gen_random_uuid(),
  order_id uuid references orders,
  title text not null,
  image_url text not null,
  before_url text,
  tags text[] not null default '{}',
  consent_verified boolean not null default false,
  featured boolean not null default false,
  created_at timestamptz not null default now()
);

create table inquiries (
  id uuid primary key default gen_random_uuid(),
  type text not null default 'general',    -- general | bridal | bulk | alteration
  name text not null,
  phone text not null,
  message text not null,
  images text[] not null default '{}',
  status text not null default 'new',      -- new | contacted | quoted | converted | closed
  quote_amount int,
  created_at timestamptz not null default now()
);

-- ───────────────────────────── Finance & partnership ─────────────────────────────
create table partners (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid references profiles,
  name text not null,
  role text not null,                      -- tech_online | stitching
  share_percent numeric(5,2) not null default 50
);

create table money_accounts (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  type text not null,                      -- bank | jazzcash | easypaisa | cash_box | rider_cash
  opening_balance int not null default 0
);

create table expense_categories (
  id uuid primary key default gen_random_uuid(),
  grp text not null,
  name text not null,
  monthly_budget int,
  is_active boolean not null default true,
  unique (grp, name)
);

create table expenses (
  id uuid primary key default gen_random_uuid(),
  spent_on date not null default current_date,
  category_id uuid not null references expense_categories,
  amount int not null check (amount > 0),
  account_id uuid references money_accounts,
  paid_by_partner_id uuid references partners,
  vendor text,
  order_id uuid references orders,
  receipt_url text,
  notes text,
  status expense_status not null default 'approved',
  added_by uuid references profiles,
  approved_by uuid references profiles,
  created_at timestamptz not null default now()
);
create index expenses_spent_idx on expenses (spent_on);

create table partner_transactions (
  id uuid primary key default gen_random_uuid(),
  partner_id uuid not null references partners,
  type partner_txn_type not null,
  amount int not null,
  happened_on date not null default current_date,
  notes text,
  settlement_month text,
  created_at timestamptz not null default now()
);

create table monthly_settlements (
  month text primary key,                  -- '2026-11'
  revenue int not null,
  expenses int not null,
  net_profit int not null,
  reserve int not null default 0,
  distributable int not null,
  share_a int not null,
  share_b int not null,
  status text not null default 'draft',    -- draft | closed
  approved_a_at timestamptz,
  approved_b_at timestamptz,
  created_at timestamptz not null default now()
);

create table audit_logs (
  id bigint generated always as identity primary key,
  actor_id uuid references profiles,
  action text not null,
  entity text not null,
  entity_id text,
  diff jsonb,
  created_at timestamptz not null default now()
);

-- ───────────────────────────── Monthly P&L view ─────────────────────────────
create or replace view monthly_pnl as
with rev as (
  select to_char(coalesce(verified_at, created_at), 'YYYY-MM') as month, sum(amount)::int as revenue
  from payments where status in ('verified', 'partial') group by 1
), exp as (
  select to_char(spent_on, 'YYYY-MM') as month, sum(amount)::int as expenses
  from expenses where status = 'approved' group by 1
)
select coalesce(rev.month, exp.month) as month,
       coalesce(revenue, 0) as revenue,
       coalesce(expenses, 0) as expenses,
       coalesce(revenue, 0) - coalesce(expenses, 0) as net_profit
from rev full outer join exp on rev.month = exp.month;

-- ───────────────────────────── RLS ─────────────────────────────
alter table profiles enable row level security;
alter table customers enable row level security;
alter table standard_sizes enable row level security;
alter table brand_size_map enable row level security;
alter table measurement_profiles enable row level security;
alter table garment_types enable row level security;
alter table designs enable row level security;
alter table delivery_zones enable row level security;
alter table riders enable row level security;
alter table orders enable row level security;
alter table order_items enable row level security;
alter table order_status_history enable row level security;
alter table rider_jobs enable row level security;
alter table payment_accounts enable row level security;
alter table payments enable row level security;
alter table reviews enable row level security;
alter table gallery_items enable row level security;
alter table inquiries enable row level security;
alter table partners enable row level security;
alter table money_accounts enable row level security;
alter table expense_categories enable row level security;
alter table expenses enable row level security;
alter table partner_transactions enable row level security;
alter table monthly_settlements enable row level security;
alter table audit_logs enable row level security;

-- public catalog reads
create policy "public read sizes" on standard_sizes for select using (true);
create policy "public read brand map" on brand_size_map for select using (true);
create policy "public read garments" on garment_types for select using (true);
create policy "public read designs" on designs for select using (is_active);
create policy "public read zones" on delivery_zones for select using (true);
create policy "public read accounts" on payment_accounts for select using (is_active);
create policy "public read reviews" on reviews for select using (status = 'published');
create policy "public read gallery" on gallery_items for select using (consent_verified);

-- staff: operational tables
create policy "staff self profile" on profiles for select using (id = auth.uid() or is_staff());
do $$
declare t text;
begin
  foreach t in array array['customers','measurement_profiles','riders','orders','order_items','order_status_history',
                           'rider_jobs','payments','inquiries','reviews','gallery_items','designs','garment_types',
                           'standard_sizes','brand_size_map','delivery_zones','payment_accounts']
  loop
    execute format('create policy "staff all %1$s" on %1$I for all using (is_staff()) with check (is_staff())', t);
  end loop;
  -- finance tables: partners / admin / accountant only
  foreach t in array array['partners','money_accounts','expense_categories','expenses','partner_transactions',
                           'monthly_settlements','audit_logs']
  loop
    execute format('create policy "finance all %1$s" on %1$I for all using (is_finance()) with check (is_finance())', t);
  end loop;
end $$;

-- ───────────────────────────── Seed data ─────────────────────────────
insert into garment_types (slug, name, base_price, base_days, sort) values
  ('simple', 'Simple Suit', 1800, 7, 1),
  ('designer', 'Designer Suit', 2800, 8, 2),
  ('party', 'Party / Fancy Wear', 4500, 10, 3),
  ('kurti', 'Kurti / Short Shirt', 1400, 6, 4),
  ('maxi', 'Maxi / Frock', 5500, 12, 5),
  ('bridal', 'Bridal & Formal', 15000, 21, 6);

insert into delivery_zones (code, name, areas, fee, free_above, fixed_days) values
  ('A', 'Core', array['Garhi Shahu','Shadman','GOR','Upper Mall','Cantt','Cavalry Ground','Gulberg'], 150, 5000, null),
  ('B', 'Prime', array['DHA Phase 1-6','Askari','Model Town','Garden Town','Faisal Town','Walton'], 250, 8000, null),
  ('C', 'Extended', array['DHA Phase 7-9','Johar Town','Wapda Town','Bahria Town','Valencia','Lake City'], 400, 12000, array['tue','fri']);

insert into standard_sizes (garment, label, data) values
  ('shirt', 'XS',  '{"chest":34,"waist":30,"hip":37,"shoulder":13.5,"armhole":7.5,"sleeve":21,"length":38}'),
  ('shirt', 'S',   '{"chest":36,"waist":32,"hip":39,"shoulder":14,"armhole":8,"sleeve":21.5,"length":39}'),
  ('shirt', 'M',   '{"chest":38,"waist":34,"hip":41,"shoulder":14.5,"armhole":8.5,"sleeve":22,"length":40}'),
  ('shirt', 'L',   '{"chest":40,"waist":36,"hip":43,"shoulder":15,"armhole":9,"sleeve":22.5,"length":40}'),
  ('shirt', 'XL',  '{"chest":42,"waist":38,"hip":45,"shoulder":15.5,"armhole":9.5,"sleeve":23,"length":41}'),
  ('shirt', 'XXL', '{"chest":44,"waist":40,"hip":47,"shoulder":16,"armhole":10,"sleeve":23,"length":41}'),
  ('shirt', '3XL', '{"chest":46,"waist":42,"hip":49,"shoulder":16.5,"armhole":10.5,"sleeve":23.5,"length":42}');
-- NOTE: placeholder chart — finalise with the master tailor after measuring benchmark brand garments.

insert into expense_categories (grp, name) values
  ('Production','Karigar wages'),('Production','Threads & lining'),('Production','Buttons, lace & trims'),
  ('Production','Machine repair'),('Production','Machines & tools'),
  ('Delivery','Rider salaries'),('Delivery','Fuel allowance'),('Delivery','Courier charges'),('Delivery','Packaging & bags'),
  ('Premises','Rent'),('Premises','Electricity (LESCO)'),('Premises','Gas & water'),('Premises','Internet'),
  ('Staff','Staff salaries'),('Staff','Eid bonus'),('Staff','Staff meals'),
  ('Marketing','Meta / Instagram ads'),('Marketing','TikTok ads'),('Marketing','Photography'),('Marketing','Printing'),
  ('Technology','Domain & hosting'),('Technology','Software subscriptions'),
  ('Admin & legal','Bank & wallet charges'),('Admin & legal','Accountant'),('Admin & legal','Taxes'),
  ('Losses','Fabric compensation'),('Losses','Rework'),('Other','Miscellaneous');

insert into partners (name, role, share_percent) values
  ('Tech & Online Partner', 'tech_online', 50),
  ('Stitching Partner', 'stitching', 50);

insert into money_accounts (name, type) values
  ('Business bank account', 'bank'), ('JazzCash', 'jazzcash'), ('Easypaisa', 'easypaisa'), ('Shop cash box', 'cash_box');
