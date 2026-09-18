import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#0a0a0a",
        surface: "#141414",
        "surface-hover": "#1a1a1a",
        border: "#222222",
        "text-tertiary": "#555555",
        "text-secondary": "#888888",
        "text-primary": "#f0f0f0",
        accent: "#00d4ff",
        "accent-glow": "rgba(0, 212, 255, 0.2)",
        "accent-subtle": "rgba(0, 212, 255, 0.08)",
        error: "#ff4444",
        success: "#44ff88",
        warning: "#ffdd44",
      },
      borderRadius: {
        panel: "8px",
        button: "4px",
        input: "8px",
        lg: "12px",
      },
      fontFamily: {
        display: ["Clash Grotesk", "system-ui", "sans-serif"],
        body: ["var(--font-body)", "Instrument Sans", "system-ui", "sans-serif"],
        mono: ["Geist Mono", "ui-monospace", "monospace"],
        sans: ["var(--font-body)", "Instrument Sans", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
export default config;
