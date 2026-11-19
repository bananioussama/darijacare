// Tests E2E (Phase 6) : parcours réels sur la pile Docker Compose (make up), via le
// frontal HTTPS. Les comptes viennent de ../.env (make e2e les y lit).
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  globalSetup: "./e2e/global-setup.ts",
  timeout: 180_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  outputDir: "test-results",
  use: {
    baseURL: process.env.DARIJACARE_E2E_URL ?? "https://127.0.0.1:8443",
    // Certificat auto-signé de deploy/certs (démonstration locale).
    ignoreHTTPSErrors: true,
    locale: "fr-FR",
    reducedMotion: "reduce",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
