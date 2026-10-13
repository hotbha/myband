/**
 * What the landing page's analyser panel shows - and why it is real.
 *
 * Every number below was measured by this pipeline on a real file during the closed
 * beta run, then read back out of `public.analysis_results` (the `chords`, `key`,
 * `bpm` and `midi` rows of one session). Nothing here is a plausible-looking
 * placeholder: `117.45`, `C# minor` and the six chords are what the worker actually
 * wrote, which is the point of the panel - a demo that cannot be checked against the
 * product is worse than no demo.
 *
 * Two things are illustrations, and both are labelled as such where they render:
 *
 * * the **waveform** on the panel is drawn from a deterministic generator, not from
 *   the recording, because shipping a copyrighted master in the JS bundle is not an
 *   option;
 * * the **order** the chords are laid out in a strip is the API's own reading of the
 *   timeline. `asDetected` is the ranked progression the digest stores - the chords
 *   the song keeps returning to - and not a transcription of bar one.
 *
 * `simple` is the second reading the song page offers. It is spelled out rather than
 * derived: `chord_summary.parent_state` decides those labels in Python, and a second
 * implementation in the browser would be a second opinion about one song.
 */

export type DemoChords = {
  /** The detector's own name, straight out of the digest. */
  detector: string;
  /** How many labelled stretches the timeline has. */
  segments: number;
  /** The worker's mean confidence over the segments that named a chord, 0..1. */
  confidence: number;
  /** The ranked progression, exactly as stored. */
  asDetected: string[];
  /** The same chords as triads - the song page's "Simple" reading. */
  simple: string[];
};

export type DemoAnalysis = {
  title: string;
  duration: string;
  bpm: number;
  key: string;
  /** Krumhansl-Schmuckler correlation of the winning key. */
  keyStrength: number;
  /** Beats the tempo estimate was built from. */
  beats: number;
  chords: DemoChords;
  midi: {
    /** Notes in the sketch. */
    notes: number;
    /** Size of the exported `.mid`. */
    bytes: number;
    transcriber: string;
    /** The sketch covers the recording's first this many seconds. */
    windowSeconds: number;
  };
};

/** One whole beta run, as the panel's footer reports it. */
export type SampledTrack = {
  title: string;
  duration: string;
  bpm: number;
  key: string;
};

/** The pipeline that produced every result on this page. `MYBAND_PIPELINE_VERSION`. */
export const PIPELINE_VERSION = "0.2.0";

/** The song the hero panel and the chord preview are built from. */
export const FEATURED_ANALYSIS: DemoAnalysis = {
  title: "Tera Suroor",
  duration: "5:44",
  bpm: 117.45,
  key: "C# minor",
  keyStrength: 0.824,
  beats: 631,
  chords: {
    detector: "librosa-chroma-viterbi",
    segments: 170,
    confidence: 0.741,
    asDetected: ["C#m7", "C#maj7", "C#sus2", "G#maj7", "Amaj7", "C#"],
    simple: ["C#m", "C#", "C#", "G#", "A", "C#"],
  },
  midi: {
    notes: 29,
    bytes: 269,
    transcriber: "pyin-monophonic",
    windowSeconds: 30,
  },
};

/**
 * The three tracks that were uploaded through the browser and analysed end to end.
 *
 * Shown as a sample of the run rather than as testimonials, because there are no
 * testimonials yet - the beta has ten seats and they are not filled.
 */
export const SAMPLE_RUN: SampledTrack[] = [
  { title: "Tera Suroor", duration: "5:44", bpm: 117.45, key: "C# minor" },
  { title: "Jyoti", duration: "4:07", bpm: 89.1, key: "G major" },
  { title: "Ganesha", duration: "1:02", bpm: 107.67, key: "C# minor" },
];

/**
 * Bar heights for the panel's waveform.
 *
 * Deterministic on purpose. A `Math.random()` here would render one set of bars on the
 * server and another in the browser, and React would report a hydration mismatch on
 * the page's most prominent element. This is a seeded generator with a fixed shape
 * (loud at the start, a quiet patch in the middle, a busy outro) because a waveform
 * that looks like noise does not look like music.
 */
export function waveformBars(count: number, seed = 2_026_100_9): number[] {
  let state = seed;

  return Array.from({ length: count }, (_, index) => {
    state = (state * 1_103_515_245 + 12_345) % 2_147_483_648;
    const noise = state / 2_147_483_648;
    const position = index / count;
    const envelope =
      0.42 + 0.3 * Math.sin(position * Math.PI * 1.4) + 0.18 * Math.cos(position * Math.PI * 5);
    const dip = position > 0.44 && position < 0.58 ? 0.45 : 1;

    return Math.min(1, Math.max(0.08, (envelope * noise + 0.22) * dip));
  });
}
