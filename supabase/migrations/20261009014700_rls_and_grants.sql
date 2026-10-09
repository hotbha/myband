-- =============================================================================
-- MyBand.video - 03 row level security and grants
-- =============================================================================
--
-- Who is who:
--
--   * `anon` / `authenticated` are what a browser JWT maps to when the Data API
--     (PostgREST) is called directly. They are the roles these policies exist
--     for, and the only roles that get table privileges.
--   * The FastAPI service is NOT one of them. It connects with the project's
--     `postgres` connection string, a role that bypasses RLS, so these policies
--     do not protect the API from itself: every query the API issues must scope
--     by user_id explicitly. RLS here is the second line of defence for the
--     browser path (and for a future Realtime subscription), not the primary
--     authorization layer.
--
-- Design of the matrix:
--
--   * Ownership only. A row is visible when its owner column equals auth.uid();
--     visibility (`deleted_at is null`) is folded into the same predicate so a
--     soft-deleted row cannot be read through the Data API.
--   * No DELETE policies anywhere. Deletion is a soft delete performed by the
--     API, so a browser session can never destroy a row.
--   * No INSERT policies anywhere, and no INSERT grant: the API is the single
--     writer for uploads, analysis_jobs and analysis_results, and it is also the
--     writer for songs and projects (there is no browser-side Supabase client in
--     this app). Adding one later is a deliberate, reviewable migration.
--   * UPDATE is granted per column, so the privileged fields of a row (status,
--     checksums, job state, ownership) are not writable even by their owner.
--   * `(select auth.uid())` rather than a bare `auth.uid()`: the sub-select is
--     an InitPlan evaluated once per statement, while the bare call is evaluated
--     once per row and turns an index scan into a per-row function call.
-- =============================================================================

-- RLS is enabled on every table, including the internal queue. A table with RLS
-- enabled and no policy denies every non-bypassing role, which is exactly the
-- intent for storage_gc_queue.
alter table public.profiles         enable row level security;
alter table public.projects         enable row level security;
alter table public.songs            enable row level security;
alter table public.uploads          enable row level security;
alter table public.analysis_jobs    enable row level security;
alter table public.analysis_results enable row level security;
alter table public.storage_gc_queue enable row level security;

-- FORCE ROW LEVEL SECURITY is deliberately absent: it would bind the table owner
-- as well, i.e. the API and every migration, and the API is not the role RLS is
-- meant to constrain.

-- -----------------------------------------------------------------------------
-- profiles
-- -----------------------------------------------------------------------------
create policy profiles_select_own
    on public.profiles for select
    to authenticated
    using (id = (select auth.uid()) and deleted_at is null);

create policy profiles_update_own
    on public.profiles for update
    to authenticated
    using (id = (select auth.uid()) and deleted_at is null)
    with check (id = (select auth.uid()));

-- -----------------------------------------------------------------------------
-- projects
-- -----------------------------------------------------------------------------
create policy projects_select_own
    on public.projects for select
    to authenticated
    using (owner_id = (select auth.uid()) and deleted_at is null);

create policy projects_update_own
    on public.projects for update
    to authenticated
    using (owner_id = (select auth.uid()) and deleted_at is null)
    with check (owner_id = (select auth.uid()));

-- -----------------------------------------------------------------------------
-- songs
-- -----------------------------------------------------------------------------
create policy songs_select_own
    on public.songs for select
    to authenticated
    using (user_id = (select auth.uid()) and deleted_at is null);

-- WITH CHECK also proves the target project belongs to the caller, otherwise a
-- song could be filed into (or moved into) someone else's project. The subquery
-- on projects is itself filtered by that table's policy, so both layers agree.
create policy songs_update_own
    on public.songs for update
    to authenticated
    using (user_id = (select auth.uid()) and deleted_at is null)
    with check (
        user_id = (select auth.uid())
        and (
            project_id is null
            or exists (
                select 1
                from public.projects p
                where p.id = songs.project_id
                  and p.owner_id = (select auth.uid())
                  and p.deleted_at is null
            )
        )
    );

-- -----------------------------------------------------------------------------
-- uploads: readable by their owner, written only by the API
-- -----------------------------------------------------------------------------
-- The lifecycle (presign, completion, abort, expiry) is driven by the API, which
-- verifies the object really exists in R2 before it is linked to a song. So there
-- is no INSERT or UPDATE policy for a browser session.
create policy uploads_select_own
    on public.uploads for select
    to authenticated
    using (user_id = (select auth.uid()));

-- -----------------------------------------------------------------------------
-- analysis_jobs
-- -----------------------------------------------------------------------------
create policy analysis_jobs_select_own
    on public.analysis_jobs for select
    to authenticated
    using (user_id = (select auth.uid()) and deleted_at is null);

-- -----------------------------------------------------------------------------
-- analysis_results
-- -----------------------------------------------------------------------------
-- No visibility predicate of its own: a result follows its job, and deleting a
-- song soft deletes the job that hides the results with it. Enqueueing and
-- claiming are API-only, so this table is read-only for a browser session.
create policy analysis_results_select_own
    on public.analysis_results for select
    to authenticated
    using (user_id = (select auth.uid()));

-- -----------------------------------------------------------------------------
-- storage_gc_queue: no policies at all
-- -----------------------------------------------------------------------------
-- RLS is enabled above and no policy is created here, so no browser session can
-- read, write or even count the queue. Only the API and the GC worker touch it.

-- -----------------------------------------------------------------------------
-- Grants
-- -----------------------------------------------------------------------------
-- Supabase's default privileges hand `anon` and `authenticated` full access to
-- every new table in `public` (config.toml: auto_expose_new_tables, and the cloud
-- default is the same). Strip that first, then grant back only what a session
-- may do. The ALTER DEFAULT PRIVILEGES statements stop the next migration from
-- re-opening the hole when it creates a table and forgets to think about grants.
revoke all on all tables in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
revoke all on all functions in schema public from anon, authenticated, public;

alter default privileges in schema public
    revoke all on tables from anon, authenticated;
alter default privileges in schema public
    revoke execute on functions from public, anon, authenticated;

grant usage on schema public to anon, authenticated;

-- Read access for the owner's rows, subject to the policies above. `anon`
-- receives nothing: an unauthenticated request can neither read nor write.
grant select on
    public.profiles,
    public.projects,
    public.songs,
    public.uploads,
    public.analysis_jobs,
    public.analysis_results
to authenticated;

-- The only columns a user may rewrite from the browser. Everything else -
-- ownership, ids, statuses, checksums, job state, plan - belongs to the API.
--
-- `deleted_at` is deliberately absent from both. Deleting a song has to enqueue
-- its R2 objects for removal and settle whatever job is running on it, which is
-- one API transaction: a browser-side one-column UPDATE would skip all of that and
-- leave the bucket holding an object nothing references. It also happens to sit on
-- a Postgres trap - a policy whose WITH CHECK contains a subquery cannot be
-- satisfied when the same statement makes the new row invisible to the SELECT
-- policy (docs/schema.md, "Soft deletes and the browser").
grant update (display_name, avatar_url) on public.profiles to authenticated;
grant update (name) on public.projects to authenticated;
grant update (title, artist, project_id) on public.songs to authenticated;

