import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { EmailAuthForm } from "@/features/auth/components/email-auth-form";
import { FormMessage } from "@/features/auth/components/form-message";
import { GoogleSignInForm } from "@/features/auth/components/google-sign-in-form";
import { safeRedirectPath } from "@/features/auth/schemas";
import { getIdentity } from "@/features/auth/session";

export const metadata: Metadata = {
  title: "Sign in - MyBand.video",
};

type LoginPageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = await searchParams;
  const next = safeRedirectPath(params.next);
  const error = readTextParam(params.error);

  // Signed in already? Skip the form. Middleware does this as well; repeating it
  // here keeps the page correct on its own if the matcher is ever narrowed.
  const identity = await getIdentity();

  if (identity) {
    redirect(next);
  }

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-sm flex-col justify-center gap-6 px-6 py-12">
      <div className="space-y-1.5">
        <h1 className="text-2xl font-semibold tracking-tight">Sign in to MyBand.video</h1>
        <p className="text-sm text-muted-foreground">
          Upload a track and get BPM, key, chords, MIDI and song sections back.
        </p>
      </div>

      {error ? <FormMessage status="error">{error}</FormMessage> : null}

      <GoogleSignInForm next={next} />

      <div className="flex items-center gap-3 text-xs tracking-wide text-muted-foreground uppercase">
        <span className="h-px flex-1 bg-border" />
        or
        <span className="h-px flex-1 bg-border" />
      </div>

      <EmailAuthForm next={next} />
    </main>
  );
}

/**
 * Reads a text search param, ignoring repeated params and capping the length so
 * a crafted URL cannot push an unbounded string into the page.
 */
function readTextParam(value: string | string[] | undefined): string | null {
  const raw = Array.isArray(value) ? value[0] : value;

  if (typeof raw !== "string") {
    return null;
  }

  const trimmed = raw.trim();

  return trimmed.length > 0 ? trimmed.slice(0, 200) : null;
}
