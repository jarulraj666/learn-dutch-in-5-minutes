/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/api/:path*",
      },
      {
        source: "/output/:path*",
        destination: "http://localhost:8000/output/:path*",
      },
    ];
  },
};

module.exports = nextConfig;
