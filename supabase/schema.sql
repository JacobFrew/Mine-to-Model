-- Mine to Model: watchlist & notes
-- Paste this into Supabase → SQL Editor → New query → Run.

create table if not exists public.watchlist (
  user_id     uuid not null default auth.uid() references auth.users(id) on delete cascade,
  company_id  text not null,          -- the company's id on the map, e.g. "cameco"
  ticker      text,                   -- e.g. "CCJ"
  buy_price   numeric,                -- Telegram alert when the price is at or below this
  notes       text,
  alerted_on  date,                   -- set by the daily job when an alert is sent
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  primary key (user_id, company_id)
);

-- Row Level Security: each signed-in person only sees and edits their own rows.
alter table public.watchlist enable row level security;

drop policy if exists "read own watchlist" on public.watchlist;
create policy "read own watchlist" on public.watchlist
  for select using (auth.uid() = user_id);

drop policy if exists "add to own watchlist" on public.watchlist;
create policy "add to own watchlist" on public.watchlist
  for insert with check (auth.uid() = user_id);

drop policy if exists "edit own watchlist" on public.watchlist;
create policy "edit own watchlist" on public.watchlist
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "remove from own watchlist" on public.watchlist;
create policy "remove from own watchlist" on public.watchlist
  for delete using (auth.uid() = user_id);

-- The daily GitHub job uses the service role key, which bypasses these rules
-- so it can read buy prices and mark alerts as sent.
