import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "MyBand.video",
  description: "Music intelligence platform: BPM, key, chords, MIDI and song sections.",
};

/**
 * App Router entry point. Next.js falls back to the Pages Router when the `app`
 * directory has no root layout, so this file is what actually selects the router
 * mode and pulls `globals.css` (the Tailwind v4 entrypoint) into the build.
 */
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
