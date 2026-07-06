#!/usr/bin/env node
/**
 * Records a browser walkthrough of the AdOps Signal demo workflow and saves it as
 * docs/demo/adops-signal-demo.webm.
 *
 * This script only drives the existing app through the browser (Playwright). It does not
 * modify any application code, UI, or backend behavior.
 *
 * The recorder never assumes a fixed recommendation id or title: after filtering the
 * Decision Queue to Campaign 1048 (pending status), it approves whichever pending
 * recommendation card is first in the list. This makes the script repeatable across
 * reruns as long as a pending recommendation exists for that campaign. If none does
 * (e.g. because a prior run already approved the only one and the diagnosis did not
 * produce a new pending item), the script fails fast with instructions to reseed.
 *
 * Regenerate the recording:
 *   npm install
 *   npx playwright install --with-deps chromium
 *   docker compose exec backend python seed.py   # reseed so Campaign 1048 has a pending recommendation
 *   npm run record
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
const OUTPUT_PATH = path.join(REPO_ROOT, "docs", "demo", "adops-signal-demo.webm");

const BASE_URL = process.env.DEMO_BASE_URL ?? "http://localhost:3000";
const EMAIL = process.env.DEMO_EMAIL ?? "adops@demo.adops.local";
const PASSWORD = process.env.DEMO_PASSWORD ?? "SignalDemo!2026";
const HEADLESS = process.env.DEMO_HEADLESS !== "false";

const VIEWPORT = { width: 1440, height: 900 };
const APPROVAL_RATIONALE =
  "Evidence in the investigation supports this recommendation. Approving for demo validation of the human-in-the-loop decision workflow.";

function pause(page, ms) {
  return page.waitForTimeout(ms);
}

async function main() {
  const videoDir = fs.mkdtempSync(path.join(os.tmpdir(), "adops-demo-"));
  const browser = await chromium.launch({ headless: HEADLESS });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    recordVideo: { dir: videoDir, size: VIEWPORT }
  });
  const page = await context.newPage();

  try {
    console.log(`Opening ${BASE_URL}/dashboard`);
    await page.goto(`${BASE_URL}/dashboard`, { waitUntil: "networkidle" });

    const loginButton = page.getByRole("button", { name: "Enter workspace" });
    const needsLogin = await loginButton.isVisible({ timeout: 5000 }).catch(() => false);
    if (needsLogin) {
      console.log("Signing in with the seeded AdOps Manager demo user");
      await page.getByLabel("Email").fill(EMAIL);
      await page.getByLabel("Password").fill(PASSWORD);
      await pause(page, 500);
      await loginButton.click();
    } else {
      console.log("Already authenticated; continuing to dashboard");
    }

    await page.getByRole("heading", { name: "Delivery Operations" }).waitFor({ timeout: 20000 });
    console.log("Dashboard / Operations page loaded");
    await pause(page, 1800);

    console.log("Filtering the risk queue to Campaign 1048");
    const search = page.getByPlaceholder("Campaign, advertiser, or ID");
    await search.click();
    await search.fill("1048");
    await pause(page, 1000);

    console.log("Opening the investigation for Campaign 1048");
    const campaignRow = page.getByRole("row").filter({ hasText: "ID 1048" });
    await campaignRow.getByRole("link", { name: "Diagnose", exact: true }).click();
    await page.getByRole("heading", { name: "Campaign Investigation" }).waitFor({ timeout: 20000 });
    await pause(page, 1200);

    console.log("Running diagnosis");
    await page.getByRole("button", { name: "Diagnose", exact: true }).click();
    await page.getByRole("heading", { name: "Ranked Root Causes" }).waitFor({ timeout: 30000 });
    await pause(page, 1200);
    await page.getByRole("heading", { name: "Evidence", exact: true }).scrollIntoViewIfNeeded();
    await pause(page, 2200);

    console.log("Generating the client-safe brief");
    await page.getByRole("button", { name: "Create client brief" }).click();
    await page.getByText("Client-safe brief").waitFor({ timeout: 20000 });
    await pause(page, 2200);

    console.log("Opening the Decision Queue");
    await page.getByRole("link", { name: "Decision Queue" }).click();
    await page.getByRole("heading", { name: "Decision Queue" }).waitFor({ timeout: 20000 });
    await pause(page, 1000);

    console.log("Filtering the Decision Queue to Campaign 1048, pending decisions only");
    await page.getByLabel("Campaign filter").selectOption({ label: "Campaign 1048" });
    await page.getByLabel("Decision status filter").selectOption({ label: "Pending" });
    await pause(page, 900);

    console.log("Looking up the current pending recommendation for Campaign 1048");
    const emptyState = page.getByText("No decisions in this view");
    const pendingCards = page
      .locator("article")
      .filter({ has: page.getByRole("button", { name: "Approve", exact: true }) });
    await Promise.race([
      pendingCards.first().waitFor({ state: "visible", timeout: 15000 }),
      emptyState.waitFor({ state: "visible", timeout: 15000 })
    ]).catch(() => {});

    const pendingCount = await pendingCards.count();
    if (pendingCount === 0) {
      throw new Error(
        "No pending recommendation found for Campaign 1048. The demo data has likely already " +
          "been decided by a previous run. Reseed the demo data and rerun this recorder:\n" +
          "  docker compose exec backend python seed.py"
      );
    }

    const recommendationCard = pendingCards.first();
    const recommendationId = (await recommendationCard.getByText(/^Recommendation \d+$/).innerText()).trim();
    const recommendationTitle = (await recommendationCard.locator("h2").innerText()).trim();
    console.log(`Approving the first pending recommendation found: ${recommendationId} - "${recommendationTitle}"`);

    await recommendationCard.scrollIntoViewIfNeeded();
    await pause(page, 900);
    await recommendationCard.getByLabel("Decision rationale").fill(APPROVAL_RATIONALE);
    await pause(page, 1400);
    await recommendationCard.getByRole("button", { name: "Approve", exact: true }).click();
    await page.getByText(/was approved/).waitFor({ timeout: 20000 });
    await pause(page, 2200);

    console.log("Opening the Governance Record");
    await page.getByRole("link", { name: "Governance Record" }).click();
    await page.getByRole("heading", { name: "Governance Record" }).waitFor({ timeout: 20000 });
    await pause(page, 1000);

    console.log("Showing the recorded audit entry");
    await page.getByText(recommendationTitle).first().scrollIntoViewIfNeeded();
    await pause(page, 3000);

    console.log("Demo flow complete");
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
  console.error("Demo recording failed:", error.message);
  process.exit(1);
});
