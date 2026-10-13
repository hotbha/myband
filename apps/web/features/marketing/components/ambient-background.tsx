/**
 * The page's canvas: atmosphere before content.
 *
 * Four layers, all of them decorative and all of them `aria-hidden`, so a screen reader
 * gets straight to the copy:
 *
 * * two **aurora** blobs on slow, opposing drifts - violet behind the hero, cyan low and
 *   to the right - which is what stops a near-black page from reading as flat;
 * * a **grid** faded out by a radial mask, giving the hero floor something to sit on
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

export function AmbientBackground() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-canvas">
      <div className="absolute -top-72 left-1/2 h-[46rem] w-[46rem] -translate-x-1/2 animate-drift rounded-full bg-signal/25 blur-[140px]" />
      <div className="absolute top-1/4 -right-56 h-[38rem] w-[38rem] animate-drift-reverse rounded-full bg-pulse/15 blur-[150px]" />
      <div className="absolute -bottom-64 -left-40 h-[34rem] w-[34rem] animate-drift rounded-full bg-signal/15 blur-[140px] [animation-delay:-8s]" />

      <div
        className="absolute inset-0"
        style={{
          backgroundImage: GRID_LINES,
          backgroundSize: "76px 76px",
          maskImage: "radial-gradient(115% 75% at 50% 0%, black 10%, transparent 70%)",
          WebkitMaskImage: "radial-gradient(115% 75% at 50% 0%, black 10%, transparent 70%)",
        }}
      />

      <div
        className="absolute inset-0 opacity-[0.035] mix-blend-soft-light"
        style={{ backgroundImage: GRAIN, backgroundSize: "140px 140px" }}
      />

      <div
        className="absolute inset-0"
        style={{
          backgroundImage:
            "radial-gradient(125% 85% at 50% -10%, transparent 38%, oklch(0 0 0 / 0.6) 100%)",
        }}
      />
    </div>
  );
}
