"use client";

import { Check } from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { AUDIENCES } from "../copy";
import { Reveal } from "./reveal";
import { SectionHeading } from "./section-heading";

/**
 * Who it is for, as four tabs rather than four paragraphs.
 *
 * A landing page that addresses everybody at once addresses nobody, and the honest version
 * of this section is narrow: these are the four people the beta cohort actually contains -
 * a guitarist, a producer, a singer, a teacher. Each panel says what that person gets out
 * of the analysis, in their terms, and stops.
 *
 * Radix does the work that matters here: arrow keys move between tabs, only the selected
 * panel is in the DOM, and `role="tablist"` comes for free. The panel fades in with a
 * `tw-animate-css` utility instead of a JS transition, because the content is remounted on
 * every switch and there is nothing to carry state between.
 */
export function AudienceTabs() {
  return (
    <section
      id="who"
      aria-labelledby="who-title"
      className="scroll-mt-24 px-5 py-20 sm:px-6 sm:py-28"
    >
      <div className="mx-auto max-w-6xl">
        <SectionHeading
          id="who-title"
          eyebrow="Who it's for"
          title="Built for people who have to play the thing"
          lede="Cover artists, content creators and anyone else who learns songs for a living get the same four answers. These are the four we built them for first."
        />

        <Reveal className="mt-12">
          <Tabs defaultValue={AUDIENCES[0]?.id ?? "guitarists"} className="gap-6">
            <TabsList className="grid h-auto w-full grid-cols-2 gap-1 bg-white/[0.04] p-1 lg:w-fit lg:grid-cols-4">
              {AUDIENCES.map((audience) => (
                <TabsTrigger key={audience.id} value={audience.id} className="h-10 gap-2 px-4">
                  <audience.icon className="size-4" aria-hidden />
                  {audience.label}
                </TabsTrigger>
              ))}
            </TabsList>

            {AUDIENCES.map((audience) => (
              <TabsContent
                key={audience.id}
                value={audience.id}
                className="animate-in duration-300 fade-in slide-in-from-bottom-1"
              >
                <div className="grid gap-8 rounded-3xl border border-white/[0.08] bg-white/[0.02] p-6 backdrop-blur-xl sm:p-8 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
                  <div>
                    <h3 className="font-display text-2xl leading-tight tracking-tight text-balance">
                      {audience.headline}
                    </h3>
                    <p className="mt-4 text-base/relaxed text-pretty text-muted-foreground">
                      {audience.description}
                    </p>
                  </div>

                  <ul className="space-y-3 lg:border-l lg:border-white/[0.07] lg:pl-8">
                    {audience.points.map((point) => (
                      <li key={point} className="flex gap-3 text-sm/relaxed">
                        <Check className="mt-0.5 size-4 shrink-0 text-pulse" aria-hidden />
                        <span>{point}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </TabsContent>
            ))}
          </Tabs>
        </Reveal>
      </div>
    </section>
  );
}
