const { chromium } = require("playwright");
const path = require("node:path");

async function main() {
  const url = process.argv[2];
  const output = process.argv[3];
  if (!url || !output) {
    throw new Error("Usage: node capture_demo.cjs <url> <output.png>");
  }

  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
  });
  await page.goto(url, { waitUntil: "networkidle" });
  await page.screenshot({
    path: path.resolve(output),
    fullPage: false,
  });
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
