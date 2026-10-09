import {
  chordsSchema,
  songListSchema,
  songWithJobSchema,
  type Chords,
  type SongWithJob,
} from "@myband/shared";

import { apiFetch, requireBaseUrl } from "@/lib/api";
import { createSupabaseServerClient } from "@/lib/supabase/server";

/**
 * The API, called from a Server Component.
 *
 * Same contract as the browser client, different credentials: the token comes from the request's
 * cookies rather than from the SDK in a tab, and the base URL is a server-only variable so an
 * internal hostname is never handed to a browser.
 *
 * `getSession()` is the *only* thing read from it here. That call does not verify the token -
 * `features/auth/session.ts` explains why it must not be trusted for authorization - but nothing is
 * trusted on the strength of it: the token is presented to the API, which verifies the signature and
 * the claims before it looks at a single row.
 */

/** How many songs the dashboard shows. The API caps `limit` at 100. */
const LIBRARY_LIMIT = 20;

function baseUrl(): string {
  return requireBaseUrl(process.env.API_BASE_URL, "API_BASE_URL");
}

/** The caller's access token, or `null` when the session could not be read at all. */
async function accessToken(): Promise<string | null> {
  const supabase = await createSupabaseServerClient();
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

export async function fetchLibrary(): Promise<SongWithJob[]> {
  const token = await accessToken();

  if (!token) {
    // The page guard has already turned anonymous callers away, so this is a session that could
    // not be refreshed rather than an open door.
    return [];
  }

  const { songs } = await apiFetch(
    { path: `/songs?limit=${LIBRARY_LIMIT}`, baseUrl: baseUrl(), token },
    songListSchema,
  );

  return songs;
}

/** One song and its current job: what a screen about a single track is about. */
export async function fetchSong(songId: string): Promise<SongWithJob> {
  return apiFetch(
    { path: `/songs/${songId}`, baseUrl: baseUrl(), token: await requireToken() },
    songWithJobSchema,
  );
}

/**
 * A song's chord timeline (`GET /songs/{id}/chords`).
 *
 * The timeline itself rather than a link, unlike the MIDI: a screen renders this, so the API is the
 * thing that reads the object and the browser is handed the answer. Ownership was checked before
 * any of it was returned.
 */
export async function fetchChords(songId: string): Promise<Chords> {
  return apiFetch(
    { path: `/songs/${songId}/chords`, baseUrl: baseUrl(), token: await requireToken() },
    chordsSchema,
  );
}

/**
 * The caller's token, or a failure worth showing.
 *
 * Deliberately not the empty answer `fetchLibrary` gives: a library that cannot be read is still a
 * usable page - the uploader on it works - while a song page with no song is not. A session that
 * cannot be read there is an error, and saying so is more useful than rendering nothing.
 */
async function requireToken(): Promise<string> {
  const token = await accessToken();

  if (!token) {
    throw new Error("Your session has expired. Sign in again to see this song.");
  }

  return token;
}
