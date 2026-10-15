"use client";

import { MAX_UPLOAD_MIB, type AnalysisJob, type Song } from "@myband/shared";
import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Panel, PanelHeader } from "@/features/design-system/components/panel";
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
 * disabled" cannot drift apart. Each of the five states a person can see - idle,
 * chosen, uploading, finishing, queued - is drawn differently on purpose: an upload that
 * looks the same while it is working and while it is waiting on the API is an upload
 * nobody can tell apart from a stuck one.
 *
 * The drop zone never disappears, including after a refusal. It is the only way to pick a
 * different file, and replacing it with a red sentence would leave somebody looking at a
 * problem with no way to act on it.
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
    <Panel aria-labelledby="upload-heading" className="p-4 sm:p-5">
      <PanelHeader id="upload-heading" eyebrow="Upload" title="Analyse a track" />

      <p className="mt-2 text-xs/relaxed text-muted-foreground">
        MP3 or WAV, up to {MAX_UPLOAD_MIB} MiB. The file goes straight to storage; the API only
        signs the URL for it.
      </p>

      {/* Chosen, so the zone is replaced rather than annotated: one file, one action. */}
      {file ? (
        <div className="mt-4 flex items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{file.name}</p>
            <p className="mt-0.5 font-mono text-xs text-muted-foreground tabular-nums">
              {formatBytes(file.size)}
            </p>
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
      ) : (
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
            "mt-4 rounded-xl border border-dashed p-6 text-center transition-colors",
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
      )}

      {busy ? (
        <div className="mt-4 space-y-2">
          <Progress value={percent} className="h-1.5" aria-label="Upload progress" />

          {/* Two sentences, because there are two different waits: the bytes going to
              storage, which the browser can report, and the two API calls after them,
              which it cannot. */}
          <p role="status" className="text-xs text-muted-foreground">
            {phase === "uploading"
              ? `Uploading - ${percent}%`
              : "Uploaded. Confirming the file and queueing the analysis..."}
          </p>
        </div>
      ) : null}

      {queued ? (
        <div
          role="status"
          className="mt-4 rounded-xl border border-pulse/25 bg-pulse/[0.08] px-3 py-2.5"
        >
          <p className="text-sm font-medium">{queued.song.title} is queued for analysis.</p>

          {queued.job ? (
            <p className="mt-1 truncate font-mono text-[0.6rem] tracking-[0.12em] text-muted-foreground uppercase">
              job {queued.job.id.slice(0, 8)} · {queued.job.status} · pipeline{" "}
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
          className="mt-4 rounded-xl border border-destructive/40 bg-destructive/10 px-3 py-2.5 text-sm text-destructive"
        >
          {error}
        </p>
      ) : null}
    </Panel>
  );
}
