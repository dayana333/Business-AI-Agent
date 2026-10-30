import json

from TOOLS import collect, kaspi_search, normalize


ROWS = [
    {"marketplace": "kaspi", "product_id": "1", "brand": "", "model": "",
     "title": "Наушники Xiaomi Edition Redmi Buds 7S черный", "price_kzt": 27900},
    {"marketplace": "kaspi", "product_id": "2", "brand": "", "model": "",
     "title": "Наушники Xiaomi Edition Redmi Buds 7S зеленый", "price_kzt": 29990},
    {"marketplace": "kaspi", "product_id": "2", "brand": "", "model": "",
     "title": "Наушники Xiaomi Edition Redmi Buds 7S зеленый", "price_kzt": 29990},
]


def test_variant_of_detects_colour_and_size():
    assert normalize.variant_of("Redmi Buds 7S черный")["color"] == "черный"
    assert normalize.variant_of("Redmi 13C 128 ГБ")["size"] == "128гб"
    assert normalize.variant_of("Redmi Buds 7S")["color"] == ""


def test_base_title_removes_variant_words():
    black = normalize.base_title("Наушники Xiaomi Edition Redmi Buds 7S черный")
    green = normalize.base_title("Наушники Xiaomi Edition Redmi Buds 7S зеленый")
    assert black == green == "xiaomi edition redmi buds 7s"


def test_canonical_key_prefers_brand_and_model():
    row = {"brand": "Xiaomi", "model": "Redmi Buds 6", "title": "anything"}
    assert normalize.canonical_key(row) == "xiaomi redmi buds 6"


def test_group_variants_groups_colours_of_one_product():
    groups = normalize.group_variants(ROWS)
    assert len(groups) == 1
    assert groups[0]["offers"] == 3
    assert sorted(groups[0]["variants"]) == ["зеленый", "черный"]


def test_dedupe_drops_same_marketplace_and_product_id():
    assert len(collect.dedupe(ROWS)) == 2


def test_availability_map():
    assert collect.availability("ok") == "available"
    assert collect.availability("reachable") == "partial"
    assert collect.availability("blocked") == "blocked"
    assert collect.availability("error") == "error"


def test_write_status_keeps_sources_and_timestamps(tmp_path):
    statuses = {
        "kaspi": {"status": "ok", "rows": 12, "route": "browser", "checked_at": "2026-10-26T10:00:00"},
    }
    path = collect.write_status(tmp_path / "status.json", "redmi buds", statuses, ROWS)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["rows_total"] == 3
    assert data["base_products"] == 1
    assert data["marketplaces"]["kaspi"]["availability"] == "available"
    assert data["marketplaces"]["kaspi"]["route"] == "browser"


def test_status_line_shows_state():
    line = collect.status_line("kaspi", {"status": "error", "reason": "Timeout"})
    assert "error" in line and "Timeout" in line


def test_kaspi_card_parsing_helpers():
    assert kaspi_search._price("29 990 ₸") == 29990
    assert kaspi_search._reviews("(11 отзывов)") == 11
    assert kaspi_search._reviews("") is None
    assert kaspi_search._stars("rating _small _49") == 4.9
    assert kaspi_search._stars("rating _small _46") == 4.6
    assert kaspi_search._stars("") == ""
