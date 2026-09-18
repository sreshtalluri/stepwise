import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "stepwise — every angle, from the one video you have",
  description:
    "Upload a dance clip filmed on one camera. Get the dancer back as a 3D body you can spin, slow down, and take one count at a time.",
};

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
      <body>{children}</body>
    </html>
  );
}
