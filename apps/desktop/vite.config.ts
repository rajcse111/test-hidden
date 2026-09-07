import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  // Vite resolves .env relative to cwd, which is apps/desktop — but this
  // project keeps a single .env at the repo root. Without envDir the VITE_*
  // vars there are silently ignored and the renderer uses its fallbacks.
  envDir: path.resolve(__dirname, "../.."),
  plugins: [react()],
  server: {
    port: 5173,
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
