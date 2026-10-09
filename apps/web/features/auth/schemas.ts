import { z } from "zod";

/**
 * Validation shared by the auth Server Actions, the login form and the JWT
 * claims we read back from Supabase.
 *
 * Two untrusted boundaries are covered here: `FormData` arriving from the
 * browser, and the access-token payload handed over by the Supabase SDK. Neither
 * is trusted without parsing.
 */

const emailSchema = z.email({ message: "Enter a valid email address." });

/** Minimum length for new passwords. Supabase's own default minimum is 6. */
export const SIGN_UP_MIN_PASSWORD_LENGTH = 8;

const newPasswordSchema = z.string().min(SIGN_UP_MIN_PASSWORD_LENGTH, {
  message: `Use at least ${SIGN_UP_MIN_PASSWORD_LENGTH} characters.`,
});

/** Sign-in only checks presence: the password itself is verified by Supabase. */
const existingPasswordSchema = z.string().min(1, { message: "Enter your password." });

export const signInSchema = z.object({
  email: emailSchema,
  password: existingPasswordSchema,
});

export const signUpSchema = z.object({
  email: emailSchema,
  password: newPasswordSchema,
});

/** Where a signed-in user lands when no explicit target was requested. */
export const DEFAULT_REDIRECT = "/dashboard";

/**
 * Only same-origin relative paths are accepted. Rejecting a leading `//` or `\`
 * blocks the open-redirect tricks (`//evil.com`, `/\evil.com`) that let an
 * attacker bounce a freshly authenticated user onto a site they control.
 */
const redirectPathSchema = z.string().regex(/^\/(?!\/)[^\\\s]*$/, {
  message: "Unsafe redirect target.",
});

export function safeRedirectPath(value: unknown, fallback: string = DEFAULT_REDIRECT): string {
  const parsed = redirectPathSchema.safeParse(value);
  return parsed.success ? parsed.data : fallback;
}

export type AuthField = "email" | "password";

const AUTH_FIELDS: readonly AuthField[] = ["email", "password"];

/** State shape returned by every auth Server Action and fed to `useActionState`. */
export type AuthActionState = {
  /** `notice` is neutral feedback (e.g. "confirm your email"), `error` is a failure. */
  status: "idle" | "error" | "notice";
  message: string | null;
  fieldErrors: Partial<Record<AuthField, string>>;
};

export const initialAuthActionState: AuthActionState = {
  status: "idle",
  message: null,
  fieldErrors: {},
};

/**
 * Turns a failed parse into form state. The first message per field wins, so
 * each input shows exactly one reason it was rejected.
 */
export function invalidInputState(error: z.ZodError): AuthActionState {
  const fieldErrors: Partial<Record<AuthField, string>> = {};

  for (const issue of error.issues) {
    const field = AUTH_FIELDS.find((candidate) => candidate === issue.path[0]);

    if (field && !fieldErrors[field]) {
      fieldErrors[field] = issue.message;
    }
  }

  return {
    status: "error",
    message: "Check the highlighted fields.",
    fieldErrors,
  };
}
