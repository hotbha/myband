import { songListSchema, type SongWithJob } from "@myband/shared";

import { apiFetch, requireBaseUrl } from "@/lib/api";
import { createSupabaseServerClient } from "@/lib/supabase/server";

/**
 * The API, called from a Server Component.
 *
 * Same contract as the browser client, different credentials: the token comes from
 * the request's cookies rather than from the SDK in a tab, and the base URL is a
 * server-only variable so an internal hostname is never handed to a browser.
 *
 * `getSession()` is the *only* thing read from it here. That call does not verify
 * the token - `features/auth/session.ts` explains why it must not be trusted for
 * authorization - but nothing is trusted on the strength of it: the token is
 * presented to the API, which verifies the signature and the claims before it looks
 * at a single row.
 */

/** How many songs the dashboard shows. The API caps `limit` at 100. */
const LIBRARY_LIMIT = 20;

export async function fetchLibrary(): Promise<SongWithJob[]> {
  const supabase = await createSupabaseServerClient();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;

  if (!token) {
    // The page guard has already turned anonymous callers away, so this is a
    // session that could not be refreshed rather than an open door.
    return [];
  }

  const { songs } = await apiFetch(
    {
      path: `/songs?limit=${LIBRARY_LIMIT}`,
      baseUrl: requireBaseUrl(process.env.API_BASE_URL, "API_BASE_URL"),
      token,
    },
    songListSchema,
  );

  return songs;
}
