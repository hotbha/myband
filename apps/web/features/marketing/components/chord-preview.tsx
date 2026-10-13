"use client";

import { motion } from "motion/react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { FEATURED_ANALYSIS } from "../demo-analysis";
import { Reveal } from "./reveal";
import { SectionHeading } from "./section-heading";

/**
 * The chord timeline, drawn the way the song page draws it.
 *
 * The page's demo is the real interface rather than a screenshot: the same two readings on
 * the same toggle, with the same `aria-pressed` buttons a keyboard user gets in the
 * product. **Simple** shows each chord as the triad underneath it, which is what somebody
 * playing along wants; **as detected** shows the label the detector produced, `C#sus2` and
 * `G#maj7` included.
 *
 * What is shown is the ranked progression - the six chords the recording keeps returning to,
 * in the order the API ranks them by coverage. Bar-level timings are not printed here,
 * because they belong to one specific run of one specific upload, and the caption says so
 * instead of inventing a plausible-looking timeline.
 *
 * Both readings come from `demo-analysis.ts` rather than being derived in the browser:
 * `chord_summary.parent_state` decides those labels in Python, and a second implementation
 * here would be a second opinion about one song.
 */
type Reading = "simple" | "detected";

const READINGS: { id: Reading; label: string; hint: string }[] = [
  { id: "simple", label: "Simple", hint: "Every chord as the triad underneath it" },
  { id: "detected", label: "As detected", hint: "The label the detector actually produced" },
];

export function ChordPreview() {
  const [reading, setReading] = useState<Reading>("simple");
  const { chords } = FEATURED_ANALYSIS;
  const labels = reading === "simple" ? chords.simple : chords.asDetected;

  return (
    <section
      id="chords"
      aria-labelledby="chords-title"
      className="scroll-mt-24 px-5 py-20 sm:px-6 sm:py-28"
    >
      <div className="mx-auto max-w-6xl">
        <SectionHeading
          id="chords-title"
          eyebrow="Chord timeline"
          title="Every chord, and how sure it was"
          lede="A wall of chords is not an answer. This is the same analysis read two ways - the triads you can play, or the exact labels the detector produced - with the confidence attached, so you know which bars to double-check."
        />

        <Reveal className="mt-14">
          <div className="relative overflow-hidden rounded-3xl border border-white/[0.08] bg-white/[0.025] p-5 backdrop-blur-xl sm:p-7">
            <div className="absolute inset-x-10 top-0 h-px bg-gradient-to-r from-transparent via-signal/60 to-transparent" />

            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className="font-mono text-[0.6rem] tracking-[0.18em] text-muted-foreground uppercase">
                  {FEATURED_ANALYSIS.title} · {FEATURED_ANALYSIS.key}
                </p>
                <h3 className="mt-2 font-display text-lg tracking-tight">
                  Chords it keeps returning to
                </h3>
              </div>

              <div
                role="group"
                aria-label="Chord labels"
                className="inline-flex items-center gap-1"
              >
                {READINGS.map((option) => (
                  <Button
                    key={option.id}
                    type="button"
                    size="xs"
                    variant={reading === option.id ? "secondary" : "ghost"}
                    aria-pressed={reading === option.id}
                    title={option.hint}
                    onClick={() => setReading(option.id)}
                  >
                    {option.label}
                  </Button>
                ))}
              </div>
            </div>

            <motion.ol
              key={reading}
              data-reveal=""
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, ease: "easeOut" }}
              className="mt-6 grid grid-cols-3 gap-2 sm:grid-cols-6"
            >
              {labels.map((label, index) => (
                <li
                  key={`${index}-${label}`}
                  className={cn(
                    "rounded-xl border border-white/[0.07] bg-white/[0.02] px-3 py-4 text-center transition-colors hover:border-signal/30",
                    index === 0 && "border-signal/25 bg-signal/[0.07]",
                  )}
                >
                  <span className="font-mono text-[0.6rem] text-muted-foreground/70">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span className="mt-1.5 block font-display text-xl tracking-tight">{label}</span>
                </li>
              ))}
            </motion.ol>

            <dl className="mt-6 grid gap-3 border-t border-white/[0.07] pt-5 sm:grid-cols-3">
              <Figure label="Chord segments" value={`${chords.segments}`} />
              <Figure label="Mean confidence" value={`${Math.round(chords.confidence * 100)}%`} />
              <Figure label="Detector" value={chords.detector} mono />
            </dl>
          </div>

          <p className="mt-4 text-xs/relaxed text-muted-foreground">
            The chords above are this recording&apos;s real ranked progression, and both readings
            are the API&apos;s own. Bar-level timings live on the song page, where they belong to
            one specific upload.
          </p>
        </Reveal>
      </div>
    </section>
  );
}

/** One figure under the strip. */
function Figure({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="font-mono text-[0.58rem] tracking-[0.16em] text-muted-foreground uppercase">
        {label}
      </dt>
      <dd className={cn("mt-1.5 text-sm font-medium", mono && "font-mono text-[0.78rem]")}>
        {value}
      </dd>
    </div>
  );
}
