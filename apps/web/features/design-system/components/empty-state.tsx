import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * "Nothing here yet", said in one sentence that also says what will happen.
 *
 * The dashed edge is the whole vocabulary: it means *nothing exists here*, and it is
 * never used for anything that does. That is why a queued analysis and an empty library
 * get the same treatment - both are states, neither is an error.
 *
 * Which is also why this is a `<p>` and not an alert. The three ways to reach an empty
 * state in this product are "you have not uploaded anything", "this song is still
 * queued" and "this recording has no chords in it", and none of them is a failure. A
 * caller with a real failure uses the destructive treatment instead, and a caller with a
 * state that should be announced while nothing else is happening can pass `role`.
 */
export function EmptyState({
  children,
  role,
  className,
}: {
  children: ReactNode;
  role?: "status";
  className?: string;
}) {
  return (
    <p
      role={role}
      className={cn(
        "rounded-2xl border border-dashed border-border p-6 text-sm/relaxed text-muted-foreground",
        className,
      )}
    >
      {children}
    </p>
  );
}
