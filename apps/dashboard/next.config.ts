import type { NextConfig } from "next";

// Security headers on every response (v0.33).
//
// The dashboard server is the only browser-reachable component — it holds the
// reviewer session cookie and proxies authenticated API calls — so the browser
//-facing hardening baseline lives here:
// - X-Frame-Options DENY + CSP frame-ancestors 'none': the control plane must
//   never be framable (clickjacking).
// - base-uri 'self': stop <base> hijacks without touching Next's inline
//   scripts (a full script-src 'self' CSP would break Next's hydration
//   bootstrap; frame-ancestors is the high-value directive and is safe).
// - nosniff, Referrer-Policy, Permissions-Policy: standard hardening.
// - HSTS in production only: localhost/HTTP dev must not get a cached
//   HTTPS-only policy.
const securityHeaders = [
  { key: "X-Frame-Options", value: "DENY" },
  {
    key: "Content-Security-Policy",
    value: "frame-ancestors 'none'; base-uri 'self'",
  },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=()",
  },
  ...(process.env.NODE_ENV === "production"
    ? [{
        key: "Strict-Transport-Security",
        value: "max-age=31536000; includeSubDomains",
      }]
    : []),
];

const nextConfig: NextConfig = {
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
