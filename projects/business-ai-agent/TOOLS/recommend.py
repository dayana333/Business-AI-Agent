"""Deterministic ranking of collected offers into budget / mid / premium picks.

Numbers only: the model explains them, it does not choose them.

When a query is supplied, offers are first filtered on exact brand / model
matches.  Fuzzy spellings (for example ``PNDRA`` for ``PANDORA``) are treated
as different words: a listing is only kept when the requested brand appears
as a whole word in its title or brand field.
"""

import math
import re
import statistics

WEIGHTS = {
    # Every tier prefers the upper half of its band, so no tier defaults to the
    # cheapest item that barely qualifies.
    "budget": {"price_position": 0.25, "rating": 0.45, "reviews": 0.30},
    "mid": {"price_position": 0.25, "rating": 0.45, "reviews": 0.30},
    "premium": {"price_position": 0.35, "rating": 0.40, "reviews": 0.25},
}
TIERS = ("budget", "mid", "premium")
ROLES = {
    "budget": "Best budget",
    "mid": "Best mid-range",
    "premium": "Best premium",
}
MIN_OFFERS = 3
MIN_RATING = 4.5
MIN_REVIEWS = 10
QUALITY_NOTE = f"rating {MIN_RATING}+ and {MIN_REVIEWS}+ reviews"

# Marketing words that describe a category rather than a brand/product.
GENERIC_TERMS = {
    "jewellery", "jewelry", "украшение", "украшения", "ювелирный", "ювелирные",
    "купить", "shop", "online", "original", "оригинал", "new", "новый",
    "best", "лучший", "cheap", "дешево", "недорого", "for", "для",
    "women", "woman", "men", "man", "женский", "женские", "мужской", "мужские",
    "wireless", "беспроводной", "беспроводные", "bluetooth", "блютуз",
    "phone", "телефон", "смартфон", "laptop", "ноутбук", "tablet", "планшет",
    "watch", "часы", "headphones", "наушники", "earbuds", "наушники",
    "браслет", "bracelet", "кольцо", "ring", "серьги", "earrings",
    "колье", "necklace", "подвеска", "pendant", "шарм", "charm",
    "заколка", "hair", "clip", "clamp", "крабик", "для", "волос",
    "and", "the", "а", "в", "на", "с", "и", "по",
}
KNOWN_BRANDS = {
    "pandora", "apple", "iphone", "ipad", "macbook", "airpods", "samsung",
    "galaxy", "xiaomi", "redmi", "poco", "huawei", "honor", "sony", "jbl",
    "nike", "adidas", "reebok", "puma", "dyson", "philips",
    "bosch", "lg", "asus", "acer", "lenovo", "hp", "dell", "canon", "nikon",
    "logitech", "razer", "corsair", "anker", "soundcore", "baseus", "ugreen",
    "tecno", "infinix", "realme", "oneplus", "oppo", "vivo", "google",
    "pixel", "garmin", "casio", "tissot", "swatch", "zara", "uniqlo",
    "nivea", "cerave", "loreal", "maybelline", "essence", "catrice",
    "tiffany", "cartier", "gucci", "prada", "chanel", "dior", "versace",
    "armani", "boss", "lacoste", "tommy", "hilfiger", "calvin", "klein",
    "skechers", "vans", "converse", "asics", "mizuno",
    "milwaukee", "makita", "dewalt", "karcher", "tefal", "redmond",
    "polaris", "philips", "braun", "rowenta", "lg", "samsung", "haier",
}
_UNITS = {
    "см", "cm", "мм", "mm", "г", "g", "кг", "kg", "мл", "ml", "л", "l",
    "шт", "pcs", "вт", "w", "mah", "гб", "gb", "тб", "tb", "%",
}
_FAMILIES = {
    "bracelet": ("браслет", "bracelet", "брендлет"),
    "ring": ("кольцо", "ring", "обручальн"),
    "earrings": ("серьг", "earring", "пусет", "пусеты"),
    "necklace": ("колье", "necklace", "ожерель"),
    "pendant": ("подвеск", "pendant", "кулон"),
    "charm": ("шарм", "charm", "шармик"),
    "hairclip": ("заколк", "hair clip", "крабик", "зажим"),
    "watch": ("час", "watch"),
    "phone": ("телефон", "смартфон", "phone", "iphone", "galaxy"),
    "laptop": ("ноутбук", "laptop", "macbook"),
    "headphones": ("наушник", "headphone", "earbud", "airpods"),
}

_RU_SUFFIXES = sorted(
    {
        "ами", "ями", "ому", "ему", "ыми", "ими", "ого", "его", "ей", "ой",
        "ий", "ый", "ая", "яя", "ое", "ее", "ые", "ие", "ов", "ев", "ам",
        "ям", "ом", "ем", "ах", "ях", "а", "я", "ы", "и", "е", "у", "ю",
    },
    key=len,
    reverse=True,
)
_EN_SUFFIXES = sorted(
    {"ing", "ed", "es", "s", "ly", "er", "est"}, key=len, reverse=True
)
_WORD_RE = re.compile(r"[0-9a-zа-яё]+", re.IGNORECASE)


def _num(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(a, b):
    return round((a - b) / b * 100, 1) if b else 0.0


def _clean(word):
    return word.lower().replace("ё", "е")


def _words(text):
    return [_clean(w) for w in _WORD_RE.findall(str(text or ""))]


def _stem(token):
    """Very small RU/EN stemmer, enough for product-word matching."""
    token = _clean(token)
    if not token:
        return token
    if re.search(r"[а-я]", token):
        suffixes = _RU_SUFFIXES
    else:
        suffixes = _EN_SUFFIXES
    for suffix in suffixes:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def _term_in(term, tokens, text):
    """Match a whole short term, or a prefix for longer product words."""
    term = _clean(term)
    if not term:
        return False
    if len(term) <= 3:
        return term in tokens
    stem = _stem(term)
    return any(t == stem or (t.startswith(stem) and len(t) >= 4) for t in tokens)


def _phrase_in(phrase, tokens, text):
    phrase_tokens = _words(phrase)
    if not phrase_tokens:
        return False
    if len(phrase_tokens) == 1:
        return phrase_tokens[0] in tokens
    for start in range(len(tokens) - len(phrase_tokens) + 1):
        if tokens[start:start + len(phrase_tokens)] == phrase_tokens:
            return True
    return False


def parse_query(query):
    """Split a query into exact brand, model, product and size tokens."""
    raw = str(query or "").strip()
    words = _words(raw)
    original = [w for w in re.findall(r"[0-9A-Za-zА-Яа-яЁё]+", raw)]
    spec_idx = set()
    for i, word in enumerate(words):
        if word.isdigit() and i + 1 < len(words) and words[i + 1] in _UNITS:
            spec_idx.add(i)
            spec_idx.add(i + 1)
    brand = []
    for i, word in enumerate(words):
        if word in KNOWN_BRANDS and word not in GENERIC_TERMS:
            brand = [word]
            break
    model = [
        word for i, word in enumerate(words)
        if re.search(r"\d", word) and i not in spec_idx and len(word) > 1
    ]
    product = [
        word for i, word in enumerate(words)
        if i not in spec_idx
        and word not in brand
        and word not in model
        and word not in GENERIC_TERMS
        and len(word) > 1
    ]
    fallback = [
        word for i, word in enumerate(words)
        if i not in spec_idx and word not in brand and word not in model and len(word) > 1
    ]
    return {
        "raw": raw,
        "words": words,
        "brand": tuple(brand),
        "model": tuple(dict.fromkeys(model)),
        "product": tuple(dict.fromkeys(product)),
        "match_any": tuple(dict.fromkeys(product or fallback)),
    }


def _row_tokens(row):
    parts = [row.get("title", ""), row.get("brand", "")]
    for key in ("specs", "description"):
        value = row.get(key)
        if isinstance(value, list):
            parts.extend(str(v) for v in value)
        elif value:
            parts.append(str(value))
    return _words(" ".join(parts))


def relevance(row, query_info):
    """Return ``(matched, 0..1 score, reason)`` for one listing."""
    info = query_info or {}
    tokens = _row_tokens(row)
    token_set = set(tokens)
    brand = info.get("brand") or ()
    model = info.get("model") or ()
    product = info.get("product") or ()
    match_any = info.get("match_any") or ()
    if not brand and not model and not product:
        return True, 0.5, "generic category query; no keyword filtering"

    score = 0.0
    if brand:
        if not all(_phrase_in(b, tokens, " ".join(tokens)) for b in brand):
            return False, 0.0, "requested brand does not appear as a whole word"
        score += 0.50
    if model:
        hits = sum(1 for m in model if m in token_set or m in " ".join(tokens))
        if hits < len(model):
            return False, 0.0, "requested model number is missing"
        score += 0.20 * hits / len(model)
    if product:
        hits = sum(1 for term in product if _term_in(term, token_set, " ".join(tokens)))
        score += 0.25 * hits / len(product)
    elif brand:
        score += 0.20
    elif match_any:
        if not any(_term_in(term, token_set, " ".join(tokens)) for term in match_any):
            return False, 0.0, "no product word matches the query"
        score += 0.25
    return True, min(1.0, score), "relevant"


def _family(title):
    text = _clean(title)
    for name, words in _FAMILIES.items():
        if any(word in text for word in words):
            return name
    return "other"


def _price_check(offers):
    """Name prices that are ridiculously low compared with the rest of the market."""
    if len(offers) < 3:
        return []
    groups = {}
    for row in offers:
        family = _family(row.get("title", ""))
        groups.setdefault(family, []).append(row)

    def stats(members):
        prices = sorted(r["price_kzt"] for r in members)
        median = statistics.median(prices)
        q1 = statistics.quantiles(prices, n=4, method="inclusive")[0] if len(prices) >= 4 else min(prices)
        return median, q1

    references = {}
    for family, members in groups.items():
        if len(members) >= 3:
            references[family] = stats(members)
    overall = stats(offers)

    for row in offers:
        family = _family(row.get("title", ""))
        median, q1 = references.get(family, overall)
        if median <= 0:
            continue
        ratio = row["price_kzt"] / median
        far_below_median = ratio < 0.30
        below_budget_floor = q1 > 0 and row["price_kzt"] < q1 * 0.60
        if not (far_below_median or below_budget_floor):
            continue
        row["_anomaly"] = True
        median_text = f"{median:,.0f}".replace(",", " ")
        row["price_flag"] = (
            f"Anomaly price: {ratio:.0%} of the similar-offer median "
            f"({median_text} ₸); check pack size, model or seller"
        )

    return [
        {
            "title": r.get("title", ""),
            "price_kzt": r["price_kzt"],
            "url": r.get("url", ""),
            "image_url": r.get("image_url") or r.get("image") or "",
            "reason": r.get("price_flag", ""),
        }
        for r in offers if r.get("_anomaly")
    ]


def _seller_score(row):
    rating = _num(row.get("seller_rating"))
    reviews = _num(row.get("seller_reviews"))
    if rating is None:
        return None
    depth = math.log10(reviews + 1) / 3 if reviews else 0.5
    return max(0.0, min(1.0, (rating / 5) * (0.6 + 0.4 * depth)))


def _nearest_price_cut(ordered, target, lo, hi):
    """Nearest cut that does not split offers with the same price."""
    candidates = [
        i for i in range(lo, hi + 1)
        if ordered[i - 1]["price_kzt"] != ordered[i]["price_kzt"]
    ]
    if not candidates:
        return target
    return min(candidates, key=lambda i: (abs(i - target), i))


def split_tiers(rows):
    """Split by price: lowest 40% = budget, next 40% = mid, top 20% = premium.

    Offers with the same price stay in one band, so a cluster of identical
    prices cannot appear in both mid and premium.
    """
    ordered = sorted(rows, key=lambda r: r["price_kzt"])
    if len(ordered) < 3:
        return {}
    n = len(ordered)
    budget_count = max(1, round(n * 0.40))
    premium_count = max(1, round(n * 0.20))
    budget_count = min(budget_count, n - 2)
    premium_count = min(premium_count, n - budget_count - 1)
    cut1 = _nearest_price_cut(ordered, budget_count, 1, n - 2)
    cut2 = _nearest_price_cut(ordered, n - premium_count, cut1 + 1, n - 1)
    return {
        "budget": ordered[:cut1],
        "mid": ordered[cut1:cut2],
        "premium": ordered[cut2:],
    }


def _upper_position(price, prices):
    """Reward the upper half of a price band; never punish a high price."""
    if not prices:
        return 0.5
    lo, hi = min(prices), max(prices)
    if hi <= lo:
        return 0.5
    median = statistics.median(prices)
    if price <= median:
        return 0.0
    return (price - median) / (hi - median)


def _score(row, segment, tier):
    prices = [r["price_kzt"] for r in segment]
    max_reviews = max((_num(r.get("reviews_count")) or 0) for r in segment) or 1
    weights = WEIGHTS[tier]
    reviews = _num(row.get("reviews_count")) or 0
    price_part = _upper_position(row["price_kzt"], prices)
    price_key = "price_position"
    rating_part = row["_rating"] / 5
    review_part = math.log10(reviews + 1) / math.log10(max_reviews + 1)
    base = (
        weights[price_key] * price_part
        + weights["rating"] * rating_part
        + weights["reviews"] * review_part
    )
    seller = _seller_score(row)
    if seller is not None:
        base = base * 0.9 + 0.1 * seller
    if row.get("_relevance"):
        base = base * 0.9 + 0.1 * row["_relevance"]
    if row.get("_anomaly"):
        base *= 0.5
    return base


def _value_label(score):
    if score >= 0.85:
        return "high"
    if score >= 0.7:
        return "good"
    return "moderate"


def describe(row, segment, tier):
    prices = [r["price_kzt"] for r in segment]
    ratings = [r["_rating"] for r in segment]
    med_price = statistics.median(prices)
    med_rating = statistics.median(ratings)
    reviews = _num(row.get("reviews_count")) or 0
    advantages, disadvantages = [], []

    if row.get("_brand_query"):
        advantages.append("requested brand appears in the title (not an authenticity proof)")
    if row["_rating"] >= max(ratings) - 1e-9:
        advantages.append(f"highest rating in the {tier} tier ({row['_rating']})")
    if reviews and reviews == max((_num(r.get('reviews_count')) or 0) for r in segment):
        advantages.append(f"most reviews in the {tier} tier ({int(reviews):,}) — strongest evidence")
    if tier == "premium":
        advantages.append(
            f"premium shortlist: top 20% by price in this comparison "
            f"(from {min(prices):,.0f} KZT)"
        )
        if row["price_kzt"] > med_price:
            advantages.append(
                f"premium positioning: {_pct(row['price_kzt'], med_price)}% above the premium-tier median"
            )
    elif tier == "mid":
        if row["price_kzt"] > med_price:
            advantages.append(
                f"upper middle band: {_pct(row['price_kzt'], med_price)}% above the middle-tier median"
            )
        elif row["price_kzt"] < med_price:
            disadvantages.append(
                f"{abs(_pct(row['price_kzt'], med_price))}% below the middle-tier median; lower-priced end"
            )
    elif row["price_kzt"] < med_price:
        advantages.append(f"{abs(_pct(row['price_kzt'], med_price))}% below the {tier}-tier median price")
    if row["_rating"] >= 4.8:
        advantages.append(f"rating {row['_rating']} is in the top band (4.8+)")
    seller = _seller_score(row)
    if seller is not None and seller >= 0.8:
        advantages.append(
            f"seller rated {row.get('seller_rating')} from {row.get('seller_reviews')} reviews"
        )

    if reviews < MIN_REVIEWS:
        disadvantages.append(f"only {int(reviews)} reviews — weaker evidence, treat with care")
    elif reviews < 50:
        disadvantages.append(f"only {int(reviews)} reviews — small sample, treat with care")
    else:
        advantages.append(f"{int(reviews):,} reviews — evidence of real buyer activity")
    if row["price_kzt"] > med_price and tier == "budget":
        disadvantages.append(f"{_pct(row['price_kzt'], med_price)}% above the budget-tier median price")
    if row["_rating"] < med_rating:
        disadvantages.append(f"rating {row['_rating']} is below the {tier}-tier median {med_rating}")
    if row.get("price_flag"):
        disadvantages.append(row["price_flag"])
    if seller is not None and seller < 0.65:
        disadvantages.append("seller rating or review depth is weak")
    if not disadvantages:
        disadvantages.append("no clear weakness in this data; check the listing and seller terms")
    if not advantages:
        advantages.append("balanced price, rating and review volume")

    return advantages, disadvantages


def _pick_best(scored, used_products):
    for score, row in scored:
        title_key = _clean(row.get("title", ""))
        if title_key in used_products:
            continue
        used_products.add(title_key)
        return score, row
    return None


def recommend(rows, query=None):
    """Return the three picks plus tier statistics. No model, no guessing."""
    info = parse_query(query) if query else None
    relevant = []
    excluded = []
    for row in rows:
        if info:
            matched, score, reason = relevance(row, info)
            if not matched:
                if len(excluded) < 5:
                    excluded.append({
                        "title": row.get("title", ""),
                        "price_kzt": _num(row.get("price_kzt")),
                        "reason": reason,
                    })
                continue
            copy = dict(row)
            copy["_relevance"] = round(score, 3)
            copy["_brand_query"] = bool(info.get("brand"))
            relevant.append(copy)
        else:
            relevant.append(dict(row))

    offers = []
    skipped_no_rating = []
    for row in relevant:
        rating = _num(row.get("rating"))
        price = _num(row.get("price_kzt"))
        if not price or not rating:
            skipped_no_rating.append(row.get("title", ""))
            continue
        copy = dict(row)
        copy["_rating"] = rating
        copy["price_kzt"] = price
        offers.append(copy)

    anomalies = _price_check(offers) if offers else []
    flagged = {
        (r.get("marketplace"), r.get("product_id"), r.get("title"))
        for r in offers if r.get("_anomaly")
    }
    for row in relevant:
        if (row.get("marketplace"), row.get("product_id"), row.get("title")) in flagged:
            row["_anomaly"] = True
    ranking_offers = [r for r in offers if not r.get("_anomaly")]
    quality_offers = [
        r for r in ranking_offers
        if r["_rating"] >= MIN_RATING
        and (_num(r.get("reviews_count")) or 0) >= MIN_REVIEWS
    ]
    relevant_clean = [r for r in relevant if not r.get("_anomaly")]
    result = {
        "offers_used": len(ranking_offers),
        "offers_meeting_quality": len(quality_offers),
        "quality_floor": {
            "min_rating": MIN_RATING,
            "min_reviews": MIN_REVIEWS,
            "basis": "product review count is the public evidence of buyer activity; sales counts are not public",
        },
        "quality_filtered_examples": [
            {
                "title": r.get("title", ""),
                "price_kzt": r["price_kzt"],
                "rating": r["_rating"],
                "reviews_count": _num(r.get("reviews_count")) or 0,
            }
            for r in ranking_offers if r not in quality_offers
        ][:5],
        "relevant_found": len(relevant),
        "filtered_out": max(0, len(rows) - len(relevant)),
        "filtered_examples": excluded,
        "skipped_without_rating": skipped_no_rating,
        "anomaly_prices": anomalies,
        "tiers": {},
        "picks": [],
        "status": "ok",
        "relevant_rows": relevant_clean,
    }
    if query:
        result["query_terms"] = {
            "brand": list(info["brand"]),
            "model": list(info["model"]),
            "product": list(info["product"]),
        }

    if info and not relevant:
        result["status"] = "no_relevant"
        if info["brand"]:
            result["reason"] = (
                f"No listing title contains the exact brand “{info['brand'][0]}”. "
                "Similar-looking spellings are not treated as the same brand. "
                f"{len(rows)} offer(s) were excluded."
            )
        else:
            result["reason"] = (
                f"No listing matches the query “{info['raw']}”. "
                f"{len(rows)} offer(s) were excluded."
            )
        return result

    if info and len(relevant) < MIN_OFFERS:
        result["status"] = "insufficient_relevant"
        result["reason"] = (
            f"Only {len(relevant)} relevant offer(s) matched “{info['raw']}”; "
            f"at least {MIN_OFFERS} are needed for three recommendations. "
            f"{len(rows) - len(relevant)} unrelated offer(s) were excluded."
        )
        return result

    if len(ranking_offers) < MIN_OFFERS:
        result["status"] = "insufficient_data"
        result["reason"] = (
            f"{len(ranking_offers)} offer(s) with price and rating remained after price checks; "
            f"at least {MIN_OFFERS} are needed for three recommendations"
        )
        return result

    if len(quality_offers) < MIN_OFFERS:
        result["status"] = "insufficient_quality"
        result["reason"] = (
            f"Only {len(quality_offers)} offer(s) meet the quality floor ({QUALITY_NOTE}); "
            f"at least {MIN_OFFERS} are needed for three recommendations. "
            f"{len(ranking_offers) - len(quality_offers)} weak offer(s) were excluded."
        )
        return result

    segments = split_tiers(quality_offers)
    used_products = set()
    gate_note = (
        f"quality floor: {QUALITY_NOTE} — "
        f"{len(quality_offers)} of {len(ranking_offers)} priced offers passed"
    )
    for tier in TIERS:
        segment = segments[tier]
        candidates = segment
        scored = sorted(
            ((_score(row, segment, tier), row) for row in candidates),
            key=lambda pair: pair[0],
            reverse=True,
        )
        picked = _pick_best(scored, used_products)
        if picked is None:
            result["status"] = "insufficient_distinct"
            result["picks"] = []
            result["reason"] = (
                f"No unused distinct product remained for the {tier} tier; "
                "three different products are needed for three recommendations. "
                "Nothing was duplicated to fill the card."
            )
            return result
        score, best = picked
        advantages, disadvantages = describe(best, segment, tier)
        prices = [r["price_kzt"] for r in segment]
        ratings = [r["_rating"] for r in segment]
        result["tiers"][tier] = {
            "offers": len(segment),
            "price_min": min(prices),
            "price_max": max(prices),
            "price_median": statistics.median(prices),
            "rating_median": round(statistics.median(ratings), 2),
            "rating_mean": round(statistics.mean(ratings), 2),
            "quality_gate": gate_note,
        }
        result["picks"].append(
            {
                "tier": tier,
                "role": ROLES[tier],
                "title": best.get("title", ""),
                "marketplace": best.get("marketplace", ""),
                "product_id": best.get("product_id", ""),
                "brand": best.get("brand", ""),
                "image_url": best.get("image_url") or best.get("image") or "",
                "price_kzt": best["price_kzt"],
                "rating": best["_rating"],
                "reviews_count": _num(best.get("reviews_count")),
                "url": best.get("url", ""),
                "score": round(score, 3),
                "value_for_money": _value_label(score),
                "advantages": advantages,
                "disadvantages": disadvantages,
                "price_flag": best.get("price_flag", ""),
                "seller": best.get("seller", ""),
                "seller_rating": _num(best.get("seller_rating")),
                "seller_reviews": _num(best.get("seller_reviews")),
                "also_considered": [
                    {"title": r.get("title", ""), "price_kzt": r["price_kzt"],
                     "rating": r["_rating"],
                     "reviews_count": _num(r.get("reviews_count")),
                     "score": round(s, 3)}
                    for s, r in scored[1:3] if _clean(r.get("title", "")) != _clean(best.get("title", ""))
                ][:2],
            }
        )
        if info and info["brand"]:
            result["picks"][-1]["brand_match"] = "exact title match"
            result["picks"][-1]["authenticity"] = (
                "The brand name appears in the listing title; authenticity is not verified."
            )

    chosen_titles = {_clean(p.get("title", "")) for p in result["picks"]}
    for pick in result["picks"]:
        seen = set(chosen_titles)
        alternatives = []
        for alt in pick.get("also_considered", []):
            key = _clean(alt.get("title", ""))
            if key in seen:
                continue
            seen.add(key)
            alternatives.append(alt)
        pick["also_considered"] = alternatives[:2]

    cheapest = min(ranking_offers, key=lambda r: r["price_kzt"])
    cheapest_quality = min(quality_offers, key=lambda r: r["price_kzt"])
    budget = result["picks"][0]
    cheapest_label = "cheapest non-anomaly listing" if anomalies else "cheapest listing"
    cheapest_title = _clean(cheapest.get("title", ""))
    cheapest_quality_title = _clean(cheapest_quality.get("title", ""))
    budget_title = _clean(budget.get("title", ""))
    if cheapest_title == budget_title:
        result["note"] = (
            f"quality floor ({QUALITY_NOTE}) applied; the {cheapest_label} also won the budget tier"
        )
    elif cheapest_title == cheapest_quality_title:
        result["note"] = (
            f"quality floor ({QUALITY_NOTE}) applied; the {cheapest_label} "
            f"({cheapest.get('title')} at {cheapest['price_kzt']:.0f} KZT) passed the floor "
            f"but scored lower than the budget pick ({budget.get('title')} at "
            f"{budget['price_kzt']:.0f} KZT)"
        )
    else:
        result["note"] = (
            f"quality floor ({QUALITY_NOTE}) applied; budget pick is not the {cheapest_label}: "
            f"{cheapest.get('title')} at {cheapest['price_kzt']:.0f} KZT was excluded by the floor. "
            f"The cheapest passing offer is {cheapest_quality.get('title')} at "
            f"{cheapest_quality['price_kzt']:.0f} KZT, but it scored lower than the budget pick"
        )
    if result["filtered_out"]:
        result["note"] += (
            f"; {result['filtered_out']} unrelated offer(s) were filtered out before ranking"
        )
    if anomalies:
        label = "offer" if len(anomalies) == 1 else "offers"
        result["note"] += (
            f"; {len(anomalies)} anomaly-priced {label} named and left out of the picks"
        )
    return result
