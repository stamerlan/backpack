import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const dir = path.dirname(fileURLToPath(import.meta.url));
const binNm = path.join(dir, "..", "bin", "node_modules");

const { default: react } = await import(
  pathToFileURL(
    path.join(binNm, "@vitejs", "plugin-react", "dist", "index.js")
  ).href
);

function extraNm() {
  return {
    name: "extra-node-modules",
    enforce: "pre",
    async resolveId(id, importer, opts) {
      if (
        !id ||
        !importer ||
        importer.includes("node_modules") ||
        id.startsWith(".") ||
        id.startsWith("\0") ||
        id.startsWith("node:") ||
        path.isAbsolute(id)
      ) {
        return null;
      }
      const fake = path.join(binNm, "vite", "package.json");
      if (!fs.existsSync(fake)) {
        return null;
      }
      return this.resolve(id, fake, { ...opts, skipSelf: true });
    },
  };
}

export default {
  root: dir,
  base: "./",
  plugins: [react(), extraNm()],
  build: {
    outDir: "../bin/assets",
    assetsDir: "static",
    emptyOutDir: true,
    sourcemap: true,
    target: "chrome110",
  },
  server: {
    port: 5173,
    strictPort: true,
    fs: { allow: [".."] },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    css: false,
    deps: {
      moduleDirectories: ["../bin/node_modules"],
    },
  },
};
