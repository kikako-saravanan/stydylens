import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Hide the Next.js dev-mode indicator badge (bottom-left corner) — it's
  // a framework debugging aid, not part of this app's UI.
  devIndicators: false,
};

export default nextConfig;
