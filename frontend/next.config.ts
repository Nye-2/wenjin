import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  reactStrictMode: true,
  transpilePackages: ["framer-motion"],
  output: "standalone",
  env: {
    NEXT_PUBLIC_LANGGRAPH_BASE_URL: process.env.NEXT_PUBLIC_LANGGRAPH_BASE_URL || "/langgraph",
    NEXT_PUBLIC_BACKEND_BASE_URL: process.env.NEXT_PUBLIC_BACKEND_BASE_URL || "/api",
  },
};

export default nextConfig;
