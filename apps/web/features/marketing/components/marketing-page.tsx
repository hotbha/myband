import { AudienceTabs } from "./audience-tabs";
import { BetaAccess } from "./beta-access";
import { ChordPreview } from "./chord-preview";
import { Faq } from "./faq";
import { FeatureGrid } from "./feature-grid";
import { FinalCta } from "./final-cta";
import { Hero } from "./hero";
import { HowItWorks } from "./how-it-works";
import { MarketingShell } from "./marketing-shell";
import { Roadmap } from "./roadmap";
import { SiteFooter } from "./site-footer";
import { SiteHeader } from "./site-header";

/**
 * The landing page, top to bottom.
 *
 * The order is the argument: claim, evidence, what you get, how it works, the interface
 * itself, who it is for - and then, before asking for anything, the part most landing pages
 * leave out. `Roadmap` sits directly above the beta section on purpose. Somebody is about to
 * type their email address; the last thing they should read first is what this product does
 * *not* do yet, so that whatever they sign up for is the thing they actually get.
 *
 * `signedIn` arrives from the server, so a returning tester is offered their dashboard
 * instead of a sign-up form they have already filled in once.
 */
export function MarketingPage({ signedIn }: { signedIn: boolean }) {
  return (
    <MarketingShell>
      <SiteHeader signedIn={signedIn} />

      <main id="main">
        <Hero signedIn={signedIn} />
        <FeatureGrid />
        <HowItWorks />
        <ChordPreview />
        <AudienceTabs />
        <Roadmap />
        <BetaAccess />
        <Faq />
        <FinalCta signedIn={signedIn} />
      </main>

      <SiteFooter />
    </MarketingShell>
  );
}
