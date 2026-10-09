import { NextResponse, type NextRequest } from "next/server";

import { safeRedirectPath } from "@/features/auth/schemas";
import { createSupabaseServerClient } from "@/lib/supabase/server";

/**
 * Landing point for every flow that redirects back from Supabase: Google OAuth,
 * email confirmation links and (later) password recovery.
 *
 * Supabase sends a short-lived `code`; exchanging it for a session is what turns
 * the redirect into signed-in cookies. The PKCE verifier lives in a cookie that
 * `@supabase/ssr` wrote when the flow started, which is why this has to be a
 * Route Handler rather than client-side code.
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const { searchParams, origin } = request.nextUrl;

  const next = safeRedirectPath(searchParams.get("next"));
  const code = searchParams.get("code");
  const providerError = searchParams.get("error_description") ?? searchParams.get("error");

  if (providerError) {
    return loginRedirect(origin, providerError);
  }

  if (!code) {
    return loginRedirect(origin, "That sign-in link is incomplete or has expired.");
  }

  try {
    const supabase = await createSupabaseServerClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);

    if (error) {
      return loginRedirect(origin, error.message);
    }
  } catch {
    // A malformed verifier or an unreachable Auth server: show the user
    // something actionable instead of a 500.
    return loginRedirect(origin, "We could not complete that sign-in. Please try again.");
  }

  const response = NextResponse.redirect(new URL(next, origin));

  // This response carries the new session cookie, so it must never be cached by
  // a CDN or reverse proxy - a cached copy would sign the next visitor in as
  // this user.
  response.headers.set("Cache-Control", "private, no-store");

  return response;
}

function loginRedirect(origin: string, message: string): NextResponse {
  const url = new URL("/login", origin);
  url.searchParams.set("error", message);

  return NextResponse.redirect(url);
}
