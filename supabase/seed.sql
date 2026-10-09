-- =============================================================================
-- MyBand.video - local development seed
-- =============================================================================
--
-- Loaded by `supabase db reset` (config.toml -> db.seed.sql_paths). It is never
-- applied to a deployed project: `supabase db push` does not run seeds, and the
-- account below is a fixed, well-known credential.
--
-- Ids are literal UUIDv7 values because the application generates its own keys -
-- there is no database default to fall back on (see migration 01). The literals
-- are readable on purpose:
--
--   0192f5c0-...  the demo user        0192f5c5-...  analysis results
--   0192f5c1-...  projects             0192f5c6-...  storage gc queue
--   0192f5c2-...  songs                0192f5c3-...  uploads
--   0192f5c4-...  analysis jobs
--
-- Demo login: demo@myband.local / password123
-- =============================================================================

-- The seed needs bcrypt for the demo password. GoTrue hashes passwords itself
-- (golang.org/x/crypto/bcrypt), so nothing else in the stack needs pgcrypto -
-- this line exists only so the seed can be re-run and re-derived locally.
create extension if not exists pgcrypto with schema extensions;

-- -----------------------------------------------------------------------------
-- Demo account
-- -----------------------------------------------------------------------------
-- auth.identities is not optional: GoTrue resolves a password login through the
-- identity row, so a user without one cannot sign in.
insert into auth.users (
    instance_id,
    id,
    aud,
    role,
    email,
    encrypted_password,
    email_confirmed_at,
    -- GoTrue scans these into non-nullable Go strings, so NULL is not an option:
    -- leaving any of them unset makes password login fail with "converting NULL to
    -- string is unsupported" and an HTTP 500. This is the single most common way a
    -- hand-written seed produces an account that cannot sign in.
    confirmation_token,
    recovery_token,
    email_change,
    email_change_token_new,
    email_change_token_current,
    reauthentication_token,
    phone_change,
    phone_change_token,
    raw_app_meta_data,
    raw_user_meta_data,
    created_at,
    updated_at
)
values (
    '00000000-0000-0000-0000-000000000000',
    '0192f5c0-0000-7000-8000-000000000001',
    'authenticated',
    'authenticated',
    'demo@myband.local',
    extensions.crypt('password123', extensions.gen_salt('bf')),
    now() - interval '30 days',
    '', '', '', '', '', '', '', '',
    '{"provider": "email", "providers": ["email"]}'::jsonb,
    '{"full_name": "Demo Producer"}'::jsonb,
    now() - interval '30 days',
    now() - interval '30 days'
);

insert into auth.identities (
    provider_id,
    user_id,
    identity_data,
    provider,
    last_sign_in_at,
    created_at,
    updated_at
)
values (
    '0192f5c0-0000-7000-8000-000000000001',
    '0192f5c0-0000-7000-8000-000000000001',
    jsonb_build_object('sub', '0192f5c0-0000-7000-8000-000000000001',
                       'email', 'demo@myband.local'),
    'email',
    now() - interval '1 day',
    now() - interval '30 days',
    now() - interval '30 days'
);

-- public.profiles is filled by the on_auth_user_created trigger, so there is no
-- insert here. Touching the row proves the trigger ran.
update public.profiles set plan = 'pro'
where id = '0192f5c0-0000-7000-8000-000000000001';

-- -----------------------------------------------------------------------------
-- Projects
-- -----------------------------------------------------------------------------
insert into public.projects (id, owner_id, name, created_at) values
    ('0192f5c1-0000-7000-8000-000000000001',
     '0192f5c0-0000-7000-8000-000000000001', 'Live Set 2026', now() - interval '21 days'),
    ('0192f5c1-0000-7000-8000-000000000002',
     '0192f5c0-0000-7000-8000-000000000001', 'Demos', now() - interval '9 days');

-- -----------------------------------------------------------------------------
-- Songs
-- -----------------------------------------------------------------------------
-- repeat('9c', 32) is a fake, deterministic sha256 (64 hex characters) - good
-- enough to exercise the checksum CHECKs without inventing a real file.
insert into public.songs (
    id, user_id, project_id, title, artist, duration_ms,
    source_object_key, source_checksum, source_bytes, source_content_type, created_at
) values
    ('0192f5c2-0000-7000-8000-000000000001',
     '0192f5c0-0000-7000-8000-000000000001',
     '0192f5c1-0000-7000-8000-000000000001',
     'Midnight Drive', 'Demo Producer', 214500,
     'users/0192f5c0-0000-7000-8000-000000000001/uploads/0192f5c3-0000-7000-8000-000000000001/midnight-drive.wav',
     repeat('9c', 32), 37964712, 'audio/wav', now() - interval '20 days'),
    ('0192f5c2-0000-7000-8000-000000000002',
     '0192f5c0-0000-7000-8000-000000000001',
     '0192f5c1-0000-7000-8000-000000000001',
     'Basement Take 4', 'Demo Producer', 183000,
     'users/0192f5c0-0000-7000-8000-000000000001/uploads/0192f5c3-0000-7000-8000-000000000002/basement-take-4.mp3',
     repeat('4d', 32), 4382190, 'audio/mpeg', now() - interval '19 days'),
    ('0192f5c2-0000-7000-8000-000000000003',
     '0192f5c0-0000-7000-8000-000000000001',
     '0192f5c1-0000-7000-8000-000000000002',
     'Untitled Sketch', null, null,
     'users/0192f5c0-0000-7000-8000-000000000001/uploads/0192f5c3-0000-7000-8000-000000000003/untitled-sketch.flac',
     repeat('7a', 32), 58201744, 'audio/flac', now() - interval '8 days');

-- -----------------------------------------------------------------------------
-- Uploads: one claimed row per song, plus one that is still in flight
-- -----------------------------------------------------------------------------
insert into public.uploads (
    id, user_id, song_id, object_key, status, declared_bytes, declared_content_type,
    bytes_actual, content_type_actual, checksum_actual, etag_actual,
    expires_at, completed_at, created_at
) values
    (
        '0192f5c3-0000-7000-8000-000000000001',
        '0192f5c0-0000-7000-8000-000000000001',
        '0192f5c2-0000-7000-8000-000000000001',
        'users/0192f5c0-0000-7000-8000-000000000001/uploads/0192f5c3-0000-7000-8000-000000000001/midnight-drive.wav',
        'completed', 37964712, 'audio/wav',
        37964712, 'audio/wav', repeat('9c', 32), '8a1c1f0d5b7e4a2f9c3d6e8b0a4f2c7d',
        now() - interval '19 days', now() - interval '20 days' + interval '5 minutes',
        now() - interval '20 days'
    ),
    (
        '0192f5c3-0000-7000-8000-000000000002',
        '0192f5c0-0000-7000-8000-000000000001',
        '0192f5c2-0000-7000-8000-000000000002',
        'users/0192f5c0-0000-7000-8000-000000000001/uploads/0192f5c3-0000-7000-8000-000000000002/basement-take-4.mp3',
        'completed', 4382190, 'audio/mpeg',
        4382190, 'audio/mpeg', repeat('4d', 32), '0b7f9e2c41a85d36f0c2e7d19a4b6c83',
        now() - interval '18 days', now() - interval '19 days' + interval '2 minutes',
        now() - interval '19 days'
    ),
    (
        '0192f5c3-0000-7000-8000-000000000003',
        '0192f5c0-0000-7000-8000-000000000001',
        '0192f5c2-0000-7000-8000-000000000003',
        'users/0192f5c0-0000-7000-8000-000000000001/uploads/0192f5c3-0000-7000-8000-000000000003/untitled-sketch.flac',
        'completed', 58201744, 'audio/flac',
        58201744, 'audio/flac', repeat('7a', 32), 'd2e5c804f6b91a37e0d4c58127ab93f6',
        now() - interval '7 days', now() - interval '8 days' + interval '9 minutes',
        now() - interval '8 days'
    ),
    (
        -- In flight: expires_at is in the past an hour from now, so the sweeper
        -- has something to find.
        '0192f5c3-0000-7000-8000-000000000004',
        '0192f5c0-0000-7000-8000-000000000001',
        null,
        'users/0192f5c0-0000-7000-8000-000000000001/uploads/0192f5c3-0000-7000-8000-000000000004/half-track.wav',
        'pending', 24861234, 'audio/wav',
        null, null, null, null,
        now() + interval '1 hour', null, now() - interval '10 minutes'
    );

-- -----------------------------------------------------------------------------
-- Analysis jobs: succeeded, in flight, and failed
-- -----------------------------------------------------------------------------
insert into public.analysis_jobs (
    id, user_id, song_id, status, pipeline_version, source_object_key, source_checksum,
    attempts, compute_seconds, runpod_job_id, error_code, error_message,
    dispatched_at, started_at, finished_at, heartbeat_at, created_at
) values
    (
        '0192f5c4-0000-7000-8000-000000000001',
        '0192f5c0-0000-7000-8000-000000000001',
        '0192f5c2-0000-7000-8000-000000000001',
        'succeeded', '0.1.0',
        'users/0192f5c0-0000-7000-8000-000000000001/uploads/0192f5c3-0000-7000-8000-000000000001/midnight-drive.wav',
        repeat('9c', 32),
        1, 42.318, 'rp_2f9c31a4', null, null,
        now() - interval '20 days' + interval '2 minutes',
        now() - interval '20 days' + interval '3 minutes',
        now() - interval '20 days' + interval '3 minutes 42 seconds',
        now() - interval '20 days' + interval '3 minutes 30 seconds',
        now() - interval '20 days'
    ),
    (
        '0192f5c4-0000-7000-8000-000000000002',
        '0192f5c0-0000-7000-8000-000000000001',
        '0192f5c2-0000-7000-8000-000000000002',
        'running', '0.1.0',
        'users/0192f5c0-0000-7000-8000-000000000001/uploads/0192f5c3-0000-7000-8000-000000000002/basement-take-4.mp3',
        repeat('4d', 32),
        1, null, 'rp_7b02de55', null, null,
        now() - interval '4 minutes', now() - interval '3 minutes', null,
        now() - interval '30 seconds',
        now() - interval '5 minutes'
    ),
    (
        '0192f5c4-0000-7000-8000-000000000003',
        '0192f5c0-0000-7000-8000-000000000001',
        '0192f5c2-0000-7000-8000-000000000003',
        'failed', '0.1.0',
        'users/0192f5c0-0000-7000-8000-000000000001/uploads/0192f5c3-0000-7000-8000-000000000003/untitled-sketch.flac',
        repeat('7a', 32),
        1, null, 'rp_5ad9c0f1', 'decode_error',
        'ffmpeg could not decode the source object (unsupported codec).',
        now() - interval '8 days' + interval '1 minute',
        now() - interval '8 days' + interval '90 seconds',
        now() - interval '8 days' + interval '2 minutes',
        now() - interval '8 days' + interval '100 seconds',
        now() - interval '8 days'
    );

-- -----------------------------------------------------------------------------
-- Results of the succeeded job (the running and failed ones produced none)
-- -----------------------------------------------------------------------------
-- Two shapes are exercised here: `summary` only (bpm, key, sections) and
-- `summary` + an R2 object for the full payload (chords, midi). payload_bytes is
-- the writer's measurement of `summary`, capped at 8192 by a CHECK.
insert into public.analysis_results (
    id, job_id, user_id, kind, summary, payload_bytes,
    object_key, object_bytes, object_content_type, created_at
) values
    (
        '0192f5c5-0000-7000-8000-000000000001',
        '0192f5c4-0000-7000-8000-000000000001',
        '0192f5c0-0000-7000-8000-000000000001',
        'bpm',
        '{"bpm": 124.0, "beat_count": 443, "confidence": 0.96}'::jsonb,
        58, null, null, null,
        now() - interval '20 days' + interval '3 minutes 42 seconds'
    ),
    (
        '0192f5c5-0000-7000-8000-000000000002',
        '0192f5c4-0000-7000-8000-000000000001',
        '0192f5c0-0000-7000-8000-000000000001',
        'key',
        '{"camelot": "11A", "confidence": 0.88, "key": "F#", "mode": "minor"}'::jsonb,
        68, null, null, null,
        now() - interval '20 days' + interval '3 minutes 42 seconds'
    ),
    (
        '0192f5c5-0000-7000-8000-000000000003',
        '0192f5c4-0000-7000-8000-000000000001',
        '0192f5c0-0000-7000-8000-000000000001',
        'chords',
        '{"progression": ["F#m", "D", "A", "E"], "segment_count": 168, "unique_chords": 7}'::jsonb,
        96,
        'users/0192f5c0-0000-7000-8000-000000000001/songs/0192f5c2-0000-7000-8000-000000000001/artifacts/0192f5c4-0000-7000-8000-000000000001/chords.jsonl',
        184320, 'application/x-ndjson',
        now() - interval '20 days' + interval '3 minutes 42 seconds'
    ),
    (
        '0192f5c5-0000-7000-8000-000000000004',
        '0192f5c4-0000-7000-8000-000000000001',
        '0192f5c0-0000-7000-8000-000000000001',
        'midi',
        '{}'::jsonb,
        0,
        'users/0192f5c0-0000-7000-8000-000000000001/songs/0192f5c2-0000-7000-8000-000000000001/artifacts/0192f5c4-0000-7000-8000-000000000001/analysis.mid',
        20431, 'audio/midi',
        now() - interval '20 days' + interval '3 minutes 42 seconds'
    ),
    (
        '0192f5c5-0000-7000-8000-000000000005',
        '0192f5c4-0000-7000-8000-000000000001',
        '0192f5c0-0000-7000-8000-000000000001',
        'sections',
        '{"sections": [
            {"name": "intro", "start_ms": 0, "end_ms": 16320},
            {"name": "verse", "start_ms": 16320, "end_ms": 65280},
            {"name": "chorus", "start_ms": 65280, "end_ms": 114240},
            {"name": "verse", "start_ms": 114240, "end_ms": 163200},
            {"name": "chorus", "start_ms": 163200, "end_ms": 214500}
        ]}'::jsonb,
        312, null, null, null,
        now() - interval '20 days' + interval '3 minutes 42 seconds'
    );

-- -----------------------------------------------------------------------------
-- Point each song at its newest job (the queue service does this on completion)
-- -----------------------------------------------------------------------------
update public.songs set latest_job_id = '0192f5c4-0000-7000-8000-000000000001'
where id = '0192f5c2-0000-7000-8000-000000000001';
update public.songs set latest_job_id = '0192f5c4-0000-7000-8000-000000000002'
where id = '0192f5c2-0000-7000-8000-000000000002';
update public.songs set latest_job_id = '0192f5c4-0000-7000-8000-000000000003'
where id = '0192f5c2-0000-7000-8000-000000000003';

-- -----------------------------------------------------------------------------
-- Storage GC: an aborted upload whose multipart parts are still in the bucket
-- -----------------------------------------------------------------------------
-- The uploads row is already gone (deleted with the aborted attempt); what
-- remains is the debt to R2. user_id is kept even though the row outlives the
-- upload, and would be nulled rather than cascaded if the account closed.
insert into public.storage_gc_queue (
    id, user_id, object_key, operation, multipart_upload_id, reason, next_attempt_at
) values (
    '0192f5c6-0000-7000-8000-000000000001',
    '0192f5c0-0000-7000-8000-000000000001',
    'users/0192f5c0-0000-7000-8000-000000000001/uploads/0192f5c3-0000-7000-8000-000000000005/half-track.wav',
    'abort_multipart',
    '2~aBcDeFgHiJkLmNoPqRsTuVwXyZ012345',
    'upload_aborted',
    now()
);


