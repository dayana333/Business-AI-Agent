"""Deterministic, evidence-labelled research brief built from collected offers.

No model, no market-size guesses, no review text. Every sentence is derived from
the rows or explicitly marked as unavailable.
"""

import datetime as dt
import statistics
from collections import Counter

from TOOLS import normalize

MARKET_NAMES = ("kaspi",)
ROUTE_LABEL = {
    "ok": "live search",
    "error": "error",
}


def _num(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _money(value):
    return f"{round(value):,}".replace(",", " ") + " ₸"


def _pct(value):
    return f"{value:.1f}%"


def _pct_change(a, b):
    return (a - b) / b * 100 if b else 0.0


def _percentile(values, p):
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * p
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def _quartiles(prices):
    return {
        "q1": round(_percentile(prices, 0.25)),
        "median": round(_percentile(prices, 0.5)),
        "q3": round(_percentile(prices, 0.75)),
    }


def _outliers(rows, q1, q3):
    spread = q3 - q1
    low, high = q1 - 1.5 * spread, q3 + 1.5 * spread
    return [r for r in rows if r["price_kzt"] < low or r["price_kzt"] > high]


def _readiness(coverage, rows, groups, review_data=None):
    rated = [r for r in rows if _num(r.get("rating")) is not None]
    deep = [r for r in rated if (_num(r.get("reviews_count")) or 0) >= 20]
    checks = [
        {
            "label": "Kaspi search returned offers",
            "passed": coverage.get("kaspi", 0) > 0,
            "detail": f"{coverage.get('kaspi', 0)} offers from Kaspi",
        },
        {
            "label": "At least 10 offers",
            "passed": len(rows) >= 10,
            "detail": f"{len(rows)} offers collected",
        },
        {
            "label": "Ratings on at least 70% of offers",
            "passed": bool(rows) and len(rated) / len(rows) >= 0.7,
            "detail": f"{len(rated)} of {len(rows)} offers have a rating",
        },
        {
            "label": "At least 3 distinct base products",
            "passed": len(groups) >= 3,
            "detail": f"{len(groups)} base product(s) after variant grouping",
        },
        {
            "label": "20+ reviews on at least half of rated offers",
            "passed": bool(rated) and len(deep) / len(rated) >= 0.5,
            "detail": f"{len(deep)} of {len(rated)} rated offers have 20+ reviews",
        },
    ]
    if review_data is not None:
        readable = review_data.get("status") == "ok" and (review_data.get("reviews_analysed") or 0) > 0
        checks.append({
            "label": "Review text from product pages",
            "passed": readable,
            "detail": (
                f"{review_data.get('reviews_analysed', 0)} reviews read from "
                f"{len([p for p in review_data.get('products', []) if p.get('status') == 'ok'])} product page(s)"
                if readable else (review_data.get("reason") or "No review text was visible")
            ),
        })
    total = len(checks)
    passed = sum(1 for c in checks if c["passed"])
    if passed == total:
        level, label = "strong", "Strong enough for a first screening"
    elif passed >= max(3, total - 2):
        level, label = "partial", "Partial — usable for a price screen only"
    else:
        level, label = "weak", "Weak — collect more data before deciding"
    return {"passed": passed, "total": total, "level": level, "label": label, "checks": checks}


def _source_lines(statuses, coverage):
    lines = []
    for name in MARKET_NAMES:
        status = statuses.get(name, {}) or {}
        count = coverage.get(name, 0)
        route = ROUTE_LABEL.get(status.get("status"), status.get("status") or "unknown")
        line = f"{name.capitalize()}: {count} offers · {route}"
        if status.get("captured_at"):
            line += f" · captured {status['captured_at']}"
        if status.get("reason"):
            line += f" · {status['reason']}"
        lines.append(line)
    return lines


def _market_mix(rows):
    counts = Counter(r.get("marketplace", "unknown") for r in rows)
    total = len(rows) or 1
    parts = []
    for name, count in counts.most_common():
        parts.append(f"{name.capitalize()} {count} ({count / total * 100:.0f}%)")
    return parts


def _segment_lines(picks):
    if not picks or picks.get("status") != "ok":
        return []
    lines = []
    for tier in ("budget", "mid", "premium"):
        data = picks["tiers"][tier]
        lines.append(
            f"{tier.capitalize()}: {data['offers']} offers, "
            f"{_money(data['price_min'])}–{_money(data['price_max'])}, "
            f"median {_money(data['price_median'])}, median rating {data['rating_median']}"
        )
    return lines


def _md_cell(text):
    return str(text or "").replace("|", "/").replace("\n", " ").strip()


def _theme_names(themes, analysed, limit=3):
    total = analysed or 1
    return ", ".join(
        f"{t['theme']} ({t['count']}/{total}, {t['share_pct']}%)"
        for t in (themes or [])[:limit]
    )


def _review_section(review_data, statuses):
    """Explain what review text was checked and what it actually says."""
    if review_data is None:
        return [
            "Only ratings and review counts are available: review text was not collected.",
            "Review text and customer sentiment were not collected, so complaints, quality issues and use cases cannot be analysed.",
        ]
    if review_data.get("status") != "ok":
        checked = review_data.get("checked") or []
        reason = review_data.get("reason") or "No review text was visible."
        lines = [f"Checked {len(checked)} Kaspi product page(s): {reason}"]
        for url in checked:
            lines.append(f"Checked page: {url}")
        return lines

    products = [p for p in review_data.get("products", []) if p.get("status") == "ok"]
    total_available = sum((p.get("total_reviews") or 0) for p in products)
    total_text = f"{round(total_available):,}".replace(",", " ")
    lines = [
        f"Read {review_data.get('reviews_analysed', 0)} visible reviews from {len(products)} Kaspi product page(s); "
        f"those pages show {total_text} reviews in total. This is a sample, not a full census.",
    ]
    for product in products:
        pos = _theme_names(product.get("themes_positive"), product.get("analysed"), 3) or "no repeated positive theme in this sample"
        neg = _theme_names(product.get("themes_negative"), product.get("analysed"), 3) or "no repeated complaint in this sample"
        lines.append(
            f"{product.get('title', '')[:70]} — {product.get('analysed', 0)} of "
            f"{product.get('total_reviews') or '?'} visible reviews read; "
            f"{product.get('negative', 0)} negative (1–3★), {product.get('positive', 0)} positive (4–5★); "
            f"most liked: {pos}; most complained about: {neg}; confidence {product.get('confidence', 'low')}."
        )
        for theme in (product.get("themes_negative") or [])[:1]:
            for example in theme.get("examples", [])[:1]:
                lines.append(
                    f"Example ({example['rating']:g}★, {example.get('date') or 'date unknown'}, "
                    f"{theme['theme']}): “{example['text']}”"
                )
        for theme in (product.get("themes_positive") or [])[:1]:
            for example in theme.get("examples", [])[:1]:
                lines.append(
                    f"Example ({example['rating']:g}★, {example.get('date') or 'date unknown'}, "
                    f"{theme['theme']}): “{example['text']}”"
                )
    if (statuses.get("kaspi") or {}).get("status") != "ok":
        lines.append(
            "No review text was readable from Kaspi for this query (public access was blocked or returned no usable page); "
            "its ratings are not treated as review-text evidence."
        )
    lines.append(
        "Frequencies are keyword counts within positive and negative reviews; a review can mention more than one theme. "
        "They describe this visible sample, not all reviews."
    )
    return lines


def _review_evidence(review_data):
    if not review_data:
        return {"status": "not_checked"}
    return {
        "status": review_data.get("status"),
        "reviews_analysed": review_data.get("reviews_analysed", 0),
        "reviews_available": review_data.get("reviews_available", 0),
        "checked_pages": review_data.get("checked", []),
        "products": [
            {
                "title": p.get("title", ""),
                "url": p.get("url", ""),
                "analysed": p.get("analysed", 0),
                "total_reviews": p.get("total_reviews"),
                "negative": p.get("negative", 0),
                "positive": p.get("positive", 0),
                "themes_positive": [t["theme"] for t in p.get("themes_positive", [])[:5]],
                "themes_negative": [t["theme"] for t in p.get("themes_negative", [])[:5]],
                "confidence": p.get("confidence", "none"),
            }
            for p in review_data.get("products", [])
        ],
    }


def _comparison_rows(picks):
    if not picks or picks.get("status") != "ok":
        return []
    rows = []
    for pick in picks.get("picks", []):
        ev = pick.get("review_evidence") or {}
        advantages = pick.get("advantages", []) + [
            f"reviews: {name}" for name in ev.get("positive_themes", [])[:2]
        ]
        complaints = ev.get("negative_themes", [])
        rows.append({
            "product": pick.get("title", ""),
            "price": _money(pick.get("price_kzt")),
            "rating": f"{pick.get('rating')} ({int(pick.get('reviews_count') or 0)} reviews)",
            "advantages": "; ".join(advantages[:4]),
            "complaints": "; ".join(complaints[:3]) or "none repeated in the visible sample",
            "quality_evidence": pick.get("quality_evidence", ""),
            "reason": pick.get("recommendation_reason", ""),
            "confidence": pick.get("confidence", "none"),
        })
    return rows


def build(rows, facts, picks, statuses, coverage, query, review_data=None):
    """Return the report payload used by the UI and the Markdown export."""
    if not rows:
        raise ValueError("No offers to report")
    prices = sorted(r["price_kzt"] for r in rows if r.get("price_kzt"))
    rated = [r for r in rows if _num(r.get("rating")) is not None]
    ratings = [_num(r["rating"]) for r in rated]
    deep = [r for r in rated if (r.get("reviews_count") or 0) >= 20]
    q = _quartiles(prices)
    spread_pct = _pct_change(prices[-1], prices[0])
    outliers = _outliers(rows, q["q1"], q["q3"])
    groups = normalize.group_variants(rows)
    readiness = _readiness(coverage, rows, groups, review_data)

    top_rated = sorted(
        rated, key=lambda r: (_num(r["rating"]), _num(r.get("reviews_count")) or 0), reverse=True
    )[:3]
    cheapest = sorted(rows, key=lambda r: r["price_kzt"])[:3]

    summary = [
        f"Observed {len(rows)} Kaspi offers for “{query}”. "
        f"Prices range from {_money(prices[0])} to {_money(prices[-1])} "
        f"(median {_money(q['median'])}, spread {_pct(spread_pct)}).",
    ]
    if rated:
        top_share = sum(1 for r in ratings if r >= 4.5) / len(ratings) * 100
        summary.append(
            f"Ratings exist for {len(rated)} of {len(rows)} offers; median {statistics.median(ratings):.2f}, "
            f"and {_pct(top_share)} of rated offers are 4.5 or higher. "
            f"Only {len(deep)} of {len(rated)} rated offers have 20+ reviews."
        )
    else:
        summary.append("No ratings were returned, so quality cannot be compared.")
    summary.append(
        f"Decision readiness: {readiness['label']} ({readiness['passed']} of {readiness['total']} evidence checks passed). "
        "Demand, sales and profit cannot be judged from these fields."
    )

    market = [
        "Marketplace mix: " + "; ".join(_market_mix(rows)) + ".",
        f"Prices: Q1 {_money(q['q1'])}, median {_money(q['median'])}, Q3 {_money(q['q3'])}. "
        f"Interquartile range {_money(q['q3'] - q['q1'])}.",
        f"Offers group into {len(groups)} base product(s) after variant matching within Kaspi.",
    ]
    segment_lines = _segment_lines(picks)
    if segment_lines:
        market.extend(segment_lines)

    competition = [
        "Cheapest offers: " + "; ".join(
            f"{r['title'][:60]} ({r['marketplace']}, {_money(r['price_kzt'])})" for r in cheapest
        ) + ".",
    ]
    if top_rated:
        competition.append(
            "Highest-rated offers: " + "; ".join(
                f"{r['title'][:60]} ({_num(r['rating'])}, {_num(r.get('reviews_count')) or 0} reviews)"
                for r in top_rated
            ) + "."
        )
    if outliers:
        competition.append(
            f"{len(outliers)} price outlier(s) outside 1.5×IQR: " + "; ".join(
                f"{r['title'][:50]} ({_money(r['price_kzt'])})" for r in outliers[:4]
            ) + ("; …" if len(outliers) > 4 else "") + "."
        )
    else:
        competition.append("No price outliers outside 1.5×IQR.")
    competition.append("This compares listings, not businesses: seller costs, delivery terms and sales are unknown.")

    review_total = f"{round(sum((r.get('reviews_count') or 0) for r in rated)):,}".replace(",", " ")
    if review_data is None:
        reviews = [
            f"Only ratings and review counts are available: {len(rated)} rated offers, "
            f"{review_total} reviews in total.",
            "Review text and customer sentiment were not collected, so complaints, quality issues and use cases cannot be analysed.",
            f"{sum(1 for r in rated if (r.get('reviews_count') or 0) < 20)} rated offer(s) have fewer than 20 reviews — treat their ratings as weak evidence.",
        ]
    else:
        reviews = _review_section(review_data, statuses)

    opportunities = []
    opportunities.append(
        "Compare variants of the same base product: price gaps between configurations can show where a cheaper version is a real alternative."
    )
    if picks and picks.get("status") == "ok":
        budget = picks["tiers"]["budget"]["price_median"]
        premium = picks["tiers"]["premium"]["price_median"]
        if budget:
            opportunities.append(
                f"Observed price ladder: premium median is {premium / budget:.1f}× the budget median "
                f"({_money(premium)} vs {_money(budget)}). A mid-price position is visible, but demand support is unproven."
            )
    if rated and len(deep) < len(rated) / 2:
        opportunities.append(
            "Review depth is thin on many offers. If you can collect verified reviews, review depth may become a differentiator; this is a hypothesis, not a proven demand signal."
        )
    if not opportunities:
        opportunities.append("No data-backed opportunity can be stated from this sample yet.")

    risks = [
        "The sample is a search-page snapshot, not the full market.",
        (
            "SWOT is not generated: it still needs costs, demand and market-size evidence; review text is only a visible sample."
            if review_data and review_data.get("status") == "ok"
            else "SWOT is not generated: it needs costs, demand and review evidence that this dataset does not contain."
        ),
        "Prices are asking prices; they may include promotions and exclude delivery or customs.",
        "No sales, demand, market size or growth data were collected.",
        "No seller costs, commissions or tax data, so margin and break-even are not estimated.",
        "Variant matching uses title normalisation within Kaspi; confirm that matched offers are the same configuration.",
        "A search page can mix accessories, bundles and different configurations; check each listing before using the minimum or maximum price.",
    ]
    next_steps = [
        "Re-run the same Kaspi query and compare snapshots to see whether prices are stable or promotional.",
        "Open the top picks and verify the exact configuration, delivery, returns and warranty.",
        "Re-run in 7 days to see whether prices are stable or promotional.",
        "Check delivery, commission and packaging costs yourself before setting a price; this report does not estimate profit.",
    ]
    if review_data and review_data.get("status") == "ok":
        next_steps.insert(1, "Read more review pages for the top picks to raise the sample above the current visible slice.")

    sources = _source_lines(statuses, coverage)
    evidence = {
        "query": query,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "offers": len(rows),
        "base_products": len(groups),
        "marketplaces": {n: coverage.get(n, 0) for n in MARKET_NAMES},
        "sources": sources,
        "review_analysis": _review_evidence(review_data),
    }
    if review_data is not None:
        evidence["sources"].append(
            "Review text: Kaspi product pages — "
            f"{review_data.get('reviews_analysed', 0)} reviews read"
            + (f" · {review_data.get('reason')}" if review_data.get("status") != "ok" else "")
        )

    report = {
        "readiness": readiness,
        "summary": summary,
        "market": market,
        "competition": competition,
        "reviews": reviews,
        "opportunities": opportunities,
        "risks": risks,
        "next_steps": next_steps,
        "evidence": evidence,
        "price": {**q, "min": round(prices[0]), "max": round(prices[-1]), "spread_pct": round(spread_pct, 1)},
        "comparison": _comparison_rows(picks),
    }
    report["markdown"] = to_markdown(report)
    return report


def to_markdown(report):
    evidence = report["evidence"]
    lines = [
        f"# Market research brief: {evidence['query']}",
        "",
        f"Generated: {evidence['generated_at']}  ",
        f"Offers: {evidence['offers']} · base products: {evidence['base_products']}  ",
        "Marketplaces: " + ", ".join(
            f"{name} {count}" for name, count in evidence["marketplaces"].items()
        ),
        "",
        f"## Decision readiness — {report['readiness']['label']}",
        f"{report['readiness']['passed']} of {report['readiness']['total']} evidence checks passed.",
        "",
    ]
    for check in report["readiness"]["checks"]:
        lines.append(f"- [{'x' if check['passed'] else ' '}] {check['label']} — {check['detail']}")
    sections = [
        ("Executive summary", "summary"),
        ("Market overview", "market"),
        ("Competitor and price evidence", "competition"),
        ("Customer feedback evidence", "reviews"),
        ("Opportunities to test (hypotheses)", "opportunities"),
        ("Risks and limitations", "risks"),
        ("Next checks", "next_steps"),
    ]
    for title, key in sections:
        lines += ["", f"## {title}", ""]
        for item in report[key]:
            lines.append(f"- {item}")
    if report.get("comparison"):
        lines += ["", "## Final comparison", "",
                  "| Product | Price | Rating (reviews) | Advantages | Common complaints | Quality evidence | Recommendation reason | Confidence |",
                  "|---|---:|---|---|---|---|---|---|"]
        for item in report["comparison"]:
            lines.append(
                "| " + " | ".join(_md_cell(item[k]) for k in (
                    "product", "price", "rating", "advantages", "complaints",
                    "quality_evidence", "reason", "confidence",
                )) + " |"
            )
    lines += ["", "## Sources", ""]
    for item in evidence["sources"]:
        lines.append(f"- {item}")
    lines += ["", "Only collected fields are used. Missing data is marked, never invented.", ""]
    return "\n".join(lines)
