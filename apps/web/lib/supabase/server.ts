import { createServerClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";
import { cookies } from "next/headers";

import { getSupabaseEnv } from "./env";

/**
 * Supabase client for Server Components, Server Actions and Route Handlers.
 *
 * A new client is created per request and never cached in a module-level
 * variable: it holds the caller's session and writes their cookies, so sharing
 * one instance across requests would leak sessions between users. Session
 * initialisation is lazy - nothing reaches the network until `getClaims()`,
 * `getUser()` or `getSession()` is called.
 *
 * The session lives in cookies, which is what makes it readable by the server
 * on the next request.
 */
export async function createSupabaseServerClient(): Promise<SupabaseClient> {
  const cookieStore = await cookies();
  const { url, publishableKey } = getSupabaseEnv();

  return createServerClient(url, publishableKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          for (const { name, value, options } of cookiesToSet) {
            cookieStore.set(name, value, options);
          }
        } catch {
          // Server Components render against a read-only cookie store, so writing
          // throws there. Ignoring the write is safe: middleware refreshes the
          // session on every request, so the worst case is one extra refresh.
        }
      },
    },
  });
}
