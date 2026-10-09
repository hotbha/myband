import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import { getSupabaseEnv } from "./env";

type AuthCookie = { name: string; value: string; options: CookieOptions };

const LOGIN_PATH = "/login";
const AUTHENTICATED_HOME = "/dashboard";

/**
 * Paths that do not need a session.
 *
 * Everything else is protected by default, so a route added tomorrow is gated
 * without anybody remembering to list it. The inverse rule - a list of
 * protected paths - fails open the moment a route is forgotten, which is how
 * dashboards end up public.
 */
const PUBLIC_PATHS: ReadonlySet<string> = new Set(["/", LOGIN_PATH, "/auth/callback"]);

/**
 * Refreshes the Supabase session and enforces route protection.
 *
 * Runs before every matched request and does two things:
 *
 * 1. `getClaims()` verifies the access token and refreshes the session when the
 *    token is close to expiring. The refreshed tokens are written back through
 *    `setAll` - this is what keeps a server-rendered session alive.
 * 2. Requests to a protected path without a verified identity are redirected to
 *    `/login`, carrying the original path so the user lands where they wanted.
 *
 * `getClaims()` is called before any response is built on purpose: a refresh
 * that completes after the response is committed cannot be written to cookies
 * and would be lost.
 */
export async function updateSession(request: NextRequest): Promise<NextResponse> {
  let response = NextResponse.next({ request });
  let refreshedCookies: AuthCookie[] = [];
  const refreshedHeaders: Record<string, string> = {};

  const { url, publishableKey } = getSupabaseEnv();

  const supabase = createServerClient(url, publishableKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet, headers) {
        for (const { name, value } of cookiesToSet) {
          request.cookies.set(name, value);
        }

        refreshedCookies = [...refreshedCookies, ...cookiesToSet];
        Object.assign(refreshedHeaders, headers);

        // Rebuild the response so the refreshed cookies are forwarded to the
        // Server Components that render this request.
        response = NextResponse.next({ request });
      },
    },
  });

  const { data } = await supabase.auth.getClaims();
  const isAuthenticated = Boolean(data?.claims);
  const { pathname, search } = request.nextUrl;

  if (!isAuthenticated && !PUBLIC_PATHS.has(pathname)) {
    return withRefreshedCookies(
      NextResponse.redirect(loginUrl(request, `${pathname}${search}`)),
      refreshedCookies,
      refreshedHeaders,
    );
  }

  if (isAuthenticated && pathname === LOGIN_PATH) {
    return withRefreshedCookies(
      NextResponse.redirect(new URL(AUTHENTICATED_HOME, request.url)),
      refreshedCookies,
      refreshedHeaders,
    );
  }

  return withRefreshedCookies(response, refreshedCookies, refreshedHeaders);
}

function loginUrl(request: NextRequest, nextPath: string): URL {
  const url = new URL(LOGIN_PATH, request.url);
  url.searchParams.set("next", nextPath);
  return url;
}

/**
 * Copies the cookies produced by a token refresh - and the cache headers
 * Supabase ships with them - onto the response that is actually returned.
 *
 * The headers matter when deployed behind a CDN or reverse proxy: a cached
 * response carrying `Set-Cookie` would hand one user's session to the next.
 */
function withRefreshedCookies(
  response: NextResponse,
  cookies: readonly AuthCookie[],
  headers: Record<string, string>,
): NextResponse {
  for (const { name, value, options } of cookies) {
    response.cookies.set(name, value, options);
  }

  for (const [name, value] of Object.entries(headers)) {
    response.headers.set(name, value);
  }

  return response;
}
