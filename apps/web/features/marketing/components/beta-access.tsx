"use client";

import { ArrowRight, Clock, Lock, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { type FormEvent, useId, useState } from "react";
import { z } from "zod";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { Reveal } from "./reveal";
import { SectionHeading } from "./section-heading";

/** The same rule the login form uses: one definition of a valid address per app. */
const emailSchema = z.email({ message: "Enter a valid email address." });

const PERKS = [
  { icon: Sparkles, text: "Free for the ten, with no card on file and nothing to install" },
  { icon: Clock, text: "A direct line to the people building it, bugs and requests included" },
  { icon: Lock, text: "Your uploads stay yours: scoped to your account, never used for training" },
];

/**
 * The beta, and an email field that tells the truth about what it does.
 *
 * There is no waitlist table in this product, so a form that said "you are on the list"
 * would be lying about where the address went. Instead the field hands off to the sign-up
 * flow that actually exists - `/login?email=...` opens the email and password form with the
 * address already filled in - so the capture works end to end on the first try and the seat
 * is a real account rather than a row in somebody's inbox.
 *
 * Validation is the same `z.email` schema the Server Action uses, so a typo is caught here
 * the way it would be caught there. The error is wired through `aria-invalid` and
 * `aria-describedby` and announced with `role="alert"`, rather than only being red.
 */
export function BetaAccess() {
  const router = useRouter();
  const inputId = useId();
  const errorId = `${inputId}-error`;

  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const parsed = emailSchema.safeParse(email.trim());

    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Enter a valid email address.");
      return;
    }

    setError(null);
    setSubmitting(true);
    router.push(`/login?email=${encodeURIComponent(parsed.data)}&next=/dashboard`);
  }

  return (
    <section
      id="beta"
      aria-labelledby="beta-title"
      className="scroll-mt-24 px-5 py-20 sm:px-6 sm:py-24"
    >
      <div className="mx-auto max-w-6xl">
        <SectionHeading
          id="beta-title"
          eyebrow="Closed beta"
          title="Currently accepting 10 beta testers"
          lede="Ten seats, free while we are in beta, handed out by hand. Enter your email and we will open the sign-up form with it already filled in."
        />

        <Reveal className="mt-12">
          <div className="relative overflow-hidden rounded-[1.75rem] border border-white/[0.09] bg-white/[0.03] p-6 backdrop-blur-xl sm:p-10">
            <div
              aria-hidden
              className="pointer-events-none absolute -top-28 left-1/2 h-56 w-[32rem] -translate-x-1/2 rounded-full bg-signal/20 blur-[100px]"
            />

            <div className="relative grid gap-9 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:items-center lg:gap-14">
              <div>
                <Badge
                  variant="outline"
                  className="border-pulse/30 bg-pulse/10 font-mono text-[0.6rem] tracking-[0.14em] text-pulse uppercase"
                >
                  10 seats · free
                </Badge>

                <h3 className="mt-5 font-display text-2xl leading-tight tracking-tight text-balance sm:text-[1.75rem]">
                  Bring one song you have been meaning to learn
                </h3>

                <ul className="mt-6 space-y-3">
                  {PERKS.map((perk) => (
                    <li key={perk.text} className="flex gap-3 text-sm/relaxed">
                      <perk.icon className="mt-0.5 size-4 shrink-0 text-pulse" aria-hidden />
                      <span className="text-muted-foreground">{perk.text}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <form onSubmit={onSubmit} className="space-y-3" noValidate>
                <div className="space-y-2">
                  <Label htmlFor={inputId}>Your email</Label>
                  <div className="flex flex-col gap-3 sm:flex-row">
                    <Input
                      id={inputId}
                      type="email"
                      name="email"
                      autoComplete="email"
                      inputMode="email"
                      placeholder="you@example.com"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      aria-invalid={Boolean(error)}
                      aria-describedby={error ? errorId : undefined}
                      className="h-11 rounded-xl border-white/15 bg-white/[0.04] md:text-[0.95rem]"
                    />

                    <Button
                      type="submit"
                      size="lg"
                      disabled={submitting}
                      className="h-11 shrink-0 rounded-xl bg-gradient-to-br from-signal to-signal-strong px-5 text-[0.95rem] transition hover:brightness-110"
                    >
                      {submitting ? "Opening..." : "Request Beta Access"}
                      <ArrowRight className="size-4" aria-hidden />
                    </Button>
                  </div>
                </div>

                {error ? (
                  <p id={errorId} role="alert" className="text-sm text-destructive">
                    {error}
                  </p>
                ) : null}

                <p className="text-xs/relaxed text-muted-foreground">
                  This takes you to sign-up with your address filled in. Seats are activated by
                  hand.
                </p>
              </form>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
