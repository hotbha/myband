import type { Chords, SongWithJob } from "@myband/shared";

import { EmptyState } from "@/features/design-system/components/empty-state";
import { Fact } from "@/features/design-system/components/metric";
import { Panel, PanelHeader } from "@/features/design-system/components/panel";

import { DownloadMidiButton } from "./download-midi-button";

/** One line of provenance. */
type Provenance = { label: string; value: string };

/**
 * The export, at the bottom of the page where a reference panel belongs.
 *
 * The MIDI is the one thing here that leaves the product, and the copy is careful about what
 * it actually is: the pitch line the analyser read off the recording, as a `.mid` file. It is
 * not an arrangement, and promising one would be the kind of claim somebody discovers is
 * false on their first import - which is why the button is the last thing on the page rather
 * than the first.
 *
 * The control appears only when `latest_job_id` is set, because that pointer only moves when
 * a job succeeds: a song that has never been analysed cannot have an artifact, and a button
 * that could only ever answer 404 would be a button that teaches people not to trust buttons.
 */
export function SongExports({ song }: { song: SongWithJob }) {
  return (
    <Panel aria-labelledby="exports-heading">
      <PanelHeader id="exports-heading" eyebrow="Export" title="Take it to your DAW" />

      {song.latest_job_id ? (
        <div className="mt-5 space-y-4">
          <p className="text-sm/relaxed text-muted-foreground">
            The MIDI is the pitch line the analyser read off this recording, as a{" "}
            <span className="font-mono text-xs text-foreground/80">.mid</span> file - a sketch to
            start from rather than a finished arrangement. Import it, and the notes land on a track
            you can edit.
          </p>

          <DownloadMidiButton
            songId={song.id}
            title={song.title}
            label="Download MIDI"
            variant="default"
            className="h-10 rounded-xl bg-gradient-to-br from-signal to-signal-strong px-5 text-[0.95rem] shadow-[0_16px_40px_-16px_var(--signal)] transition hover:brightness-110"
          />
        </div>
      ) : (
        <EmptyState className="mt-5 rounded-xl">
          The MIDI appears here once this song has been analysed. A song still waiting on a worker
          has nothing to hand over yet.
        </EmptyState>
      )}
    </Panel>
  );
}

/**
 * How the analysis was made, as a list of facts rather than a paragraph.
 *
 * This is the panel that makes the numbers on this page checkable. A detector's name, the
 * vocabulary it was allowed to choose from, its hop size and the pipeline version are the four
 * things that explain why one upload came back differently from another - and the job's own id
 * and compute time are what somebody needs to quote when they report that it did.
 *
 * The values are whatever the API answered with, in monospace, in the order they matter. A
 * value that was not reported is left out rather than shown as a dash: this list is a record,
 * and an empty row in a record is worse than a shorter record.
 */
export function SongMethod({ song, chords }: { song: SongWithJob; chords: Chords | null }) {
  const facts = provenanceOf(song, chords);

  return (
    <Panel aria-labelledby="method-heading">
      <PanelHeader id="method-heading" eyebrow="Method" title="How this was measured" />

      {facts.length === 0 ? (
        <EmptyState className="mt-5 rounded-xl">
          The analyser&apos;s settings appear here once it has finished with this song.
        </EmptyState>
      ) : (
        <dl className="mt-4">
          {facts.map((fact) => (
            <Fact key={fact.label} label={fact.label}>
              {fact.value}
            </Fact>
          ))}
        </dl>
      )}
    </Panel>
  );
}

/** The settings the timeline reports, then the job's own record of itself. */
function provenanceOf(song: SongWithJob, chords: Chords | null): Provenance[] {
  const job = song.job;
  const compute = readSeconds(job?.compute_seconds);

  const candidates: (Provenance | null)[] = [
    chords === null ? null : { label: "Detector", value: chords.detector },
    chords === null ? null : { label: "Vocabulary", value: chords.vocabulary },
    chords === null ? null : { label: "Hop", value: `${chords.hop_ms} ms` },
    chords === null || chords.key === null ? null : { label: "Key", value: chords.key },
    job === null ? null : { label: "Pipeline", value: job.pipeline_version },
    compute === null ? null : { label: "Compute", value: `${compute.toFixed(1)} s` },
    job === null ? null : { label: "Job", value: job.id.slice(0, 8) },
  ];

  return candidates.filter((fact): fact is Provenance => fact !== null);
}

/**
 * A compute time as a number, or nothing.
 *
 * `compute_seconds` is a decimal the API may serialise as a string to keep its precision, so
 * both forms are accepted and anything that is not a finite number is treated as "not
 * reported" rather than printed as `NaN s`.
 */
function readSeconds(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) {
    return null;
  }

  const seconds = Number(value);

  return Number.isFinite(seconds) ? seconds : null;
}
