import type { ReactNode } from "react";

import { AmbientBackground } from "@/features/design-system/components/ambient-background";

/**
 * Everything a marketing page needs around it, and nothing it does not.
 *
 * Four jobs, and each one is here because the alternative was a bug:
 *
 * * `marketing` scopes the dark palette (see `globals.css`) and `data-surface` is what the
 *   `body:has()` rule keys off, so the document behind the page is dark too and an
 *   overscroll on iOS does not flash white.
 * * `overflow-x-clip` keeps the hero panel's deliberate overhang from turning into a
 *   horizontal scrollbar on a wide screen. `clip` rather than `hidden`, because `hidden`
 *   would create a scroll container and break `position: sticky` in the header.
 * * the skip link is the first thing in the DOM: this page has a fixed header, six
 *   sections and a five-item menu, which is exactly the shape that needs one.
 * * `<noscript>` neutralises `[data-reveal]`. Every reveal on this page is an inline style
 *   from `motion`, so with JavaScript disabled the sections would sit at `opacity: 0`
 *   forever - a page that looks empty is worse than a page without animation.
 */
export function MarketingShell({ children }: { children: ReactNode }) {
  return (
    <div
      className="dark marketing relative min-h-dvh overflow-x-clip text-foreground"
      data-surface="marketing"
    >
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-[60] focus:rounded-lg focus:bg-background focus:px-4 focus:py-2 focus:text-sm focus:text-foreground focus:ring-2 focus:ring-ring"
      >
        Skip to content
      </a>

      <AmbientBackground variant="marketing" />

      <noscript>
        <style>{`[data-reveal]{opacity:1 !important;transform:none !important;animation:none !important}`}</style>
      </noscript>

      {children}
    </div>
  );
}
