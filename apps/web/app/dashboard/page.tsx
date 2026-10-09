import type { Metadata } from "next";

import type { SongWithJob } from "@myband/shared";

import { LogoutButton } from "@/features/auth/components/logout-button";
import { requireIdentity } from "@/features/auth/session";
import { LibraryRefresh } from "@/features/uploads/components/library-refresh";
import { SongList } from "@/features/uploads/components/song-list";
import { UploadDropzone } from "@/features/uploads/components/upload-dropzone";
import { hasWorkInFlight } from "@/features/uploads/jobs";
import { fetchLibrary } from "@/features/uploads/server-api";
import { messageFor } from "@/lib/api";

export const metadata: Metadata = {
  title: "Dashboard - MyBand.video",
};

/**
 * Protected route.
 *
 * Middleware turns anonymous requests away before they get here; this second check
 * is the actual authorization boundary, so the page is safe even if the matcher is
 * narrowed or middleware is bypassed.
 *
 * The library is read on the server, in the same request that renders it: one round
 * trip to the API, no loading spinner, and nothing for the browser to fetch on
 * mount. Two client components sit on top of it - the uploader, which refreshes the page
 * when it has queued a job, and the poller, which refreshes it while a job is in flight.
 * Neither of them owns a row.
 */
export default async function DashboardPage() {
  const identity = await requireIdentity("/dashboard");
  const library = await loadLibrary();

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-3xl flex-col gap-8 px-6 py-12">
      <header className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Signed in as {identity.name ?? identity.email ?? identity.id}
          </p>
        </div>
        <LogoutButton />
      </header>

      <UploadDropzone />

      <section className="space-y-4">
        <div className="flex items-baseline justify-between gap-4">
          <h2 className="text-lg font-medium">Library</h2>
          {/* Renders nothing but the status line it is worth: while a worker holds a
              job, the list below is a snapshot that will be wrong shortly. */}
          {library.ok ? <LibraryRefresh active={hasWorkInFlight(library.songs)} /> : null}
        </div>
        {library.ok ? (
          <SongList songs={library.songs} />
        ) : (
          <p
            role="alert"
            className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            The library could not be loaded. {library.message}
          </p>
        )}
      </section>
    </main>
  );
}

type Library = { ok: true; songs: SongWithJob[] } | { ok: false; message: string };

/**
 * The library, or why it is not here.
 *
 * A failing API is reported in the page rather than thrown: an exception in a Server
 * Component replaces the whole route with an error screen, which would take the
 * uploader down with it - and the uploader is what someone would use to try again.
 */
async function loadLibrary(): Promise<Library> {
  try {
    return { ok: true, songs: await fetchLibrary() };
  } catch (cause) {
    return { ok: false, message: messageFor(cause) };
  }
}
