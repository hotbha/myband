"use client";

import { AudioWaveform, Menu, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** The page's sections, in the order they appear. One list, so the menu cannot drift. */
const NAV = [
  { href: "#features", label: "Features" },
  { href: "#how-it-works", label: "How it works" },
  { href: "#chords", label: "Chords" },
  { href: "#who", label: "Who it's for" },
  { href: "#faq", label: "FAQ" },
];

/**
 * The header, and the only thing on the page that follows you.
 *
 * It starts flush with the canvas and picks up a border and a blur once the page has
 * moved, which is the cheapest way to keep a call to action reachable without a bar
 * sitting on top of the hero from the first frame.
 *
 * The mobile panel is rendered conditionally and animated with `tw-animate-css` utilities
 * rather than `AnimatePresence`: for a panel that is either there or not, the CSS version
 * is less machinery and it degrades to an instant appearance if anything goes wrong.
 *
 * `aria-expanded` and `aria-controls` are set on the toggle, and the panel closes when a
 * link inside it is followed - a menu that stays open behind the section it just scrolled
 * to is the classic version of this bug.
 */
export function SiteHeader({ signedIn }: { signedIn: boolean }) {
  const [lifted, setLifted] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setLifted(window.scrollY > 12);

    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });

    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-50 transition-colors duration-300",
        lifted
          ? "border-b border-white/[0.07] bg-black/50 backdrop-blur-xl"
          : "border-b border-transparent",
      )}
    >
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-6 px-5 sm:px-6">
        <Link
          href="/"
          className="flex items-center gap-2.5 rounded-lg outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        >
          <span className="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-signal to-signal-strong shadow-[0_8px_24px_-10px_var(--signal)]">
            <AudioWaveform className="size-4 text-white" aria-hidden />
          </span>
          <span className="font-display text-base font-semibold tracking-tight">
            MyBand<span className="text-muted-foreground">.video</span>
          </span>
        </Link>

        <nav aria-label="Sections" className="hidden lg:block">
          <ul className="flex items-center gap-7 text-sm text-muted-foreground">
            {NAV.map((item) => (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className="rounded-md transition-colors hover:text-foreground"
                >
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <div className="flex items-center gap-2">
          <Button
            asChild
            size="sm"
            className="hidden bg-gradient-to-br from-signal to-signal-strong px-4 transition hover:brightness-110 sm:inline-flex"
          >
            <Link href={signedIn ? "/dashboard" : "/login"}>
              {signedIn ? "Dashboard" : "Early Access"}
            </Link>
          </Button>

          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="lg:hidden"
            aria-expanded={open}
            aria-controls="mobile-nav"
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((value) => !value)}
          >
            {open ? <X className="size-5" /> : <Menu className="size-5" />}
          </Button>
        </div>
      </div>

      {open ? (
        <div
          id="mobile-nav"
          className="animate-in border-t border-white/[0.07] bg-black/80 backdrop-blur-xl duration-200 fade-in slide-in-from-top-2 lg:hidden"
        >
          <nav aria-label="Sections" className="mx-auto max-w-6xl px-5 py-4 sm:px-6">
            <ul className="grid gap-1">
              {NAV.map((item) => (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    onClick={() => setOpen(false)}
                    className="block rounded-lg px-3 py-2.5 text-sm text-muted-foreground transition-colors hover:bg-white/[0.05] hover:text-foreground"
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>

            <Button
              asChild
              className="mt-3 w-full bg-gradient-to-br from-signal to-signal-strong"
              onClick={() => setOpen(false)}
            >
              <Link href={signedIn ? "/dashboard" : "/login"}>
                {signedIn ? "Open dashboard" : "Early Access"}
              </Link>
            </Button>
          </nav>
        </div>
      ) : null}
    </header>
  );
}
