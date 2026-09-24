import type { Metadata, Viewport } from "next";
import Link from "next/link";
import { privacy } from "../lib/copy";
import "./globals.css";
import "./front.css";

// Every clause is true today (DESIGN.md §7h): clips up to 60 s, one to six
// dancers, loops of any length under Counts and parts, 0.5x to 1x, mirror, and
// a 3D body drawn on the video. No "upload" (links work too) and no "the dancer".
export const metadata: Metadata = {
  // Absolute URLs for the share image (app/opengraph-image.png). No custom
  // domain yet (docs/DEPLOYMENT.md); NEXT_PUBLIC_SITE_URL overrides.
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "https://stepwise.sreshta-talluri.workers.dev"),
  title: "stepwise: learn any dance, step by step",
  description:
    "Add a dance video up to 60 seconds long, with one to six dancers. Loop any part, slow it down, mirror it, and see each dancer as a 3D body on the video.",
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
        {/* Bricolage Grotesque (display and counts; Google Fonts, SIL OFL) and
            Switzer (body; Indian Type Foundry via Fontshare). Both free for
            commercial use, which matters for a public repo. DESIGN.md §5.
            /privacy names both hosts: change it if either moves. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link rel="preconnect" href="https://api.fontshare.com" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wdth,wght@12..96,75..100,400..800&display=swap"
        />
        <link
          rel="stylesheet"
          href="https://api.fontshare.com/v2/css?f[]=switzer@400,500,600,700&display=swap"
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
