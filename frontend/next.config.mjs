import path from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = path.dirname(fileURLToPath(import.meta.url));

export default {
  distDir: process.env.NEXT_BUILD_DIR || ".next",
  outputFileTracingRoot: projectRoot,
  devIndicators: false,
  async rewrites() {
    const backend = process.env.BACKEND_API_URL || "http://127.0.0.1:8000";
    return [
      { source: "/api/v1/:path*", destination: `${backend}/api/v1/:path*` },
    ];
  },
};
