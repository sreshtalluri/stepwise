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
        border: "#222222",
        "text-primary": "#f0f0f0",
        "text-secondary": "#888888",
        accent: "#00d4ff",
        "accent-glow": "rgba(0, 212, 255, 0.2)",
        error: "#ff4444",
        success: "#44ff88",
      },
      borderRadius: {
        panel: "8px",
        button: "4px",
        input: "8px",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
export default config;
