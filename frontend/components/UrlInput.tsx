"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { validateVideoUrl } from "@/lib/validation";

export function UrlInput() {
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    const validation = validateVideoUrl(url);
    if (!validation.valid) {
      setError(validation.error ?? "Invalid URL");
      return;
    }

    setLoading(true);

    try {
      const res = await fetch("/api/process", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Failed to process");
      }

      const { jobId } = await res.json();
      router.push(`/viewer/${jobId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <div className="relative">
        <input
          type="text"
          value={url}
          onChange={(e) => {
            setUrl(e.target.value);
            setError(null);
          }}
          placeholder="Paste any video URL"
          disabled={loading}
          className={`
            w-full px-5 py-4 rounded-panel
            bg-surface border transition-all duration-200
            text-text-primary placeholder:text-text-secondary
            text-lg outline-none
            ${
              error
                ? "border-error"
                : "border-border focus:border-accent focus:shadow-[0_0_20px_rgba(0,212,255,0.15)]"
            }
            disabled:opacity-50 disabled:cursor-not-allowed
          `}
        />

        <button
          type="submit"
          disabled={loading || !url.trim()}
          className="
            absolute right-2 top-1/2 -translate-y-1/2
            px-5 py-2 rounded-button
            bg-accent text-bg font-semibold text-sm
            hover:brightness-110 active:brightness-90
            disabled:opacity-30 disabled:cursor-not-allowed
            transition-all duration-150
          "
        >
          {loading ? (
            <span className="inline-block w-4 h-4 border-2 border-bg border-t-transparent rounded-full spin-slow" />
          ) : (
            "Analyze"
          )}
        </button>
      </div>

      {error && (
        <p className="mt-3 text-error text-sm text-center">{error}</p>
      )}
    </form>
  );
}
