import Link from "next/link";

import type { SongWithJob } from "@myband/shared";

import { EmptyState } from "@/features/design-system/components/empty-state";
import { Panel, PanelHeader } from "@/features/design-system/components/panel";

import { JobStatusBadge } from "./job-status-badge";

/**
 * What is being worked on right now, and what went wrong.
 *
 * This is the workspace's activity panel, and it is deliberately not a log. A log would
 * mean a table of events nobody reads; what is worth knowing is the two things that are
 * actually actionable - a job a worker is holding, and a job that failed with a reason
 * attached - so those are the only two rows this panel can hold.
 *
 * It is rendered even when it is empty, because "nothing is running" is worth saying
 * once on a screen where uploads are analysed in the background: it answers the question
 * a person has after uploading, which is whether anything is happening. That answer is an
 * `EmptyState` with a sentence rather than a blank panel, per the design system.
 *
 * A failure is the one place in the product that gets `role="alert"` on a list, because a
 * failed analysis is the only state here that somebody needs to be interrupted by.
 */
export function WorkInFlight({ songs }: { songs: SongWithJob[] }) {
  const active = songs.filter((song) => song.job !== null);

  return (
    <Panel aria-labelledby="activity-heading" className="p-4 sm:p-5">
      <PanelHeader
        id="activity-heading"
        eyebrow="Activity"
        right={
          active.length > 0 ? (
            <span className="font-mono text-xs text-muted-foreground tabular-nums">
              {active.length}
            </span>
          ) : null
        }
      />

      {active.length === 0 ? (
        <EmptyState className="mt-4 rounded-xl p-4">
          Nothing is running. An upload is analysed in the background, and it appears here until it
          finishes.
        </EmptyState>
      ) : (
        <ul className="mt-4 space-y-2">
          {active.map((song) => (
            <li
              key={song.id}
              className="rounded-xl border border-white/[0.07] bg-white/[0.02] px-3 py-2.5"
            >
              <div className="flex items-start justify-between gap-3">
                <Link
                  href={`/songs/${song.id}`}
                  className="min-w-0 truncate text-sm font-medium underline-offset-4 hover:underline"
                >
                  {song.title}
                </Link>

                {song.job ? <JobStatusBadge status={song.job.status} /> : null}
              </div>

              {song.job ? (
                <p className="mt-1.5 truncate font-mono text-[0.6rem] tracking-[0.12em] text-muted-foreground/70 uppercase">
                  job {song.job.id.slice(0, 8)} · pipeline {song.job.pipeline_version}
                </p>
              ) : null}

              {/* The API's own sentence, when it had one. A failure with no reason is a
                  dead end, which is why `error_code` is shown even when the message is not. */}
              {song.job?.status === "failed" ? (
                <p role="alert" className="mt-2 text-xs/relaxed text-destructive">
                  {song.job.error_message ?? song.job.error_code ?? "The analysis failed."}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
