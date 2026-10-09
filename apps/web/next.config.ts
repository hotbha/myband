import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // `@myband/shared` ships TypeScript source (no build step), so Next must
  // transpile it as if it were part of this app.
  transpilePackages: ["@myband/shared"],
};

export default nextConfig;
