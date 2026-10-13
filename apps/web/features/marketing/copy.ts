/**
 * The landing page's words, and the shape of every section that repeats.
 *
 * Copy lives here rather than inside the components for the same reason the API's
 * schemas live in `@myband/shared`: a claim and the thing it claims about should be
 * editable in one place, and this is the surface most likely to be rewritten by
 * somebody who is not a developer.
 *
 * Two rules hold everywhere in this file:
 *
 * 1. **Nothing is claimed that the product does not do today.** Song sections, the AI
 *    guitarist, the AI drummer and band generation appear once, in `ROADMAP`, under a
 *    heading that says they are not available.
 * 2. **Every number is one the pipeline measured.** The figures in the feature cards
 *    and the answers are taken from `demo-analysis.ts` and from the modules that
 *    produced them, so a tester who checks will find them.
 */
import {
  Activity,
  AudioWaveform,
  Download,
  FileMusic,
  GraduationCap,
  Guitar,
  Layers,
  ListMusic,
  Mic,
  Music,
  SlidersHorizontal,
  Upload,
  Wand2,
} from "lucide-react";
import type { ComponentType } from "react";

/** What an icon slot accepts. Deliberately loose: any component that draws an SVG. */
type Icon = ComponentType<{ className?: string }>;

export type Feature = {
  icon: Icon;
  title: string;
  description: string;
  /** The measurement this capability is anchored to, shown in the monospace face. */
  meta: string;
};

/** The four things the product does, in the order they matter to a player. */
export const FEATURES: Feature[] = [
  {
    icon: Activity,
    title: "BPM Detection",
    description:
      "Tempo is tracked across the whole recording rather than read off the intro, so a track that opens with a bare vocal still lands on the right number.",
    meta: "117.45 BPM · 631 beats",
  },
  {
    icon: Music,
    title: "Key Analysis",
    description:
      "All 24 keys are scored against the recording's average chroma, and the winner arrives with its correlation. When a key is close to a coin toss, you can see that it was.",
    meta: "C# minor · strength 0.82",
  },
  {
    icon: ListMusic,
    title: "Chord Timeline",
    description:
      "A bar-by-bar chord timeline with two readings on the same screen: the plain triad under each chord, or the label the detector actually heard, extensions and inversions intact.",
    meta: "170 segments · 74% mean",
  },
  {
    icon: FileMusic,
    title: "MIDI Export",
    description:
      "A monophonic MIDI sketch of the melody, tempo map included, ready to drag into your DAW and build on. A starting point for an arrangement, not a finished part.",
    meta: "29 notes · 269 B",
  },
];

export type Step = {
  icon: Icon;
  title: string;
  description: string;
  detail: string;
};

/** Upload, analyse, explore, create - what actually happens, in order. */
export const STEPS: Step[] = [
  {
    icon: Upload,
    title: "Upload",
    description:
      "Drop in an MP3 or a WAV, up to 200 MiB, straight from your phone or your DAW's bounce. Nothing to install.",
    detail: "MP3 · WAV",
  },
  {
    icon: SlidersHorizontal,
    title: "Analyze",
    description:
      "A worker decodes the file, measures duration, tempo and key, reads the chord timeline, then transcribes the melody - and stores all of it against your song.",
    detail: "measure · chords · transcribe",
  },
  {
    icon: AudioWaveform,
    title: "Explore",
    description:
      "Read the timeline bar by bar, flip between simple chords and the as-detected labels, and see how certain the detector was about each one.",
    detail: "two readings, one timeline",
  },
  {
    icon: Download,
    title: "Create",
    description:
      "Take the MIDI into your DAW or the chords into rehearsal. The analysis stays in your library, ready for the next time somebody asks what key it is in.",
    detail: "MIDI · chord timeline",
  },
];

export type Audience = {
  id: string;
  label: string;
  icon: Icon;
  headline: string;
  description: string;
  points: string[];
};

/** The tabs. Four, because four is what the cohort actually contains so far. */
export const AUDIENCES: Audience[] = [
  {
    id: "guitarists",
    label: "Guitarists",
    icon: Guitar,
    headline: "Stop hunting for the key by ear.",
    description:
      "Load a track, see the chords it is built on, and play it in the time it takes to find the file. No capo guessing, no scrubbing back to the same bar forty times.",
    points: [
      "The chord timeline in the key the track was played in",
      "A simple triad reading, or the full detected label",
      "A MIDI melody line to practise against",
    ],
  },
  {
    id: "producers",
    label: "Producers",
    icon: SlidersHorizontal,
    headline: "Reference tracks, decoded before you load a loop.",
    description:
      "Tempo and key come back together, with the chords the record keeps returning to - useful when you are matching a groove, and more useful when you are deliberately fighting one.",
    points: [
      "Tempo and key in one pass, before the first sample is dropped",
      "The ranked progression, so you can hear what the record is doing",
      "A MIDI sketch to rework into something that is yours",
    ],
  },
  {
    id: "singers",
    label: "Singers",
    icon: Mic,
    headline: "Find out what key you are actually singing in.",
    description:
      "The key and how confidently it was detected, the changes laid out in time, and a melody line to check your entry against - usually the part a backing track hides.",
    points: [
      "The recording's key, plus the strength behind that answer",
      "Chord changes in order, with the time each one lands",
      "A monophonic melody sketch to pitch your entry against",
    ],
  },
  {
    id: "teachers",
    label: "Teachers",
    icon: GraduationCap,
    headline: "Turn any song into next week's lesson.",
    description:
      "One screen with the chords, their timing and the detector's own confidence - the honest way to teach that analysis is a reading of a recording, not a fact about it.",
    points: [
      "Bar-by-bar chords a student can follow at the piano",
      "Confidence shown, so ambiguity becomes a talking point",
      "MIDI to hand out as homework instead of a YouTube link",
    ],
  },
];

export type RoadmapItem = {
  icon: Icon;
  title: string;
  description: string;
};

/**
 * Not available today, and labelled that way wherever it is mentioned - which is the
 * only reason this section exists at all. Somebody who signs up expecting an AI drummer
 * that does not exist is somebody who leaves.
 */
export const ROADMAP: RoadmapItem[] = [
  {
    icon: Layers,
    title: "Song Sections",
    description: "Verse, chorus, bridge - timed, so a wall of chords becomes a map.",
  },
  {
    icon: Guitar,
    title: "AI Guitarist",
    description: "Guitar parts played from the analysis, in the feel of the original.",
  },
  {
    icon: AudioWaveform,
    title: "AI Drummer",
    description: "Grooves that follow the tempo and the sections we already measure.",
  },
  {
    icon: Wand2,
    title: "Band Performance",
    description: "A full arrangement generated from a single upload, if the parts earn it.",
  },
];

/** The stack, named, because this is the honest version of "AI-powered". */
export const BUILT_WITH: string[] = [
  "librosa",
  "chroma-viterbi",
  "Krumhansl-Schmuckler",
  "pYIN",
  "PostgreSQL",
  "Cloudflare R2",
];

export type Faq = { question: string; answer: string };

/** Every answer here is checkable against the product or against the pipeline. */
export const FAQS: Faq[] = [
  {
    question: "What file formats are supported?",
    answer:
      "MP3 and WAV, up to 200 MiB each. Anything else is refused before a byte is uploaded, and the same rules are checked again on the server against the file that actually arrived.",
  },
  {
    question: "Is it free?",
    answer:
      "The closed beta is free and there is no card on file. Pricing for whatever comes after the beta is not settled, and beta testers will hear the number before anybody else does.",
  },
  {
    question: "Is my music private?",
    answer:
      "Your uploads belong to your account and nothing else: reads are scoped to your user id at the database level, and downloads are handed out as short-lived links that expire. MyBand does not train models on your music, because there are no training pipelines in the product.",
  },
  {
    question: "Can I upload my own songs?",
    answer:
      "Yes - your own recordings, your own bounces, anything you hold the rights to analyse. Please do not upload anything you do not, and treat that as your responsibility rather than ours.",
  },
  {
    question: "How accurate is it?",
    answer:
      "It depends on the recording, so the confidence is shown rather than hidden. Chord detection reports its mean confidence per song and key detection reports its correlation. A dense mix with heavy reverb is genuinely harder than a clean acoustic take: on one 62-second clip the key came back only 0.26 strong, which is the interface telling you not to trust it too far.",
  },
  {
    question: "What can the MIDI actually do?",
    answer:
      "It is a monophonic sketch of the melody from the first 30 seconds, transcribed with pYIN. One line: no bass, no drums, no harmony, and it is not a multitrack transcription. Enough to arrange from, not enough to release.",
  },
  {
    question: "Where are song sections and the AI band?",
    answer:
      "Not shipped. Song sections, the AI guitarist, the AI drummer and band performance generation are on the roadmap and labelled as planned wherever they appear - nothing on this page claims they work today.",
  },
];
