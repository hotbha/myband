import {
  chordsSchema,
  sectionsSchema,
  songListSchema,
  songWithJobSchema,
  type Chords,
  type Sections,
  type SongWithJob,
} from "@myband/shared";

import { apiFetch, messageFor, requireBaseUrl } from "@/lib/api";
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

/**
 * How many songs a screen shows. The API caps `limit` at 100.
 *
 * Exported because the screen that renders the list has to be able to say when the list is
 * a window rather than everything: a rail that silently stops at twenty reads as "you have
 * twenty songs".
 */
export const LIBRARY_LIMIT = 20;

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

/**
 * The library, or why it is not here.
 *
 * A failing API is reported rather than thrown. An exception inside a Server Component
 * replaces the whole route with an error screen, which would take the uploader down with it
 * - and the uploader is what somebody would use to try again. So the shape of the failure
 * is part of this module's contract, and everything that draws the library takes the union
 * rather than an array, which is what makes "the list is empty" and "the list could not be
 * read" impossible to confuse.
 */
export type Library = { ok: true; songs: SongWithJob[] } | { ok: false; message: string };

export async function loadLibrary(): Promise<Library> {
  try {
    return { ok: true, songs: await fetchLibrary() };
  } catch (cause) {
    return { ok: false, message: messageFor(cause) };
  }
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
 * A song's sections (`GET /songs/{id}/sections`).
 *
 * The same read as the chord timeline and the same reasoning: the list is what a screen renders, so
 * the API fetches the object and this is handed the answer. Ownership was checked before any of it
 * was returned.
 */
export async function fetchSections(songId: string): Promise<Sections> {
  return apiFetch(
    { path: `/songs/${songId}/sections`, baseUrl: baseUrl(), token: await requireToken() },
    sectionsSchema,
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
