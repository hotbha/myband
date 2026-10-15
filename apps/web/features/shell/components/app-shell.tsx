import Link from "next/link";
import type { ReactNode } from "react";

import { LogoutButton } from "@/features/auth/components/logout-button";
import type { AuthIdentity } from "@/features/auth/session";
import { AmbientBackground } from "@/features/design-system/components/ambient-background";
import { BrandMark } from "@/features/design-system/components/brand-mark";

/**
 * The chrome every protected screen shares.
 *
 * It is a frame, not a grid: a header, a canvas, and one container with the width the
 * design system defines. The columns inside it belong to the screen, which is what lets
 * the dashboard be a three-column workspace and the song page be three full-width bands
 * without either one re-implementing the header, the canvas or the skip link.
 *
 * Four jobs, and each one is here because the alternative was a bug:
 *
 * * `product` scopes the palette and `data-surface` is what the `body:has()` rule keys
 *   off, so the document behind the page is dark too and an overscroll on iOS does not
 *   flash the app shell's light background.
 * * `overflow-x-clip` keeps a wide screen's aurora from turning into a horizontal
 *   scrollbar. `clip` rather than `hidden`, because `hidden` would create a scroll
 *   container and break `position: sticky` in the header.
 * * the skip link is the first thing in the DOM. Every screen here has a header, and the
 *   library rail can be twenty rows long, which is exactly the shape that needs one.
 * * `<noscript>` neutralises `[data-reveal]`, because the reveals on the landing page are
 *   inline styles from `motion` and with JavaScript off they would sit at `opacity: 0`
 *   forever. Nothing in the workspace animates on mount today, and this is here so that
 *   the first screen that does cannot reintroduce the problem.
 *
 * The header is static rather than scroll-reactive on purpose. The landing page's header
 * lifts when the page moves because it starts over a hero; a workspace header sits over a
 * list that is scrolled from the first interaction, so the border is always on and there
 * is no scroll listener and no Client Component.
 *
 * `context` is the second half of the breadcrumb - the song's title, say. The Library
 * link is the one way back from any screen, and it is in the same place on all of them,
 * so nobody has to learn where "back" lives.
 */
export function AppShell({
  identity,
  context,
  children,
}: {
  identity: AuthIdentity;
  context?: string;
  children: ReactNode;
}) {
  return (
    <div
      className="dark product relative min-h-dvh overflow-x-clip text-foreground"
      data-surface="product"
    >
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-[60] focus:rounded-lg focus:bg-background focus:px-4 focus:py-2 focus:text-sm focus:text-foreground focus:ring-2 focus:ring-ring"
      >
        Skip to content
      </a>

      <AmbientBackground variant="product" />

      <noscript>
        <style>{`[data-reveal]{opacity:1 !important;transform:none !important;animation:none !important}`}</style>
      </noscript>

      <header className="sticky top-0 z-50 border-b border-white/[0.07] bg-canvas/70 backdrop-blur-xl">
        <div className="mx-auto flex h-16 w-full max-w-[96rem] items-center justify-between gap-4 px-5 sm:px-8">
          <div className="flex min-w-0 items-center gap-4">
            <BrandMark compact />

            <nav aria-label="Breadcrumb" className="min-w-0">
              <ol className="flex min-w-0 items-center gap-2 text-sm">
                <li className="shrink-0">
                  <Link
                    href="/dashboard"
                    className="rounded-md text-muted-foreground transition-colors hover:text-foreground"
                  >
                    Library
                  </Link>
                </li>

                {context ? (
                  <li className="flex min-w-0 items-center gap-2">
                    <span aria-hidden className="text-muted-foreground/50">
                      /
                    </span>
                    <span className="truncate text-foreground">{context}</span>
                  </li>
                ) : null}
              </ol>
            </nav>
          </div>

          <div className="flex shrink-0 items-center gap-3">
            <p className="hidden max-w-[12rem] truncate text-xs text-muted-foreground sm:block">
              {identity.name ?? identity.email ?? identity.id}
            </p>
            <LogoutButton />
          </div>
        </div>
      </header>

      <main id="main" className="mx-auto w-full max-w-[96rem] px-5 pt-10 pb-16 sm:px-8">
        {children}
      </main>
    </div>
  );
}
