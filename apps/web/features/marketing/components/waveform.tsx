import { cn } from "@/lib/utils";

/**
 * The waveform that runs through the page's visuals.
 *
 * Every bar is a `<span>` with a percentage height, which is a lot cheaper than a canvas
 * and means the shape survives being resized, printed, or read by a text scraper. It is
 * decorative everywhere it appears - the numbers next to it are the information - so the
 * container is hidden from assistive technology unless a caller passes a `label`.
 *
 * `animated` staggers each bar's rise by 14 ms. The staggering is done in CSS (an
 * animation-delay per bar) rather than by animating 72 motion components, which keeps the
 * hero's first paint free of JavaScript work; `[data-reveal]` in `globals.css` turns the
 * whole thing off for a reader who has asked for reduced motion.
 */
export function Waveform({
  bars,
  className,
  animated = false,
  label,
}: {
  bars: number[];
  className?: string;
  animated?: boolean;
  label?: string;
}) {
  return (
    <div
      aria-hidden={label ? undefined : true}
      aria-label={label}
      role={label ? "img" : undefined}
      className={cn("flex h-full w-full items-end gap-[2px]", className)}
    >
      {bars.map((value, index) => (
        <span
          key={index}
          className={cn(
            "min-w-[1px] flex-1 origin-bottom rounded-full bg-gradient-to-t from-signal-strong/45 via-signal to-pulse",
            animated && "animate-rise motion-reduce:animate-none",
          )}
          style={{
            height: `${Math.max(4, Math.round(value * 100))}%`,
            // Rounded and stringified on purpose. Two values here are read back out of the
            // DOM during hydration: the browser normalises `transform-origin: bottom` to
            // `center bottom` (hence the `origin-bottom` class above rather than a style),
            // and it keeps an opacity as the literal text it was given - so a full-precision
            // float like 0.7705158876922589 comes back as "0.770516" and React reports a
            // hydration mismatch on the hero's most prominent element.
            opacity: (0.35 + value * 0.65).toFixed(3),
            animationDelay: animated ? `${index * 14}ms` : undefined,
          }}
        />
      ))}
    </div>
  );
}
