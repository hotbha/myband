import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

import { FEATURES } from "../copy";
import { Reveal } from "./reveal";
import { SectionHeading } from "./section-heading";

/**
 * What the product does today, as four cards.
 *
 * The eyebrow says "today" and the section is exactly that: the four capabilities that
 * were certified on this build. Everything else the company intends to build lives in one
 * place further down the page, under a heading that says it is not here yet.
 *
 * Each card ends on a measurement rather than a platitude. "170 segments · 74% mean" is
 * checkable against the panel at the top of the page, and that is the difference between a
 * feature grid and a list of adjectives.
 */
export function FeatureGrid() {
  return (
    <section
      id="features"
      aria-labelledby="features-title"
      className="scroll-mt-24 px-5 py-20 sm:px-6 sm:py-28"
    >
      <div className="mx-auto max-w-6xl">
        <SectionHeading
          id="features-title"
          eyebrow="Available today"
          title="Four measurements, one upload"
          lede="A song goes in and comes back as a tempo, a key, a chord timeline and a MIDI sketch. Each one is reported with the evidence behind it, because a number a musician cannot check is a number they will not use."
        />

        <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((feature, index) => (
            <Reveal key={feature.title} delay={index * 0.08} className="h-full">
              <Card className="group flex h-full gap-0 border-white/[0.07] bg-white/[0.025] py-6 transition-[transform,border-color,background-color,box-shadow] duration-300 hover:-translate-y-1 hover:border-signal/30 hover:bg-white/[0.045] hover:shadow-[0_28px_70px_-40px_var(--signal)]">
                <CardHeader className="gap-4">
                  <span className="grid size-10 place-items-center rounded-xl border border-white/10 bg-gradient-to-br from-signal/25 to-pulse/10">
                    <feature.icon className="size-5 text-signal-soft" />
                  </span>
                  <CardTitle className="font-display text-lg tracking-tight">
                    {feature.title}
                  </CardTitle>
                  <CardDescription className="text-sm/relaxed">
                    {feature.description}
                  </CardDescription>
                </CardHeader>

                <CardContent className="mt-auto">
                  <p className="border-t border-white/[0.07] pt-4 font-mono text-[0.68rem] tracking-[0.04em] text-signal-soft/90">
                    {feature.meta}
                  </p>
                </CardContent>
              </Card>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
