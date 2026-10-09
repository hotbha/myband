import type { ReactNode } from "react";

import type { SongWithJob } from "@myband/shared";

import { formatBytes } from "../file-rules";
import { JobStatusBadge } from "./job-status-badge";

/**
 * The library: one line per song, newest first.
 *
 * `job` is the analysis in flight. A song whose analysis has finished has none -
 * `songs.latest_job_id` only moves when a job succeeds - so that pointer answers
 * "has this ever been analysed", the same distinction
 * `apps/api/app/schemas/song.py` documents. Reading it here costs nothing: it is a
 * column on the row the list already has.
 */
export function SongList({ songs }: { songs: SongWithJob[] }) {
  if (songs.length === 0) {
    return (
      <p className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
        Nothing here yet. Upload a track and it appears here with its analysis.
      </p>
    );
  }

  return (
    <ul className="divide-y rounded-lg border">
      {songs.map((song) => (
        <li key={song.id} className="flex items-center justify-between gap-4 p-4">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{song.title}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {describe(song)} ·{" "}
              <time dateTime={song.created_at}>{song.created_at.slice(0, 10)}</time>
            </p>
          </div>
          {statusOf(song)}
        </li>
      ))}
    </ul>
  );
}

/** Artist, the analysis headline, and the upload's own facts, missing pieces left out. */
function describe(song: SongWithJob): string {
  const parts = [
    song.artist,
    song.bpm === null ? null : `${Math.round(Number(song.bpm))} BPM`,
    song.musical_key,
    durationOf(song),
    song.source_bytes === null ? null : formatBytes(song.source_bytes),
    song.source_content_type,
  ];

  return parts.filter((part): part is string => part !== null).join(" · ");
}

/** The recording's length as m:ss, or nothing at all until something has measured it. */
function durationOf(song: SongWithJob): string | null {
  if (song.duration_ms === null) {
    return null;
  }

  const seconds = Math.round(song.duration_ms / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function statusOf(song: SongWithJob): ReactNode {
  if (song.job) {
    return <JobStatusBadge status={song.job.status} />;
  }

  if (song.latest_job_id) {
    return <JobStatusBadge status="succeeded" />;
  }

  return <span className="shrink-0 text-xs text-muted-foreground">Not analysed</span>;
}
