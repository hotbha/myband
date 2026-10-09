-- =============================================================================
-- 04. The analysis headline, denormalised onto `songs`
-- =============================================================================
-- BPM and key are the two facts the product is asked for first, and the library
-- list asks for them once per row. `analysis_results` already holds them for a
-- job, but reading them from there costs a join into `analysis_jobs` plus a jsonb
-- extraction per song - which is the same argument that put `latest_job_id` on
-- this table, and the reason that pointer is denormalised too.
--
-- The worker writes both columns in the transaction that finishes a job, so a
-- song with a job that succeeded carries its headline, and a song nothing has
-- analysed yet carries nulls rather than an invented value.
--
-- `musical_key` is one text value ("A minor") rather than a (tonic, mode) pair
-- because that is how the API, the UI and the analysis itself talk about it. The
-- 24 legal spellings are asserted by the CHECK below instead of by a lookup table
-- nothing would join to.
--
-- No new index: nothing filters or sorts by either column, and the library list is
-- already served by `songs_user_id_created_at_idx`.
-- -----------------------------------------------------------------------------
alter table public.songs
    add column bpm         numeric(6, 2),
    add column musical_key text;

comment on column public.songs.bpm is
    'Tempo in beats per minute, written by the analysis worker when a job succeeds.';
comment on column public.songs.musical_key is
    'Key as "<tonic> <mode>", e.g. "A minor". One of the 24 spellings the CHECK allows.';

alter table public.songs
    -- A tempo is a positive number of beats per minute; 1000 is past anything
    -- playable and catches a detector that returned garbage.
    add constraint songs_bpm_check
        check (bpm is null or (bpm > 0 and bpm <= 1000)),
    -- Every key has a tonic and a mode, and no other spelling is storable. The
    -- analysis produces exactly this shape, so a mismatch is a bug caught at the
    -- write rather than in the UI.
    add constraint songs_musical_key_check
        check (musical_key is null or musical_key ~ '^[A-G](#|b)? (major|minor)$');
