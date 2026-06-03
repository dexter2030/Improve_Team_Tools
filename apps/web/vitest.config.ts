import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Resolve "@/..." tak jak tsconfig paths (vitest nie czyta ich sam).
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
