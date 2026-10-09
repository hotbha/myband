import Link from "next/link";

import { Button } from "@/components/ui/button";
import { getIdentity } from "@/features/auth/session";

/**
 * Landing page. Public by design (see `PUBLIC_PATHS` in the middleware), so it
 * reads the session only to decide which call to action to show - `getIdentity`
 * verifies the token and never throws.
 */
export default async function HomePage() {
  const identity = await getIdentity();

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-2xl flex-col justify-center gap-6 px-6 py-12">
      <div className="space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight">MyBand.video</h1>
        <p className="text-muted-foreground">
          Music intelligence for your uploads: BPM, key, chords, MIDI and song sections, ready for
          your DAW.
        </p>
      </div>

      <div>
        <Button asChild>
          <Link href={identity ? "/dashboard" : "/login"}>
            {identity ? "Open dashboard" : "Sign in"}
          </Link>
        </Button>
      </div>
    </main>
  );
}
