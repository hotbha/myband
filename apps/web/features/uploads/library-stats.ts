import type { SongWithJob } from "@myband/shared";

import { isInFlight } from "./jobs";

/**
 * What a screenful of the library adds up to.
 *
 * This is arithmetic over rows the server already fetched, and nothing here is an
 * estimate: every figure is either a count of rows in the window or a sum of values the
 * API returned. That is why the numbers are always presented with their denominator
 * ("across the 20 tracks shown") - the dashboard asks the API for the newest 20 songs, so
 * a total that pretends to be the whole account would be a lie about the window.
 *
 * A number that could not be measured is `null` rather than `0`. A tempo range of
 * `0-0 BPM` is not a fact about a library with nothing measured in it; it is a bug that
 * looks like a measurement, and the screen draws nothing at all for a `null`.
 */

/** Which key, and how many tracks in the window are in it. */
export type KeyCount = { key: string; count: number };

export type LibraryStats = {
  /** Rows in the window - the denominator for everything else. */
  shown: number;
  /** Songs with a measurement: a BPM, a key, or a finished job behind them. */
  analysed: number;
  /** Songs a worker is holding right now. */
  inFlight: number;
  /** Songs whose last job failed. */
  failed: number;
  /** Total length of the recordings that have been decoded, in milliseconds. */
  measuredMs: number;
  /** The window's tempo range, or `null` when nothing in it has a tempo. */
  tempo: { min: number; max: number } | null;
  /** Keys in the window, most common first. */
  keys: KeyCount[];
};

export function summariseLibrary(songs: SongWithJob[]): LibraryStats {
  const bpms = songs.map(tempoOf).filter((bpm): bpm is number => bpm !== null);
  const keys = new Map<string, number>();
  let measuredMs = 0;

  for (const song of songs) {
    if (song.musical_key) {
      keys.set(song.musical_key, (keys.get(song.musical_key) ?? 0) + 1);
    }

    measuredMs += song.duration_ms ?? 0;
  }

  return {
    shown: songs.length,
    analysed: songs.filter(isAnalysed).length,
    inFlight: songs.filter(inFlight).length,
    failed: songs.filter((song) => song.job?.status === "failed").length,
    measuredMs: songs.some((song) => song.duration_ms !== null) ? measuredMs : 0,
    tempo: bpms.length > 0 ? { min: Math.min(...bpms), max: Math.max(...bpms) } : null,
    keys: [...keys.entries()]
      .map(([key, count]) => ({ key, count }))
      .sort((a, b) => b.count - a.count || a.key.localeCompare(b.key)),
  };
}

/**
 * The song's tempo as a number, or nothing.
 *
 * `bpm` is a decimal the API serialises as a string to keep its precision, so it is read
 * as a number before it is used - `uploads.ts` documents that, and a `Number()` that
 * returned `NaN` is treated as "not measured" rather than as a tempo of `NaN BPM`.
 */
export function tempoOf(song: SongWithJob): number | null {
  if (song.bpm === null) {
    return null;
  }

  const bpm = Number(song.bpm);

  return Number.isFinite(bpm) ? bpm : null;
}

/** Whether anything has ever measured this song. */
export function isAnalysed(song: SongWithJob): boolean {
  return song.latest_job_id !== null || song.bpm !== null || song.musical_key !== null;
}

function inFlight(song: SongWithJob): boolean {
  return song.job !== null && isInFlight(song.job.status);
}
