import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const rootDir = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  base: "./",
  server: {
    origin: "http://localhost:5174"
  },
  build: {
    emptyOutDir: true,
    manifest: true,
    outDir: resolve(rootDir, "../static/dist"),
    rollupOptions: {
      input: {
        "admin-extension": resolve(rootDir, "src/admin-extension.css")
      }
    }
  }
});
