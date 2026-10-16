import { Badge } from "@/components/ui/badge";

import { ROADMAP } from "../copy";
import { Reveal } from "./reveal";
import { SectionHeading } from "./section-heading";

/**
 * The roadmap, and the honesty clause that makes it safe to have one.
 *
 * Every other section on this page describes something the product does. This one does the
 * opposite, and it earns its place: the fastest way to lose a musician is to let them sign
 * up expecting a feature that does not exist. The cards are dashed, grey and stamped
 * `Planned` so that nobody can mistake one of them for a shipping capability, even in a
 * screenshot of the page.
 */
export function Roadmap() {
  return (
    <section
      id="roadmap"
      aria-labelledby="roadmap-title"
      className="scroll-mt-24 px-5 pb-20 sm:px-6 sm:pb-28"
    >
      <div className="mx-auto max-w-6xl">
        <SectionHeading
          id="roadmap-title"
          eyebrow="Not built yet"
          title="What is coming, and what it is not"
          lede="Nothing in this section works today. It is here so you can see where the product is going - and judge whether the part that exists now is worth your time."
        />

        <div className="mt-12 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {ROADMAP.map((item, index) => (
            <Reveal key={item.title} delay={index * 0.06} className="h-full">
              <div className="h-full rounded-2xl border border-dashed border-white/[0.12] bg-white/[0.015] p-5">
                <div className="flex items-center justify-between gap-3">
                  <item.icon className="size-4 text-muted-foreground" aria-hidden />
                  <Badge
                    variant="outline"
                    className="border-white/10 font-mono text-[0.58rem] tracking-[0.14em] text-muted-foreground uppercase"
                  >
                    Planned
                  </Badge>
                </div>

                <h3 className="mt-5 font-display text-base tracking-tight text-foreground/90">
                  {item.title}
                </h3>
                <p className="mt-2 text-sm/relaxed text-muted-foreground">{item.description}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
