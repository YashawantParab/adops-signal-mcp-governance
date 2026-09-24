#!/usr/bin/env node
/**
 * Records a browser walkthrough of the Phase 1-3 governed-agent flow and saves
 * it as docs/demo/adops-signal-governance-demo.webm - a SECOND recording,
 * separate from record-demo.mjs (which still covers the original legacy
 * diagnose -> approve -> audit flow and is unmodified).
 *
 * NOT YET EXECUTED IN THE SESSION THAT WROTE THIS FILE. It was written
 * against the real page structure (frontend/app/mcp-governance/**) but has
 * not been run through an actual Playwright browser and recorded - doing so
 * requires `npx playwright install --with-deps chromium` and a live browser
 * session, which that session did not do. Do not treat its existence as proof
 * the flow was demo-recorded; run it and watch the output before relying on it.
 *
 * Without OPENAI_API_KEY/ANTHROPIC_API_KEY configured on the backend, the
 * agent run will honestly show execution_mode=deterministic_fallback with a
 * fallback_reason of missing_provider_key - this script does not fake an LLM
 * run. Configure a real provider key on the backend before recording to
 * capture the llm_mcp_agent + gate-decision path instead.
 *
 * Regenerate the recording:
 *   npm install
 *   npx playwright install --with-deps chromium
 *   docker compose exec backend python seed.py   # reseed for a clean run
 *   npm run record:governance
 *
 * Configuration (all optional, via environment variables):
 *   DEMO_BASE_URL  - frontend origin (default: http://localhost:3000)
 *   DEMO_EMAIL     - seeded demo user email    (default: adops@demo.adops.local)
 *   DEMO_PASSWORD  - seeded demo user password (default: SignalDemo!2026)
 *   DEMO_HEADLESS  - "false" to watch the browser while it records (default: true)
 */

import { chromium } from "playwright";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "..", "..");
const OUTPUT_PATH = path.join(REPO_ROOT, "docs", "demo", "adops-signal-governance-demo.webm");

const BASE_URL = process.env.DEMO_BASE_URL ?? "http://localhost:3000";
const EMAIL = process.env.DEMO_EMAIL ?? "adops@demo.adops.local";
const PASSWORD = process.env.DEMO_PASSWORD ?? "SignalDemo!2026";
const HEADLESS = process.env.DEMO_HEADLESS !== "false";

const VIEWPORT = { width: 1440, height: 900 };
const APPROVAL_RATIONALE = "Reviewed the proposed frequency-cap change against current pacing; approving for the demo walkthrough.";

function pause(page, ms) {
  return page.waitForTimeout(ms);
}

async function main() {
  const videoDir = fs.mkdtempSync(path.join(os.tmpdir(), "adops-governance-demo-"));
  const browser = await chromium.launch({ headless: HEADLESS });
  const context = await browser.newContext({ viewport: VIEWPORT, recordVideo: { dir: videoDir, size: VIEWPORT } });
  const page = await context.newPage();

  try {
    console.log(`Opening ${BASE_URL}/dashboard`);
    await page.goto(`${BASE_URL}/dashboard`, { waitUntil: "networkidle" });

    const loginButton = page.getByRole("button", { name: "Enter workspace" });
    if (await loginButton.isVisible({ timeout: 5000 }).catch(() => false)) {
      console.log("Signing in with the seeded AdOps Manager demo user");
      await page.getByLabel("Email").fill(EMAIL);
      await page.getByLabel("Password").fill(PASSWORD);
      await pause(page, 500);
      await loginButton.click();
    }

    console.log("Opening the MCP Agent Console");
    await page.goto(`${BASE_URL}/mcp-governance/agent`, { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: "MCP Agent Console" }).waitFor({ timeout: 20000 });
    await pause(page, 1200);

    console.log("Running a governed investigation for a seeded campaign");
    await page.getByPlaceholder(/Example: Analyze campaign/).fill(
      "Why is this campaign underdelivering, and is it safe to expand inventory?"
    );
    await pause(page, 600);
    await page.getByRole("button", { name: /Run Governance Analysis/ }).click();
    await page.getByText(/Execution/).first().waitFor({ timeout: 45000 });
    await pause(page, 2500);

    console.log("Showing the execution mode and any Decision Gates result");
    const gatesHeading = page.getByRole("heading", { name: "Decision Gates" });
    if (await gatesHeading.isVisible({ timeout: 5000 }).catch(() => false)) {
      await gatesHeading.scrollIntoViewIfNeeded();
      await pause(page, 2500);
    }

    console.log("Opening the Governance Record for this run");
    const openRunLink = page.getByRole("link", { name: /Open|Governance Record/ }).first();
    if (await openRunLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      await openRunLink.click();
      await page.getByText(/Governance Record/).first().waitFor({ timeout: 20000 });
      await pause(page, 2500);
    }

    console.log("Opening the Synthetic Action Console");
    await page.goto(`${BASE_URL}/mcp-governance/actions`, { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: "Synthetic Action Console" }).waitFor({ timeout: 20000 });
    await pause(page, 1200);

    console.log("Proposing a frequency-cap adjustment");
    await page.getByRole("button", { name: "Propose Action" }).click();
    await pause(page, 1500);

    console.log("Approving the proposed action");
    const rationaleInput = page.getByPlaceholder("Approval rationale").first();
    if (await rationaleInput.isVisible({ timeout: 10000 }).catch(() => false)) {
      await rationaleInput.fill(APPROVAL_RATIONALE);
      await pause(page, 800);
      await page.getByRole("button", { name: "Approve" }).first().click();
      await pause(page, 1500);
    }

    console.log("Executing the approved action");
    const executeButton = page.getByRole("button", { name: "Execute" }).first();
    if (await executeButton.isVisible({ timeout: 10000 }).catch(() => false)) {
      await executeButton.click();
      await pause(page, 2000);
    }

    console.log("Showing before/after state and verification result");
    await pause(page, 2500);

    console.log("Rolling back the executed action");
    const rollbackButton = page.getByRole("button", { name: "Roll back" }).first();
    if (await rollbackButton.isVisible({ timeout: 10000 }).catch(() => false)) {
      await rollbackButton.click();
      await pause(page, 2000);
    }

    console.log("Governance flow demo complete");
  } finally {
    const video = page.video();
    await context.close();
    await browser.close();

    if (video) {
      const recordedPath = await video.path();
      fs.mkdirSync(path.dirname(OUTPUT_PATH), { recursive: true });
      fs.copyFileSync(recordedPath, OUTPUT_PATH);
      fs.rmSync(videoDir, { recursive: true, force: true });
      console.log(`Saved recording to ${path.relative(REPO_ROOT, OUTPUT_PATH)}`);
    }
  }
}

main().catch((error) => {
  console.error("Governance demo recording failed:", error.message);
  process.exit(1);
});
