// @ts-check
import js from "@eslint/js";
import prettier from "eslint-config-prettier/flat";

/**
 * Base flat ESLint config shared by every workspace package.
 *
 * Package-level configs (`apps/web`, `packages/shared`) import this array and
 * append their own rules. TypeScript syntax rules are intentionally NOT defined
 * here: `apps/web` gets them from `eslint-config-next` and `packages/shared`
 * from `typescript-eslint`. Declaring the `@typescript-eslint` plugin twice
 * (two different plugin objects under one namespace) makes flat config throw.
 */
export default [
  {
    ignores: [
      "**/node_modules/**",
      "**/.next/**",
      "**/out/**",
      "**/dist/**",
      "**/build/**",
      "**/coverage/**",
      "**/.venv/**",
      "**/__pycache__/**",
      "**/next-env.d.ts",
      "**/pnpm-lock.yaml",
    ],
  },
  js.configs.recommended,
  {
    // TypeScript already resolves identifiers; `no-undef` is a false-positive
    // factory on type-only references.
    files: ["**/*.ts", "**/*.tsx"],
    rules: {
      "no-undef": "off",
    },
  },
  {
    files: ["**/*.js", "**/*.mjs", "**/*.cjs"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
    },
  },
  prettier,
];
