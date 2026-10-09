import type { JobStatus } from "@myband/shared";

import { cn } from "@/lib/utils";

/**
 * What is happening to a song, as one word.
 *
 * The statuses are the API's job state machine (docs/upload-flow.md). Queued,
 * dispatched and running are all "in progress" from a user's side; succeeded, failed
 * and canceled are terminal, and only two of those are worth alarming anyone about.
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
  queued: "border-border bg-muted text-muted-foreground",
  dispatched: "border-border bg-muted text-muted-foreground",
  running: "border-border bg-secondary text-secondary-foreground",
  succeeded: "border-transparent bg-primary text-primary-foreground",
  failed: "border-destructive/40 bg-destructive/10 text-destructive",
  canceled: "border-border bg-muted text-muted-foreground",
};

export function JobStatusBadge({ status, className }: { status: JobStatus; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded-full border px-2.5 py-0.5 text-xs font-medium",
        TONES[status],
        className,
      )}
    >
      {LABELS[status]}
    </span>
  );
}
