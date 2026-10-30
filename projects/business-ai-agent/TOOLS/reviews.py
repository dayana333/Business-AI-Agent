"""Read and analyse real customer review text from public product pages.

Only visible reviews from a normal browser session are used. Every number is
computed from the collected text; missing review access is reported, not guessed.
"""

import json
import re
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NODE_SCRIPT = Path(__file__).with_name("kaspi_reviews.mjs")
MAX_PRODUCTS = 3

POSITIVE_THEMES = {
    "Appearance and shade": [
        r"красив", r"оттен", r"цвет", r"блест", r"сия", r"shade", r"color",
        r"әдемі", r"түс", r"сәйкес",
    ],
    "Light, non-sticky texture": [
        r"не липн", r"лёгк", r"легк", r"текстур", r"не скатыва", r"не растека",
        r"комфорт", r"мягк", r"жеңіл", r"қолайлы",
    ],
    "Moisture and lip care": [
        r"увлажн", r"пита", r"зажив", r"губы.{0,20}(мягк|нежн)", r"күтім",
    ],
    "Scent and taste": [
        r"запах.{0,25}(прият|класс|вкусн|обалд|божеств)", r"аромат",
        r"привкус", r"пахнет.{0,15}(прият|вкусн)", r"иіс",
    ],
    "Packaging and size": [
        r"компакт", r"удобно с собой", r"упаковк.{0,25}(хорош|цел|аккурат|красив)",
        r"объ[её]м", r"маленьк", r"кішкентай", r"ыңғайлы",
    ],
    "Fast delivery": [
        r"доставк.{0,35}(быстр|раньше|вовремя|хорош)", r"быстр",
        r"пришл", r"жеткіз",
    ],
    "Value for money": [
        r"цена", r"недорог", r"стоит", r"качеств", r"сапа",
    ],
    "Overall satisfaction": [
        r"рахмет", r"ұнады", r"понрав", r"тамаша", r"совету",
    ],
    "Long wear": [
        r"держится", r"стойк", r"долго", r"остается на губах", r"ұзақ",
    ],
}

NEGATIVE_THEMES = {
    "Sticky or heavy texture": [
        r"липн", r"липк", r"тяжел", r"варень", r"густ", r"скатыва", r"жирн",
        r"растека",
    ],
    "Shade or colour mismatch": [
        r"цвет не", r"оттенок не", r"не соответств", r"другой цвет", r"бледн",
        r"некрасив", r"слишком ярк", r"түс.{0,25}(емес|басқа)",
    ],
    "Defects or fast wear": [
        r"брак", r"дефект", r"сломал", r"треснул", r"высох", r"испорт",
        r"поддел", r"быстро закон", r"хватило на.{0,20}(день|недел|месяц)",
        r"сапасы.{0,25}(нашар|төмен)",
    ],
    "Longevity or wear problems": [
        r"не стойк", r"не держ", r"быстро стира", r"быстро сход",
        r"быстро исчез", r"держится недолго", r"исчеза",
    ],
    "Description or photo mismatch": [
        r"не соответств", r"не как на фото", r"не как на картинк",
        r"другой оттенок", r"обман",
    ],
    "Overall quality disappointment": [
        r"разочаров", r"ужасн", r"отвратительн", r"плох", r"не понрав",
    ],
    "Packaging damage": [
        r"поврежд", r"разбит", r"протек", r"помят", r"порван",
    ],
    "Delivery problems": [
        r"доставк.{0,35}(долго|задерж|опазд|плох|проблем)",
        r"задерж", r"не приш", r"опазд",
        r"жеткіз.{0,25}(кеш|болма)",
    ],
    "Lip irritation or dryness": [
        r"аллерг", r"раздраж", r"сушит", r"жжет", r"жжёт", r"опух",
        r"губы.{0,25}(сох|треск|бол)",
    ],
    "Unpleasant smell or taste": [
        r"запах.{0,25}(плох|неприят|отврат|ужас|хим)", r"воня",
        r"привкус.{0,20}(плох|горьк|неприят)", r"горьк", r"иіс.{0,20}жаман",
    ],
    "Too small or little product": [
        r"маленьк", r"мало", r"объ[её]м", r"размер", r"кішкентай",
    ],
    "Wrong item or variant": [
        r"не тот", r"пересорт", r"другой товар",
    ],
    "Expensive": [
        r"дорого", r"цена.{0,20}(высок|куса)", r"қымбат",
    ],
}

_ALL_THEMES = {**POSITIVE_THEMES, **NEGATIVE_THEMES}


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _snippet(text, limit=180):
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _theme_hits(text):
    return [name for name, patterns in _ALL_THEMES.items()
            if any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)]


def collect_for_picks(picks, pages=4, timeout=180):
    """Fetch visible reviews for up to three Kaspi picks. Never raises on a block."""
    products = []
    seen = set()
    for pick in (picks or {}).get("picks", [])[:MAX_PRODUCTS]:
        url = (pick.get("url") or "").strip()
        if not url.startswith("https://kaspi.kz/shop/p/") or url in seen:
            continue
        seen.add(url)
        products.append({"title": pick.get("title", ""), "url": url})
    if not products:
        return {
            "status": "unavailable",
            "checked": [],
            "reason": "No Kaspi product page was available for the selected offers.",
            "products": [],
        }
    if not NODE_SCRIPT.exists():
        return {
            "status": "error",
            "checked": [p["url"] for p in products],
            "reason": f"Review browser script missing: {NODE_SCRIPT.name}",
            "products": [],
        }
    try:
        proc = subprocess.run(
            ["node", str(NODE_SCRIPT), str(pages), *[p["url"] for p in products]],
            capture_output=True, text=True, timeout=timeout,
        )
    except Exception as exc:
        return {
            "status": "error",
            "checked": [p["url"] for p in products],
            "reason": f"{type(exc).__name__}: {exc}",
            "products": [],
        }
    if proc.returncode != 0:
        reason = (proc.stderr or proc.stdout or "browser script failed").strip().splitlines()
        return {
            "status": "error",
            "checked": [p["url"] for p in products],
            "reason": reason[-1] if reason else "browser script failed",
            "products": [],
        }
    try:
        pages_data = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        return {
            "status": "error",
            "checked": [p["url"] for p in products],
            "reason": f"Bad review output: {exc}",
            "products": [],
        }

    analyses = []
    for product, page in zip(products, pages_data):
        analyses.append(analyse_page(product, page))
    readable = [a for a in analyses if a["status"] == "ok"]
    return {
        "status": "ok" if readable else "unavailable",
        "checked": [p["url"] for p in products],
        "products": analyses,
        "reviews_analysed": sum(a["analysed"] for a in analyses),
        "reviews_available": sum((a.get("total_reviews") or 0) for a in analyses),
        "reason": "" if readable else "No review text was visible on the checked product pages.",
    }


def analyse_page(product, page):
    """Turn one product page's visible reviews into themes, examples and confidence."""
    if page.get("status") != "ok":
        return {
            "title": product.get("title", ""),
            "url": product.get("url", ""),
            "status": page.get("status", "error"),
            "reason": page.get("reason", "Review text was not visible."),
            "image_url": page.get("image_url", ""),
            "seller": page.get("seller", ""),
            "seller_rating": page.get("seller_rating"),
            "seller_reviews": page.get("seller_reviews"),
            "total_reviews": page.get("total_reviews"),
            "analysed": 0,
            "positive": 0,
            "negative": 0,
            "themes_positive": [],
            "themes_negative": [],
            "examples_positive": [],
            "examples_negative": [],
            "confidence": "none",
        }

    reviews = []
    for review in page.get("reviews") or []:
        text = _snippet(review.get("text"), 1200)
        rating = _num(review.get("rating"))
        if not text or rating is None:
            continue
        reviews.append({**review, "text": text, "rating": rating})

    positive = [r for r in reviews if r["rating"] >= 4]
    negative = [r for r in reviews if r["rating"] <= 3]
    pos_counts = Counter()
    neg_counts = Counter()
    pos_examples = {}
    neg_examples = {}
    for review in positive:
        for theme in _theme_hits(review["text"]):
            if theme in POSITIVE_THEMES:
                pos_counts[theme] += 1
                pos_examples.setdefault(theme, []).append(review)
    for review in negative:
        for theme in _theme_hits(review["text"]):
            if theme in NEGATIVE_THEMES:
                neg_counts[theme] += 1
                neg_examples.setdefault(theme, []).append(review)

    def rows(counter, examples):
        total = len(reviews) or 1
        result = []
        for theme, count in counter.most_common():
            result.append({
                "theme": theme,
                "count": count,
                "share_pct": round(count / total * 100, 1),
                "examples": [
                    {"text": _snippet(r["text"], 220), "rating": r["rating"],
                     "date": r.get("date", "")}
                    for r in examples.get(theme, [])[:2]
                ],
            })
        return result

    total_reviews = page.get("total_reviews")
    if len(reviews) < 10:
        confidence = "low"
    elif total_reviews and len(reviews) / total_reviews < 0.1:
        confidence = "low"
    else:
        confidence = "medium"
    return {
        "title": product.get("title", ""),
        "url": product.get("url", ""),
        "status": "ok",
        "image_url": page.get("image_url", ""),
        "seller": page.get("seller", ""),
        "seller_rating": page.get("seller_rating"),
        "seller_reviews": page.get("seller_reviews"),
        "total_reviews": total_reviews,
        "analysed": len(reviews),
        "positive": len(positive),
        "negative": len(negative),
        "mean_rating": round(sum(r["rating"] for r in reviews) / len(reviews), 2) if reviews else None,
        "negative_share_pct": round(len(negative) / len(reviews) * 100, 1) if reviews else None,
        "themes_positive": rows(pos_counts, pos_examples),
        "themes_negative": rows(neg_counts, neg_examples),
        "confidence": confidence,
        "sample_note": (
            f"Read {len(reviews)} of {total_reviews or 'unknown'} visible reviews; "
            "this is a sample, not a full census."
        ),
    }


def evidence_for_pick(pick, analysis):
    """Attach review evidence to a recommendation without inventing an opinion."""
    if not analysis or analysis.get("status") != "ok":
        return {
            "review_analysed": 0,
            "review_positive": 0,
            "review_total": analysis.get("total_reviews") if analysis else None,
            "positive_themes": [],
            "negative_themes": [],
            "review_examples": [],
            "confidence": "none",
        }
    total = analysis["analysed"] or 1
    pos = [
        f"{t['theme']} ({t['count']}/{total}, {t['share_pct']}%)"
        for t in analysis["themes_positive"][:3]
    ]
    neg = [
        f"{t['theme']} ({t['count']}/{total}, {t['share_pct']}%)"
        for t in analysis["themes_negative"][:3]
    ]
    examples = []
    for theme in analysis["themes_negative"][:1] + analysis["themes_positive"][:1]:
        for example in theme["examples"][:1]:
            examples.append({
                "theme": theme["theme"],
                "text": example["text"],
                "rating": example["rating"],
            })
    return {
        "review_analysed": analysis["analysed"],
        "review_positive": analysis.get("positive", 0),
        "review_total": analysis.get("total_reviews"),
        "positive_themes": pos,
        "negative_themes": neg,
        "review_examples": examples,
        "confidence": analysis.get("confidence", "low"),
    }


def attach_to_picks(picks, data):
    """Add review evidence and a transparent recommendation reason to each pick."""
    if not picks or picks.get("status") != "ok":
        return picks
    by_url = {p.get("url"): p for p in (data or {}).get("products", [])}
    for pick in picks.get("picks", []):
        analysis = by_url.get(pick.get("url"))
        evidence = evidence_for_pick(pick, analysis)
        if analysis and analysis.get("image_url") and not pick.get("image_url"):
            pick["image_url"] = analysis["image_url"]
        if analysis and analysis.get("seller"):
            pick["seller"] = analysis["seller"]
            pick["seller_rating"] = analysis.get("seller_rating")
            pick["seller_reviews"] = analysis.get("seller_reviews")
        pick["review_evidence"] = evidence
        pick["review_advantages"] = evidence["positive_themes"]
        pick["review_disadvantages"] = evidence["negative_themes"]
        pick["confidence"] = evidence["confidence"]
        tier = pick.get("tier")
        tier_data = (picks.get("tiers") or {}).get(tier, {})
        median = tier_data.get("price_median")
        basis = {
            "budget": "Cheapest passing offer in the lowest price band",
            "mid": "Strongest rating/review score in the upper middle band",
            "premium": "Highest weighted score in the top 20% by price",
        }.get(tier, "Selected by the tier score")
        def money(value):
            return f"{value:,.0f}".replace(",", " ") + " ₸"
        price_part = (
            f"at {money(pick['price_kzt'])}"
            + (f" vs the tier median {money(median)}" if median else "")
        )
        review_part = "no usable review text"
        if evidence["review_analysed"]:
            pos = ", ".join(evidence["positive_themes"][:2]) or "no repeated positive theme"
            neg = ", ".join(evidence["negative_themes"][:2]) or "no repeated complaint in this sample"
            review_part = (
                f"{evidence['review_analysed']} visible reviews read: positives — {pos}; "
                f"complaints — {neg}"
            )
        count = int(pick["reviews_count"]) if pick.get("reviews_count") not in (None, "") else 0
        short_basis = {
            "budget": "Cheapest offer that passed the quality floor",
            "mid": "Best balance of price, rating and review depth",
            "premium": "Strongest premium option in this comparison",
        }.get(tier, "Best option in this tier")
        pick["summary"] = f"{short_basis}: {pick.get('rating')}/5 from {count:,} product reviews."
        if evidence["review_analysed"]:
            pick["summary"] += (
                f" {evidence['review_positive']} of {evidence['review_analysed']} visible reviews"
                " are positive."
            )
        pick["quality_evidence"] = (
            f"rating {pick.get('rating')} from {count} reviews; "
            f"{review_part}; confidence {evidence['confidence']}"
        )
        pick["recommendation_reason"] = (
            f"{basis}; {price_part}; rating {pick.get('rating')} from "
            f"{count} reviews; {review_part}."
        )
        pick["suitable_for"] = {
            "budget": "Price-sensitive buyers who still need a strong rating and a large review base.",
            "mid": "Buyers who want the strongest balance of price, rating and review depth.",
            "premium": "Buyers willing to pay more for a stronger shade/finish reputation; check the sample caveat.",
        }.get(tier, "")
        if tier == "premium" and evidence["negative_themes"]:
            pick["category_note"] = (
                "The higher price is only partly supported: the visible sample also contains complaints."
            )
        elif tier == "premium":
            pick["category_note"] = (
                "The higher price is supported by rating/review depth and positive review themes in the sample, "
                f"not by price alone; confidence is {evidence['confidence']} because only "
                f"{evidence['review_analysed']} of {evidence['review_total'] or '?'} reviews were read."
            )
    return picks


def _words(text):
    return re.findall(r"[a-zа-яё0-9]+", (text or "").lower())


def _seller_evidence(pick, brand_terms):
    seller = (pick.get("seller") or "").strip()
    seller_words = _words(seller)
    title_words = _words(pick.get("title", ""))
    title_match = pick.get("brand_match") == "exact title match" or (
        bool(brand_terms) and all(term in title_words for term in brand_terms)
    )
    seller_match = bool(seller_words) and all(term in seller_words for term in brand_terms)
    rating = pick.get("seller_rating")
    reviews = pick.get("seller_reviews")
    strong = (
        rating is not None and reviews is not None
        and float(rating) >= 4.5 and int(reviews) >= 20
    )
    return {
        "seller": seller,
        "seller_rating": rating,
        "seller_reviews": reviews,
        "title_match": title_match,
        "seller_match": seller_match,
        "seller_history_strong": strong,
        "likely_original": bool(brand_terms and title_match and seller_match and strong),
    }


def apply_original_gate(picks):
    """Keep only Kaspi picks with the strongest available brand evidence.

    This is not an authenticity guarantee: Kaspi exposes no authenticity field.
    The gate accepts a pick only when the exact brand is in the title, the seller
    name matches the brand, and the seller has at least a 4.5 rating and 20 reviews.
    """
    if not picks or picks.get("status") != "ok":
        return picks
    brand_terms = (picks.get("query_terms") or {}).get("brand") or []
    if not brand_terms:
        picks["originality"] = {
            "status": "not_applicable",
            "reason": "No exact brand in the query; the seller-name check was not applied.",
        }
        return picks

    total = len(picks.get("picks", []))
    kept, dropped = [], []
    for pick in picks.get("picks", []):
        evidence = _seller_evidence(pick, brand_terms)
        if pick.get("marketplace") != "kaspi":
            evidence["status"] = "not_checked"
            kept.append(pick)
            pick["originality"] = evidence
            continue
        pick["originality"] = evidence
        if evidence["likely_original"]:
            pick["authenticity"] = (
                f'Seller “{evidence["seller"]}” matches the brand and has '
                f'{evidence["seller_rating"]}/5 from {evidence["seller_reviews"]} seller reviews. '
                "This is the strongest available signal; Kaspi does not provide an authenticity guarantee."
            )
            kept.append(pick)
        else:
            if not evidence["seller"]:
                reason = "seller name is missing"
            elif not evidence["seller_match"]:
                reason = "seller name does not match the brand"
            elif not evidence["seller_history_strong"]:
                reason = "seller rating or review history is too thin"
            else:
                reason = "title does not contain the exact brand"
            dropped.append({"title": pick.get("title", ""), "reason": reason})

    picks["picks"] = kept
    picks["originality"] = {
        "status": "kept" if kept else "no_likely_original",
        "checked": total,
        "kept": len(kept),
        "dropped": dropped,
        "note": (
            "Likely-original check: seller name must match the brand and the seller must have "
            "4.5+/5 from 20+ reviews. This filters evidence, it does not prove authenticity."
        ),
    }
    if dropped:
        picks["note"] = (picks.get("note", "") + "; " if picks.get("note") else "") + (
            f"{len(dropped)} pick(s) removed by the likely-original check: "
            + "; ".join(d["reason"] for d in dropped)
        )
    if kept:
        picks["note"] = (picks.get("note", "") + "; " if picks.get("note") else "") + (
            f"likely-original check kept {len(kept)} of {total} pick(s): "
            "seller name matches the brand. This is evidence, not a guarantee"
        )
    if not kept:
        picks["status"] = "no_likely_original"
        picks["reason"] = (
            "No Kaspi pick passed the likely-original check: the seller name did not match "
            "the brand or the seller history was too thin. Kaspi does not provide an "
            "authenticity guarantee, so no pick is shown."
        )
    return picks
