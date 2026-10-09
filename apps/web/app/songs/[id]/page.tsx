import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import type { Chords, SongWithJob } from "@myband/shared";

import { requireIdentity } from "@/features/auth/session";
import { ChordProgression, ChordTimeline } from "@/features/uploads/components/chord-timeline";
import { DownloadMidiButton } from "@/features/uploads/components/download-midi-button";
import { JobStatusBadge } from "@/features/uploads/components/job-status-badge";
import { fetchChords, fetchSong } from "@/features/uploads/server-api";
import { describeSong } from "@/features/uploads/song-summary";
import { ApiError, messageFor } from "@/lib/api";

export const metadata: Metadata = {
  title: "Chords - MyBand.video",
};

/**
 * One song: what was measured, and what it plays.
 *
 * A Server Component, like the dashboard and for the same reason - the song and its timeline are read
 * with the request that renders them, so there is no spinner, no mount-time fetch, and nothing in the
 * tab that could disagree with the server. The route is protected twice over: middleware turns
 * anonymous requests away, and `requireIdentity` is the actual authorization boundary.
 *
 * The timeline has three states and they are deliberately different on screen:
 *
 * * **loaded** - the timeline, the chords the song is made of, and the detector's own confidence.
 * * **pending** - the API answered `analysis_not_ready`: the song exists and nothing has produced
 *   chords for it yet. That is a fact about a job, not a failure, and it is not dressed as one.
 * * **failed** - anything else. A song that is not this caller's, or is deleted, is a real 404 and
 *   gets `notFound()` rather than a message.
 */
export default async function SongPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  await requireIdentity(`/songs/${id}`);

  const [song, chords] = await Promise.all([loadSong(id), loadChords(id)]);

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-3xl flex-col gap-8 px-6 py-12">
      <header className="space-y-3">
        <Link
          href="/dashboard"
          className="text-xs text-muted-foreground underline underline-offset-2"
        >
          Library
        </Link>

        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 space-y-1">
            <h1 className="truncate text-2xl font-semibold tracking-tight">
              {song.ok ? song.value.title : "Song"}
            </h1>
            {song.ok ? (
              <p className="text-sm text-muted-foreground">{describeSong(song.value)}</p>
            ) : null}
          </div>
          {song.ok && song.value.latest_job_id ? (
            <DownloadMidiButton songId={song.value.id} title={song.value.title} />
          ) : null}
        </div>

        {song.ok && song.value.job ? <JobStatusBadge status={song.value.job.status} /> : null}
      </header>

      {song.ok ? null : <Notice message={song.message} tone="error" />}

      <section className="space-y-4">
        <h2 className="text-lg font-medium">Chords</h2>

        {chords.kind === "loaded" ? (
          <>
            <p className="text-xs text-muted-foreground">
              Read from the recording by {chords.chords.detector}, bar by bar
              {chords.chords.key ? ` in ${chords.chords.key}` : ""}. Times are when each chord
              starts; the number on the right is how sure the detector was.
            </p>
            <ChordProgression chords={chords.chords} />
            <ChordTimeline chords={chords.chords} />
          </>
        ) : (
          <Notice message={chords.message} tone={chords.kind === "pending" ? "muted" : "error"} />
        )}
      </section>
    </main>
  );
}

/** The song, or why it is not here. */
type Loaded = { ok: true; value: SongWithJob } | { ok: false; message: string };

/** The timeline, plus the one refusal that is a state rather than a failure. */
type ChordsState =
  | { kind: "loaded"; chords: Chords }
  | { kind: "pending"; message: string }
  | { kind: "failed"; message: string };

async function loadSong(songId: string): Promise<Loaded> {
  try {
    return { ok: true, value: await fetchSong(songId) };
  } catch (cause) {
    if (cause instanceof ApiError && cause.code === "song_not_found") {
      // Somebody else's song, or a deleted one, is a 404 rather than a sentence to render.
      notFound();
    }

    return { ok: false, message: messageFor(cause) };
  }
}

async function loadChords(songId: string): Promise<ChordsState> {
  try {
    return { kind: "loaded", chords: await fetchChords(songId) };
  } catch (cause) {
    if (cause instanceof ApiError && cause.code === "song_not_found") {
      notFound();
    }

    if (cause instanceof ApiError && cause.code === "analysis_not_ready") {
      // The API distinguishes "not analysed yet" from "analysed, and it produced no chords" from
      // "the timeline is gone", and its sentence is the one worth showing.
      return { kind: "pending", message: cause.message };
    }

    return { kind: "failed", message: messageFor(cause) };
  }
}

/** A message worth showing a person, styled for whether it is a problem or a state. */
function Notice({ message, tone }: { message: string; tone: "error" | "muted" }) {
  if (tone === "muted") {
    return (
      <p className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">{message}</p>
    );
  }

  return (
    <p
      role="alert"
      className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
    >
      {message}
    </p>
  );
}
