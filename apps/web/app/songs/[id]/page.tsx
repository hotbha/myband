import type { Metadata } from "next";
import { notFound } from "next/navigation";

import type { Chords, SongWithJob } from "@myband/shared";

import { requireIdentity } from "@/features/auth/session";
import { EmptyState } from "@/features/design-system/components/empty-state";
import { Panel, PanelHeader } from "@/features/design-system/components/panel";
import { AppShell } from "@/features/shell/components/app-shell";
import { ChordTimeline } from "@/features/uploads/components/chord-timeline";
import { SongExports, SongMethod } from "@/features/uploads/components/song-exports";
import { SongOverview } from "@/features/uploads/components/song-overview";
import { fetchChords, fetchSong } from "@/features/uploads/server-api";
import { ApiError, messageFor } from "@/lib/api";

export const metadata: Metadata = {
  title: "Analysis - MyBand.video",
};

/**
 * One song, read the way an instrument is read: identity, then the measurements, then the
 * timeline, then what you can take away.
 *
 * Three bands, each full width, and the width is the point. The measurements sit in one row of
 * six rather than two rows of three, and the timeline spans the workspace with its list beside a
 * summary that sticks while the list scrolls past - the difference between a page that shows an
 * analysis and a page somebody can work in. See docs/WIREFRAMES.md, section 6.
 *
 * A Server Component, like the dashboard and for the same reason: the song and its timeline are
 * read with the request that renders them, so there is no spinner, no mount-time fetch, and
 * nothing in the tab that could disagree with the server. The two reads are issued together
 * because neither needs the other's answer. The route is protected twice over - middleware turns
 * anonymous requests away, and `requireIdentity` is the actual authorization boundary.
 *
 * The timeline has three states and they are deliberately different on screen:
 *
 * * **loaded** - the timeline, the chords the song is made of, and how sure the detector was.
 * * **pending** - the API answered `analysis_not_ready`: the song exists and nothing has produced
 *   chords for it yet. That is a fact about a job, not a failure, and it is not dressed as one.
 * * **failed** - anything else. A song that is not this caller's, or is deleted, is a real 404 and
 *   gets `notFound()` rather than a message.
 */
export default async function SongPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const identity = await requireIdentity(`/songs/${id}`);

  const [song, chords] = await Promise.all([loadSong(id), loadChords(id)]);

  // A song that could not be read is the one state with nothing else to say: a timeline below
  // would be a timeline of an unknown song. So the error is the whole page, and it says so.
  if (!song.ok) {
    return (
      <AppShell identity={identity} context="Song">
        <Panel aria-labelledby="overview-heading">
          <PanelHeader id="overview-heading" eyebrow="Song" title="This song is not available" />

          <p
            role="alert"
            className="mt-5 rounded-xl border border-destructive/40 bg-destructive/10 px-3 py-2.5 text-sm/relaxed text-destructive"
          >
            {song.message}
          </p>
        </Panel>
      </AppShell>
    );
  }

  const value = song.value;
  const timeline = chords.kind === "loaded" ? chords.chords : null;

  return (
    <AppShell identity={identity} context={value.title}>
      <div className="space-y-6">
        <SongOverview song={value} chords={timeline} />

        <Panel aria-labelledby="timeline-heading">
          <PanelHeader
            id="timeline-heading"
            eyebrow="Chord timeline"
            title="Every chord, and when it plays"
          />

          <div className="mt-5">
            {chords.kind === "loaded" ? (
              <ChordTimeline chords={chords.chords} durationMs={value.duration_ms} />
            ) : (
              <EmptyState role={chords.kind === "pending" ? "status" : undefined}>
                {chords.message}
              </EmptyState>
            )}
          </div>
        </Panel>

        <div className="grid gap-6 lg:grid-cols-2">
          <SongExports song={value} />
          <SongMethod song={value} chords={timeline} />
        </div>
      </div>
    </AppShell>
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
