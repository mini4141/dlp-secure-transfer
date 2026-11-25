import { test, expect, Browser, Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

// One journey, two uses: the e2e test (always) and proof screenshots (when SHOT_DIR is set).
// SHOT_SET=local -> 01-send-form ... 07-audit-log; SHOT_SET=eks -> 01-eks-approval, 02-eks-download, 03-eks-audit.
const SHOT_DIR = process.env.SHOT_DIR;
const SHOT_SET = process.env.SHOT_SET || "local";
const PASSWORD = process.env.SEED_PASSWORD || "demo-password";
const SAMPLE = path.resolve(__dirname, "../../samples/customers.csv");

const NAMES: Record<string, Record<string, string>> = {
  local: {
    send: "01-send-form",
    scanning: "02-scanning",
    findings: "03-approval-findings",
    preview: "04-redacted-preview",
    download: "05-recipient-download",
    limit: "06-limit-reached",
    audit: "07-audit-log",
  },
  eks: { findings: "01-eks-approval", download: "02-eks-download", audit: "03-eks-audit" },
};

async function shot(page: Page, key: string, fullPage = false) {
  const name = NAMES[SHOT_SET]?.[key];
  if (!SHOT_DIR || !name) return;
  fs.mkdirSync(SHOT_DIR, { recursive: true });
  await page.screenshot({ path: path.join(SHOT_DIR, `${name}.png`), fullPage });
}

async function login(browser: Browser, email: string) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto("/login");
  await page.fill("input[name=email]", email);
  await page.fill("input[name=password]", PASSWORD);
  await page.click("button.primary");
  await expect(page.locator(".who")).toContainText(email);
  return page;
}

test("sender -> approver (redacted) -> recipient download -> limit -> audit", async ({ browser }) => {
  // 1. Sam sends customers.csv (contains fake card numbers, emails, phones)
  const sam = await login(browser, "sam@corp.test");
  await sam.goto("/send");
  await sam.fill("input[name=recipients]", "partner@example.org");
  await sam.fill("textarea[name=message]", "Customer export for the Q4 reconciliation");
  await sam.fill("input[name=password]", "link-secret-42");
  await sam.fill("input[name=max_downloads]", "1");
  await sam.setInputFiles("input[name=files]", SAMPLE);
  await shot(sam, "send");
  await sam.click("#send-btn");
  await sam.waitForURL(/\/transfers\/\d+$/);
  const transferId = sam.url().split("/").pop()!;
  await shot(sam, "scanning");

  // 2. The Go worker flags PII -> needs approval
  await expect(sam.locator("#status")).toHaveText("pending approval", { timeout: 90_000 });
  const link = (await sam.locator("#link").innerText()).trim();

  // 3. Ava reviews obfuscated findings + redacted preview, approves the redacted copy
  const ava = await login(browser, "ava@corp.test");
  await ava.goto(`/approvals/${transferId}`);
  await expect(ava.locator("table[id^=findings]")).toContainText("4111 **** **** 1111");
  await expect(ava.locator("body")).not.toContainText("4111 1111 1111 1111");
  await shot(ava, "findings", true);
  await ava.locator("pre.preview").scrollIntoViewIfNeeded();
  await expect(ava.locator("pre.preview")).toContainText("[REDACTED:card]");
  await shot(ava, "preview");
  await ava.click("button[value=redacted]");
  await ava.waitForURL(/\/approvals$/);
  await expect(sam.locator("#status")).toHaveText("ready", { timeout: 30_000 });

  // 4. Recipient: password, then a single allowed download
  const ctx = await browser.newContext({ acceptDownloads: true });
  const rec = await ctx.newPage();
  await rec.goto(link);
  await rec.fill("input[name=password]", "link-secret-42");
  await rec.click("button.primary");
  await expect(rec.locator("table")).toContainText("customers.csv");
  await shot(rec, "download");
  const [download] = await Promise.all([rec.waitForEvent("download"), rec.click("a.btn")]);
  const body = fs.readFileSync((await download.path())!, "utf8");
  expect(body).toContain("[REDACTED:card]");
  expect(body).not.toContain("4111 1111 1111 1111");

  // 5. The next download is beyond the limit
  const href = await rec.locator("a.btn").getAttribute("href");
  await rec.goto(href!);
  await expect(rec.locator("#msg")).toHaveText("Download limit reached");
  await shot(rec, "limit");

  // 6. Admin sees the whole story in the audit log
  const admin = await login(browser, "admin@corp.test");
  await admin.goto(`/admin?transfer_id=${transferId}`);
  const audit = admin.locator("#audit");
  for (const action of ["transfer.created", "transfer.uploaded", "scan.completed", "transfer.approved.redacted", "download.completed", "download.denied"]) {
    await expect(audit).toContainText(action);
  }
  await shot(admin, "audit", true);
});
