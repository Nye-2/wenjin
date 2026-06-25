import type { NextConfig } from "next";
import path from "node:path";
import { loadEnvConfig } from "@next/env";

const DEFAULT_DEV_API_PROXY_TARGET = "http://localhost:8001";
const repoRoot = path.resolve(__dirname, "..");

loadEnvConfig(repoRoot, process.env.NODE_ENV !== "production");

function trimTrailingSlashes(value: string): string {
  return value.replace(/\/+$/, "");
}

const nextConfig: NextConfig = {
  /* config options here */
  reactStrictMode: true,
  transpilePackages: ["framer-motion"],
  turbopack: {
    root: __dirname,
  },
  output: "standalone",
  async rewrites() {
    if (process.env.NODE_ENV !== "development") {
      return [];
    }

    const target = trimTrailingSlashes(
      process.env.WENJIN_DEV_API_PROXY_TARGET ??
        DEFAULT_DEV_API_PROXY_TARGET,
    );

    return [
      {
        source: "/api/:path*",
        destination: `${target}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
