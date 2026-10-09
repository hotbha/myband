/**
 * @myband/shared
 *
 * Single source of truth for the contracts that cross the web/api boundary
 * (types + Zod schemas consumed by apps/web).
 *
 * NOTE: apps/api is Python and cannot import this package. FastAPI's Pydantic
 * models are the mirror of these contracts; TypeScript is generated from the
 * FastAPI OpenAPI schema only if/when that duplication starts to hurt.
 */
export * from "./analysis";
export * from "./uploads";
