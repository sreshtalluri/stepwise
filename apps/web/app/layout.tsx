import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "stepwise — lesson",
  description: "See the dance from any angle, from the one video you have.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        {/* Cabinet Grotesk + Switzer, DESIGN.md §5. Both free for commercial use. */}
        <link
          rel="stylesheet"
          href="https://api.fontshare.com/v2/css?f[]=cabinet-grotesk@700,800&f[]=switzer@400,500,600&display=swap"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
