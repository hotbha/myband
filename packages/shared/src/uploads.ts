/**
 * The upload lifecycle's contracts, which both sides of the wire agree to.
 *
 * `apps/api` is the source of truth: these schemas mirror its Pydantic models
 * field for field, snake_case included, so no field has to be renamed on the way
 * between languages. They are *parsed* against the API's answers rather than
 * asserted with `as`, which turns a drifted response into a loud error at the
 * boundary instead of `undefined` three components deep.
 *
 * The product rules below (which extensions, how large) are a mirror of
 * `apps/api/app/services/uploads.py`, kept so the browser can refuse a file before
 * spending 200 MB of someone's bandwidth. The API re-checks all of them, and its
 * answer is the one that counts.
 */
import { z } from "zod";

/** The extensions this product accepts. Mirrors `CONTENT_TYPES_BY_EXTENSION`. */
export const AUDIO_EXTENSIONS = ["mp3", "wav"] as const;

/** Every MIME type a browser realistically reports for those extensions. */
export const CONTENT_TYPES_BY_EXTENSION: Readonly<Record<string, readonly string[]>> = {
  mp3: ["audio/mpeg", "audio/mp3", "audio/mpeg3", "audio/x-mpeg-3"],
  wav: ["audio/wav", "audio/wave", "audio/x-wav", "audio/vnd.wave"],
};

/** 200 MiB. `MAX_UPLOAD_BYTES` in `apps/api/app/services/uploads.py`. */
export const MAX_UPLOAD_BYTES = 200 * 1024 * 1024;

/** The number the UI shows in prose, so the rule is never spelled twice. */
export const MAX_UPLOAD_MIB = MAX_UPLOAD_BYTES / (1024 * 1024);

/** Timestamps arrive as ISO 8601 with an offset, always in UTC. */
const timestamp = z.iso.datetime({ offset: true });

export const uploadStatusSchema = z.enum(["pending", "completed", "aborted", "expired"]);

export const jobStatusSchema = z.enum([
  "queued",
  "dispatched",
  "running",
  "succeeded",
  "failed",
  "canceled",
]);

/** One row of `public.uploads`. */
export const uploadSchema = z.object({
  id: z.uuid(),
  song_id: z.uuid().nullable(),
  object_key: z.string(),
  status: uploadStatusSchema,
  declared_bytes: z.number().int().nullable(),
  declared_content_type: z.string().nullable(),
  bytes_actual: z.number().int().nullable(),
  content_type_actual: z.string().nullable(),
  etag_actual: z.string().nullable(),
  expires_at: timestamp,
  completed_at: timestamp.nullable(),
  created_at: timestamp,
});

/** One row of `public.analysis_jobs`. */
export const analysisJobSchema = z.object({
  id: z.uuid(),
  song_id: z.uuid(),
  status: jobStatusSchema,
  pipeline_version: z.string(),
  attempts: z.number().int(),
  // A decimal: FastAPI serialises it as a string to keep its precision, but a
  // number is parsed too rather than trusting either form.
  compute_seconds: z.union([z.string(), z.number()]).nullable(),
  error_code: z.string().nullable(),
  error_message: z.string().nullable(),
  dispatched_at: timestamp.nullable(),
  started_at: timestamp.nullable(),
  finished_at: timestamp.nullable(),
  created_at: timestamp,
});

/** One row of `public.songs`. */
export const songSchema = z.object({
  id: z.uuid(),
  project_id: z.uuid().nullable(),
  latest_job_id: z.uuid().nullable(),
  title: z.string(),
  artist: z.string().nullable(),
  duration_ms: z.number().int().nullable(),
  // The analysis headline, written by the worker. A decimal, serialised the same way
  // `compute_seconds` is; null until a job has succeeded.
  bpm: z.union([z.string(), z.number()]).nullable(),
  musical_key: z.string().nullable(),
  source_object_key: z.string(),
  source_bytes: z.number().int().nullable(),
  source_content_type: z.string().nullable(),
  created_at: timestamp,
  updated_at: timestamp,
});

/** A song and what is currently happening to it. */
export const songWithJobSchema = songSchema.extend({
  job: analysisJobSchema.nullable(),
});

export const presignResponseSchema = z.object({
  upload: uploadSchema,
  upload_url: z.url(),
  method: z.literal("PUT"),
  headers: z.record(z.string(), z.string()),
  max_bytes: z.number().int().positive(),
});

export const completeResponseSchema = z.object({
  upload: uploadSchema,
  song: songSchema,
  job: analysisJobSchema.nullable(),
});

export const songListSchema = z.object({
  songs: z.array(songWithJobSchema),
});

/** The API's single error shape, status codes documented in docs/upload-flow.md. */
export const apiProblemSchema = z.object({
  detail: z.object({ code: z.string(), message: z.string() }),
});

/**
 * Where to fetch a song's MIDI (`GET /songs/{id}/midi`).
 *
 * A signed URL rather than the file, with the same shape of trust as the upload's:
 * short-lived, scoped to one object, and fetched when the user asks for it. The link
 * carries its own authorization, so nothing stores it.
 */
export const midiDownloadSchema = z.object({
  url: z.url(),
  expires_at: timestamp,
});

export type MidiDownload = z.infer<typeof midiDownloadSchema>;

export type UploadStatus = z.infer<typeof uploadStatusSchema>;
export type JobStatus = z.infer<typeof jobStatusSchema>;
export type Upload = z.infer<typeof uploadSchema>;
export type AnalysisJob = z.infer<typeof analysisJobSchema>;
export type Song = z.infer<typeof songSchema>;
export type SongWithJob = z.infer<typeof songWithJobSchema>;
export type PresignResponse = z.infer<typeof presignResponseSchema>;
export type CompleteResponse = z.infer<typeof completeResponseSchema>;
export type SongList = z.infer<typeof songListSchema>;
