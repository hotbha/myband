"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

/**
 * Keeps the library honest while a worker holds a job.
 *
 * The list is rendered on the server, so it is a snapshot of the moment the page was
 * requested - correct, and stale the second the worker finishes. Rather than hand the
 * list to the browser to own, this re-runs the Server Component on a timer: the rows
 * still come from the API, and nothing here knows what a song is.
 *
 * Two things end it. Polling stops when nothing is in flight - which is the next
 * render's answer rather than a guess made here - and it stops after `MAX_TICKS`,
 * because work still unfinished after the worker's own lease has passed is an
 * operational problem, not something worth asking about every five seconds. A hidden
 * tab is skipped too: the interval keeps its rhythm, the refresh that nobody can see
 * does not happen.
 *
 * The timer is not a subscription and does not need to be: it is the same
 * `router.refresh()` the uploader calls when it has queued a job, which is the only
 * other thing that makes this list change.
 */
const POLL_INTERVAL_MS = 5_000;

/**
 * 15 minutes. `MYBAND_WORKER_JOB_TIMEOUT_SECONDS`'s default, and the same window the
 * queue's sweep uses to decide a worker is gone (`queue.STALE_AFTER`), so a job that
 * outlives it is either about to be reaped or never had a worker at all.
 */
const MAX_TICKS = 180;

/** The point at which this gives up watching, in whole minutes. */
const MAX_MINUTES = Math.round((MAX_TICKS * POLL_INTERVAL_MS) / 60_000);

export function LibraryRefresh({ active }: { active: boolean }) {
  const router = useRouter();
  const [ticks, setTicks] = useState(0);

  const polling = active && ticks < MAX_TICKS;

  useEffect(() => {
    if (!polling) {
      return;
    }

    const timer = setInterval(() => {
      if (!document.hidden) {
        router.refresh();
      }
      setTicks((count) => count + 1);
    }, POLL_INTERVAL_MS);

    return () => clearInterval(timer);
  }, [polling, router]);

  if (!active) {
    return null;
  }

  if (!polling) {
    return (
      <p className="text-xs text-muted-foreground">
        Nothing has finished after {MAX_MINUTES} minutes.{" "}
        <button
          type="button"
          className="underline underline-offset-2 hover:text-foreground"
          onClick={() => {
            setTicks(0);
            router.refresh();
          }}
        >
          Check again
        </button>
      </p>
    );
  }

  return (
    <p role="status" className="text-xs text-muted-foreground">
      Analysing - this list updates itself.
    </p>
  );
}
