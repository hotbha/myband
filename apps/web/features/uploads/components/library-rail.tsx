import Link from "next/link";

import { EmptyState } from "@/features/design-system/components/empty-state";
import { Panel, PanelHeader } from "@/features/design-system/components/panel";
import { cn } from "@/lib/utils";

import type { Library } from "../server-api";
import { describeSong } from "../song-summary";
import { SongStatusTag } from "./job-status-badge";
import { LibraryRefresh } from "./library-refresh";

/**
 * The library, as a column.
 *
 * This is the workspace's navigation: there is no menu of screens, because a product with
 * three routes and two destinations does not need one. What you can open is the list of
 * things you have, so the list is what sits on the left and stays put.
 *
 * A row shows three things and no more - the title, one line of facts, and the state -
 * because a rail is scanned rather than read. At 17.5rem the fact line truncates rather
 * than wrapping: a wrapped description makes every row a different height and the list stops
 * being scannable, which is the only thing a rail is for. On a phone the rail is full width
 * and the same rows are used, which is why the component does not know or care which of the
 * two it is in.
 *
 * It takes the *result* rather than the list, so "nothing here yet" and "the library could
 * not be read" cannot be drawn as the same thing - which is the mistake a screen makes when
 * a failed fetch is quietly turned into `[]`.
 *
 * `activeSongId` marks the row for the song already on screen. It carries the same accent
 * treatment the chord strip gives its top chord (`border-signal/25 bg-signal/[0.07]`), so
 * "this is the selected one" means one thing across the whole product.
 *
 * The poller lives here too, because it is about this list: while a worker holds a job these
 * rows are a snapshot that will be wrong shortly, and this is the only place that can say so.
 */
export function LibraryRail({
  library,
  active = false,
  activeSongId,
  limit,
}: {
  library: Library;
  active?: boolean;
  activeSongId?: string;
  limit?: number;
}) {
  return (
    <Panel aria-labelledby="library-heading" className="p-4 sm:p-5">
      <PanelHeader
        id="library-heading"
        eyebrow="Library"
        right={
          library.ok ? (
            <span className="font-mono text-xs text-muted-foreground tabular-nums">
              {library.songs.length} {library.songs.length === 1 ? "track" : "tracks"}
            </span>
          ) : null
        }
      />

      {library.ok ? (
        <>
          {library.songs.length === 0 ? (
            <EmptyState className="mt-4 rounded-xl">
              Nothing here yet. Upload a track and it appears here with its analysis.
            </EmptyState>
          ) : (
            <ul className="mt-4 space-y-1">
              {library.songs.map((song) => (
                <li key={song.id}>
                  <Link
                    href={`/songs/${song.id}`}
                    aria-current={song.id === activeSongId ? "page" : undefined}
                    className={cn(
                      "block rounded-xl border px-3 py-2.5 transition-colors",
                      song.id === activeSongId
                        ? "border-signal/25 bg-signal/[0.07]"
                        : "border-transparent hover:border-white/[0.07] hover:bg-white/[0.03]",
                    )}
                  >
                    <span className="flex items-start justify-between gap-3">
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium">{song.title}</span>
                        <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                          {describeSong(song)}
                        </span>
                      </span>

                      <SongStatusTag song={song} />
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}

          {limit !== undefined && library.songs.length >= limit ? (
            <p className="mt-3 text-xs text-muted-foreground">The newest {limit}, newest first.</p>
          ) : null}

          <div className="mt-3 empty:mt-0">
            <LibraryRefresh active={active} />
          </div>
        </>
      ) : (
        // The failure is reported inside the rail rather than by replacing the screen: the
        // uploader beside it still works, and retrying is why somebody would be here.
        <p
          role="alert"
          className="mt-4 rounded-xl border border-destructive/40 bg-destructive/10 px-3 py-2.5 text-sm/relaxed text-destructive"
        >
          The library could not be loaded. {library.message}
        </p>
      )}
    </Panel>
  );
}
