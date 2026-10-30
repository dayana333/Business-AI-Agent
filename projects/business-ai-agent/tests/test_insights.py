import pytest

from TOOLS import insights, market_data, recommend


def row(price, rating, reviews, brand="Soundcore", model="Q30", title=None):
    return {
        "marketplace": "kaspi",
        "product_id": f"kaspi-{model}-{price}",
        "brand": brand,
        "model": model,
        "title": title or f"{brand} {model} headphones",
        "price_kzt": price,
        "rating": rating,
        "reviews_count": reviews,
        "url": f"https://example.test/kaspi/{price}",
        "observed_at": "2026-10-27T10:00:00",
    }


ROWS = [
    row(20000, 4.4, 40),
    row(22000, 4.6, 300),
    row(24000, 4.5, 120),
    row(30000, 4.7, 500, model="Q35"),
    row(32000, 4.8, 800, model="Q35"),
    row(34000, 4.6, 150, model="Q35"),
    row(40000, 4.9, 900, model="Q45"),
    row(42000, 4.7, 90, model="Q45"),
    row(44000, 4.8, 250, model="Q45"),
    row(50000, 4.5, 20, model="Q55"),
    row(52000, 4.9, 1200, model="Q55"),
    row(55000, 4.3, 12, model="Q55"),
]


def payload(rows):
    facts = market_data.summarise(rows)
    picks = recommend.recommend(rows)
    coverage = {"kaspi": len([r for r in rows if r["marketplace"] == "kaspi"])}
    statuses = {"kaspi": {"status": "ok"}}
    return insights.build(rows, facts, picks, statuses, coverage, "headphones")


def test_full_sample_passes_all_checks_and_is_marked_strong():
    report = payload(ROWS)
    assert report["readiness"]["passed"] == 5
    assert report["readiness"]["level"] == "strong"
    assert report["price"]["min"] == 20000
    assert report["price"]["max"] == 55000


def test_summary_and_market_use_observed_numbers_only():
    report = payload(ROWS)
    text = " ".join(report["summary"] + report["market"])
    assert "12 Kaspi offers" in text
    assert "20 000 ₸" in text
    assert "55 000 ₸" in text
    assert "4 of 3" not in text


def test_products_are_grouped_within_kaspi():
    report = payload(ROWS)
    text = " ".join(report["market"])
    assert "4 base product(s)" in text


def test_reviews_section_marks_text_as_unavailable():
    report = payload(ROWS)
    text = " ".join(report["reviews"])
    assert "Review text" in text
    assert "not collected" in text


def test_swot_is_declined_instead_of_invented():
    report = payload(ROWS)
    assert any("SWOT is not generated" in item for item in report["risks"])


def test_markdown_has_sections_sources_and_disclaimer():
    report = payload(ROWS)
    md = report["markdown"]
    assert md.startswith("# Market research brief: headphones")
    assert "## Executive summary" in md
    assert "## Sources" in md
    assert "Kaspi: 12 offers" in md
    assert "Missing data is marked, never invented." in md


def test_one_thin_offer_sample_is_weak():
    report = payload([dict(ROWS[0], rating="", reviews_count="")])
    assert report["readiness"]["level"] == "weak"
    labels = [c["label"] for c in report["readiness"]["checks"]]
    assert "At least 10 offers" in labels
    assert "At least 3 distinct base products" in labels


def test_empty_input_is_rejected():
    with pytest.raises(ValueError):
        insights.build([], {}, {}, {}, {}, "x")


def test_empty_rating_strings_from_the_collector_are_not_numbers():
    rows = ROWS + [dict(ROWS[0], product_id="blank", rating="", reviews_count="")]
    facts = market_data.summarise(rows)
    assert facts["all_rows_by_marketplace"]["kaspi"]["mean_rating"] is not None
    report = payload(rows)
    assert report["readiness"]["passed"] >= 3
