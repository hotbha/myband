"use client";

import { useCallback, useState } from "react";

import { Button } from "@/components/ui/button";
import { messageFor } from "@/lib/api";

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
 * and the row is the only place to say so.
 */
export function DownloadMidiButton({ songId, title }: { songId: string; title: string }) {
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
    <div className="flex shrink-0 flex-col items-end gap-1">
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={busy}
        onClick={download}
        // The visible label is short because the row already says which song this is;
        // a screen reader hears the row and the button out of context.
        aria-label={`Download ${title} as MIDI`}
      >
        {busy ? "Preparing..." : "MIDI"}
      </Button>

      {error ? (
        <p role="alert" className="max-w-56 text-right text-xs text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
