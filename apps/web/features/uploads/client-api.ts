import {
  completeResponseSchema,
  presignResponseSchema,
  type CompleteResponse,
  type PresignResponse,
} from "@myband/shared";

import { apiFetch, requireBaseUrl } from "@/lib/api";
import { getAccessToken } from "@/lib/supabase/client";

/**
 * The API, called from the browser.
 *
 * The caller's token is attached here and nowhere else, and the base URL is a
 * `NEXT_PUBLIC_` variable because this code runs in the tab. The audio itself does
 * not pass through any of this: `presignUpload` returns a URL, and
 * `put-to-storage.ts` PUTs to it directly.
 *
 * Only the endpoints the interface uses are wrapped. `GET /songs/{id}`,
 * `GET /uploads/{id}` and `GET /jobs/{id}` exist on the API (docs/upload-flow.md)
 * and get a wrapper when a screen needs one.
 */

function baseUrl(): string {
  return requireBaseUrl(process.env.NEXT_PUBLIC_API_BASE_URL, "NEXT_PUBLIC_API_BASE_URL");
}

/** Reserve an object and get the URL that fills it. */
export async function presignUpload(file: File): Promise<PresignResponse> {
  return apiFetch(
    {
      path: "/uploads/presign",
      baseUrl: baseUrl(),
      token: await getAccessToken(),
      method: "POST",
      body: {
        filename: file.name,
        // The API falls back to the extension when a browser reports no type.
        content_type: file.type || null,
        bytes: file.size,
      },
    },
    presignResponseSchema,
  );
}

/**
 * Tell the API the object landed. It answers with the song and the queued job.
 *
 * Answers 201 the first time and 200 when the same upload was already completed -
 * a double click is not an error, and both answer with the same song and job.
 */
export async function completeUpload(input: {
  uploadId: string;
  title: string;
}): Promise<CompleteResponse> {
  return apiFetch(
    {
      path: "/uploads/complete",
      baseUrl: baseUrl(),
      token: await getAccessToken(),
      method: "POST",
      body: { upload_id: input.uploadId, title: input.title },
    },
    completeResponseSchema,
  );
}
