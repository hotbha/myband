import type { SongWithJob } from "@myband/shared";

import { EmptyState } from "@/features/design-system/components/empty-state";
import { MicroLabel } from "@/features/design-system/components/eyebrow";
import { Metric } from "@/features/design-system/components/metric";
import { Panel, PanelHeader } from "@/features/design-system/components/panel";

import { summariseLibrary } from "../library-stats";
import { formatTotalDuration } from "../song-summary";

/**
 * What this screenful of library adds up to.
 *
 * Every number is a count or a sum over the rows the server already fetched, and none of
 * them is an estimate - so each one is labelled with what it is a number *of*. The
 * denominator matters more than the numerator here: the dashboard asks for the newest
 * twenty songs, and a tile that said "12 tracks" without saying "of the 20 shown" would be
 * making a claim about an account nobody has counted.
 *
 * The key spread is the one chart in the product that is not a measurement of one song,
 * and it is a chart for the same reason the chord lane is: a count per key is a
 * distribution, and a distribution drawn as words is a list. It is drawn with percentage
 * widths and no dependency, like everything else in the design system - see the Charts
 * section of docs/DESIGN_SYSTEM.md.
 */
export function LibraryMetrics({ songs }: { songs: SongWithJob[] }) {
  const stats = summariseLibrary(songs);
  const busiest = stats.keys[0]?.count ?? 0;
  const withKey = stats.keys.reduce((total, entry) => total + entry.count, 0);

  return (
    <Panel aria-labelledby="metrics-heading" className="p-4 sm:p-5">
      <PanelHeader id="metrics-heading" eyebrow="At a glance" />

      <dl className="mt-4 grid grid-cols-2 gap-2.5">
        <Metric label="Tracks" value={String(stats.shown)} hint="in this window" />
        <Metric
          label="Analysed"
          value={String(stats.analysed)}
          hint={stats.failed > 0 ? `${stats.failed} failed` : "measured end to end"}
        />
        <Metric
          label="In flight"
          value={String(stats.inFlight)}
          hint={stats.inFlight === 0 ? "nothing running" : "with a worker now"}
        />
        <Metric
          label="Audio"
          value={stats.measuredMs === 0 ? "-" : formatTotalDuration(stats.measuredMs)}
          hint="of decoded length"
        />
      </dl>

      {stats.tempo ? (
        <p className="mt-3 text-xs text-muted-foreground">
          Tempo runs{" "}
          <span className="font-mono text-foreground tabular-nums">
            {stats.tempo.min.toFixed(2)}-{stats.tempo.max.toFixed(2)}
          </span>{" "}
          BPM in the tracks that have one.
        </p>
      ) : null}

      <div className="mt-5 border-t border-white/[0.07] pt-4">
        <MicroLabel>Keys</MicroLabel>

        {stats.keys.length === 0 ? (
          <EmptyState className="mt-3 rounded-xl p-4">
            No keys measured yet. A key appears here once an analysis has finished.
          </EmptyState>
        ) : (
          <ul className="mt-3 space-y-2">
            {stats.keys.map((entry) => (
              <li key={entry.key} className="flex items-center gap-3">
                <span className="w-24 shrink-0 truncate font-mono text-xs" title={entry.key}>
                  {entry.key}
                </span>

                <span className="h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-black/25">
                  <span
                    className="block h-full rounded-full bg-gradient-to-r from-signal to-pulse"
                    style={{ width: `${Math.round((entry.count / busiest) * 100)}%` }}
                  />
                </span>

                <span className="w-4 shrink-0 text-right font-mono text-xs text-muted-foreground tabular-nums">
                  {entry.count}
                </span>
              </li>
            ))}
          </ul>
        )}

        <p className="mt-3 text-xs text-muted-foreground">
          Across the {withKey} {withKey === 1 ? "track" : "tracks"} in this window that reported a
          key.
        </p>
      </div>
    </Panel>
  );
}
