-- MTK Codex lead CRM.
-- Run in the Supabase SQL editor (or `supabase db push`).
-- The app talks to this table with the service-role key only, from server routes.

create table if not exists public.leads (
  id                text primary key,
  name              text not null,
  business_type     text not null default '',
  area              text not null default '',
  phone             text not null default '',
  email             text not null default '',
  website           text not null default '',
  lead_score        integer not null default 0,
  lead_tier         text not null default 'C',
  scenario          text not null default '',
  rating            numeric(3, 2),
  reviews           integer,
  google_maps_url   text not null default '',
  recommended_pitch text not null default '',
  message           text not null default '',
  status            text not null default 'new'
                    check (status in ('new', 'queued', 'contacted', 'replied', 'interested', 'won', 'lost', 'skipped')),
  channel           text not null default 'whatsapp',
  notes             text not null default '',
  last_contacted    date,
  next_followup     date,
  do_not_contact    boolean not null default false,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

create index if not exists leads_status_idx on public.leads (status);
create index if not exists leads_next_followup_idx on public.leads (next_followup);
create index if not exists leads_created_at_idx on public.leads (created_at desc);
create index if not exists leads_phone_idx on public.leads (phone);

-- Keep updated_at accurate even when rows are edited directly in Supabase.
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists leads_set_updated_at on public.leads;
create trigger leads_set_updated_at
before update on public.leads
for each row execute function public.set_updated_at();

-- Lock the table down. RLS is enabled with no policies, so only the
-- service-role key (server-side) can read or write. Never ship that key to the browser.
alter table public.leads enable row level security;

comment on table public.leads is 'MTK Codex outreach leads and CRM state. Server-only access via service role.';
