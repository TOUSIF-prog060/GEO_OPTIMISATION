import type { NextConfig } from "next";

// The Python API (FastAPI, src/api/main.py). The browser only ever talks to Next.js;
// /api/* is proxied so there is no CORS and no database credential in the frontend.
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  devIndicators: { position: "top-right" },
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default nextConfig;
