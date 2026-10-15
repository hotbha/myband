import type { JobStatus, SongWithJob } from "@myband/shared";

/**
 * Which jobs are still moving.
 *
 * `analysis_job.ACTIVE_STATUSES` on the API side, mirrored: the three statuses that mean
 * work is in flight. Everything else is terminal, and a song with no job at all has
 * nothing outstanding either.
 *
 * A plain module rather than part of a component, because both sides ask: the dashboard
 * decides on the server whether anything is worth watching, and the poller is a Client
 * Component that cannot be called from one. Details of what each status means are in
 * `docs/queue-state-machine.md`.
 */
const IN_FLIGHT: ReadonlySet<JobStatus> = new Set<JobStatus>(["queued", "dispatched", "running"]);

/** Whether a single job is waiting on, or being held by, a worker. */
export function isInFlight(status: JobStatus): boolean {
  return IN_FLIGHT.has(status);
}

/** Whether anything in the library is waiting on a worker. */
export function hasWorkInFlight(songs: SongWithJob[]): boolean {
  return songs.some((song) => song.job !== null && IN_FLIGHT.has(song.job.status));
}
