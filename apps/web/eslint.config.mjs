// @ts-check
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { FlatCompat } from "@eslint/eslintrc";

import base from "../../eslint.config.mjs";

const compat = new FlatCompat({
  baseDirectory: dirname(fileURLToPath(import.meta.url)),
});

/**
 * Next.js still publishes its ESLint configs in the legacy (`extends`) format,
 * so they are loaded through FlatCompat. `base` comes from the repo root and
 * already silences formatting rules via eslint-config-prettier.
 */
const config = [
  {
    ignores: [".next/**", "node_modules/**", "next-env.d.ts"],
  },
  ...base,
  ...compat.extends("next/core-web-vitals", "next/typescript"),
];

export default config;
