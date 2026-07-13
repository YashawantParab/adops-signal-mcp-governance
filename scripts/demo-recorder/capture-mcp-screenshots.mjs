#!/usr/bin/env node
/**
 * Captures README/docs screenshots of the deployed MCP Governance Control Plane.
 *
 * Read-only: signs in with the seeded demo user, screenshots existing pages, and
 * writes PNGs to docs/assets/. Does not create, approve, or reject anything.
 *
 * Usage:
 *   npm install
 *   npx playwright install --with-deps chromium
 *   node capture-mcp-screenshots.mjs
 *
 * Configuration (all optional, via environment variables):
 *   DEMO_BASE_URL - frontend origin (default: deployed Vercel demo)
 *   DEMO_EMAIL    - seeded demo user email    (default: adops@demo.adops.local)
 *   DEMO_PASSWORD - seeded demo user password (default: SignalDemo!2026)
 */

import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "..", "..");
const ASSETS_DIR = path.join(REPO_ROOT, "docs", "assets");

const BASE_URL = process.env.DEMO_BASE_URL ?? "https://adops-signal-mcp-governance.vercel.app";
const EMAIL = process.env.DEMO_EMAIL ?? "adops@demo.adops.local";
const PASSWORD = process.env.DEMO_PASSWORD ?? "SignalDemo!2026";

const VIEWPORT = { width: 1440, height: 900 };

function pause(page, ms) {
  return page.waitForTimeout(ms);
}

async function main() {
  fs.mkdirSync(ASSETS_DIR, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: VIEWPORT });
  const page = await context.newPage();

  try {
    console.log(`Opening ${BASE_URL}/mcp-governance`);
    await page.goto(`${BASE_URL}/mcp-governance`, { waitUntil: "networkidle", timeout: 90000 });

    const loginButton = page.getByRole("button", { name: "Enter workspace" });
    const needsLogin = await loginButton.isVisible({ timeout: 8000 }).catch(() => false);
    if (needsLogin) {
      console.log("Signing in with the seeded AdOps Manager demo user");
      await page.getByLabel("Email").fill(EMAIL);
      await page.getByLabel("Password").fill(PASSWORD);
      await pause(page, 400);
      await loginButton.click();
      await page.waitForURL(/\/dashboard/, { timeout: 20000 });
      console.log("Logged in; navigating back to /mcp-governance");
      await page.goto(`${BASE_URL}/mcp-governance`, { waitUntil: "networkidle", timeout: 30000 });
    } else {
      console.log("Already authenticated; continuing");
    }

    await page.getByRole("heading", { name: "MCP Governance Dashboard" }).waitFor({ timeout: 30000 });
    await pause(page, 1500);
    await page.screenshot({ path: path.join(ASSETS_DIR, "mcp-dashboard.png") });
    console.log("Captured mcp-dashboard.png");

    console.log(`Opening ${BASE_URL}/mcp-governance/agent`);
    await page.goto(`${BASE_URL}/mcp-governance/agent`, { waitUntil: "networkidle", timeout: 30000 });
    await pause(page, 1500);
    await page.screenshot({ path: path.join(ASSETS_DIR, "mcp-agent-console.png") });
    console.log("Captured mcp-agent-console.png");

    console.log(`Opening ${BASE_URL}/mcp-governance/approvals`);
    await page.goto(`${BASE_URL}/mcp-governance/approvals`, { waitUntil: "networkidle", timeout: 30000 });
    await pause(page, 1500);
    await page.screenshot({ path: path.join(ASSETS_DIR, "mcp-decision-queue.png") });
    console.log("Captured mcp-decision-queue.png");

    console.log(`Opening ${BASE_URL}/mcp-governance/tools`);
    await page.goto(`${BASE_URL}/mcp-governance/tools`, { waitUntil: "networkidle", timeout: 30000 });
    await pause(page, 1500);
    await page.screenshot({ path: path.join(ASSETS_DIR, "mcp-tool-registry.png") });
    console.log("Captured mcp-tool-registry.png");

    console.log("Finding a recent run for the Governance Record screenshot");
    await page.goto(`${BASE_URL}/mcp-governance`, { waitUntil: "networkidle", timeout: 30000 });
    await pause(page, 1000);
    const runLink = page.locator('a[href*="/mcp-governance/runs/"]').first();
    const hasRun = await runLink.isVisible({ timeout: 8000 }).catch(() => false);
    if (hasRun) {
      await runLink.click();
      await page.waitForURL(/\/mcp-governance\/runs\/.+/, { timeout: 20000 });
      await pause(page, 1500);
      await page.screenshot({ path: path.join(ASSETS_DIR, "governance-record.png") });
      console.log("Captured governance-record.png");
    } else {
      console.log("No existing run found to open for the Governance Record screenshot; skipping.");
    }

    console.log("Done.");
  } finally {
    await context.close();
    await browser.close();
  }
}

main().catch((error) => {
  console.error("Screenshot capture failed:", error.message);
  process.exit(1);
});
