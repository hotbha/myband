import { CONTENT_TYPES_BY_EXTENSION, MAX_UPLOAD_BYTES, MAX_UPLOAD_MIB } from "@myband/shared";

/**
 * What may be uploaded, checked in the browser first.
 *
 * These rules mirror `apps/api/app/services/uploads.py` and exist only to refuse a
 * file before spending someone's bandwidth on it. The API checks all of them again
 * against the object that actually landed in storage, so nothing here is a security
 * boundary - which is why it is allowed to be approximate (a browser's idea of a
 * MIME type is a guess) where the API is not.
 */
export type AudioFileCheck = { ok: true } | { ok: false; message: string };

export function checkAudioFile(file: File): AudioFileCheck {
  const allowedTypes = CONTENT_TYPES_BY_EXTENSION[extensionOf(file.name)];

  if (!allowedTypes) {
    return {
      ok: false,
      message: `Only MP3 and WAV files can be analysed - "${file.name}" is neither.`,
    };
  }

  if (file.type && !allowedTypes.includes(file.type.toLowerCase())) {
    return {
      ok: false,
      message: `"${file.name}" reports itself as ${file.type}, which is not an MP3 or a WAV.`,
    };
  }

  if (file.size === 0) {
    return { ok: false, message: `"${file.name}" is empty.` };
  }

  if (file.size > MAX_UPLOAD_BYTES) {
    return {
      ok: false,
      message: `Files must be ${MAX_UPLOAD_MIB} MiB or smaller - "${file.name}" is ${formatBytes(file.size)}.`,
    };
  }

  return { ok: true };
}

/** A size a person can read, for the one place a size is ever shown. */
export function formatBytes(bytes: number): string {
  const mebibytes = bytes / (1024 * 1024);

  return mebibytes >= 1
    ? `${mebibytes.toFixed(1)} MiB`
    : `${Math.max(1, Math.round(bytes / 1024))} KiB`;
}

/**
 * A song title taken from the file's own name.
 *
 * Sent with the upload so the library reads "Midnight Drive" rather than the
 * `midnight_drive` the object key had to be sanitised into.
 */
export function titleFromFileName(fileName: string): string {
  const stem = fileName.replace(/\.[^.]+$/, "").trim();

  return stem.slice(0, 200) || "Untitled";
}

/** The extension without its dot, lowercase. `''` when the name has none. */
function extensionOf(fileName: string): string {
  const name = fileName.split(/[\\/]/).pop() ?? fileName;
  const dot = name.lastIndexOf(".");

  return dot === -1 ? "" : name.slice(dot + 1).toLowerCase();
}
