import type { Chords, SongWithJob } from "@myband/shared";

import { EmptyState } from "@/features/design-system/components/empty-state";
import { Metric } from "@/features/design-system/components/metric";
import { Panel, PanelHeader } from "@/features/design-system/components/panel";

import { meanConfidence } from "../chord-view";
import { isInFlight } from "../jobs";
import { tempoOf } from "../library-stats";
import { describeSong, durationOf } from "../song-summary";
import { JobStatusBadge } from "./job-status-badge";

/** One measurement, as the design system's metric tile wants it. */
type Measurement = { label: string; value: string; unit?: string; hint: string };

/**
 * The top band: what this song is, and what was measured in it.
 *
 * Six tiles across the width rather than two rows of three, because a row of measurements is
 * read left to right and a wrapped grid makes the eye zig-zag. On a narrow screen the same
 * six wrap into a 2x2x2 grid and nothing about their order changes, which is the point of
 * having one `Metric` component rather than six hand-built tiles.
 *
 * **A measurement that does not exist is absent, not zero.** A song nobody has analysed has
 * no tempo, and `0 BPM` would be a claim that the recording is static; so the tiles are built
 * by filtering, and the band says what is happening instead when there is nothing to show.
 *
 * `chords` is optional because the timeline and the song are fetched independently: a job can
 * finish writing a measurement while the timeline is still being read, and the top band is
 * perfectly readable without it.
 */
export function SongOverview({ song, chords }: { song: SongWithJob; chords: Chords | null }) {
  const measurements = measurementsOf(song, chords);

  return (
    <Panel aria-labelledby="overview-heading">
      <PanelHeader
        id="overview-heading"
        eyebrow="Song"
        title={song.title}
        right={song.job ? <JobStatusBadge status={song.job.status} /> : null}
      />

      <p className="mt-2 text-xs/relaxed break-words text-muted-foreground">{describeSong(song)}</p>

      {measurements.length === 0 ? (
        <EmptyState role={isPending(song) ? "status" : undefined} className="mt-5 rounded-xl">
          {isPending(song)
            ? "This song has not been analysed yet. It is queued - the measurements appear here when the worker finishes with it."
            : "Nothing has been measured in this song yet. The numbers appear here as soon as the analyser has finished."}
        </EmptyState>
      ) : (
        <dl className="mt-5 grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
          {measurements.map((measurement) => (
            <Metric key={measurement.label} {...measurement} />
          ))}
        </dl>
      )}
    </Panel>
  );
}

/** Whether the song is waiting on a worker, which is a state rather than a failure. */
function isPending(song: SongWithJob): boolean {
  return song.job !== null && isInFlight(song.job.status);
}

/**
 * Every measurement this song can honestly report, in the order they matter.
 *
 * The hints are the part worth reading twice. Each one is derived from data actually in hand
 * rather than from a plausible-sounding description of the pipeline: the key's hint compares
 * the song's key with the one the chord reader reported, so it can say "confirmed by the chord
 * reader" only when two independent rows in the API agree. Where nothing more is known, the
 * hint says what the number is a measurement *of* - which is still the difference between a
 * figure somebody can use and a figure they have to guess at.
 */
function measurementsOf(song: SongWithJob, chords: Chords | null): Measurement[] {
  const bpm = tempoOf(song);
  const mean = chords ? meanConfidence(chords) : null;
  const length = durationOf(song);

  const candidates: (Measurement | null)[] = [
    bpm === null
      ? null
      : {
          label: "Tempo",
          value: bpm.toFixed(2),
          unit: "BPM",
          hint: "one tempo for the whole song",
        },
    song.musical_key === null
      ? null
      : {
          label: "Key",
          value: song.musical_key,
          hint: keyHint(song.musical_key, chords?.key ?? null),
        },
    mean === null
      ? null
      : {
          label: "Confidence",
          value: String(Math.round(mean * 100)),
          unit: "%",
          hint: "mean, over the chords it named",
        },
    chords === null || chords.segments.length === 0
      ? null
      : {
          label: "Chords",
          value: String(chords.segments.length),
          unit: "segments",
          hint: "bar by bar, in time order",
        },
    chords === null
      ? null
      : {
          label: "Coverage",
          value: String(Math.round(chords.coverage * 100)),
          unit: "%",
          hint: "of the recording's length",
        },
    length === null ? null : { label: "Length", value: length, hint: "decoded from the file" },
  ];

  return candidates.filter((measurement): measurement is Measurement => measurement !== null);
}

/**
 * What the key's hint says, which depends on whether the chord reader agreed.
 *
 * Two rows in the API report a key - the song's own measurement and the timeline's - and they
 * are computed from the same recording by the same pipeline. When they agree, saying so is
 * worth a line: it is the closest thing to a confidence the key has in this data. When they
 * disagree, the honest thing is to name both values rather than pick one, because a musician
 * choosing a scale needs to know that the two readings differ.
 */
function keyHint(songKey: string, chordKey: string | null): string {
  if (chordKey === null) {
    return "detected, over the whole recording";
  }

  return chordKey === songKey ? "confirmed by the chord reader" : `chord reader says ${chordKey}`;
}
