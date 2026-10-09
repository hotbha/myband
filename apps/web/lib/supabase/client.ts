import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

import { getSupabaseEnv } from "./env";

/**
 * Supabase client for Client Components.
 *
 * One instance per tab, created on first use. The SDK holds the session and its
 * refresh timer *on the instance*, so a second one would start a second refresh
 * loop and the two would race over the same cookies.
 */
let client: SupabaseClient | undefined;

export function createSupabaseBrowserClient(): SupabaseClient {
  if (!client) {
    const { url, publishableKey } = getSupabaseEnv();
    client = createBrowserClient(url, publishableKey);
  }

  return client;
}

/**
 * The access token for the signed-in user, for calling `apps/api`.
 *
 * `getSession()` is the right call here, and only here: this code runs in the
 * browser, which *is* the holder of the session, and the SDK refreshes an expired
 * token before handing one back. The API verifies the signature and the claims
 * itself, so nothing is trusted merely because the browser offered it.
 */
export async function getAccessToken(): Promise<string> {
  const { data, error } = await createSupabaseBrowserClient().auth.getSession();
  const token = data.session?.access_token;

  if (error || !token) {
    throw new Error("You are not signed in. Reload the page and sign in again.");
  }

  return token;
}
