"use client";

import { useActionState } from "react";

import { Button } from "@/components/ui/button";

import { signInWithGoogle } from "../actions";
import { initialAuthActionState } from "../schemas";
import { FormMessage } from "./form-message";

/**
 * Google sign-in button.
 *
 * The action returns the provider URL and redirects the browser to it, so the
 * button needs client state only to disable itself while the round trip is in
 * flight.
 */
export function GoogleSignInForm({ next }: { readonly next: string }) {
  const [state, formAction, isPending] = useActionState(signInWithGoogle, initialAuthActionState);

  return (
    <form action={formAction} className="space-y-3">
      <input type="hidden" name="next" value={next} />
      <Button type="submit" variant="outline" className="w-full" disabled={isPending}>
        {isPending ? "Redirecting to Google..." : "Continue with Google"}
      </Button>
      {state.message ? (
        <FormMessage status={state.status === "notice" ? "notice" : "error"}>
          {state.message}
        </FormMessage>
      ) : null}
    </form>
  );
}
