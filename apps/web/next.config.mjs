/** @type {import('next').NextConfig} */
const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  // Proxy the API through the Next origin so the browser makes same-origin
  // requests. Without this, EventSource for SSE is subject to CORS and the
  // stream is the one thing that must never be flaky.
  //
  // Note: Next resolves rewrites at BUILD time and writes them into
  // routes-manifest.json, so NEXT_PUBLIC_API_URL must be set before
  // `next build` -- setting it only before `next start` has no effect. The
  // default matches the port the README tells you to run the API on.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/:path*` }];
  },
};

export default nextConfig;
