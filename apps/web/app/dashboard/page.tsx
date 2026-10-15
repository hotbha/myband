import type { Metadata } from "next";

import { requireIdentity } from "@/features/auth/session";
import { EmptyState } from "@/features/design-system/components/empty-state";
import { Panel, PanelHeader } from "@/features/design-system/components/panel";
import { AppShell } from "@/features/shell/components/app-shell";
import { AnalysisCard } from "@/features/uploads/components/analysis-card";
import { LibraryMetrics } from "@/features/uploads/components/library-metrics";
import { LibraryRail } from "@/features/uploads/components/library-rail";
import { UploadDropzone } from "@/features/uploads/components/upload-dropzone";
import { WorkInFlight } from "@/features/uploads/components/work-in-flight";
import { hasWorkInFlight } from "@/features/uploads/jobs";
import { isAnalysed } from "@/features/uploads/library-stats";
import { LIBRARY_LIMIT, loadLibrary } from "@/features/uploads/server-api";

export const metadata: Metadata = {
  title: "Dashboard - MyBand.video",
};

/**
 * The workspace: everything a returning user needs, in one screen.
 *
 * Three regions, and each one answers a different question. The **library** (left) is the
 * inventory: what do I have? The **analyses** (centre) are the results: what did it find
 * out? The **utility rail** is the work: what can I do, and what is running? All three are
 * drawn from one array of rows, fetched once in the request that renders the page, so
 * nothing here can disagree with anything else here.
 *
 * The columns are chosen by width, and the order they collapse in is the design decision
 * rather than an accident of the markup:
 *
 * * **one column** (below 768px) - upload, activity, analyses, library, metrics. The action
 *   first, then whether it is running, then the results, then the inventory, then the
 *   summary. Mobile is a scroll, so the order is a priority order.
 * * **two columns** (768px and up) - the library rail on the left, everything else in the
 *   main column.
 * * **three columns** (1280px and up) - rail, analyses, utility rail. The utility column
 *   only appears here because below 1280px the three fixed-width columns and their gaps do
 *   not fit in the viewport, and three cramped columns are worse than two comfortable ones.
 *
 * At 768px and up the placement is explicit (`col-start`/`row-start` on each region), which
 * is what lets the *document* order stay the mobile priority order while the *visual* order
 * is a workspace. See docs/WIREFRAMES.md, section 4.
 *
 * The page is a Server Component and reads the library in the same request that renders it:
 * one round trip to the API, no loading spinner, and nothing for the browser to fetch on
 * mount. Two Client Components sit on top of it - the uploader, which refreshes the page
 * when it has queued a job, and the poller inside the rail, which refreshes it while a job
 * is in flight. Neither of them owns a row.
 */
export default async function DashboardPage() {
  const identity = await requireIdentity("/dashboard");
  const library = await loadLibrary();

  const songs = library.ok ? library.songs : [];
  const analysed = songs.filter(isAnalysed);

  return (
    <AppShell identity={identity}>
      <div className="grid items-start gap-6 md:grid-cols-[17.5rem_minmax(0,1fr)] xl:grid-cols-[17.5rem_minmax(0,1fr)_20rem]">
        <div className="md:col-start-2 md:row-start-1 xl:col-start-3 xl:row-start-1">
          <UploadDropzone />
        </div>

        <div className="md:col-start-2 md:row-start-2 xl:col-start-3 xl:row-start-3">
          <WorkInFlight songs={songs} />
        </div>

        <div className="md:col-start-2 md:row-start-3 xl:col-start-2 xl:row-span-3 xl:row-start-1">
          <Panel aria-labelledby="analyses-heading">
            <PanelHeader
              id="analyses-heading"
              eyebrow="Recent analyses"
              title="What the analyser found"
              right={
                <span className="font-mono text-xs text-muted-foreground tabular-nums">
                  {analysed.length} of {songs.length}
                </span>
              }
            />

            {analysed.length === 0 ? (
              <EmptyState className="mt-4 rounded-xl">
                Nothing has been measured yet. Upload a track and its tempo, key and chords appear
                here.
              </EmptyState>
            ) : (
              <ul className="mt-4 space-y-3">
                {analysed.map((song) => (
                  <li key={song.id}>
                    <AnalysisCard song={song} />
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>

        <div className="md:col-start-1 md:row-span-4 md:row-start-1 xl:col-start-1 xl:row-span-3">
          <LibraryRail
            library={library}
            active={library.ok && hasWorkInFlight(library.songs)}
            limit={LIBRARY_LIMIT}
          />
        </div>

        <div className="md:col-start-2 md:row-start-4 xl:col-start-3 xl:row-start-2">
          <LibraryMetrics songs={songs} />
        </div>
      </div>
    </AppShell>
  );
}
