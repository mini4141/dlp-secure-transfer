import { test, expect } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

// Screenshot of one trace that spans API -> SQS -> worker (needs Jaeger; skipped otherwise).
const JAEGER = process.env.JAEGER_URL;
const SHOT_DIR = process.env.SHOT_DIR;

test.skip(!JAEGER, "JAEGER_URL not set");

test("trace API -> worker in Jaeger", async ({ page, request }) => {
  let traceId = "";
  for (let i = 0; i < 20 && !traceId; i++) {
    const res = await request.get(`${JAEGER}/api/traces?service=dlp-worker&limit=20`);
    const traces = (await res.json()).data || [];
    const both = traces.find((t: any) => {
      const services = new Set(Object.values(t.processes).map((p: any) => p.serviceName));
      return services.has("dlp-api") && services.has("dlp-worker");
    });
    if (both) traceId = both.traceID;
    else await new Promise((r) => setTimeout(r, 2000));
  }
  expect(traceId, "a trace containing dlp-api and dlp-worker spans").not.toEqual("");
  await page.goto(`${JAEGER}/trace/${traceId}`);
  await expect(page.locator("body")).toContainText("dlp.scan");
  await page.waitForTimeout(1500);
  if (SHOT_DIR) {
    fs.mkdirSync(SHOT_DIR, { recursive: true });
    await page.screenshot({ path: path.join(SHOT_DIR, "09-trace-api-to-worker.png") });
  }
});
