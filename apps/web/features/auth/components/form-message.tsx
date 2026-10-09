import { cn } from "@/lib/utils";

export type FormMessageProps = {
  status: "error" | "notice";
  children: React.ReactNode;
  className?: string;
};

/**
 * Inline feedback for the auth screens. Used by the forms for action results and
 * by the login page for the `?error=` message an OAuth callback can produce.
 * No client interactivity, so it stays a Server Component.
 */
export function FormMessage({ status, children, className }: FormMessageProps) {
  return (
    <p
      // `alert` interrupts a screen reader, `status` waits for a pause: failures
      // deserve the interruption, notices do not.
      role={status === "error" ? "alert" : "status"}
      className={cn(
        "rounded-md border px-3 py-2 text-sm",
        status === "error"
          ? "border-destructive/40 bg-destructive/10 text-destructive"
          : "border-border bg-muted text-muted-foreground",
        className,
      )}
    >
      {children}
    </p>
  );
}
