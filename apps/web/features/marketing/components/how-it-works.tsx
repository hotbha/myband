import { STEPS } from "../copy";
import { Reveal } from "./reveal";
import { SectionHeading } from "./section-heading";

/**
 * How it works, in four steps, on a hairline that runs behind them.
 *
 * Deliberately not a list of features in disguise: each step says what happens to the file
 * - uploaded, decoded and measured, read, exported - because "how it works" is where a
 * musician decides whether the answer can be trusted.
 */
export function HowItWorks() {
  return (
    <section
      id="how-it-works"
      aria-labelledby="how-title"
      className="scroll-mt-24 px-5 py-20 sm:px-6 sm:py-28"
    >
      <div className="mx-auto max-w-6xl">
        <SectionHeading
          id="how-title"
          eyebrow="How it works"
          title="Upload, analyze, explore, create"
          lede="Four steps, and only the first one needs you. Everything else happens on a worker while you get on with something else."
        />

        <div className="relative mt-14">
          <div className="absolute inset-x-0 top-[1.1rem] hidden h-px bg-gradient-to-r from-transparent via-signal/40 to-transparent lg:block" />

          <ol className="relative grid gap-10 sm:grid-cols-2 lg:grid-cols-4 lg:gap-6">
            {STEPS.map((step, index) => (
              <Reveal key={step.title} delay={index * 0.08} className="h-full">
                <li className="h-full">
                  <div className="flex items-center gap-3">
                    <span className="grid size-9 place-items-center rounded-full border border-white/10 bg-canvas/90 backdrop-blur">
                      <step.icon className="size-4 text-signal-soft" />
                    </span>
                    <span className="font-mono text-xs tracking-[0.2em] text-muted-foreground">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                  </div>

                  <h3 className="mt-5 font-display text-lg tracking-tight">{step.title}</h3>
                  <p className="mt-2 text-sm/relaxed text-muted-foreground">{step.description}</p>
                  <p className="mt-3 font-mono text-[0.65rem] tracking-[0.04em] text-signal-soft/80">
                    {step.detail}
                  </p>
                </li>
              </Reveal>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
