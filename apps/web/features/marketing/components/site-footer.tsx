import { AudioWaveform } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";

import { ROADMAP } from "../copy";

/** Anchors and real destinations only: no social accounts, no legal pages that do not exist. */
const PRODUCT_LINKS = [
  { href: "#features", label: "Features" },
  { href: "#how-it-works", label: "How it works" },
  { href: "#chords", label: "Chord timeline" },
  { href: "#who", label: "Who it's for" },
  { href: "#faq", label: "Questions" },
];

/**
 * The footer: what this is, where to go, and what is not here yet.
 *
 * The roadmap items appear a second time on purpose. Somebody who scrolls straight to the
 * bottom is exactly the person most likely to assume an AI drummer exists because the
 * industry keeps promising one, so the label travels with the words: `Planned`, in the
 * same place, on every screen size.
 */
export function SiteFooter() {
  return (
    <footer className="border-t border-white/[0.07] px-5 py-12 sm:px-6 sm:py-14">
      <div className="mx-auto grid max-w-6xl gap-10 sm:grid-cols-2 lg:grid-cols-4">
        <div className="lg:col-span-2">
          <div className="flex items-center gap-2.5">
            <span className="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-signal to-signal-strong">
              <AudioWaveform className="size-4 text-white" aria-hidden />
            </span>
            <span className="font-display text-base font-semibold tracking-tight">
              MyBand<span className="text-muted-foreground">.video</span>
            </span>
          </div>

          <p className="mt-4 max-w-sm text-sm/relaxed text-muted-foreground">
            Understand any song in minutes. Upload a track, get its tempo, key, chord timeline and a
            MIDI sketch back.
          </p>

          <Badge
            variant="outline"
            className="mt-5 border-pulse/25 bg-pulse/[0.08] font-mono text-[0.6rem] tracking-[0.14em] text-pulse uppercase"
          >
            Closed beta · 10 seats
          </Badge>
        </div>

        <nav aria-label="Sections">
          <h2 className="font-mono text-[0.6rem] tracking-[0.16em] text-muted-foreground uppercase">
            This page
          </h2>
          <ul className="mt-4 space-y-2.5 text-sm">
            {PRODUCT_LINKS.map((item) => (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className="rounded-md text-muted-foreground transition-colors hover:text-foreground"
                >
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <div>
          <h2 className="font-mono text-[0.6rem] tracking-[0.16em] text-muted-foreground uppercase">
            Planned, not shipped
          </h2>
          <ul className="mt-4 space-y-2.5 text-sm">
            {ROADMAP.map((item) => (
              <li key={item.title} className="flex items-center gap-2 text-muted-foreground/70">
                {item.title}
                <span className="rounded border border-white/10 px-1.5 py-0.5 font-mono text-[0.55rem] tracking-[0.1em] uppercase">
                  Soon
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="mx-auto mt-12 flex max-w-6xl flex-col gap-2 border-t border-white/[0.07] pt-6 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <p>
          © {new Date().getFullYear()} MyBand.video · Built for guitarists, producers, singers and
          teachers.
        </p>
        <p className="font-mono tracking-[0.06em]">BPM · key · chords · MIDI</p>
      </div>
    </footer>
  );
}
