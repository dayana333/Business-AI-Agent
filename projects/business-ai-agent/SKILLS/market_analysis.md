# Skill: Market and Competitor Analysis (Function 1)

Use this skill when the seller names a product or asks what Kaspi competitors charge.

## 1. The tool and its exact location

- File: `TOOLS/market_data.py` — inside this project, next to `AGENT.md`.
- Python import: `from TOOLS import market_data` (run from `~/work/projects/business-ai-agent`).
- Tool name given to the chat model: `market_data_summary`. It is defined in `TOOL_SPEC` inside `TOOLS/market_data.py` and registered in `TOOLS/__init__.py` as `TOOLS["market_data_summary"]`.
- Data file: `data/marketplace_data.csv`. Demo file for tests: `data/sample_marketplace_data.csv`.

Columns of the CSV: `marketplace, product_id, brand, model, title, price_kzt, rating, reviews_count, url, observed_at, notes`.

## 2. How to call and execute the tool

There are three entry points; they all run the same `market_data.summary()` function.

1. Inside the agent (normal path): `python3 agent.py market --product "<name>" --data data/marketplace_data.csv`.
   `agent.py` forces the model to call `market_data_summary(path, product)`, executes that call with `market_data.summary()`, and sends the JSON back to the model as a `tool` message. The report is written only after that message exists.
2. From Python:
   ```python
   from TOOLS import market_data
   facts = market_data.summary("data/marketplace_data.csv", product="Redmi Buds 6")
   ```
3. From the shell (debugging only):
   ```
   python3 TOOLS/market_data.py data/marketplace_data.csv
   ```

If the tool raises an error (file missing, bad column, non-numeric price), report that error text to the seller. Do not continue with made-up rows.

## 3. How to use the tool output

The tool returns one dict. Use it field by field:

| Tool field | Use in the report |
|---|---|
| `rows_analysed`, `source_file` | Header and limitations line |
| `marketplaces`, `missing_marketplaces` | Say that Kaspi is the source; `missing_marketplaces` is empty |
| `sample_data` | If `true`, start with "Demo data — the numbers are fake." |
| `offers` | Competitor table: marketplace, title, price, rating, reviews, url, observed_at |
| `all_rows_by_marketplace` | Kaspi statistics; it mixes models |
| `recommendations.options` | The three picks (budget / mid / premium) computed in code |
| `recommendations.weights`, `recommendations.sample_stats`, `recommendations.bands` | How the score was built |

Never recompute a number the tool already returns, and never widen a claim beyond the rows in `offers`.

## 4. Three recommended options (required in every report)

`TOOLS/recommend.py` first names **Anomaly prices**: offers below 30% of the
similar-offer median, or below 60% of the lowest quartile. They are shown
separately and left out of the picks, because a ridiculously cheap listing (for
example a hoodie at 2 000 ₸ when the market starts near 3 000 ₸) would otherwise
distort the budget tier.

Then it splits the offers by price: **budget = lowest 40%**, **mid = next 40%**,
**premium = top 20%**. Offers with the same price stay in one band, so a cluster
of identical prices cannot appear in both mid and premium. Mid and premium prefer
the upper half of their band, so the pick is not the cheapest item that barely
qualifies. Each band is ranked by one
score:

- rating: up to 45 points (`rating / 5 * 45`)
- review confidence: up to 30 points (log scale, relative to the strongest offer in the band)
- price position: up to 25 points (upper half of the band scores higher)

Report the three picks returned in `recommendations.options`, in this order:

1. **Best budget option** — affordable, but with a good rating and real review evidence.
2. **Best mid-range option** — best balance of price, rating and review volume.
3. **Best premium option** — from the top 20% by price; price position, quality and review depth all count.

For each one give: title and link, price ₸, rating, review count, the score and its
three parts, why it was selected, advantages, possible disadvantages, value for money
(rating points per 1 000 ₸). Then one short paragraph comparing the three and explaining
what the extra money buys.

Rules for the picks:

- No emoji in the report.
- Use exactly the products in `recommendations.options`; never swap in a different or cheaper product.
- The cheapest offer is not automatically the budget pick: the budget pick prefers the upper half of the lowest price band. A low rating or a thin review count lowers the score, and that must be visible in the comparison.
- Review text is collected only from visible public Kaspi product pages. Use the returned excerpts and theme counts; never invent review text, themes or frequencies. If review status is not ok, name the checked page and say what was unavailable.
- Seller, warranty and delivery conditions are not in the data: list them as unknown, not as disadvantages of a specific product.

## 5. Hard rules

- You must actually run `market_data_summary` before writing the report. Use its real output; never estimate, recall or invent prices, ratings, review counts or market statistics.
- If no `tool` message is present in the conversation, stop and say the tool was not executed — do not write numbers from memory.
- Never claim a live Kaspi search when the collected status says error. Report the route and reason from `statuses`.
- Match variants within Kaspi only on brand + model. `Redmi Buds 6` and `Redmi Buds 6 Play` are different products.
- Percentages and medians come from the tool output. Label every interpretation (demand, seasonality, why a price is higher) as a hypothesis.
- If a row title starts with `[SAMPLE]`, its numbers are fake demo values and must be labelled as such in the output.

## Three recommendations (required for every product search)

`TOOLS/recommend.py` does the ranking; you explain it. Never re-rank and never default to the cheapest offer.

How the code ranks (state this in one line in the report):
1. Offers without a price or a rating cannot be judged on quality and are listed as skipped.
2. Prices are split into three tiers (budget = lowest 40%, mid = next 40%, premium = top 20%).
3. Inside a tier the score mixes price position, rating and review volume:
   - budget weights: price position 0.25, rating 0.45, reviews 0.30
   - mid weights: price position 0.25, rating 0.45, reviews 0.30
   - premium weights: price position 0.35, rating 0.40, reviews 0.25
4. The highest score in each tier is the pick. The tool also returns `advantages`, `disadvantages`,
   `value_for_money`, `also_considered` and the tier price/rating statistics.

For each of the three options the report must show: name and link, price, rating, review count,
why it won, main advantages, possible disadvantages, value for money, and who it suits.

Customer feedback: read the collected review-text output. For each product state how many
reviews were analysed vs available, positive/negative counts, the most frequent themes with
counts and shares, and short real examples. A review can mention several themes. Say that this
is a visible sample, not all reviews. Never infer a theme from a rating alone.

## Research brief (UI)

`TOOLS/insights.py` builds the evidence-labelled brief from the same rows: readiness checks,
executive summary, market overview, competitor/price evidence, collected review evidence,
opportunities as hypotheses, risks, next checks and a Markdown export. Keep these rules:
- A readiness check must show the real count, not a score out of 100.
- SWOT/PESTEL/BCG are not generated without the data they need (costs, demand, market size, full review coverage).
- The brief never claims demand or profit; it says those fields were not collected.
- If Kaspi returns nothing, name the error and do not build a report from invented rows.

If `status` is `insufficient_data`, do not produce three picks: say how many offers were usable and what is missing.
