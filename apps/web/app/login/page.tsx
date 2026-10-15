import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { EmailAuthForm } from "@/features/auth/components/email-auth-form";
import { FormMessage } from "@/features/auth/components/form-message";
import { GoogleSignInForm } from "@/features/auth/components/google-sign-in-form";
import { safeRedirectPath } from "@/features/auth/schemas";
import { getIdentity } from "@/features/auth/session";
import { AmbientBackground } from "@/features/design-system/components/ambient-background";
import { BrandMark } from "@/features/design-system/components/brand-mark";
import { MicroLabel } from "@/features/design-system/components/eyebrow";
import { Panel } from "@/features/design-system/components/panel";
import { FEATURES } from "@/features/marketing/copy";

export const metadata: Metadata = {
  title: "Sign in - MyBand.video",
};

type LoginPageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

/**
 * The one screen a signed-out visitor can be sent to, and the only one that is two-up.
 *
 * The brand panel on the left is the landing page's evidence, reused: the same logo, the same
 * display headline, and the same four capabilities with the same measured numbers beside them -
 * both read out of `features/marketing/copy.ts`, which is the one place a claim about the product
 * is written. That is not decoration. Somebody arriving from the landing page has just been told
 * what this does, and a sign-in screen that greeted them with a bare form would be the moment the
 * product stopped looking like the advert. Below `lg` the panel collapses to a header block and the
 * four-item list is dropped: on a phone, at that moment, the form is the content.
 *
 * A Server Component, so the brand panel costs no JavaScript and the surface is a `.product` one -
 * the same palette, the same ambient canvas and the same `Panel` as the dashboard, because signing
 * in is part of the product and not an interstitial before it. `data-surface` is what tells
 * `globals.css` to paint the document behind the page too.
 *
 * The `searchParams` are read but never trusted: `next` goes through `safeRedirectPath` before it
 * reaches a button, and the other two are capped before they reach the DOM.
 */
export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = await searchParams;
  const next = safeRedirectPath(params.next);
  const error = readTextParam(params.error);
  // The landing page's beta form hands the address over in the query string, so somebody who
  // typed it there does not have to type it again here.
  const email = readTextParam(params.email);

  // Signed in already? Skip the form. Middleware does this as well; repeating it
  // here keeps the page correct on its own if the matcher is ever narrowed.
  const identity = await getIdentity();

  if (identity) {
    redirect(next);
  }

  return (
    <div
      className="dark product relative min-h-dvh overflow-x-clip text-foreground"
      data-surface="product"
    >
      <AmbientBackground variant="product" />

      <main
        id="main"
        className="mx-auto grid w-full max-w-5xl items-center gap-10 px-5 py-12 sm:px-6 lg:min-h-dvh lg:grid-cols-2 lg:gap-12 xl:gap-16"
      >
        <Panel>
          <BrandMark />

          {/* Display type, but a `p`: the page's one `h1` is the form's heading, and a second
              one would make the document outline claim there are two things here. */}
          <p className="mt-6 font-display text-3xl leading-[1.05] font-semibold tracking-[-0.035em] text-balance lg:text-4xl">
            Understand any song{" "}
            <span className="bg-gradient-to-r from-signal-soft via-signal to-pulse bg-clip-text text-transparent">
              in minutes
            </span>
          </p>

          <p className="mt-4 max-w-md text-sm/relaxed text-pretty text-muted-foreground">
            Upload a track and get its tempo, key, chords and a MIDI sketch back.
          </p>

          <ul className="mt-6 hidden space-y-3 border-t border-white/[0.07] pt-6 lg:block">
            {FEATURES.map(({ icon: Icon, title, meta }) => (
              <li key={title} className="flex items-center gap-3">
                <span className="grid size-8 shrink-0 place-items-center rounded-lg border border-white/[0.07] bg-white/[0.03]">
                  <Icon className="size-4 text-signal-soft" aria-hidden />
                </span>

                <span className="min-w-0">
                  <span className="block truncate text-sm">{title}</span>
                  <span className="block truncate font-mono text-[0.68rem] text-muted-foreground tabular-nums">
                    {meta}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel aria-labelledby="signin-heading" className="w-full lg:max-w-md lg:justify-self-end">
          <MicroLabel>Account</MicroLabel>

          <h1
            id="signin-heading"
            className="mt-1.5 font-display text-lg font-medium tracking-tight"
          >
            Sign in to MyBand.video
          </h1>

          <div className="mt-5 space-y-5">
            {error ? <FormMessage status="error">{error}</FormMessage> : null}

            <GoogleSignInForm next={next} />

            <div className="flex items-center gap-3">
              <span aria-hidden className="h-px flex-1 bg-border" />
              <MicroLabel>or</MicroLabel>
              <span aria-hidden className="h-px flex-1 bg-border" />
            </div>

            <EmailAuthForm next={next} defaultEmail={email} />
          </div>
        </Panel>
      </main>
    </div>
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
