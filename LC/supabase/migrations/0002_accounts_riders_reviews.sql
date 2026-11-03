-- Laraib Creative — customer accounts, rider app, reviews & notifications

-- ───────── Customer accounts (Supabase Auth email OTP) ─────────
alter table customers add column user_id uuid unique references auth.users on delete set null;
alter table measurement_profiles add column archived boolean not null default false;

-- ───────── Riders ─────────
-- Handover codes are derived server-side (HMAC of the job id with HANDOVER_SECRET),
-- so nothing secret is stored and riders cannot read a customer's code.
alter table rider_jobs drop column otp_hash;
alter table rider_jobs add column started_at timestamptz;
alter table rider_jobs add column arrived_at timestamptz;
alter table rider_jobs add column notes text;
create index rider_jobs_rider_date_idx on rider_jobs (rider_id, scheduled_date);

-- Chain of custody for fabric and sample suits
create table custody_events (
  id bigint generated always as identity primary key,
  order_id uuid not null references orders on delete cascade,
  event text not null,                 -- picked_up | received_warehouse | out_for_delivery | delivered | sample_returned
  actor_id uuid references profiles,
  rider_job_id uuid references rider_jobs,
  photo_url text,
  note text,
  created_at timestamptz not null default now()
);

create table rider_cash_closings (
  id uuid primary key default gen_random_uuid(),
  rider_id uuid not null references riders,
  closing_date date not null,
  expected int not null,
  deposited int not null,
  difference int generated always as (deposited - expected) stored,
  verified_by uuid references profiles,
  created_at timestamptz not null default now(),
  unique (rider_id, closing_date)
);

-- ───────── Reviews ─────────
alter table reviews add column customer_id uuid references customers;

-- ───────── Notifications log (WhatsApp / email) ─────────
create table notifications (
  id bigint generated always as identity primary key,
  order_id uuid references orders on delete cascade,
  channel text not null,               -- whatsapp | email
  recipient text not null,
  template text not null,
  status text not null,                -- sent | failed | skipped
  error text,
  created_at timestamptz not null default now()
);

alter table custody_events enable row level security;
alter table rider_cash_closings enable row level security;
alter table notifications enable row level security;

create policy "staff all custody_events" on custody_events for all using (is_staff()) with check (is_staff());
create policy "staff all rider_cash_closings" on rider_cash_closings for all using (is_staff()) with check (is_staff());
create policy "staff read notifications" on notifications for select using (is_staff());

-- Customer-facing reads go through server actions with the service-role key
-- after verifying the signed-in user, so no customer RLS policies are needed.
