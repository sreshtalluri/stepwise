import type { Metadata, Viewport } from "next";
import Link from "next/link";
import { privacy } from "../lib/copy";
import "./globals.css";

export const metadata: Metadata = {
  title: "stepwise — every angle, from the one video you have",
  description:
    "Upload a dance clip filmed on one camera. Get the dancer back as a 3D body you can spin, slow down, and take one count at a time.",
  // Added to the home screen from the lesson page (no service worker, no offline).
  appleWebApp: { capable: true, title: "stepwise", statusBarStyle: "black-translucent" },
};

// viewport-fit=cover lets the phone lesson run under the notch; it pads itself with
// the safe-area insets. theme_color matches the stage, which is what fills a phone.
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#1C1917" };

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        {/* Cabinet Grotesk + Switzer, Indian Type Foundry via Fontshare —
            free for commercial use, which matters for a public repo.
            DESIGN.md §5. */}
        <link rel="preconnect" href="https://api.fontshare.com" />
        <link
          rel="stylesheet"
          href="https://api.fontshare.com/v2/css?f[]=cabinet-grotesk@700,800,900&f[]=switzer@400,500,600&display=swap"
        />
      </head>
      <body>
        {children}
        <footer className="wrap meta" style={{ padding: "24px clamp(20px, 4vw, 48px) 32px" }}>
          <Link href="/privacy" style={{ textDecoration: "underline", textUnderlineOffset: 3 }}>
            {privacy.footer}
          </Link>
        </footer>
      </body>
    </html>
  );
}
