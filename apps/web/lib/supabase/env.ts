import { z } from "zod";

/**
 * Supabase credentials, validated with Zod.
 *
 * Parsed lazily - never at module scope - so `next build` succeeds without a
 * Supabase project configured (Next prerenders pages during the build), while
 * the first request that actually needs Supabase fails loudly with a readable
 * message instead of shipping `undefined` to the Auth API.
 *
 * Both `process.env.NEXT_PUBLIC_*` reads stay static on purpose: Next.js
 * inlines them into the bundle at build time and cannot do that for a computed
 * key.
 */
const supabaseEnvSchema = z.object({
  url: z.url({ message: "NEXT_PUBLIC_SUPABASE_URL must be an absolute URL." }),
  publishableKey: z
    .string()
    .min(1, { message: "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY is missing." }),
});

export type SupabaseEnv = z.infer<typeof supabaseEnvSchema>;

export function getSupabaseEnv(): SupabaseEnv {
  const parsed = supabaseEnvSchema.safeParse({
    url: process.env.NEXT_PUBLIC_SUPABASE_URL,
    publishableKey: process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
  });

  if (!parsed.success) {
    throw new Error(
      `Supabase is not configured. Copy apps/web/.env.example to apps/web/.env.local and fill it in.\n${z.prettifyError(parsed.error)}`,
    );
  }

  return parsed.data;
}
