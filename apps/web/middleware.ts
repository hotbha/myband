import type { NextRequest, NextResponse } from "next/server";

import { updateSession } from "@/lib/supabase/middleware";

/**
 * Next.js middleware entry point: it has to live at the project root and Next
 * only reads a `middleware` function plus a `config` export from it. The actual
 * work sits in `lib/supabase/middleware.ts` so it stays importable and testable
 * on its own.
 */
export function middleware(request: NextRequest): Promise<NextResponse> {
  return updateSession(request);
}

export const config = {
  /**
   * Every path except Next's build output and static images. A broad matcher is
   * what makes the default-deny rule in `updateSession` work: features added
   * later are protected without touching this file. Public assets (robots.txt,
   * sitemap.xml, audio previews) belong either here or in `PUBLIC_PATHS`.
   */
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};
