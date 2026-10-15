import Link from "next/link";

import type { SongWithJob } from "@myband/shared";

import { Button } from "@/components/ui/button";
import { MicroLabel } from "@/features/design-system/components/eyebrow";

import { formatBytes } from "../file-rules";
import { durationOf } from "../song-summary";
import { tempoOf } from "../library-stats";
import { DownloadMidiButton } from "./download-midi-button";
import { SongStatusTag } from "./job-status-badge";

/**
 * One finished analysis, as a card.
 *
 * The centre column's job is the answer rather than the inventory, so a card here leads
 * with the three measurements somebody opens this product for - tempo, key, length - and
 * keeps the upload's own facts (size, format) as one quiet line. The library rail next to
 * it lists exactly the same songs; the difference between the two is that the rail is for
 * finding a song and this is for reading one.
 *
 * Only a song that has been measured belongs here. A song that is queued or unanalysed is
 * in the utility rail under work in flight, because an unfinished analysis is state rather
 * than result.
 *
 * The card is not itself a link, and that is deliberate: it contains a link (the title)
 * and a control (the MIDI download), and a card-level click target would nest one inside
 * the other. The button is the affordance, and the title link is there for the reader who
 * expects a heading to be navigable.
 */
export function AnalysisCard({ song }: { song: SongWithJob }) {
  const bpm = tempoOf(song);
  const length = durationOf(song);

  return (
    <article className="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-4 transition-colors hover:border-signal/30 hover:bg-white/[0.04]">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="truncate font-display text-base tracking-tight">
            <Link
              href={`/songs/${song.id}`}
              className="rounded-md underline-offset-4 hover:underline"
            >
              {song.title}
            </Link>
          </h3>

          <p className="mt-1 truncate text-xs text-muted-foreground">{fileLine(song)}</p>
        </div>

        <SongStatusTag song={song} />
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
        <Stat
          label="Tempo"
          value={bpm === null ? "-" : bpm.toFixed(2)}
          unit={bpm === null ? undefined : "BPM"}
        />
        <Stat label="Key" value={song.musical_key ?? "-"} />
        <Stat label="Length" value={length ?? "-"} />
        <Stat label="Uploaded" value={song.created_at.slice(0, 10)} />
      </dl>

      <div className="mt-4 flex items-center justify-between gap-3 border-t border-white/[0.07] pt-3">
        <span className="truncate font-mono text-[0.6rem] tracking-[0.12em] text-muted-foreground/70 uppercase">
          {song.latest_job_id ? `job ${song.latest_job_id.slice(0, 8)}` : "not analysed"}
        </span>

        <div className="flex shrink-0 items-start gap-2">
          {song.latest_job_id ? <DownloadMidiButton songId={song.id} title={song.title} /> : null}

          <Button asChild variant="outline" size="sm">
            <Link
              href={`/songs/${song.id}`}
              aria-label={`Open the analysis of ${song.title}`}
              className="rounded-md"
            >
              Open
            </Link>
          </Button>
        </div>
      </div>
    </article>
  );
}

/** One labelled value inside a card. A `dd`/`dt` pair, so a screen reader reads the two together. */
function Stat({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div className="min-w-0">
      <dt>
        <MicroLabel>{label}</MicroLabel>
      </dt>
      <dd className="mt-1.5 flex items-baseline gap-1">
        <span className="min-w-0 truncate font-mono text-sm tabular-nums">{value}</span>
        {unit ? <span className="text-[0.7rem] text-muted-foreground">{unit}</span> : null}
      </dd>
    </div>
  );
}

/**
 * The upload's own facts: who it is, how big it is, what it is.
 *
 * `describeSong` is not reused here because the card already reports the measurements it
 * contains, and printing them twice on the same rectangle is noise. What is left is the
 * part the analysis does not tell you.
 */
function fileLine(song: SongWithJob): string {
  return [
    song.artist,
    song.source_bytes === null ? null : formatBytes(song.source_bytes),
    song.source_content_type,
  ]
    .filter((part): part is string => part !== null && part !== "")
    .join(" · ");
}
