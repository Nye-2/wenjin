import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  reactStrictMode: true,
  transpilePackages: ["framer-motion"],
  turbopack: {
    root: __dirname,
  },
  output: "standalone",
};

export default nextConfig;
