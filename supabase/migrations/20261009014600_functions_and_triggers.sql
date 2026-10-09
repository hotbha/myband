-- =============================================================================
-- MyBand.video - 02 functions and triggers
-- =============================================================================
--
-- Three small trigger functions, no business logic. Everything that decides
-- *whether* a row may change (job state machine, billing, ownership) lives in
-- the API, where it can be tested; these functions only keep single columns
-- honest no matter who writes the row.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- set_updated_at: stamp updated_at on every UPDATE
-- -----------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
-- SECURITY INVOKER (the default) is correct: the function only touches the row
-- the caller is already writing. search_path is pinned empty so a hostile
-- search_path cannot resolve now() to something else.
set search_path = ''
as $$
begin
    new.updated_at := now();
    return new;
end;
$$;

comment on function public.set_updated_at() is
    'BEFORE UPDATE trigger that stamps updated_at. Attached to the six tables '
    'carrying that column; storage_gc_queue stamps each state change with its '
    'own timestamp column instead.';

create trigger set_updated_at before update on public.profiles
    for each row execute function public.set_updated_at();
create trigger set_updated_at before update on public.projects
    for each row execute function public.set_updated_at();
create trigger set_updated_at before update on public.songs
    for each row execute function public.set_updated_at();
create trigger set_updated_at before update on public.uploads
    for each row execute function public.set_updated_at();
create trigger set_updated_at before update on public.analysis_jobs
    for each row execute function public.set_updated_at();
create trigger set_updated_at before update on public.analysis_results
    for each row execute function public.set_updated_at();

-- -----------------------------------------------------------------------------
-- normalize_profile: make provider metadata fit the column constraints
-- -----------------------------------------------------------------------------
-- OAuth providers are inconsistent (Google sends full_name + picture, GitHub
-- sends name + avatar_url, email signup sends nothing) and nothing stops a
-- provider from sending a 200 character name. A CHECK that can fail on signup
-- data is a signup outage, so the columns hold only a length/format assertion
-- and this BEFORE trigger does the trimming that makes them pass.
create or replace function public.normalize_profile()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    new.email := left(nullif(btrim(coalesce(new.email, '')), ''), 320);
    new.display_name := left(nullif(btrim(coalesce(new.display_name, '')), ''), 60);
    new.avatar_url := case
        when coalesce(new.avatar_url, '') like 'https://%'
            then left(btrim(new.avatar_url), 2048)
        else null
    end;
    return new;
end;
$$;

comment on function public.normalize_profile() is
    'BEFORE INSERT OR UPDATE: trims email/display_name/avatar_url, turns empty '
    'strings into NULL and drops non-https avatar URLs, so provider metadata can '
    'never violate the column CHECKs and abort a signup.';

create trigger normalize_profile before insert or update on public.profiles
    for each row execute function public.normalize_profile();

-- -----------------------------------------------------------------------------
-- handle_new_user: mirror a new auth.users row into public.profiles
-- -----------------------------------------------------------------------------
-- SECURITY DEFINER is required: the trigger fires inside GoTrue's own INSERT as
-- the auth service's role, which has no privileges on public.profiles. The
-- function is therefore pinned to an empty search_path and uses fully qualified
-- names, so it cannot be tricked into resolving `profiles` somewhere else.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    insert into public.profiles (id, email, display_name, avatar_url)
    values (
        new.id,
        new.email,
        coalesce(new.raw_user_meta_data ->> 'full_name', new.raw_user_meta_data ->> 'name'),
        coalesce(new.raw_user_meta_data ->> 'avatar_url', new.raw_user_meta_data ->> 'picture')
    )
    on conflict (id) do nothing;
    return new;
end;
$$;

comment on function public.handle_new_user() is
    'AFTER INSERT on auth.users: creates the matching public.profiles row in the '
    'same transaction as the signup, so the app never sees an account without a '
    'profile.';

create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- Backfill: accounts that predate this migration - a cloud project whose auth
-- users already exist - get their profile row now.
insert into public.profiles (id, email, display_name, avatar_url)
select
    u.id,
    u.email,
    coalesce(u.raw_user_meta_data ->> 'full_name', u.raw_user_meta_data ->> 'name'),
    coalesce(u.raw_user_meta_data ->> 'avatar_url', u.raw_user_meta_data ->> 'picture')
from auth.users u
on conflict (id) do nothing;

-- -----------------------------------------------------------------------------
-- Lock the trigger functions down
-- -----------------------------------------------------------------------------
-- PostgREST exposes every function in the exposed schema as an RPC endpoint, so
-- a SECURITY DEFINER function with the default EXECUTE to PUBLIC grant would be
-- callable by anyone holding the anon key. Trigger invocation does not check
-- EXECUTE privileges, so revoking them does not stop the triggers from firing.
revoke execute on function public.set_updated_at() from public, anon, authenticated;
revoke execute on function public.normalize_profile() from public, anon, authenticated;
revoke execute on function public.handle_new_user() from public, anon, authenticated;

