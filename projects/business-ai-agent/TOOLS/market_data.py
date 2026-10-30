"""Market data tool: load marketplace rows and compute price statistics.

Reads a CSV with the columns:
marketplace, product_id, brand, model, title, price_kzt, rating,
reviews_count, url, observed_at, notes
"""

import csv
import json
import re
import statistics
from pathlib import Path

REQUIRED = ("marketplace", "title", "price_kzt")
NUMERIC = ("price_kzt", "rating", "reviews_count")

TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "market_data_summary",
        "description": (
            "Load a Kaspi offers CSV and return price statistics and product grouping."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the marketplace CSV"},
                "product": {
                    "type": "string",
                    "description": "Optional product filter (part of the title)",
                },
            },
            "required": ["path"],
        },
    },
}


def _clean_money(text):
    return float(
        text.replace("\u00a0", "").replace(" ", "").replace("₸", "").replace(",", ".")
    )


def load(path):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Data file not found: {p}")
    rows = []
    with p.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        missing = [c for c in REQUIRED if c not in fields]
        if missing:
            raise ValueError("CSV is missing columns: " + ", ".join(missing))
        for line_no, raw in enumerate(reader, start=2):
            row = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
            if not row.get("title") or not row.get("price_kzt"):
                continue
            try:
                row["price_kzt"] = _clean_money(row["price_kzt"])
            except ValueError:
                raise ValueError(
                    f"Line {line_no}: price_kzt is not a number: {raw['price_kzt']!r}"
                )
            for key in ("rating", "reviews_count"):
                value = row.get(key, "")
                if value == "":
                    row[key] = None
                    continue
                try:
                    row[key] = float(value.replace(",", "."))
                except ValueError:
                    raise ValueError(f"Line {line_no}: {key} is not a number: {value!r}")
            if row.get("reviews_count") is not None:
                row["reviews_count"] = int(row["reviews_count"])
            row["marketplace"] = row["marketplace"].lower()
            rows.append(row)
    return rows


def match_key(row):
    brand = row.get("brand", "").lower()
    model = row.get("model", "").lower()
    if brand and model:
        return f"{brand} {model}"
    title = re.sub(r"\[sample\]", "", row["title"].lower())
    return re.sub(r"[^a-zа-я0-9]+", " ", title).strip()


def _rating(row):
    value = row.get("rating")
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stats(prices, ratings):
    return {
        "rows": len(prices),
        "min_kzt": min(prices),
        "max_kzt": max(prices),
        "median_kzt": round(statistics.median(prices)),
        "mean_kzt": round(statistics.mean(prices)),
        "mean_rating": round(statistics.mean(ratings), 2) if ratings else None,
    }


def summary(path, product=None):
    rows = load(path)
    if product:
        needle = product.lower()
        rows = [r for r in rows if needle in r["title"].lower()]
    return summarise(rows, str(path))


def summarise(rows, source_file=""):
    if not rows:
        raise ValueError("No rows to analyse (empty file or filter matched nothing)")

    by_marketplace = {}
    for row in rows:
        group = by_marketplace.setdefault(row["marketplace"], {"prices": [], "ratings": []})
        group["prices"].append(row["price_kzt"])
        rating = _rating(row)
        if rating is not None:
            group["ratings"].append(rating)
    stats = {
        name: _stats(g["prices"], g["ratings"])
        for name, g in sorted(by_marketplace.items())
    }

    groups = {}
    for row in rows:
        groups.setdefault(match_key(row), []).append(row)

    comparisons = []
    for key, items in groups.items():
        markets = {r["marketplace"] for r in items}
        if len(markets) < 2:
            continue
        prices = [r["price_kzt"] for r in items]
        cheapest = min(items, key=lambda r: r["price_kzt"])
        per_market = {}
        for item in items:
            bucket = per_market.setdefault(item["marketplace"], {"prices": [], "ratings": []})
            bucket["prices"].append(item["price_kzt"])
            rating = _rating(item)
            if rating is not None:
                bucket["ratings"].append(rating)
        comparisons.append(
            {
                "product": key,
                "by_marketplace": {
                    name: _stats(b["prices"], b["ratings"])
                    for name, b in sorted(per_market.items())
                },
                "min_kzt": min(prices),
                "max_kzt": max(prices),
                "median_kzt": round(statistics.median(prices)),
                "spread_kzt": round(max(prices) - min(prices)),
                "spread_pct": round((max(prices) - min(prices)) / min(prices) * 100, 1),
                "cheapest": cheapest["marketplace"],
                "offers": [
                    {
                        "marketplace": r["marketplace"],
                        "price_kzt": r["price_kzt"],
                        "rating": r.get("rating"),
                        "reviews_count": r.get("reviews_count"),
                        "url": r.get("url", ""),
                        "image_url": r.get("image_url", ""),
                        "observed_at": r.get("observed_at", ""),
                    }
                    for r in sorted(items, key=lambda r: r["price_kzt"])
                ],
            }
        )

    return {
        "source_file": source_file,
        "rows_analysed": len(rows),
        "marketplaces": sorted(by_marketplace),
        "missing_marketplaces": [],
        "sample_data": any(r["title"].lower().startswith("[sample]") for r in rows),
        "all_rows_by_marketplace": stats,
        "cross_marketplace": comparisons,
        "offers": [
            {
                "marketplace": r["marketplace"],
                "title": r["title"],
                "price_kzt": r["price_kzt"],
                "rating": r.get("rating"),
                "reviews_count": r.get("reviews_count"),
                "url": r.get("url", ""),
                "image_url": r.get("image_url", ""),
                "observed_at": r.get("observed_at", ""),
            }
            for r in rows
        ],
    }


if __name__ == "__main__":
    import sys

    data_path = sys.argv[1] if len(sys.argv) > 1 else "data/sample_marketplace_data.csv"
    print(json.dumps(summary(data_path), ensure_ascii=False, indent=1))
