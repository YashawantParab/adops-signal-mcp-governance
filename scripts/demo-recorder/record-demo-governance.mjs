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

async function expectPoll(getValue, predicate, timeoutMs, intervalMs = 300) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    if (predicate(await getValue())) return;
    if (Date.now() > deadline) throw new Error(`expectPoll: condition not met within ${timeoutMs}ms`);
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
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
      // The login button click triggers an async POST /api/auth/login and a
      // client-side auth-state update before the app renders as logged in -
      // navigating away immediately (the next page.goto below) raced ahead of
      // that and landed on an unauthenticated page. The button's own
      // accessible name flips to "Signing in..." the instant it's clicked
      // (see LoginScreen.tsx), so waiting for the "Enter workspace"-named
      // element to become hidden resolves immediately and does NOT wait for
      // the login to actually finish - wait for a real post-login-only
      // element instead.
      await page.getByRole("heading", { name: "Delivery Operations" }).waitFor({ timeout: 15000 });
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
    // Backend AGENT_TIMEOUT_SECONDS defaults to 45s - that is the agent
    // run's own budget, not counting the HTTP round trip, DB writes, and
    // render on top of it, so the wait here must exceed 45s with real
    // margin, not match it exactly.
    await page.getByText(/Execution/).first().waitFor({ timeout: 60000 });
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
    // The Campaign <select> has no blank/placeholder option, so its React
    // state starts at "" (no campaign selected) until a real selection event
    // fires - "Propose Action" stays disabled (campaignId is falsy) until
    // then, so explicitly choose one first rather than clicking straight away.
    // <option>s inside a closed <select> are never reported "visible" by
    // Playwright's actionability model, so waiting on one directly never
    // resolves - poll the option count instead, then let selectOption's own
    // built-in retry/actionability handling do the actual selection.
    // getByLabel("Campaign") does not reliably resolve to this <select> (its
    // accessible name computation did not match the wrapping <label>'s text
    // in practice) - address it structurally instead: the first <select>
    // inside the propose form, which is always Campaign (Action is the
    // second select in the same form).
    const campaignSelect = page.locator("form").filter({ hasText: "Propose Action" }).locator("select").first();
    await expectPoll(() => campaignSelect.locator("option").count(), (count) => count > 0, 15000);
    await campaignSelect.selectOption({ index: 0 });
    await pause(page, 500);
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
