import { Button } from "@/components/ui/button";

import { signOut } from "../actions";

/**
 * Logout control for protected screens.
 *
 * A plain `<form>` posting to a Server Action, so it works without client
 * JavaScript and needs no client component of its own.
 */
export function LogoutButton() {
  return (
    <form action={signOut}>
      <Button type="submit" variant="outline" size="sm">
        Log out
      </Button>
    </form>
  );
}
