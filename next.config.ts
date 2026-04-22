import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
