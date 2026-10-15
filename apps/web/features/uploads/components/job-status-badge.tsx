import type { JobStatus, SongWithJob } from "@myband/shared";

import { cn } from "@/lib/utils";

import { isInFlight } from "../jobs";

/**
 * What is happening to a song, as one word.
 *
 * The statuses are the API's job state machine (docs/queue-state-machine.md). Queued,
 * dispatched and running are all "in progress" from a user's side; succeeded, failed and
 * canceled are terminal, and only one of those is worth alarming anyone about.
 *
 * Two signals, and they mean different things. **Pulse** is the "good or live" colour:
 * `Analysed` uses it as a fill, exactly as the landing page's `MIDI ready` badge does, so
 * a success looks the same in the product as it does in the advert. Work in flight does
 * not get a colour at all - it gets a **pulsing dot**, which is the same live indicator
 * the marketing header uses for the beta counter. A chip that is both coloured and
 * pulsing would be two claims at once.
 *
 * The dot carries `data-reveal` so that `prefers-reduced-motion` switches its loop off:
 * it is a CSS animation, and the design system's rule is that the stylesheet, not a
 * JavaScript branch, decides that.
 */
const LABELS: Record<JobStatus, string> = {
  queued: "Queued",
  dispatched: "Starting",
  running: "Analysing",
  succeeded: "Analysed",
  failed: "Failed",
  canceled: "Canceled",
};

const TONES: Record<JobStatus, string> = {
  queued: "border-white/10 bg-white/[0.05] text-foreground",
  dispatched: "border-white/10 bg-white/[0.05] text-foreground",
  running: "border-white/10 bg-white/[0.05] text-foreground",
  succeeded: "border-pulse/30 bg-pulse/10 text-pulse",
  failed: "border-destructive/40 bg-destructive/10 text-destructive",
  canceled: "border-white/[0.07] bg-white/[0.02] text-muted-foreground",
};

export function JobStatusBadge({ status, className }: { status: JobStatus; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap",
        TONES[status],
        className,
      )}
    >
      {isInFlight(status) ? (
        <span
          data-reveal=""
          aria-hidden
          className="size-1.5 animate-live-dot rounded-full bg-pulse motion-reduce:animate-none"
        />
      ) : null}
      {LABELS[status]}
    </span>
  );
}

/**
 * One song's state, decided once.
 *
 * `job` is the analysis in flight, and a song whose analysis finished has none -
 * `songs.latest_job_id` only moves when a job succeeds. So that pointer is what answers
 * "has this ever been measured", which is a different question from "what is happening to
 * it now", and the two cases that are not a job at all are the two that need a word of
 * their own. Both the library rail and the analysis cards read their state from here, so
 * they cannot start describing the same song differently.
 *
 * A song that has never been analysed says so in muted text rather than as a tag: it is
 * the absence of a state, and a chip would give it the same weight as `Failed`.
 */
export function SongStatusTag({ song, className }: { song: SongWithJob; className?: string }) {
  if (song.job) {
    return <JobStatusBadge status={song.job.status} className={className} />;
  }

  if (song.latest_job_id) {
    return <JobStatusBadge status="succeeded" className={className} />;
  }

  return (
    <span className={cn("shrink-0 text-xs text-muted-foreground", className)}>Not analysed</span>
  );
}
