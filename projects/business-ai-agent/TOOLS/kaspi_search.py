"""Kaspi search connector: open the public search page in a real browser,
read the visible cards, and write them into the marketplace CSV format.

Usage:
    python3 TOOLS/kaspi_search.py "redmi buds"
    python3 TOOLS/kaspi_search.py "redmi buds" --save data/kaspi_redmi_buds.csv
"""

import argparse
import csv
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NODE_SCRIPT = Path(__file__).with_suffix(".mjs")
FIELDS = [
    "marketplace", "product_id", "brand", "model", "title", "price_kzt",
    "rating", "reviews_count", "url", "image_url", "observed_at", "notes",
]

TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "kaspi_search",
        "description": (
            "Search public Kaspi listings for a query in a real browser and return "
            "title, price, review count and URL for the visible cards."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "save": {"type": "string", "description": "CSV path to write"},
            },
            "required": ["query"],
        },
    },
}


def _price(text):
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def _reviews(text):
    match = re.search(r"(\d[\d\s]*)\s*отзыв", text or "", re.IGNORECASE)
    return int(match.group(1).replace(" ", "")) if match else None


def _stars(rating_class):
    """Kaspi stores the star value in a sprite class: 'rating _small _49' = 4.9."""
    match = re.search(r"_(\d{2})(?:\s|$)", rating_class or "")
    return round(int(match.group(1)) / 10, 1) if match else ""


def _product_id(href):
    match = re.search(r"/shop/p/[^/]+-(\d+)", href or "")
    return match.group(1) if match else ""


def search(query, timeout=90):
    if not NODE_SCRIPT.exists():
        raise FileNotFoundError(f"Browser script missing: {NODE_SCRIPT}")
    proc = subprocess.run(
        ["node", str(NODE_SCRIPT), query],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout).strip().splitlines()
        raise RuntimeError(msg[-1] if msg else f"browser script failed ({proc.returncode})")
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    today = dt.date.today().isoformat()
    rows = []
    for card in data["cards"]:
        price = _price(card["price"])
        if not card["title"] or not price:
            continue
        rows.append(
            {
                "marketplace": "kaspi",
                "product_id": _product_id(card["href"]),
                "brand": "",
                "model": "",
                "title": card["title"].replace("\t", " "),
                "price_kzt": price,
                "rating": _stars(card.get("ratingClass", "")),
                "reviews_count": "" if _reviews(card["reviews"]) is None else _reviews(card["reviews"]),
                "url": "https://kaspi.kz" + card["href"].split("?")[0],
                "image_url": card.get("image", ""),
                "observed_at": today,
                "notes": "public search page, browser read",
            }
        )
    return rows


def write_csv(rows, path):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return p


def main():
    parser = argparse.ArgumentParser(description="Kaspi public search -> CSV")
    parser.add_argument("query")
    parser.add_argument("--save", default=None)
    args = parser.parse_args()

    rows = search(args.query)
    if not rows:
        sys.exit("No product cards found on the page.")
    if args.save:
        path = write_csv(rows, args.save)
        print(f"{len(rows)} rows -> {path}")
    else:
        print(json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
