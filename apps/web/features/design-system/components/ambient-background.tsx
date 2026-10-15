/**
 * A surface's canvas: atmosphere before content.
 *
 * Two intensities of the same idea, and the difference is deliberate rather than a
 * matter of taste. The landing page is read in a few long glances and can afford a
 * violet aurora behind the hero; the workspace is read for minutes at a time with chrome
 * and dense text on top of it, so its blobs are smaller, fewer and dimmer, and its grid
 * fades out before it reaches the middle of the screen. A bright glow behind a table of
 * numbers is how a dark theme becomes tiring.
 *
 * Every layer is decorative and `aria-hidden`, so a screen reader gets straight to the
 * copy:
 *
 * * **aurora** blobs on slow, opposing drifts - which is what stops a near-black surface
 *   from reading as flat;
 * * a **grid** faded out by a radial mask, giving the content floor something to sit on
 *   without drawing attention to itself;
 * * **grain**, at 3.5%, which is the difference between "dark theme" and "expensive";
 * * a **vignette** that pulls the edges down so the eye lands in the middle.
 *
 * The gradients are inline styles rather than arbitrary Tailwind values: they carry
 * commas, slashes and percentage signs, and a build that silently dropped one of them
 * would be a bug nobody notices until the page looks cheap.
 */
const GRID_LINES =
  "linear-gradient(to right, oklch(1 0 0 / 5%) 1px, transparent 1px), linear-gradient(to bottom, oklch(1 0 0 / 5%) 1px, transparent 1px)";

const GRAIN =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='g'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='140' height='140' filter='url(%23g)'/%3E%3C/svg%3E\")";

/** The two surfaces, and how each one is lit. */
export type SurfaceVariant = "marketing" | "product";

export function AmbientBackground({ variant = "marketing" }: { variant?: SurfaceVariant }) {
  const marketing = variant === "marketing";

  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-canvas">
      {marketing ? (
        <>
          <div className="absolute -top-72 left-1/2 h-[46rem] w-[46rem] -translate-x-1/2 animate-drift rounded-full bg-signal/25 blur-[140px]" />
          <div className="absolute top-1/4 -right-56 h-[38rem] w-[38rem] animate-drift-reverse rounded-full bg-pulse/15 blur-[150px]" />
          <div className="absolute -bottom-64 -left-40 h-[34rem] w-[34rem] animate-drift rounded-full bg-signal/15 blur-[140px] [animation-delay:-8s]" />
        </>
      ) : (
        <>
          <div className="absolute -top-80 -left-40 h-[38rem] w-[38rem] animate-drift rounded-full bg-signal/12 blur-[150px]" />
          <div className="absolute -right-52 bottom-1/4 h-[32rem] w-[32rem] animate-drift-reverse rounded-full bg-pulse/[0.08] blur-[160px]" />
        </>
      )}

      <div
        className="absolute inset-0"
        style={{
          backgroundImage: GRID_LINES,
          backgroundSize: marketing ? "76px 76px" : "88px 88px",
          maskImage: marketing
            ? "radial-gradient(115% 75% at 50% 0%, black 10%, transparent 70%)"
            : "radial-gradient(110% 55% at 50% 0%, black 0%, transparent 62%)",
          WebkitMaskImage: marketing
            ? "radial-gradient(115% 75% at 50% 0%, black 10%, transparent 70%)"
            : "radial-gradient(110% 55% at 50% 0%, black 0%, transparent 62%)",
        }}
      />

      <div
        className="absolute inset-0 opacity-[0.035] mix-blend-soft-light"
        style={{ backgroundImage: GRAIN, backgroundSize: "140px 140px" }}
      />

      <div
        className="absolute inset-0"
        style={{
          backgroundImage: marketing
            ? "radial-gradient(125% 85% at 50% -10%, transparent 38%, oklch(0 0 0 / 0.6) 100%)"
            : "radial-gradient(120% 80% at 50% -10%, transparent 48%, oklch(0 0 0 / 0.45) 100%)",
        }}
      />
    </div>
  );
}
