-- =============================================================================
-- 0001_init.sql — Interview Cracker (Enigma for Masai) · Phase 3 schema
--
-- Target : Supabase Postgres 15+ — cloud project "Enigma for Masai" (ref reqleijouyejjzstyjeq)
--          or the optional Phase 3B self-hosted stack. Applied with the Supabase MCP
--          `apply_migration` (name "init"); storage policies live in 0002_storage.sql.
--
-- Design
--   * Five tables — profiles, jds, sessions, turns, reports — uuid PKs, timestamptz, jsonb.
--   * Owner-only RLS on every table with `to authenticated` and `(select auth.uid())`.
--     jds/sessions/turns/reports are written ONLY by the laptop server (service role,
--     bypasses RLS): the phone gets SELECT + DELETE, never INSERT/UPDATE, so a client can
--     not forge "validated" analysis or report JSON (review finding, 2026-09-05).
--   * Guest sessions: jds/sessions have a NULLABLE user_id plus a device_id (>= 32 chars,
--     random, generated on the phone or laptop). A row with user_id IS NULL matches no
--     policy; the owner later calls claim_guest_sessions(device_id) to adopt exactly the
--     rows stamped with that device (and nothing else — review finding).
--   * sessions.jd_id is ON DELETE RESTRICT: a cascade from jds would let a JD owner delete
--     sessions they do not own if a JD row were ever shared (review finding).
--   * Idempotent where Postgres allows it (IF NOT EXISTS, CREATE OR REPLACE, DROP POLICY IF
--     EXISTS + CREATE POLICY, DROP TRIGGER IF EXISTS).
-- =============================================================================

create extension if not exists pgcrypto with schema extensions;

-- 1. profiles ------------------------------------------------------------------
create table if not exists public.profiles (
  id            uuid primary key references auth.users (id) on delete cascade,
  display_name  text,
  l1_language   text,
  created_at    timestamptz not null default now()
);
comment on table  public.profiles             is 'App-visible profile for each auth user; created by the on_auth_user_created trigger.';
comment on column public.profiles.l1_language is 'Candidate first language (hi, bn, ta, ...) for L1-aware feedback later.';

-- 2. jds -----------------------------------------------------------------------
create table if not exists public.jds (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid references auth.users (id) on delete cascade,
  device_id   text,
  title       text not null,
  raw_text    text not null,
  rubric      jsonb,
  created_at  timestamptz not null default now(),
  constraint jds_owner_or_device_chk check (user_id is not null or device_id is not null),
  constraint jds_device_id_len_chk   check (device_id is null or length(device_id) between 32 and 128)
);
comment on table  public.jds           is 'Job descriptions with the Stage-A rubric (competencies + verbatim JD quotes validated by the server substring gate).';
comment on column public.jds.device_id is 'Opaque per-install secret (>= 32 random chars). Lets a guest row be claimed later. Never shown.';
create index if not exists jds_user_id_created_at_idx on public.jds (user_id, created_at desc);
create index if not exists jds_guest_device_id_idx    on public.jds (device_id) where user_id is null;

-- 3. sessions ------------------------------------------------------------------
create table if not exists public.sessions (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid references auth.users (id) on delete cascade,
  device_id       text,
  jd_id           uuid not null references public.jds (id) on delete restrict,
  pressure        text not null,
  status          text not null default 'created',
  started_at      timestamptz,
  ended_at        timestamptz,
  device_info     jsonb not null default '{}'::jsonb,
  server_version  text,
  claimed_at      timestamptz,
  created_at      timestamptz not null default now(),
  constraint sessions_pressure_chk           check (pressure in ('warmup', 'realistic', 'tough')),
  constraint sessions_status_chk             check (status in ('created', 'live', 'completed', 'aborted')),
  constraint sessions_owner_or_device_chk    check (user_id is not null or device_id is not null),
  constraint sessions_device_id_len_chk      check (device_id is null or length(device_id) between 32 and 128),
  constraint sessions_ended_after_started_chk check (ended_at is null or started_at is null or ended_at >= started_at),
  constraint sessions_device_info_object_chk check (jsonb_typeof(device_info) = 'object')
);
comment on table  public.sessions          is 'One interview round; id minted by the laptop server and synced when online.';
comment on column public.sessions.pressure is 'warmup | realistic | tough (BLUEPRINT §5.6).';
comment on column public.sessions.status   is 'created | live | completed | aborted (BLUEPRINT §4.2).';
create index if not exists sessions_user_id_created_at_idx on public.sessions (user_id, created_at desc);
create index if not exists sessions_jd_id_idx              on public.sessions (jd_id);
create index if not exists sessions_guest_device_id_idx    on public.sessions (device_id) where user_id is null;

-- 4. turns ---------------------------------------------------------------------
create table if not exists public.turns (
  id          uuid primary key default gen_random_uuid(),
  session_id  uuid not null references public.sessions (id) on delete cascade,
  idx         integer not null,
  question    jsonb,
  transcript  text,
  words       jsonb,
  analysis    jsonb,
  clip_path   text,
  started_at  timestamptz,
  ended_at    timestamptz,
  created_at  timestamptz not null default now(),
  constraint turns_idx_nonneg_chk check (idx >= 0),
  constraint turns_session_id_idx_key unique (session_id, idx)
);
comment on table  public.turns       is 'One question + answer; owned through sessions.';
comment on column public.turns.words is 'STT word list with timestamps: [{"word":"...","start":0.42,"end":0.71}, ...].';
comment on column public.turns.clip_path is 'Path in the "clips" bucket: <user_id>/<session_id>/<idx>.wav, or guest/<session_id>/<idx>.wav before a claim.';

-- 5. reports -------------------------------------------------------------------
create table if not exists public.reports (
  id          uuid primary key default gen_random_uuid(),
  session_id  uuid not null references public.sessions (id) on delete cascade,
  report      jsonb not null,
  created_at  timestamptz not null default now(),
  constraint reports_session_id_key unique (session_id)
);
comment on table public.reports is 'Stage-D evidence-locked report (BLUEPRINT §5.5); every quote already passed the server quote gate.';

-- 6. RLS -----------------------------------------------------------------------
alter table public.profiles enable row level security;
alter table public.jds      enable row level security;
alter table public.sessions enable row level security;
alter table public.turns    enable row level security;
alter table public.reports  enable row level security;

drop policy if exists profiles_select_own on public.profiles;
create policy profiles_select_own on public.profiles for select to authenticated using (id = (select auth.uid()));
drop policy if exists profiles_insert_own on public.profiles;
create policy profiles_insert_own on public.profiles for insert to authenticated with check (id = (select auth.uid()));
drop policy if exists profiles_update_own on public.profiles;
create policy profiles_update_own on public.profiles for update to authenticated using (id = (select auth.uid())) with check (id = (select auth.uid()));
drop policy if exists profiles_delete_own on public.profiles;
create policy profiles_delete_own on public.profiles for delete to authenticated using (id = (select auth.uid()));

-- server-owned tables: clients read and delete their own rows; only the service role writes
drop policy if exists jds_select_own on public.jds;
create policy jds_select_own on public.jds for select to authenticated using (user_id = (select auth.uid()));
drop policy if exists jds_delete_own on public.jds;
create policy jds_delete_own on public.jds for delete to authenticated using (user_id = (select auth.uid()));
drop policy if exists jds_insert_own on public.jds;
drop policy if exists jds_update_own on public.jds;

drop policy if exists sessions_select_own on public.sessions;
create policy sessions_select_own on public.sessions for select to authenticated using (user_id = (select auth.uid()));
drop policy if exists sessions_delete_own on public.sessions;
create policy sessions_delete_own on public.sessions for delete to authenticated using (user_id = (select auth.uid()));
drop policy if exists sessions_insert_own on public.sessions;
drop policy if exists sessions_update_own on public.sessions;

drop policy if exists turns_select_own on public.turns;
create policy turns_select_own on public.turns for select to authenticated
  using (exists (select 1 from public.sessions s where s.id = turns.session_id and s.user_id = (select auth.uid())));
drop policy if exists turns_delete_own on public.turns;
create policy turns_delete_own on public.turns for delete to authenticated
  using (exists (select 1 from public.sessions s where s.id = turns.session_id and s.user_id = (select auth.uid())));
drop policy if exists turns_insert_own on public.turns;
drop policy if exists turns_update_own on public.turns;

drop policy if exists reports_select_own on public.reports;
create policy reports_select_own on public.reports for select to authenticated
  using (exists (select 1 from public.sessions s where s.id = reports.session_id and s.user_id = (select auth.uid())));
drop policy if exists reports_delete_own on public.reports;
create policy reports_delete_own on public.reports for delete to authenticated
  using (exists (select 1 from public.sessions s where s.id = reports.session_id and s.user_id = (select auth.uid())));
drop policy if exists reports_insert_own on public.reports;
drop policy if exists reports_update_own on public.reports;

-- 7. profile bootstrap ---------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = ''
as $$
begin
  insert into public.profiles (id, display_name, l1_language)
  values (new.id, nullif(new.raw_user_meta_data ->> 'display_name', ''), nullif(new.raw_user_meta_data ->> 'l1_language', ''))
  on conflict (id) do nothing;
  return new;
end;
$$;
revoke execute on function public.handle_new_user() from public, anon, authenticated;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users for each row execute function public.handle_new_user();

-- 8. guest claim ---------------------------------------------------------------
-- SECURITY DEFINER because the rows it adopts (user_id IS NULL) match no policy. It checks
-- auth.uid(), refuses short device ids, and touches ONLY rows stamped with this device id.
-- Advisor 0029 will flag it: accepted, see docs/DECISIONS.md.
create or replace function public.claim_guest_sessions(device_id text)
returns jsonb language plpgsql security definer set search_path = ''
as $$
declare
  v_uid         uuid := auth.uid();
  v_session_ids uuid[] := '{}';
  v_sessions    integer := 0;
  v_jds         integer := 0;
  v_turns       integer := 0;
  v_reports     integer := 0;
begin
  if v_uid is null then
    raise exception 'claim_guest_sessions: no authenticated user' using errcode = '42501';
  end if;
  if claim_guest_sessions.device_id is null or length(claim_guest_sessions.device_id) < 32 then
    raise exception 'claim_guest_sessions: device_id must be at least 32 characters' using errcode = '22023';
  end if;
  with claimed as (
    update public.sessions s set user_id = v_uid, claimed_at = now()
     where s.device_id = claim_guest_sessions.device_id and s.user_id is null
    returning s.id)
  select coalesce(array_agg(id), '{}') into v_session_ids from claimed;
  v_sessions := coalesce(array_length(v_session_ids, 1), 0);
  with claimed as (
    update public.jds j set user_id = v_uid
     where j.user_id is null and j.device_id = claim_guest_sessions.device_id
    returning j.id)
  select count(*) into v_jds from claimed;
  select count(*) into v_turns   from public.turns   t where t.session_id = any (v_session_ids);
  select count(*) into v_reports from public.reports r where r.session_id = any (v_session_ids);
  return jsonb_build_object('sessions', v_sessions, 'jds', v_jds, 'turns', v_turns, 'reports', v_reports);
end;
$$;
comment on function public.claim_guest_sessions(text) is 'Adopt every guest jds/sessions row stamped with this device_id for the calling user. RPC: supabase.rpc(''claim_guest_sessions'', {''device_id'': ...}).';
revoke execute on function public.claim_guest_sessions(text) from public, anon;
grant  execute on function public.claim_guest_sessions(text) to authenticated;
