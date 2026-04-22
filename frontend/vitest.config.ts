import path from "node:path"
import { defineConfig } from "vitest/config"

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname),
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./tests/setup.ts"],
    restoreMocks: true,
    clearMocks: true,
    exclude: ["tests/e2e/**", "node_modules/**", ".next/**"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json-summary"],
      include: [
        "app/*/agent/page.tsx",
        "app/*/workflows/page.tsx",
        "app/*/workflows/*/page.tsx",
        "app/*/workflows/components/run-wizard-dialog.tsx",
        "app/*/runs/page.tsx",
        "app/*/images/page.tsx",
      ],
      thresholds: {
        statements: 80,
        functions: 80,
        lines: 80,
        branches: 65,
      },
    },
  },
})
