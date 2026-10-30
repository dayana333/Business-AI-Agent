// Read public review text from Kaspi product pages in a real browser.
// Usage: node TOOLS/kaspi_reviews.mjs pages url1 [url2 ...]
import { createRequire } from 'module';
const { chromium } = createRequire('/opt/frp/mcp/node_modules/')('playwright');

const pages = Math.max(1, Math.min(6, Number(process.argv[2]) || 4));
const urls = process.argv.slice(3);
if (!urls.length) {
  console.error('usage: node kaspi_reviews.mjs <pages> <url> [url ...]');
  process.exit(2);
}

const browser = await chromium.launch({
  executablePath: '/opt/frp/chrome-headless-shell',
  args: ['--no-sandbox'],
});
const out = [];
try {
  for (const url of urls) {
    const page = await browser.newPage({ viewport: { width: 1400, height: 2600 }, locale: 'ru-RU' });
    let sellerInfo = {};
    try {
      const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
      const imageUrl = await page.evaluate(() => {
        const meta = document.querySelector('meta[property="og:image"], meta[name="og:image"]');
        return meta ? meta.getAttribute('content') || '' : '';
      }).catch(() => '');
      await page.waitForSelector('.sellers-table__self', { state: 'attached', timeout: 8000 }).catch(() => {});
      sellerInfo = await page.evaluate(() => {
        const selfEl = document.querySelector('.sellers-table__self');
        const sellerCell = selfEl ? selfEl.querySelector('.sellers-table__cell') : null;
        const sellerText = (sellerCell ? sellerCell.innerText : '').trim();
        const sellerName = sellerText
          .replace(/\s*\(\d[\d\s]*\s*отзыв[^)]*\)\s*/gi, ' ')
          .split('\n').map((x) => x.trim()).filter(Boolean)[0] || '';
        const sellerReviewsMatch = (sellerText.match(/\((\d[\d\s]*)\s*отзыв/i) || [])[1];
        const sellerRatingClass = selfEl
          ? (selfEl.querySelector('.sellers-table__rating-wrapper .rating, .rating._seller')?.className || '')
          : '';
        const sellerRatingMatch = sellerRatingClass.match(/_(\d{2})(?:\s|$)/);
        return {
          seller: sellerName,
          seller_reviews: sellerReviewsMatch ? Number(sellerReviewsMatch.replace(/\s/g, '')) : null,
          seller_rating: sellerRatingMatch ? Number(sellerRatingMatch[1]) / 10 : null,
        };
      }).catch(() => ({}));
      if (!resp || resp.status() !== 200) {
        out.push({ url, status: 'blocked', reason: 'HTTP ' + (resp ? resp.status() : 'no response'), image_url: imageUrl, ...sellerInfo });
        continue;
      }
      await page.waitForSelector('.reviews__review', { state: 'attached', timeout: 20000 });
      await page.evaluate(() => {
        const tab = [...document.querySelectorAll('.tabs-content__tab')]
          .find((e) => /^Отзывы \(\d+\)$/.test((e.innerText || '').trim()));
        if (tab) tab.click();
      });
      await page.waitForTimeout(800);
      for (let i = 1; i < pages; i += 1) {
        const before = await page.locator('.reviews__review').count();
        const clicked = await page.evaluate(() => {
          const more = document.querySelector('.reviews__more');
          if (!more) return false;
          more.scrollIntoView({ block: 'center' });
          more.click();
          return true;
        });
        if (!clicked) break;
        await page.waitForFunction(
          (n) => document.querySelectorAll('.reviews__review').length > n,
          before,
          { timeout: 4000 },
        ).catch(() => {});
      }
      const data = await page.evaluate(() => {
        const totalMatch = (document.body.innerText.match(/\((\d[\d\s]*)\s*отзыв/i) || [])[1];
        const items = [...document.querySelectorAll('.reviews__review')].map((el) => {
          const ratingClass = el.querySelector('header .rating')?.className || '';
          const match = ratingClass.match(/_(\d{2})(?:\s|$)/);
          const paragraphs = [...el.querySelectorAll('.reviews__review-text p')]
            .map((p) => p.innerText.trim())
            .join(' ')
            .trim();
          return {
            author: el.querySelector('.reviews__author')?.innerText.trim() || '',
            date: el.querySelector('.reviews__date')?.innerText.trim() || '',
            rating: match ? Number(match[1]) / 10 : null,
            text: paragraphs.replace(/^Комментарий:\s*/i, '').replace(/\s+/g, ' ').trim(),
          };
        }).filter((r) => r.text);
        return {
          title: document.title,
          total_reviews: totalMatch ? Number(totalMatch.replace(/\s/g, '')) : null,
          reviews: items,
        };
      });
      out.push({ url, status: data.reviews.length ? 'ok' : 'no_reviews', image_url: imageUrl, ...data, ...sellerInfo });
    } catch (error) {
      out.push({ url, status: 'error', reason: String(error).split('\n')[0].slice(0, 300), ...sellerInfo });
    } finally {
      await page.close().catch(() => {});
    }
  }
} finally {
  await browser.close();
}
console.log(JSON.stringify(out));
