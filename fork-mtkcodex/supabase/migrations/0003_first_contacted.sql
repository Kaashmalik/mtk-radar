-- Track the *first* outreach message separately from the latest touch.
--
-- `last_contacted` moves forward on every follow-up, so it cannot answer
-- "how many first messages did we send today". `first_contacted` is stamped
-- once, by a trigger, the first time a lead gets a contact date.

alter table public.leads add column if not exists first_contacted date;

-- Backfill from existing history (best available signal).
update public.leads
set first_contacted = last_contacted
where first_contacted is null
  and last_contacted is not null;

create or replace function public.leads_track_first_contact()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if new.first_contacted is null and new.last_contacted is not null then
    new.first_contacted := new.last_contacted;
  end if;
  return new;
end;
$$;

drop trigger if exists leads_first_contacted on public.leads;
create trigger leads_first_contacted
  before insert or update of last_contacted on public.leads
  for each row execute function public.leads_track_first_contact();

create index if not exists leads_first_contacted_idx on public.leads (first_contacted desc);
