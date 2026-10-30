from TOOLS import insights, market_data, recommend, reviews


PAGE = {
    "status": "ok",
    "total_reviews": 120,
    "reviews": [
        {"rating": 5, "date": "01.01.2026", "text": "Красивый оттенок, не липнет, удобно с собой носить."},
        {"rating": 5, "date": "02.01.2026", "text": "Очень красивый цвет и приятный запах."},
        {"rating": 5, "date": "03.01.2026", "text": "Понравилось, качество хорошее за эту цену."},
        {"rating": 5, "date": "04.01.2026", "text": "Быстрая доставка, упаковка целая."},
        {"rating": 5, "date": "05.01.2026", "text": "Лёгкая текстура, не скатывается."},
        {"rating": 5, "date": "06.01.2026", "text": "Красивый блеск, советую."},
        {"rating": 5, "date": "07.01.2026", "text": "Приятный аромат, губы мягкие."},
        {"rating": 5, "date": "08.01.2026", "text": "Хорошая цена, буду брать ещё."},
        {"rating": 5, "date": "09.01.2026", "text": "Оттенок красивый, доставка быстрая."},
        {"rating": 5, "date": "10.01.2026", "text": "Компактный, удобно носить."},
        {"rating": 2, "date": "11.01.2026", "text": "Очень липкий, как варенье, цвет некрасивый."},
        {"rating": 1, "date": "12.01.2026", "text": "Ужасное качество, упаковка была повреждена, доставка задержалась."},
        {"rating": 1, "date": "13.01.2026", "text": "Сушит губы и неприятный запах."},
    ],
}


def test_review_analysis_counts_real_text_only():
    result = reviews.analyse_page({"title": "Test gloss", "url": "https://kaspi.kz/shop/p/x-1/"}, PAGE)
    assert result["status"] == "ok"
    assert result["analysed"] == 13
    assert result["positive"] == 10
    assert result["negative"] == 3
    assert result["themes_positive"][0]["count"] >= 2
    assert result["themes_negative"]
    assert all(t["examples"] for t in result["themes_negative"])
    assert result["confidence"] == "medium"


def test_negative_themes_are_not_counted_in_positive_reviews():
    result = reviews.analyse_page({"title": "Test", "url": "https://kaspi.kz/shop/p/x-1/"}, PAGE)
    names = [t["theme"] for t in result["themes_negative"]]
    assert "Sticky or heavy texture" in names
    assert "Packaging damage" in names
    assert "Delivery problems" in names
    assert "Lip irritation or dryness" in names


def test_no_review_access_is_reported_not_invented():
    result = reviews.analyse_page(
        {"title": "Blocked", "url": "https://kaspi.kz/shop/p/x-1/"},
        {"status": "blocked", "reason": "HTTP 403", "total_reviews": 50},
    )
    assert result["status"] == "blocked"
    assert result["analysed"] == 0
    assert result["reason"] == "HTTP 403"


def test_pick_evidence_contains_frequencies_and_confidence():
    rows = [
        {"marketplace": "kaspi", "title": f"Gloss {i}", "price_kzt": 1000 + i * 500,
         "rating": 4.7, "reviews_count": 100 + i, "url": f"https://kaspi.kz/shop/p/x-{i}/"}
        for i in range(6)
    ]
    picks = recommend.recommend(rows)
    analysis = reviews.analyse_page(
        {"title": picks["picks"][0]["title"], "url": picks["picks"][0]["url"]}, PAGE
    )
    data = {"status": "ok", "products": [analysis], "checked": [analysis["url"]]}
    reviews.attach_to_picks(picks, data)
    pick = picks["picks"][0]
    assert pick["review_evidence"]["review_analysed"] == 13
    assert any("/13," in item for item in pick["review_advantages"])
    assert "confidence" in pick["quality_evidence"]
    assert pick["recommendation_reason"]
    assert "10 of 13 visible reviews are positive" in pick["summary"]


def test_report_with_reviews_has_evidence_and_comparison():
    rows = [
        {"marketplace": "kaspi", "title": f"Gloss {i}", "price_kzt": 1000 + i * 500,
         "rating": 4.7, "reviews_count": 100 + i, "url": f"https://kaspi.kz/shop/p/x-{i}/"}
        for i in range(6)
    ]
    facts = market_data.summarise(rows)
    picks = recommend.recommend(rows)
    analysis = reviews.analyse_page(
        {"title": picks["picks"][0]["title"], "url": picks["picks"][0]["url"]}, PAGE
    )
    data = {"status": "ok", "products": [analysis], "checked": [analysis["url"]],
            "reviews_analysed": 13, "reviews_available": 120}
    reviews.attach_to_picks(picks, data)
    statuses = {"kaspi": {"status": "ok"}}
    coverage = {"kaspi": 6}
    report = insights.build(rows, facts, picks, statuses, coverage, "gloss", review_data=data)
    assert report["readiness"]["total"] == 6
    assert report["readiness"]["checks"][-1]["passed"] is True
    assert any("13 visible reviews" in item for item in report["reviews"])
    assert report["comparison"][0]["confidence"]
    assert "## Final comparison" in report["markdown"]


def _brand_rows():
    return [
        {"marketplace": "kaspi", "title": f"PANDORA bracelet {590719 + i}",
         "price_kzt": 40000 + i * 5000, "rating": 4.9, "reviews_count": 100 + i,
         "url": f"https://kaspi.kz/shop/p/pandora-{i}/"}
        for i in range(6)
    ]


def _with_seller(picks, seller, rating=5.0, reviews=985):
    for pick in picks["picks"]:
        pick["seller"] = seller
        pick["seller_rating"] = rating
        pick["seller_reviews"] = reviews
    return picks


def test_original_gate_keeps_only_brand_seller_picks():
    picks = recommend.recommend(_brand_rows(), "Pandora")
    _with_seller(picks, "Pandora")
    result = reviews.apply_original_gate(picks)
    assert result["status"] == "ok"
    assert len(result["picks"]) == 3
    assert all(p["originality"]["likely_original"] for p in result["picks"])
    assert all("does not provide an authenticity guarantee" in p["authenticity"] for p in result["picks"])


def test_original_gate_removes_seller_that_does_not_match_brand():
    picks = recommend.recommend(_brand_rows(), "Pandora")
    _with_seller(picks, "Gold Shop")
    result = reviews.apply_original_gate(picks)
    assert result["status"] == "no_likely_original"
    assert result["picks"] == []
    assert "seller name did not match" in result["reason"]


def test_original_gate_skips_query_without_exact_brand():
    picks = recommend.recommend(_brand_rows())
    result = reviews.apply_original_gate(picks)
    assert result["status"] == "ok"
    assert len(result["picks"]) == 3
    assert result["originality"]["status"] == "not_applicable"
