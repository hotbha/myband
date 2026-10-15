import { AudioWaveform } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";

/**
 * The logo, in one place.
 *
 * It appears in the landing page's header, the workspace's header and the sign-in
 * screen's brand panel, and it is the same object in all three: a signal-gradient tile
 * with the waveform in it, then the wordmark with `.video` in muted grey. Extracting it
 * is not a refactor for its own sake - a second copy is how a product ends up with two
 * slightly different logos, which is the single cheapest way to look unfinished.
 *
 * `compact` drops the `.video` suffix below the `sm` breakpoint, for a header that also
 * has to fit a destination and a sign-out control on a 375px screen. Above `sm` the two
 * variants are identical.
 *
 * The tile's shadow is the design system's "brand chip" - a signal-tinted shadow - and
 * the focus ring is the standard one, because this is a link and a keyboard user has to
 * be able to see that they are on it.
 */
export function BrandMark({
  href = "/",
  compact = false,
  className,
}: {
  href?: string;
  compact?: boolean;
  className?: string;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "flex items-center gap-2.5 rounded-lg outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
        className,
      )}
    >
      <span className="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-signal to-signal-strong shadow-[0_8px_24px_-10px_var(--signal)]">
        <AudioWaveform className="size-4 text-white" aria-hidden />
      </span>

      <span className="font-display text-base font-semibold tracking-tight">
        MyBand
        <span className={cn("text-muted-foreground", compact && "hidden sm:inline")}>.video</span>
      </span>
    </Link>
  );
}
