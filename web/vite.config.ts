import { defineConfig } from "vite";

// The page imports ../results/viewer.json, one level above this folder.
export default defineConfig({
  base: "./",
  server: { fs: { allow: [".."] } },
});
