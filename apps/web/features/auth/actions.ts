"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { createSupabaseServerClient } from "@/lib/supabase/server";

import {
  invalidInputState,
  safeRedirectPath,
  signInSchema,
  signUpSchema,
  type AuthActionState,
} from "./schemas";

const INVALID_CREDENTIALS = "That email and password combination does not match an account.";
const UNREACHABLE_AUTH_SERVER = "Sign-in is temporarily unavailable. Please try again.";
const UNEXPECTED_ERROR = "Something went wrong. Please try again.";

/**
 * Auth Server Actions.
 *
 * Everything runs on the server, so the browser never holds a Supabase key and
 * never sees a raw error object. Failures come back as `AuthActionState` for
 * `useActionState` instead of being thrown - a thrown error inside an action
 * surfaces as an opaque "server error" in the browser, which tells the user
 * nothing. Successful paths call `redirect()`, which throws on purpose: that is
 * how Next.js navigates from an action.
 */

/**
 * Sign in or sign up with email and password.
 *
 * The form has two submit buttons that post the same fields and differ only in
 * the `intent` value, so no React state is needed to know which one ran (and it
 * keeps working before hydration).
 */
export async function emailAuth(
  _state: AuthActionState,
  formData: FormData,
): Promise<AuthActionState> {
  return formData.get("intent") === "sign-up" ? signUp(formData) : signIn(formData);
}

/**
 * Starts the Google OAuth flow.
 *
 * Supabase answers with the provider URL to send the browser to; Google then
 * returns to `/auth/callback`, where the code is exchanged for a session. The
 * PKCE verifier is stored in a cookie by `@supabase/ssr`, so the exchange has to
 * happen server-side.
 */
export async function signInWithGoogle(
  _state: AuthActionState,
  formData: FormData,
): Promise<AuthActionState> {
  const next = safeRedirectPath(formData.get("next"));
  const origin = await getRequestOrigin();
  const supabase = await createSupabaseServerClient();

  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: "google",
    options: {
      redirectTo: `${origin}/auth/callback?next=${encodeURIComponent(next)}`,
    },
  });

  if (error || !data.url) {
    return { status: "error", message: error?.message ?? UNEXPECTED_ERROR, fieldErrors: {} };
  }

  redirect(data.url);
}

/**
 * Ends the session for this browser and returns the user to the login page.
 *
 * `scope: "local"` clears this browser only. The default (`global`) also revokes
 * the refresh token on the user's other devices - a surprising side effect for a
 * plain "Log out" button, and a common source of "invalid refresh token" errors
 * when other tabs or devices still hold the old token.
 */
export async function signOut(): Promise<void> {
  const supabase = await createSupabaseServerClient();
  await supabase.auth.signOut({ scope: "local" });
  redirect("/login");
}

async function signIn(formData: FormData): Promise<AuthActionState> {
  const next = safeRedirectPath(formData.get("next"));
  const parsed = signInSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
  });

  if (!parsed.success) {
    return invalidInputState(parsed.error);
  }

  const supabase = await createSupabaseServerClient();
  const { error } = await supabase.auth.signInWithPassword(parsed.data);

  if (error) {
    return {
      status: "error",
      message: messageForSignInError(error),
      fieldErrors: {},
    };
  }

  redirect(next);
}

/**
 * Wrong credentials deserve a precise answer; a rate limit or an unreachable
 * Auth server does not, because the SDK's own wording for those is
 * developer-speak ("fetch failed") rather than something to show a user.
 */
function messageForSignInError(error: { code?: string; status?: number; message: string }): string {
  if (error.code === "invalid_credentials") {
    return INVALID_CREDENTIALS;
  }

  if (error.status === undefined || error.status === 0) {
    return UNREACHABLE_AUTH_SERVER;
  }

  // Everything else (unconfirmed email, rate limit) is worth showing verbatim.
  return error.message;
}

async function signUp(formData: FormData): Promise<AuthActionState> {
  const next = safeRedirectPath(formData.get("next"));
  const parsed = signUpSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
  });

  if (!parsed.success) {
    return invalidInputState(parsed.error);
  }

  const origin = await getRequestOrigin();
  const supabase = await createSupabaseServerClient();

  const { data, error } = await supabase.auth.signUp({
    email: parsed.data.email,
    password: parsed.data.password,
    options: {
      // Where the confirmation link lands; /auth/callback exchanges the code.
      emailRedirectTo: `${origin}/auth/callback?next=${encodeURIComponent(next)}`,
    },
  });

  if (error) {
    return { status: "error", message: error.message, fieldErrors: {} };
  }

  // With email confirmation enabled no session is issued yet. An address that
  // already has an account also comes back without a session (Supabase returns a
  // decoy user), so this page cannot be used to find out who is registered.
  if (!data.session) {
    return {
      status: "notice",
      message: "Check your inbox and open the link we sent you to finish signing up.",
      fieldErrors: {},
    };
  }

  redirect(next);
}

/**
 * Origin of the incoming request, used to build the URLs Supabase redirects back
 * to. Derived from headers instead of a hardcoded environment variable so
 * preview deployments work unchanged; `x-forwarded-*` covers reverse proxies.
 * Whatever this resolves to must be listed in Supabase's Redirect URLs.
 */
async function getRequestOrigin(): Promise<string> {
  const requestHeaders = await headers();
  const origin = requestHeaders.get("origin");

  if (origin) {
    return origin;
  }

  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host");

  if (!host) {
    return "http://localhost:3000";
  }

  const isLocal = host.startsWith("localhost") || host.startsWith("127.0.0.1");
  const protocol = requestHeaders.get("x-forwarded-proto") ?? (isLocal ? "http" : "https");

  return `${protocol}://${host}`;
}
