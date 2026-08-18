import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const dir = path.dirname(fileURLToPath(import.meta.url));
const binNm = path.join(dir, "..", "..", "bin", "node_modules");

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
  /* extraNm routes the app's own imports to bin/node_modules, but the esbuild
   * pre-bundler does not run that Rollup hook, so a library resolves react
   * from src/ui/node_modules and the app ends up with two React copies, which
   * breaks hooks. Pin react and react-dom to the single bin copy so every
   * import, pre-bundled or not, lands on the same module.
   */
  resolve: {
    dedupe: ["react", "react-dom"],
    alias: {
      react: path.join(binNm, "react"),
      "react-dom": path.join(binNm, "react-dom"),
    },
  },
  build: {
    outDir: "../../bin/assets",
    assetsDir: "static",
    emptyOutDir: true,
    sourcemap: true,
    target: "chrome110",
  },
  server: {
    port: 5173,
    strictPort: true,
    fs: { allow: ["../.."] },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    css: false,
    deps: {
      moduleDirectories: ["../../bin/node_modules"],
    },
  },
};
