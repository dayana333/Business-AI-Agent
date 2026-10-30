# Status — 30 Oct 2026

## Working now
- Kaspi live search (headless Chrome) → title, price, rating, review count, URL.
- Kaspi review text (headless Chrome): up to 36 visible reviews per pick (4 pages), with
  star rating, date, real excerpt, positive/negative keyword themes and frequency counts.
- One-command pipeline: `python3 agent.py "<query>"` → collect, dedupe, stats, 3 picks
  (Best budget / Best mid-range / Best premium), statuses, CSV, markdown report.
  Every pick must pass the global quality floor: rating 4.5+ and 10+ product reviews.
  Tiers are built only from passing offers: budget = lowest 40% by price,
  mid = next 40%, premium = top 20%. Offers with the same price stay in one
  band, so a cluster of identical prices cannot appear in both mid and premium.
  All three tiers prefer the upper half of their price band, so no tier defaults
  to the cheapest item that barely qualifies. Budget and mid give price position
  25%, rating 45% and review depth 30%; premium gives 35%, 40% and 25%.
- Quality floor lowered to 4.5+ rating and 10+ reviews after feedback that
  important products were ignored. Picks with fewer than 50 reviews carry a
  small-sample warning instead of being treated as strong evidence.
- Anomaly prices are named separately: offers below 30% of the similar-offer median,
  or below 60% of the lowest quartile, are shown in a price-landscape warning box and
  left out of the picks. Tested live with "наушники": i9S-TWS at 973 ₸, 19% of the
  4 990 ₸ median. A synthetic hoodie at 2 000 ₸ is flagged against a 3 499–6 264 ₸ market.
  Each card must be a different product title: duplicates are skipped instead of filling
  another card, and the result says `insufficient_distinct` if three different products
  cannot be found.
- For a query with an exact brand (e.g. "Pandora"), Kaspi picks must pass a likely-original
  check: brand in the title, seller name matches the brand, seller rating 4.5+/5 from 20+
  reviews. Failing picks are removed and named; passed picks say it is evidence, not proof.
- Kaspi-only pipeline and UI: Wildberries and Ozon code, capture, imports and docs were removed.
- Honest Kaspi status in console, `data/collection_status.json`, and the report.
- Evidence-labelled research brief in the UI: executive summary, market overview,
  competitor/price evidence, collected review evidence (or checked-and-unavailable),
  opportunities as hypotheses, risks, next checks, and 5 explicit evidence checks. Deterministic (`TOOLS/insights.py`), no model;
  Markdown download button. Missing data is named, never filled with generic frameworks.
- Pick cards show a short summary, two reasons, one warning, and collapsed review
  evidence. Each card also lists up to two other good options from the same price band.
- High-price category shortcuts are examples, not a limit. The "Show only the Best
  premium pick" toggle works with any typed category. Tested with "кофемашина":
  Delonghi Magnifica S, 181 000 ₸; unticking the box returned all three tiers.
  Normal searches still show all three tiers.
- Final comparison table: product, price, rating/reviews, advantages, common complaints,
  quality evidence, recommendation reason and confidence level.
- Tests: 51 pass, including concise pick summaries, distinct-product cards, the quality floor, weak-offer rejection, price bands (40/40/20), review-text
  themes/frequencies, missing-review behaviour, path safety, recommendation tiers and report tests.

## Verified data sources
| Source | Status | Real data? |
|---|---|---|
| Kaspi public search | works | yes, 12 rows for "заколка крабик для волос" (30 Oct 2026) |

## Methodology reference
- MITM Institute, "Маркетинговый анализ — виды и этапы исследования" (26 Sep 2023):
  https://mitm.institute/journal--marketing--marketingovyj-analiz-vidy-i-etapy-issledovaniya
  Used for the report structure (goal → data → structured report → recommendations). PESTEL/SWOT/BCG
  are not generated because this dataset still has no cost, demand or market-size evidence;
  the brief says so explicitly instead of filling a template.

## Limits
- The likely-original check is a seller-name/history heuristic. Kaspi exposes no
  authenticity field, so it cannot prove that an item is original.
- Review text is read only from public Kaspi product pages; it is a visible sample
  (36 of 601 reviews for one tested pick), not a full census.
- Review count is public evidence of buyer activity, not a sales count. Kaspi does not
  publish sales for these listings, so the quality floor uses reviews, not purchases.
- Web UI: `python3 webui.py 8000` → premium dark workspace with feature cards, method section,
  active navigation, reveal animations, back-to-top, status badges, coverage warning, research
  brief, price stats, 3 pick cards, offers table and Markdown report (checked at desktop and
  390 px mobile widths; no console, page or request errors). The market brief uses observed
  rows plus a visible review-text sample; demand and sales are still missing.

## Next steps
1. Normalise multipacks (e.g. a 9-piece hair-clip pack) before price comparison.
2. Add more review pages to raise the visible sample.
3. Add the marketing strategy generator and final PDF report.

## Feedback section (30 Oct 2026)

- The "From customer feedback" section now shows a product strip (photo, role, title,
  price, rating, reviews read, total reviews, seller) matching the recommendation
  evidence, followed by the existing complaint cards. Tested live with "кофемашина":
  three product photos loaded, prices 35 800 / 55 800 / 181 000 ₸, no page errors.
