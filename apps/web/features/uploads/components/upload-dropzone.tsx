"use client";

import { MAX_UPLOAD_MIB, type AnalysisJob, type Song } from "@myband/shared";
import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { messageFor } from "@/lib/api";
import { cn } from "@/lib/utils";

import { completeUpload, presignUpload } from "../client-api";
import { checkAudioFile, formatBytes, titleFromFileName } from "../file-rules";
import { putFileToStorage } from "../put-to-storage";

/** What the file picker offers. The MIME aliases are for browsers that filter by type. */
const ACCEPT = ".mp3,.wav,audio/mpeg,audio/wav,audio/x-wav,audio/wave";

type Phase = "idle" | "uploading" | "finishing";

/**
 * Drag and drop, progress, and the job that comes out the other end.
 *
 * The three steps of the lifecycle happen in one function: presign, PUT, complete.
 * Only the first and the last reach the API - the middle one is the browser handing
 * bytes to object storage, which is exactly what the progress bar reports.
 *
 * The state is one small machine rather than a handful of booleans, so exactly one
 * of idle/uploading/finishing holds and "the bar is showing while the button is
 * disabled" cannot drift apart.
 */
export function UploadDropzone() {
  const router = useRouter();
  const fileInput = useRef<HTMLInputElement>(null);

  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [percent, setPercent] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [queued, setQueued] = useState<{ song: Song; job: AnalysisJob | null } | null>(null);

  const choose = useCallback((candidate: File | null | undefined) => {
    setError(null);
    setQueued(null);

    if (!candidate) {
      return;
    }

    const checked = checkAudioFile(candidate);

    if (!checked.ok) {
      setFile(null);
      setError(checked.message);
      return;
    }

    setFile(candidate);
  }, []);

  const upload = useCallback(async () => {
    if (!file) {
      return;
    }

    setError(null);
    setPercent(0);
    setPhase("uploading");

    try {
      const presigned = await presignUpload(file);

      await putFileToStorage({
        url: presigned.upload_url,
        file,
        headers: presigned.headers,
        onProgress: ({ loaded, total }) => setPercent(Math.round((loaded / total) * 100)),
      });

      // The bytes are in storage. What is left is the API's work: confirm the
      // object, write the song, queue the analysis.
      setPhase("finishing");

      const completed = await completeUpload({
        uploadId: presigned.upload.id,
        title: titleFromFileName(file.name),
      });

      setQueued({ song: completed.song, job: completed.job });
      setFile(null);
      setPhase("idle");
      // Re-renders the dashboard's Server Component, so the list comes back from the
      // API rather than from optimistic state invented here.
      router.refresh();
    } catch (cause) {
      setPhase("idle");
      setError(messageFor(cause));
    }
  }, [file, router]);

  const busy = phase !== "idle";

  return (
    <section className="space-y-4 rounded-lg border bg-card p-6 text-card-foreground">
      <div className="space-y-1">
        <h2 className="text-lg font-medium">Upload a track</h2>
        <p className="text-sm text-muted-foreground">
          MP3 or WAV, up to {MAX_UPLOAD_MIB} MiB. The file goes straight to storage; the API only
          signs the URL for it.
        </p>
      </div>

      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          choose(event.dataTransfer.files.item(0));
        }}
        className={cn(
          "rounded-lg border border-dashed p-8 text-center transition-colors",
          dragging ? "border-ring bg-accent" : "border-border",
        )}
      >
        <input
          ref={fileInput}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(event) => {
            choose(event.target.files?.item(0));
            // Lets the very same file be chosen twice in a row.
            event.target.value = "";
          }}
        />
        <p className="text-sm text-muted-foreground">Drag a track here, or</p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-3"
          disabled={busy}
          onClick={() => fileInput.current?.click()}
        >
          Choose a file
        </Button>
      </div>

      {file ? (
        <div className="flex items-center justify-between gap-4 rounded-md border p-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{file.name}</p>
            <p className="text-xs text-muted-foreground">{formatBytes(file.size)}</p>
          </div>
          <div className="flex shrink-0 gap-2">
            <Button type="button" size="sm" disabled={busy} onClick={upload}>
              {busy ? "Working..." : "Analyse"}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => setFile(null)}
            >
              Clear
            </Button>
          </div>
        </div>
      ) : null}

      {busy ? (
        <div className="space-y-2">
          <Progress value={percent} />
          <p className="text-xs text-muted-foreground">
            {phase === "uploading"
              ? `Uploading - ${percent}%`
              : "Uploaded. Confirming the file and queueing the analysis..."}
          </p>
        </div>
      ) : null}

      {queued ? (
        <div
          role="status"
          className="rounded-md border border-border bg-muted px-3 py-2 text-sm text-muted-foreground"
        >
          <p className="font-medium text-foreground">{queued.song.title} is queued for analysis.</p>
          {queued.job ? (
            <p className="mt-0.5 text-xs">
              Job {queued.job.id.slice(0, 8)} · {queued.job.status} · pipeline{" "}
              {queued.job.pipeline_version}
            </p>
          ) : null}
        </div>
      ) : null}

      {error ? (
        // The same treatment `features/auth/components/form-message.tsx` gives an
        // action failure: `alert` interrupts a screen reader, which a failure earns.
        <p
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {error}
        </p>
      ) : null}
    </section>
  );
}
