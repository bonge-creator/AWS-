/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    const target = process.env.API_PROXY_TARGET || "http://127.0.0.1:8000";
    return [
      { source: "/api/v1/:path*", destination: `${target}/api/v1/:path*` },
    ];
  },
};

module.exports = nextConfig;
