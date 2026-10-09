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
