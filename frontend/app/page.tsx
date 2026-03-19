"use client";

import { UrlInput } from "@/components/UrlInput";

export default function LandingPage() {
  return (
    <main className="hero-gradient grid-pattern min-h-screen flex flex-col items-center justify-center px-4">
      {/* Logo / Title */}
      <div className="mb-12 text-center">
        <h1 className="font-display text-5xl md:text-7xl font-bold tracking-tight mb-3">
          <span className="text-text-primary">step</span>
          <span className="text-accent">wise</span>
        </h1>
        <p className="font-body text-text-secondary text-lg md:text-xl">
          Learn any movement, frame by frame
        </p>
      </div>

      {/* URL Input */}
      <div className="w-full max-w-xl">
        <UrlInput />
      </div>

      {/* Supported platforms */}
      <p className="mt-6 text-text-secondary text-sm tracking-widest uppercase font-body">
        TikTok &middot; YouTube &middot; Instagram
      </p>
    </main>
  );
}
