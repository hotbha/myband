"use client";

import { ArrowRight, Play } from "lucide-react";
import { motion, type Variants } from "motion/react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

import { BUILT_WITH } from "../copy";
import { AnalysisConsole } from "./analysis-console";

/**
 * The hero: the claim on the left, the evidence on the right.
 *
 * The headline is the product's one sentence - "Understand any song in minutes" - and the
 * panel beside it is what makes that sentence worth believing, so the layout gives the
 * evidence more room than the claim (`0.85fr` against `1.15fr`) and lets it run off the
 * right edge on a wide screen. That deliberate imbalance is the whole composition: the
 * copy is a caption, the analyser is the object.
 *
 * The call to action is `Early Access` while the beta has seats, and the dashboard once
 * the visitor is already signed in - a returning tester should not be asked to sign up
 * again. The secondary action scrolls to the chord preview rather than to a video: there is
 * no demo video, and the preview below is a real screen.
 *
 * The stagger is one shared variant with a per-item delay, so the sequence is legible:
 * eyebrow, headline, subhead, buttons, caveat.
 */
const rise: Variants = {
  hidden: { opacity: 0, y: 20 },
  shown: { opacity: 1, y: 0 },
};

export function Hero({ signedIn }: { signedIn: boolean }) {
  const ctaHref = signedIn ? "/dashboard" : "/login";

  return (
    <section
      aria-labelledby="hero-title"
      className="relative px-5 pt-28 pb-14 sm:px-6 sm:pt-36 sm:pb-20 lg:pt-40"
    >
      <div className="mx-auto grid max-w-6xl items-center gap-12 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] lg:gap-8 xl:gap-14">
        <div>
          <motion.p
            data-reveal=""
            variants={rise}
            initial="hidden"
            animate="shown"
            transition={{ duration: 0.6, delay: 0.05, ease: [0.16, 1, 0.3, 1] }}
            className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 font-mono text-[0.62rem] tracking-[0.16em] text-muted-foreground uppercase"
          >
            <span className="size-1.5 animate-live-dot rounded-full bg-pulse" aria-hidden />
            Closed beta · 10 seats
          </motion.p>

          <motion.h1
            id="hero-title"
            data-reveal=""
            variants={rise}
            initial="hidden"
            animate="shown"
            transition={{ duration: 0.7, delay: 0.12, ease: [0.16, 1, 0.3, 1] }}
            className="mt-6 font-display text-[2.7rem] leading-[0.97] font-semibold tracking-[-0.035em] text-balance sm:text-6xl lg:text-[4.1rem]"
          >
            Understand Any Song{" "}
            <span className="bg-gradient-to-r from-signal-soft via-signal to-pulse bg-clip-text text-transparent">
              in Minutes
            </span>
          </motion.h1>

          <motion.p
            data-reveal=""
            variants={rise}
            initial="hidden"
            animate="shown"
            transition={{ duration: 0.7, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="mt-6 max-w-xl text-lg/relaxed text-pretty text-muted-foreground"
          >
            Upload a song and instantly discover BPM, Key, Chords, and MIDI. Built for musicians,
            producers, and creators.
          </motion.p>

          <motion.div
            data-reveal=""
            variants={rise}
            initial="hidden"
            animate="shown"
            transition={{ duration: 0.7, delay: 0.28, ease: [0.16, 1, 0.3, 1] }}
            className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center"
          >
            <Button
              asChild
              size="lg"
              className="h-11 w-full rounded-xl bg-gradient-to-br from-signal to-signal-strong px-6 text-[0.95rem] shadow-[0_16px_40px_-16px_var(--signal)] transition hover:brightness-110 sm:w-auto"
            >
              <Link href={ctaHref}>
                {signedIn ? "Open dashboard" : "Early Access"}
                <ArrowRight className="size-4" aria-hidden />
              </Link>
            </Button>

            <Button
              asChild
              size="lg"
              variant="outline"
              className="h-11 w-full rounded-xl border-white/15 bg-white/[0.03] px-6 text-[0.95rem] hover:bg-white/[0.07] sm:w-auto"
            >
              <Link href="#chords">
                <Play className="size-4" aria-hidden />
                See Demo
              </Link>
            </Button>
          </motion.div>

          <motion.p
            data-reveal=""
            variants={rise}
            initial="hidden"
            animate="shown"
            transition={{ duration: 0.7, delay: 0.36, ease: [0.16, 1, 0.3, 1] }}
            className="mt-4 text-sm text-muted-foreground"
          >
            MP3 or WAV, up to 200 MiB. No card, nothing to install.
          </motion.p>
        </div>

        <AnalysisConsole className="lg:-mr-6 xl:-mr-20" />
      </div>

      {/* The stack, named. "AI-powered" is a claim anybody can make; librosa, chroma-viterbi
          and pYIN are the ones a musician can look up. */}
      <motion.ul
        data-reveal=""
        variants={rise}
        initial="hidden"
        animate="shown"
        transition={{ duration: 0.8, delay: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="mx-auto mt-14 flex max-w-6xl flex-wrap items-center gap-x-5 gap-y-2 font-mono text-[0.7rem] tracking-[0.08em] text-muted-foreground/70 lg:mt-20"
      >
        <li className="tracking-[0.16em] text-muted-foreground/50 uppercase">Runs on</li>
        {BUILT_WITH.map((tool) => (
          <li key={tool}>{tool}</li>
        ))}
      </motion.ul>
    </section>
  );
}
