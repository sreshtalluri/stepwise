import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The demo is a harness, not a product: it exists so the navigation surface can be
// looked at on a phone at three metres before anyone trusts it (DESIGN.md §13,
// "still unverified"). The real app is apps/web.
export default defineConfig({
  root: "demo",
  plugins: [react()],
  server: { host: true, port: 5176 },
});
