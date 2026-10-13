import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

import { Reveal } from "./reveal";

/**
 * The last thing on the page, and the only section that is one sentence long.
 *
 * By this point a reader has seen the panel, the features, the chords and the caveats; what
 * is left is permission to try it. The primary action is the same one the hero offers -
 * `Request Beta Access` - because a second, differently-named action at the bottom of a page
 * is how landing pages convince people they have missed something.
 */
export function FinalCta({ signedIn }: { signedIn: boolean }) {
  return (
    <section aria-labelledby="final-cta-title" className="px-5 py-20 sm:px-6 sm:py-28">
      <div className="mx-auto max-w-3xl text-center">
        <Reveal>
          <h2
            id="final-cta-title"
            className="font-display text-4xl leading-[1.02] font-semibold tracking-[-0.035em] text-balance sm:text-5xl lg:text-[3.4rem]"
          >
            Start Understanding{" "}
            <span className="bg-gradient-to-r from-signal-soft via-signal to-pulse bg-clip-text text-transparent">
              Music Better
            </span>
          </h2>

          <p className="mx-auto mt-6 max-w-xl text-lg/relaxed text-pretty text-muted-foreground">
            Upload one song and see what comes back. If the analysis tells you something you did not
            already know, the beta earned its seat.
          </p>

          <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Button
              asChild
              size="lg"
              className="h-11 w-full rounded-xl bg-gradient-to-br from-signal to-signal-strong px-6 text-[0.95rem] shadow-[0_16px_44px_-18px_var(--signal)] transition hover:brightness-110 sm:w-auto"
            >
              <Link href={signedIn ? "/dashboard" : "/login"}>
                {signedIn ? "Open dashboard" : "Request Beta Access"}
                <ArrowRight className="size-4" aria-hidden />
              </Link>
            </Button>

            <Button
              asChild
              size="lg"
              variant="ghost"
              className="h-11 w-full rounded-xl px-6 text-[0.95rem] text-muted-foreground hover:text-foreground sm:w-auto"
            >
              <Link href="#features">See what you get</Link>
            </Button>
          </div>

          <p className="mt-6 font-mono text-[0.68rem] tracking-[0.06em] text-muted-foreground">
            MP3 · WAV · 200 MiB · no card
          </p>
        </Reveal>
      </div>
    </section>
  );
}
