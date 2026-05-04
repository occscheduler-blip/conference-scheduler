import type { NextConfig } from "next";

const isDesktop = process.env.BUILD_TARGET === "desktop";

const nextConfig: NextConfig = isDesktop
  ? {
      output: "export",
      trailingSlash: true,
      images: { unoptimized: true },
    }
  : {
      async rewrites() {
        return [
          { source: "/", destination: "/pages?view=home" },
          { source: "/admin", destination: "/pages?view=admin" },
          { source: "/department-head", destination: "/pages?view=department-head" },
          { source: "/professor", destination: "/pages?view=professor" },
          { source: "/student", destination: "/pages?view=student" },
        ];
      },
    };

export default nextConfig;
