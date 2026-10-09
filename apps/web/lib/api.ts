import { apiProblemSchema } from "@myband/shared";
import { z } from "zod";

/**
 * The one place a request to `apps/api` is built.
 *
 * Deliberately knows nothing about *where* the API is or who is calling: both come
 * in with the request, because a Server Component reads them from a cookie and the
 * browser reads them from the SDK. That is the whole difference between
 * `features/uploads/client-api.ts` and `features/uploads/server-api.ts`.
 *
 * Two failure modes are separated on purpose:
 *
 * * a refusal from the API becomes an {@link ApiError}, carrying the stable `code`
 *   the UI may branch on and the `message` it may show, and
 * * a response that does not match the shared schema is a bug in one of the two
 *   sides, so it throws with the mismatch spelled out instead of being guessed at.
 */

/** A refusal the API chose to send, in its documented shape. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export type ApiRequest = {
  /** Path on the API, e.g. `/songs/018f...`. */
  path: string;
  /** Absolute base URL, e.g. `http://127.0.0.1:8000`. */
  baseUrl: string;
  /** The caller's Supabase access token. */
  token: string;
  method?: "GET" | "POST";
  body?: unknown;
};

/** Turn any thrown value into something worth showing a person. */
export function messageFor(cause: unknown): string {
  if (cause instanceof ApiError || cause instanceof Error) {
    return cause.message;
  }

  return "Something went wrong. Please try again.";
}

/**
 * Validate a configured base URL, or explain how to set one.
 *
 * `undefined` is the normal state of a fresh checkout, so the failure has to name
 * the variable and the file - not throw "Invalid URL".
 */
export function requireBaseUrl(value: string | undefined, name: string): string {
  const parsed = z.url().safeParse(value);

  if (!parsed.success) {
    throw new Error(
      `${name} must be an absolute URL. Copy apps/web/.env.example to apps/web/.env.local and set it.`,
    );
  }

  return parsed.data;
}

export async function apiFetch<T>(request: ApiRequest, schema: z.ZodType<T>): Promise<T> {
  const response = await fetch(new URL(request.path, request.baseUrl), {
    method: request.method ?? "GET",
    headers: {
      Authorization: `Bearer ${request.token}`,
      ...(request.body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: request.body === undefined ? undefined : JSON.stringify(request.body),
    // Every one of these answers is per-user and per-request.
    cache: "no-store",
  });

  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    throw problemFrom(response.status, payload);
  }

  const parsed = schema.safeParse(payload);

  if (!parsed.success) {
    throw new Error(
      `The API answered in a shape this app does not understand.\n${z.prettifyError(parsed.error)}`,
    );
  }

  return parsed.data;
}

/** Read the API's error body, or describe the status when there is not one. */
function problemFrom(status: number, payload: unknown): ApiError {
  const parsed = apiProblemSchema.safeParse(payload);

  if (parsed.success) {
    return new ApiError(status, parsed.data.detail.code, parsed.data.detail.message);
  }

  return new ApiError(status, "unknown", `The API answered ${status} without a readable reason.`);
}
