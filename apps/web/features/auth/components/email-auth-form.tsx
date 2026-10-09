"use client";

import { useActionState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { emailAuth } from "../actions";
import { initialAuthActionState } from "../schemas";
import { FormMessage } from "./form-message";

/**
 * Email + password sign-in and sign-up in a single form.
 *
 * The two submit buttons post identical fields and differ only in their
 * `intent` value; the Server Action reads that value and validates against the
 * matching schema. Keeping the mode in `FormData` instead of React state means
 * the form still knows what to do before hydration and the fields are never
 * cleared by a re-render.
 */
export function EmailAuthForm({ next }: { readonly next: string }) {
  const [state, formAction, isPending] = useActionState(emailAuth, initialAuthActionState);

  return (
    <form action={formAction} className="space-y-4">
      <input type="hidden" name="next" value={next} />

      <div className="space-y-2">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          required
          aria-invalid={Boolean(state.fieldErrors.email)}
          aria-describedby={state.fieldErrors.email ? "email-error" : undefined}
        />
        {state.fieldErrors.email ? (
          <p id="email-error" className="text-sm text-destructive">
            {state.fieldErrors.email}
          </p>
        ) : null}
      </div>

      <div className="space-y-2">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          aria-invalid={Boolean(state.fieldErrors.password)}
          aria-describedby={state.fieldErrors.password ? "password-error" : undefined}
        />
        {state.fieldErrors.password ? (
          <p id="password-error" className="text-sm text-destructive">
            {state.fieldErrors.password}
          </p>
        ) : null}
      </div>

      {state.message ? (
        <FormMessage status={state.status === "notice" ? "notice" : "error"}>
          {state.message}
        </FormMessage>
      ) : null}

      <div className="flex flex-col gap-2 sm:flex-row">
        <Button type="submit" name="intent" value="sign-in" className="flex-1" disabled={isPending}>
          {isPending ? "Working..." : "Sign in"}
        </Button>
        <Button
          type="submit"
          name="intent"
          value="sign-up"
          variant="outline"
          className="flex-1"
          disabled={isPending}
        >
          Create account
        </Button>
      </div>
    </form>
  );
}
