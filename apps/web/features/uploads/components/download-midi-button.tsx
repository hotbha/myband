"use client";

import { useCallback, useState } from "react";

import { Button } from "@/components/ui/button";
import { messageFor } from "@/lib/api";
import { cn } from "@/lib/utils";

import { requestMidiDownload } from "../client-api";

/**
 * Get the song's MIDI, in the two steps the API's design asks for.
 *
 * One: the API is asked for a link, which it only hands out after checking that this
 * caller owns the song. Two: the tab is sent to that link, and the bucket answers with
 * the file. The second step is a navigation rather than a `fetch` on purpose - a fetch
 * would read the MIDI into memory and leave the user with nothing saved, while a
 * navigation lets the bucket's `Content-Disposition` do its job and the browser put a
 * file in the Downloads folder. The name on it comes from the API too.
 *
 * The failure is shown here rather than thrown: there are ordinary reasons to get a 404
 * (a song from before the pipeline stored MIDI, a job that produced no transcription),
 * and the button is the only place to say so.
 *
 * It appears twice in the product and means the same thing in both places - a small
 * outline control in a list row, and the one filled action on the song page - so it is
 * one component with the size and the label passed in rather than two implementations of
 * "ask the API, then leave".
 */
export function DownloadMidiButton({
  songId,
  title,
  label = "MIDI",
  variant = "outline",
  className,
}: {
  songId: string;
  title: string;
  label?: string;
  variant?: React.ComponentProps<typeof Button>["variant"];
  className?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const download = useCallback(async () => {
    setError(null);
    setBusy(true);

    try {
      const link = await requestMidiDownload(songId);
      window.location.assign(link.url);
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      // On the success path the tab has already left; this only matters when it
      // has not, which is every failure.
      setBusy(false);
    }
  }, [songId]);

  return (
    <div className="flex shrink-0 flex-col items-end gap-1.5">
      <Button
        type="button"
        variant={variant}
        size="sm"
        className={className}
        disabled={busy}
        onClick={download}
        // The visible label is short because the row or the panel already says which
        // song this is; a screen reader hears the control out of context.
        aria-label={`Download ${title} as MIDI`}
      >
        {busy ? "Preparing..." : label}
      </Button>

      {error ? (
        <p role="alert" className={cn("max-w-56 text-right text-xs text-destructive")}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
