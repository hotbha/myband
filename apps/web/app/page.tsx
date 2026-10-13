import type { Metadata } from "next";

import { getIdentity } from "@/features/auth/session";
import { MarketingPage } from "@/features/marketing/components/marketing-page";

/**
 * The landing page's own metadata.
 *
 * The title and description are the positioning line and the four capabilities, in the
 * words the rest of the page uses. No roadmap feature is named: a search result is a promise,
 * and this is the one place on the site where a promise is hardest to correct.
 */
export const metadata: Metadata = {
  title: "MyBand.video - Understand any song in minutes",
  description:
    "Upload a song and instantly discover BPM, Key, Chords, and MIDI. Built for musicians, producers, and creators.",
  openGraph: {
    title: "MyBand.video - Understand any song in minutes",
    description:
      "Upload a song and instantly discover BPM, Key, Chords, and MIDI. Built for musicians, producers, and creators.",
    siteName: "MyBand.video",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "MyBand.video - Understand any song in minutes",
    description:
      "Upload a song and instantly discover BPM, Key, Chords, and MIDI. Built for musicians, producers, and creators.",
  },
};

/**
 * Public by design (see `PUBLIC_PATHS` in the middleware), so it reads the session only to
 * decide which call to action to show - `getIdentity` verifies the token and never throws.
 *
 * The page itself is a composition of one section per component, and every one of them is a
 * Server Component except where a pointer or a frame is genuinely needed: the header's
 * scroll state, the hero's entrance, the chord toggle, the tabs, the accordion and the email
 * field. There is no data fetching on this page at all - the analysis panel shows a
 * recording of a real run from `demo-analysis.ts` - which is what keeps it fast for a
 * visitor who has not signed up for anything yet.
 */
export default async function HomePage() {
  const identity = await getIdentity();

  return <MarketingPage signedIn={Boolean(identity)} />;
}
