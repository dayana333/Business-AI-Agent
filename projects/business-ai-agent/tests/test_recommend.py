from TOOLS import recommend


def make(price, rating, reviews, title="item"):
    return {
        "marketplace": "kaspi", "product_id": str(price), "title": title,
        "price_kzt": price, "rating": rating, "reviews_count": reviews,
        "url": "https://kaspi.kz/shop/p/x-1/",
    }


ROWS = [
    make(100, 3.0, 5, "cheap weak"),
    make(200, 4.2, 20, "cheap ok"),
    make(300, 4.9, 1000, "budget winner"),
    make(400, 4.6, 300, "mid low"),
    make(500, 4.8, 900, "mid winner"),
    make(600, 4.7, 400, "mid high"),
    make(700, 4.9, 2000, "premium a"),
    make(800, 4.8, 100, "premium b"),
    make(900, 4.7, 3000, "premium c"),
]


def test_three_tiers_and_three_picks():
    result = recommend.recommend(ROWS)
    assert result["status"] == "ok"
    assert [p["tier"] for p in result["picks"]] == ["budget", "mid", "premium"]
    assert result["tiers"]["budget"]["offers"] == 3
    assert result["offers_meeting_quality"] == 7


def test_cheapest_is_not_automatic_winner():
    result = recommend.recommend(ROWS)
    budget = result["picks"][0]
    assert budget["price_kzt"] != 100
    assert budget["rating"] >= 4.5


def test_premium_pick_comes_from_top_price_band():
    result = recommend.recommend(ROWS)
    premium = result["picks"][2]
    assert premium["price_kzt"] >= 800
    assert result["tiers"]["premium"]["offers"] == 1


def test_picks_have_reasons_and_value_label():
    for pick in recommend.recommend(ROWS)["picks"]:
        assert pick["advantages"] and pick["disadvantages"]
        assert pick["value_for_money"] in {"high", "good", "moderate"}
        assert pick["url"].startswith("https://")


def test_insufficient_data_is_reported_not_invented():
    result = recommend.recommend(ROWS[:2])
    assert result["status"] == "insufficient_data"
    assert result["picks"] == []
    assert "at least 3" in result["reason"]


def test_offers_without_rating_are_skipped():
    rows = ROWS + [make(150, "", 0, "no rating")]
    result = recommend.recommend(rows)
    assert result["offers_used"] == 8
    assert "no rating" in result["skipped_without_rating"]


def test_quality_floor_is_reported_and_respected():
    result = recommend.recommend(ROWS)
    for tier in ("budget", "mid", "premium"):
        assert "quality_gate" in result["tiers"][tier]
        assert result["tiers"][tier]["quality_gate"].startswith("quality floor")
    for pick in result["picks"]:
        assert pick["rating"] >= recommend.MIN_RATING
        assert pick["reviews_count"] >= recommend.MIN_REVIEWS
    assert result["quality_floor"]["min_rating"] == 4.5
    assert result["quality_floor"]["min_reviews"] == 10


def test_budget_pick_is_not_the_cheapest_offer():
    rows = [
        make(100, 4.9, 10, "cheapest but thin"),
        make(200, 4.2, 500, "cheap but weak rating"),
        make(300, 4.9, 60, "first passing"),
        make(500, 4.8, 900, "second passing"),
        make(800, 4.8, 100, "premium passing"),
    ]
    result = recommend.recommend(rows)
    assert result["status"] == "ok"
    assert result["picks"][0]["price_kzt"] == 300
    assert "not the cheapest" in result["note"]
    assert all(p["rating"] >= 4.7 and p["reviews_count"] >= 50 for p in result["picks"])


def test_insufficient_quality_is_reported_not_invented():
    rows = [
        make(150, 4.9, 5, "thin evidence"),
        make(200, 4.2, 500, "weak rating"),
        make(300, 4.9, 60, "only passing"),
        make(500, 4.8, 900, "second passing"),
    ]
    result = recommend.recommend(rows)
    assert result["status"] == "insufficient_quality"
    assert result["picks"] == []
    assert "quality floor" in result["reason"]
    assert "2 weak offer(s)" in result["reason"]


def test_note_explains_why_cheapest_was_rejected():
    assert "not the cheapest" in recommend.recommend(ROWS)["note"]


def make_query(price, rating, reviews, title, product_id=None):
    row = make(price, rating, reviews, title)
    if product_id is not None:
        row["product_id"] = str(product_id)
    return row


def test_exact_brand_filters_out_similar_spelling():
    rows = [
        make_query(2900, 4.9, 50, "SILVA Jewelry bracelet", 1),
        make_query(55000, 4.9, 60, "ARU jewerllery PNDRA bracelet", 2),
        make_query(42000, 4.9, 120, "PANDORA bracelet 590719", 3),
        make_query(45000, 4.8, 90, "PANDORA bracelet 590041", 4),
        make_query(50000, 4.9, 130, "PANDORA bracelet 592453", 5),
    ]
    result = recommend.recommend(rows, "Pandora jewellery")
    assert result["status"] == "ok"
    assert result["filtered_out"] == 2
    assert all("PANDORA" in p["title"] for p in result["picks"])
    assert all(p["brand_match"] == "exact title match" for p in result["picks"])


def test_brand_query_with_no_exact_match_is_explained():
    rows = [
        make_query(2900, 4.9, 50, "SILVA Jewelry bracelet", 1),
        make_query(55000, 0, 0, "ARU jewerllery PNDRA bracelet", 2),
        make_query(65000, 0, 0, "ARU jewerllery PNDRA necklace", 3),
    ]
    result = recommend.recommend(rows, "Pandora jewellery")
    assert result["status"] == "no_relevant"
    assert result["picks"] == []
    assert "exact brand" in result["reason"]
    assert result["filtered_examples"]


def test_anomaly_price_is_named_not_picked():
    rows = [
        make_query(500, 4.9, 100, "PANDORA браслет 1", 1),
        make_query(40000, 4.9, 100, "PANDORA браслет 2", 2),
        make_query(45000, 4.8, 80, "PANDORA браслет 3", 3),
        make_query(50000, 4.9, 200, "PANDORA браслет 4", 4),
        make_query(55000, 4.7, 60, "PANDORA браслет 5", 5),
    ]
    result = recommend.recommend(rows, "Pandora браслет")
    assert result["status"] == "ok"
    assert result["anomaly_prices"][0]["price_kzt"] == 500
    assert result["anomaly_prices"][0]["reason"].startswith("Anomaly price:")
    assert all(p["price_kzt"] != 500 for p in result["picks"])
    assert len(result["relevant_rows"]) == 4


def test_generic_category_query_is_not_over_filtered():
    rows = [
        make_query(1000, 4.8, 100, "Наушники беспроводные A", 1),
        make_query(1100, 4.8, 100, "Наушники беспроводные B", 2),
        make_query(1200, 4.8, 100, "Наушники беспроводные C", 3),
    ]
    result = recommend.recommend(rows, "wireless earbuds")
    assert result["status"] == "ok"
    assert result["filtered_out"] == 0


def test_premium_can_be_the_highest_price_when_quality_is_best():
    rows = [
        make(100, 3.0, 5, "cheap weak"),
        make(200, 4.2, 20, "cheap ok"),
        make(300, 4.9, 1000, "budget winner"),
        make(400, 4.6, 300, "mid low"),
        make(500, 4.8, 900, "mid winner"),
        make(600, 4.7, 400, "mid high"),
        make(700, 4.9, 2000, "premium a"),
        make(800, 4.8, 100, "premium b"),
        make(900, 5.0, 5000, "premium flagship"),
    ]
    premium = recommend.recommend(rows)["picks"][2]
    assert premium["price_kzt"] == 900
    assert premium["rating"] == 5.0
    assert premium["reviews_count"] == 5000


def test_premium_uses_top_band_but_rejects_weak_evidence():
    rows = [
        make(100, 3.0, 5, "cheap weak"),
        make(200, 4.2, 20, "cheap ok"),
        make(300, 4.9, 1000, "budget winner"),
        make(400, 4.6, 300, "mid low"),
        make(500, 4.8, 900, "mid winner"),
        make(600, 4.7, 400, "mid high"),
        make(700, 4.9, 2000, "premium a"),
        make(800, 4.8, 100, "premium b"),
        make(900, 4.75, 5, "expensive weak evidence"),
    ]
    result = recommend.recommend(rows)
    premium = result["picks"][2]
    assert premium["price_kzt"] == 800
    assert premium["price_kzt"] >= result["tiers"]["premium"]["price_min"]
    assert premium["price_kzt"] < 900
    assert premium["reviews_count"] > 20


def test_premium_never_comes_from_below_the_top_band():
    result = recommend.recommend(ROWS)
    premium = result["picks"][2]
    tier = result["tiers"]["premium"]
    assert tier["price_min"] <= premium["price_kzt"] <= tier["price_max"]
    assert premium["price_kzt"] >= tier["price_min"]


def test_each_tier_is_a_different_product():
    rows = [
        make(100, 4.9, 100, "Same clip 1 шт"),
        make(150, 4.9, 100, "Same clip 1 шт"),
        make(200, 4.8, 100, "Other clip 1 шт"),
        make(300, 4.8, 100, "Third clip 1 шт"),
        make(500, 4.8, 100, "Premium clip 1 шт"),
    ]
    result = recommend.recommend(rows)
    assert result["status"] == "ok"
    titles = [p["title"] for p in result["picks"]]
    assert len(titles) == len(set(titles)) == 3
    assert result["picks"][0]["title"] == "Same clip 1 шт"
    assert result["picks"][2]["title"] == "Premium clip 1 шт"


def test_duplicate_titles_are_not_used_to_fill_three_cards():
    rows = [make(price, 4.9, 100, "Only one clip") for price in (100, 150, 200, 300)]
    result = recommend.recommend(rows)
    assert result["status"] == "insufficient_distinct"
    assert result["picks"] == []
    assert "different products" in result["reason"]


def test_more_options_never_repeat_the_three_chosen_products():
    rows = [
        make(100, 4.9, 100, "Clip A"), make(120, 4.9, 100, "Clip B"),
        make(150, 4.9, 100, "Clip C"), make(200, 4.8, 100, "Clip D"),
        make(250, 4.8, 100, "Clip E"), make(300, 4.8, 100, "Clip F"),
        make(500, 4.8, 100, "Clip G"), make(800, 4.8, 100, "Clip H"),
    ]
    result = recommend.recommend(rows)
    chosen = {p["title"] for p in result["picks"]}
    for pick in result["picks"]:
        assert len(pick["also_considered"]) <= 2
        for alt in pick["also_considered"]:
            assert alt["title"] not in chosen


def test_tiers_are_lowest_middle_and_highest_price_bands():
    rows = [make(1000 + i * 100, 4.8, 100, f"item {i}") for i in range(12)]
    result = recommend.recommend(rows)
    assert result["status"] == "ok"
    tiers = result["tiers"]
    assert [tiers[t]["offers"] for t in ("budget", "mid", "premium")] == [5, 5, 2]
    assert tiers["budget"]["price_max"] < tiers["mid"]["price_min"]
    assert tiers["mid"]["price_max"] < tiers["premium"]["price_min"]
    assert tiers["budget"]["price_min"] == 1000
    assert tiers["premium"]["price_max"] == 2100


def test_all_tiers_prefer_higher_prices_within_their_band():
    rows = [make(1000 + i * 100, 4.8, 100, f"item {i}") for i in range(12)]
    picks = recommend.recommend(rows)["picks"]
    assert picks[0]["price_kzt"] == 1400
    assert picks[1]["price_kzt"] == 1900
    assert picks[2]["price_kzt"] == 2100


def test_anomaly_detection_works_for_any_category():
    rows = [
        make(2000, 4.8, 100, "Hoodie basic black"),
        make(9000, 4.8, 100, "Hoodie basic grey"),
        make(10000, 4.9, 200, "Hoodie oversize black"),
        make(12000, 4.7, 100, "Hoodie premium cotton"),
        make(15000, 4.8, 100, "Hoodie heavyweight"),
    ]
    result = recommend.recommend(rows, "hoodie")
    assert result["anomaly_prices"][0]["title"] == "Hoodie basic black"
    assert result["anomaly_prices"][0]["price_kzt"] == 2000
    assert all(p["price_kzt"] != 2000 for p in result["picks"])


def test_anomaly_detects_price_below_the_budget_level():
    rows = [
        make(2000, 4.8, 100, "Hoodie print black"),
        make(3499, 4.8, 100, "Hoodie basic black"),
        make(3505, 4.9, 100, "Hoodie basic grey"),
        make(3778, 4.7, 100, "Hoodie oversize grey"),
        make(3999, 4.8, 100, "Hoodie mid black"),
        make(4990, 4.9, 200, "Hoodie premium black"),
        make(6264, 4.8, 100, "Hoodie heavy black"),
    ]
    result = recommend.recommend(rows, "hoodie")
    assert result["anomaly_prices"][0]["price_kzt"] == 2000
    assert "Anomaly price:" in result["anomaly_prices"][0]["reason"]

def test_equal_prices_are_not_split_between_bands():
    prices = [2998, 3499, 3505, 3999] + [4990] * 5 + [6264]
    rows = [make(price, 4.8, 100, f"hoodie {i}") for i, price in enumerate(prices)]
    result = recommend.recommend(rows)
    tiers = result["tiers"]
    assert [tiers[t]["offers"] for t in ("budget", "mid", "premium")] == [4, 5, 1]
    assert tiers["budget"]["price_max"] < tiers["mid"]["price_min"]
    assert tiers["mid"]["price_max"] < tiers["premium"]["price_min"]
    assert tiers["mid"]["price_median"] == 4990
    assert tiers["premium"]["price_min"] == 6264
