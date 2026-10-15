import type { SongWithJob } from "@myband/shared";

import { formatBytes } from "./file-rules";

/**
 * How a song renders as one line, used by the library list and by the song page.
 *
 * A module rather than a component because it is not a component: it is the sentence both screens
 * put under a title, and the whole point of having it in one place is that the library and the song
 * page cannot start describing the same track differently.
 */

/**
 * Artist, the analysis headline, and the upload's own facts - with the missing pieces left out.
 *
 * `bpm` is a decimal the API serialises as a string, so it is read as a number before it is rounded;
 * `duration_ms` is only present once something has decoded the file.
 */
export function describeSong(song: SongWithJob): string {
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
export function durationOf(song: SongWithJob): string | null {
  if (song.duration_ms === null) {
    return null;
  }

  const seconds = Math.round(song.duration_ms / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/**
 * A total length of audio, in hours and minutes.
 *
 * For a sum rather than one recording, so `m:ss` is the wrong shape: nobody reads
 * `72:15` as an hour and twelve minutes. Minutes are dropped once there is an hour to
 * report, because the difference between "1h 12m" and "1h 12m 4s" is not a difference
 * anyone acts on.
 */
export function formatTotalDuration(ms: number): string {
  const minutes = Math.round(ms / 60_000);

  if (minutes < 60) {
    return `${minutes}m`;
  }

  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;

  return rest === 0 ? `${hours}h` : `${hours}h ${rest}m`;
}
