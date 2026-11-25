import { test, expect } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

// Screenshot of the ArgoCD application page (skipped unless ARGOCD_URL is set).
// The capture script port-forwards argocd-server and passes the initial admin password.
const URL = process.env.ARGOCD_URL;
const SHOT_DIR = process.env.SHOT_DIR;
const SHOT_NAME = process.env.ARGOCD_SHOT_NAME || "08-argocd-app";

test.skip(!URL, "ARGOCD_URL not set");

test("ArgoCD shows dlp-secure-transfer Synced and Healthy", async ({ page }) => {
  await page.goto(`${URL}/login`);
  await page.getByRole("textbox").first().fill("admin");
  await page.locator("input[type=password]").fill(process.env.ARGOCD_PASSWORD || "");
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(/\/applications/);
  await page.goto(`${URL}/applications/argocd/dlp-secure-transfer?view=tree&resource=`);
  await expect(page.locator("body")).toContainText("Healthy", { timeout: 60_000 });
  await expect(page.locator("body")).toContainText("Synced");
  await page.waitForTimeout(2500);
  if (SHOT_DIR) {
    fs.mkdirSync(SHOT_DIR, { recursive: true });
    // mask the commit author line (a personal e-mail address)
    await page.screenshot({ path: path.join(SHOT_DIR, `${SHOT_NAME}.png`), mask: [page.getByText(/@/)] });
  }
});
