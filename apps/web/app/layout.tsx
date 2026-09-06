import type { Metadata, Viewport } from "next";

import { Environment } from "@/components/Environment";

import "./globals.css";

export const metadata: Metadata = {
  title: "RAYA — Find the source. Verify the face. Anchor the evidence.",
  description:
    "RAYA discovers a candidate with reverse image search, verifies it independently with its own face models, and anchors the evidence so it cannot be changed later.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Light-only product: one theme colour, so a dark-mode OS does not tint the
  // browser chrome against the page.
  themeColor: "#f7fcff",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {/* The photographic environment: fixed parallax layers behind all
            content. Decorative only -- it never encodes pipeline state, and it
            is pointer-events:none so it cannot affect layout or interaction. */}
        <Environment />
        {children}
      </body>
    </html>
  );
}
