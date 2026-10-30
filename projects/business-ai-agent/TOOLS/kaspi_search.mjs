// Open a Kaspi search page in the real (headless) browser and print the cards as JSON.
// Usage: node TOOLS/kaspi_search.mjs "redmi buds"
import { createRequire } from 'module';
const { chromium } = createRequire("/opt/frp/mcp/node_modules/")("playwright");

const query = process.argv[2];
if (!query) {
  console.error('usage: node kaspi_search.mjs "<query>"');
  process.exit(2);
}

const browser = await chromium.launch({
  executablePath: "/opt/frp/chrome-headless-shell",
  args: ["--no-sandbox"],
});
try {
  const page = await browser.newPage({ viewport: { width: 1400, height: 2400 }, locale: "ru-RU" });
  const url = "https://kaspi.kz/shop/search/?text=" + encodeURIComponent(query);
  const resp = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
  if (!resp || resp.status() !== 200) {
    console.error("kaspi blocked: HTTP " + (resp ? resp.status() : "no response"));
    process.exit(3);
  }
  await page.waitForSelector(".item-card", { timeout: 20000 });
  await page.waitForTimeout(1500);
  const data = await page.evaluate(() => ({
    title: document.title,
    cards: [...document.querySelectorAll(".item-card")].map((card) => ({
      title: card.querySelector(".item-card__name")?.innerText.trim() || "",
      price: card.querySelector(".item-card__prices-price")?.innerText.trim() || "",
      reviews: card.querySelector(".item-card__rating")?.innerText.trim() || "",
      ratingClass: card.querySelector(".item-card__rating .rating")?.className || "",
      href: card.querySelector(".item-card__name-link")?.getAttribute("href") || "",
      image: card.querySelector("img")?.getAttribute("src") || "",
    })),
  }));
  console.log(JSON.stringify(data));
} finally {
  await browser.close();
}
