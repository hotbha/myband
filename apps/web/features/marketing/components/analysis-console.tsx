"use client";

import { Check, Radio } from "lucide-react";
import { motion } from "motion/react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

import { FEATURED_ANALYSIS, PIPELINE_VERSION, waveformBars } from "../demo-analysis";
import { useCountUp } from "../use-count-up";
import { Waveform } from "./waveform";

/**
 * The analysis, one upload, exactly as the worker stored it.
 *
 * This is the page's argument made as an object rather than as a claim: a rail that says
 * the job finished, a waveform, six measurements, and the chords the song keeps returning
 * to. Every figure is read from `demo-analysis.ts`, which is a transcription of a real row
 * in `analysis_results` - so nothing here is a number somebody liked the look of.
 *
 * Two moments arrive at once, and that is the point: the counters run on mount, which makes
 * the panel feel like an instrument taking a measurement, and the chord chips fade in
 * behind them, which is the music arriving after the numbers. Reduced motion gets the
 * finished state immediately - see `[data-reveal]` in `globals.css`.
 *
 * The waveform is the one illustrated element and the caption says so: drawing the real
 * master would mean shipping somebody's recording in the JS bundle.
 */
export function AnalysisConsole({ className }: { className?: string }) {
  const { chords, midi } = FEATURED_ANALYSIS;
  const bars = waveformBars(64);

  const bpm = useCountUp(FEATURED_ANALYSIS.bpm, { decimals: 2 });
  const strength = useCountUp(FEATURED_ANALYSIS.keyStrength, { decimals: 2, duration: 1700 });
  const segments = useCountUp(chords.segments, { duration: 1700 });
  const confidence = useCountUp(Math.round(chords.confidence * 100), { duration: 1800 });
  const notes = useCountUp(midi.notes, { duration: 1900 });

  return (
    <figure className={cn("w-full", className)}>
      <motion.div
        data-reveal=""
        initial={{ opacity: 0, y: 32, scale: 0.985 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.9, delay: 0.25, ease: [0.16, 1, 0.3, 1] }}
        className="relative overflow-hidden rounded-3xl border border-white/10 bg-white/[0.035] p-4 shadow-[0_40px_120px_-50px_oklch(0_0_0/0.95)] backdrop-blur-xl sm:p-6"
      >
        {/* A hairline of signal along the top edge: the one place the accent is a line
            rather than a fill. */}
        <div className="absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-signal/70 to-transparent" />

        <div className="flex items-center justify-between gap-3 font-mono text-[0.6rem] tracking-[0.18em] text-muted-foreground uppercase">
          <span className="flex items-center gap-2">
            <Radio className="size-3 text-pulse" aria-hidden />
            Job succeeded
          </span>
          <span>pipeline {PIPELINE_VERSION}</span>
        </div>

        <div className="mt-5 flex items-start justify-between gap-4">
          <div className="min-w-0">
            <figcaption className="truncate font-display text-xl font-semibold tracking-tight sm:text-2xl">
              {FEATURED_ANALYSIS.title}
            </figcaption>
            <p className="mt-1 font-mono text-[0.7rem] text-muted-foreground">
              MP3 · {FEATURED_ANALYSIS.duration} · {FEATURED_ANALYSIS.beats} beats
            </p>
          </div>

          <Badge
            variant="outline"
            className="shrink-0 gap-1.5 border-pulse/30 bg-pulse/10 font-mono text-[0.6rem] tracking-[0.12em] text-pulse uppercase"
          >
            <Check className="size-3" aria-hidden />
            MIDI ready
          </Badge>
        </div>

        <div
          data-reveal=""
          className="mt-5 h-24 rounded-2xl border border-white/[0.07] bg-black/25 px-3 py-2 sm:h-28"
        >
          <Waveform bars={bars} animated label="Waveform of the analysed recording" />
        </div>

        <dl className="mt-5 grid grid-cols-2 gap-2.5 sm:grid-cols-3">
          <Metric label="Tempo" value={bpm} unit="BPM" hint="tracked, not guessed" />
          <Metric label="Key" value={FEATURED_ANALYSIS.key} hint={`strength ${strength}`} />
          <Metric label="Chords" value={segments} unit="segments" hint="one timeline" />
          <Metric label="Confidence" value={confidence} unit="%" hint="mean, per chord" />
          <Metric label="MIDI" value={notes} unit="notes" hint="monophonic line" />
          <Metric label="Export" value={String(midi.bytes)} unit="B" hint="ready for your DAW" />
        </dl>

        {/* The music, arriving behind the numbers: the chords fade in after the counters
            have settled, so the panel reads as a measurement first and a song second. */}
        <div className="mt-5">
          <p className="font-mono text-[0.6rem] tracking-[0.16em] text-muted-foreground uppercase">
            Chords it keeps returning to
          </p>

          <div className="mt-3 flex flex-wrap gap-2">
            {chords.asDetected.map((chord, index) => (
              <motion.span
                key={chord}
                data-reveal=""
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.45, delay: 0.9 + index * 0.07, ease: "easeOut" }}
                className="rounded-lg border border-white/10 bg-white/[0.05] px-2.5 py-1 font-mono text-sm"
              >
                {chord}
              </motion.span>
            ))}
          </div>
        </div>
      </motion.div>

      <figcaption className="mt-4 text-xs/relaxed text-muted-foreground">
        A real beta upload, as the worker stored it - detector{" "}
        <span className="font-mono text-[0.7rem] text-foreground/80">{chords.detector}</span>,{" "}
        {chords.segments} chord segments, a {midi.notes}-note MIDI sketch. The waveform is drawn,
        not the master.
      </figcaption>
    </figure>
  );
}

/** One measurement: a label, the number, and the one line that keeps it honest. */
function Metric({
  label,
  value,
  unit,
  hint,
}: {
  label: string;
  value: string;
  unit?: string;
  hint: string;
}) {
  return (
    <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] px-3 py-2.5">
      <dt className="font-mono text-[0.58rem] tracking-[0.16em] text-muted-foreground uppercase">
        {label}
      </dt>
      <dd className="mt-1.5 flex items-baseline gap-1">
        <span className="font-mono text-lg leading-none font-medium tabular-nums">{value}</span>
        {unit ? (
          <span className="font-mono text-[0.7rem] text-muted-foreground">{unit}</span>
        ) : null}
      </dd>
      <p className="mt-1.5 text-[0.68rem] text-muted-foreground/80">{hint}</p>
    </div>
  );
}
