"use client";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";

import { FAQS } from "../copy";
import { Reveal } from "./reveal";
import { SectionHeading } from "./section-heading";

/**
 * The questions somebody asks before they hand over a file.
 *
 * Two of these answers are unflattering on purpose: the MIDI is one monophonic line, and
 * one of the three tracks in the beta run came back with a key confidence of 0.26. A
 * product that only lists its strengths is telling the reader that the other answers are
 * worse than they are.
 *
 * The heading sits in its own column on a wide screen, so the questions read as a column of
 * sentences rather than as a wall - and each item is closed by default, which keeps the
 * section from dominating the scroll.
 */
export function Faq() {
  return (
    <section
      id="faq"
      aria-labelledby="faq-title"
      className="scroll-mt-24 px-5 py-20 sm:px-6 sm:py-28"
    >
      <div className="mx-auto grid max-w-6xl gap-10 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] lg:gap-16">
        <SectionHeading
          id="faq-title"
          eyebrow="Questions"
          title="What people ask before they upload"
          lede="Straight answers, including the two that are not flattering."
        />

        <Reveal>
          <Accordion type="single" collapsible className="border-t border-white/[0.08]">
            {FAQS.map((faq) => (
              <AccordionItem
                key={faq.question}
                value={faq.question}
                className="border-white/[0.08]"
              >
                <AccordionTrigger className="text-left text-[0.95rem] hover:no-underline data-[state=open]:text-foreground">
                  {faq.question}
                </AccordionTrigger>
                <AccordionContent className="text-sm/relaxed text-pretty text-muted-foreground">
                  {faq.answer}
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </Reveal>
      </div>
    </section>
  );
}
