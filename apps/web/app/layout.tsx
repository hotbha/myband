import type { Metadata, Viewport } from "next";
import { Bricolage_Grotesque, JetBrains_Mono, Plus_Jakarta_Sans } from "next/font/google";

import "./globals.css";

/**
 * Three families, each with one job.
 *
 * `Bricolage Grotesque` is the display face - it has a wide, slightly quirky skeleton
 * that holds up at headline sizes and reads as designed rather than as a default.
 * `Plus Jakarta Sans` does the reading. `JetBrains Mono` is not decoration: every
 * number this product reports (BPM, key strength, note counts, byte sizes) is a
 * measurement, and measurements get the monospace so they line up in a column.
 *
 * All three self-host through `next/font`, so there is no render-blocking request to a
 * third party and no layout shift when they arrive.
 */
const body = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-jakarta",
  display: "swap",
});

const display = Bricolage_Grotesque({
  subsets: ["latin"],
  variable: "--font-bricolage",
  display: "swap",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
});

/**
 * The description names the shipped capabilities only. Song sections, the AI band and
 * the rest of the roadmap are deliberately absent: a meta description that promises
 * something the product cannot deliver is the one piece of copy nobody can correct
 * after it has been indexed.
 */
export const metadata: Metadata = {
  title: "MyBand.video",
  description:
    "Understand any song in minutes. Upload an MP3 or WAV and get its tempo, key, chord timeline and a MIDI sketch back.",
};

/** Tints the browser chrome to match the dark canvas on mobile. */
export const viewport: Viewport = {
  themeColor: "#0b0a11",
};

/**
 * App Router entry point. Next.js falls back to the Pages Router when the `app`
 * directory has no root layout, so this file is what actually selects the router
 * mode and pulls `globals.css` (the Tailwind v4 entrypoint) into the build.
 *
 * No theme class is set here: the app shell keeps the neutral palette it was reviewed
 * with, and the marketing surface scopes its own (see `.marketing` in `globals.css`).
 *
 * `data-scroll-behavior="smooth"` is how Next is told that `globals.css` sets
 * `scroll-behavior: smooth` on this element - without it the build warns that client-side
 * navigations will stop honouring it in a future version.
 */
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      data-scroll-behavior="smooth"
      className={`${body.variable} ${display.variable} ${mono.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
