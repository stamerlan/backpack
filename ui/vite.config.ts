import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  root: ".",
  base: "./",
  plugins: [react()],
  build: {
    outDir: "../assets",
    assetsDir: "static",
    emptyOutDir: true,
    sourcemap: true,
    target: "chrome110",
  },
  server: {
    port: 5173,
    strictPort: true,
  },
});
