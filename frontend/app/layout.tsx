import type { Metadata } from "next";
import { Instrument_Sans } from "next/font/google";
import "./globals.css";

const instrumentSans = Instrument_Sans({
  subsets: ["latin"],
  variable: "--font-body",
  weight: ["400", "500", "600"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Stepwise — Learn Any Dance Move",
  description:
    "Paste a video URL and get an interactive 3D breakdown of any movement.",
  icons: {
    icon: [{ url: "/favicon.svg", type: "image/svg+xml" }],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <head>
        {/* Clash Grotesk from FontShare CDN */}
        <link
          href="https://api.fontshare.com/v2/css?f[]=clash-grotesk@600,700&display=swap"
          rel="stylesheet"
        />
        {/* Geist Mono from Google Fonts CDN */}
        <link
          href="https://fonts.googleapis.com/css2?family=Geist+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className={`${instrumentSans.variable} font-body bg-bg text-text-primary min-h-screen`}>
        {children}
      </body>
    </html>
  );
}
