import { redirect } from "next/navigation";
import { z } from "zod";

import { createSupabaseServerClient } from "@/lib/supabase/server";

import { DEFAULT_REDIRECT } from "./schemas";

/**
 * The signed-in user as far as the server is concerned. Deliberately just the
 * three fields the UI needs; extend it from `user_metadata` when the dashboard
 * starts using more (avatars, preferences, ...).
 */
export type AuthIdentity = {
  id: string;
  email: string | null;
  name: string | null;
};

/**
 * The Supabase SDK decodes the JWT but TypeScript knows nothing about the
 * payload's shape, so it is parsed before a single field is read.
 */
const claimsSchema = z.object({
  sub: z.string().min(1),
  email: z.string().nullish(),
  user_metadata: z.record(z.string(), z.unknown()).nullish(),
});

/** Providers spell the display name differently; first hit wins. */
const NAME_CLAIMS = ["full_name", "name"] as const;

/**
 * Verified identity for the current request, or `null` when there is none.
 *
 * `getClaims()` verifies the access-token signature - locally, against cached
 * JWKS, for projects on asymmetric signing keys (the default), and via the Auth
 * server for symmetric ones - and refreshes the session first when the token is
 * near expiry. Reach for `getUser()` instead only when the freshest user record
 * is what matters (a plan change, an email change), since it always costs a
 * network round trip.
 *
 * Do not use `getSession()` for this: it reads the cookie without revalidating
 * it, and cookies are attacker-controlled.
 */
export async function getIdentity(): Promise<AuthIdentity | null> {
  const supabase = await createSupabaseServerClient();
  const { data } = await supabase.auth.getClaims();
  const parsed = claimsSchema.safeParse(data?.claims);

  if (!parsed.success) {
    return null;
  }

  return {
    id: parsed.data.sub,
    email: parsed.data.email ?? null,
    name: readMetadataString(parsed.data.user_metadata ?? {}, NAME_CLAIMS),
  };
}

/**
 * Server-side gate for protected routes: redirects to the login page instead of
 * returning `null`.
 *
 * Middleware already blocks anonymous requests, but middleware is not an
 * authorization boundary - a single matcher or config change would expose every
 * page behind it (see CVE-2025-29927). Each protected entry point re-checks.
 */
export async function requireIdentity(nextPath: string = DEFAULT_REDIRECT): Promise<AuthIdentity> {
  const identity = await getIdentity();

  if (!identity) {
    redirect(`/login?next=${encodeURIComponent(nextPath)}`);
  }

  return identity;
}

function readMetadataString(
  metadata: Record<string, unknown>,
  keys: readonly string[],
): string | null {
  for (const key of keys) {
    const value = metadata[key];

    if (typeof value === "string" && value.length > 0) {
      return value;
    }
  }

  return null;
}
