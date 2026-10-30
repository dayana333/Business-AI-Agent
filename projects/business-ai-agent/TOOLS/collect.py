"""Collect Kaspi rows for one query, with an honest status.

    python3 TOOLS/collect.py "redmi buds"
    python3 TOOLS/collect.py "redmi buds" --save data/search_redmi_buds.csv
"""

import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from TOOLS import kaspi_search, normalize  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATUS_FILE = ROOT / "data" / "collection_status.json"

ROUTES = {
    "kaspi": "public search page in headless Chrome (TOOLS/kaspi_search.mjs)",
}

EVIDENCE = {"kaspi": ""}


def slug(query):
    return re.sub(r"[^a-zа-я0-9]+", "_", query.lower()).strip("_")[:40] or "query"


def dedupe(rows):
    seen, out = set(), []
    for row in rows:
        key = (row["marketplace"], row.get("product_id") or normalize.canonical_key(row))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def collect(query):
    rows, statuses = [], {}
    now = dt.datetime.now().isoformat(timespec="seconds")

    try:
        found = kaspi_search.search(query)
        rows += found
        statuses["kaspi"] = {"status": "ok", "rows": len(found)}
    except Exception as exc:
        statuses["kaspi"] = {
            "status": "error",
            "reason": f"{type(exc).__name__}: {exc}"[:200],
        }
    statuses["kaspi"].update(
        route=ROUTES["kaspi"], checked_at=now, evidence=EVIDENCE["kaspi"]
    )

    return dedupe(rows), statuses


def availability(status):
    return {
        "ok": "available",
        "reachable": "partial",
        "blocked": "blocked",
        "error": "error",
    }.get(status, "unknown")


def write_status(path, query, statuses, rows):
    groups = normalize.group_variants(rows)
    payload = {
        "query": query,
        "checked_at": dt.datetime.now().isoformat(timespec="seconds"),
        "rows_total": len(rows),
        "base_products": len(groups),
        "marketplaces": {
            name: {
                "availability": availability(item.get("status", "unknown")),
                "status": item.get("status", "unknown"),
                "rows": item.get("rows", 0),
                "reason": item.get("reason", ""),
                "note": item.get("note", ""),
                "auth": item.get("auth", "not required"),
                "route": item.get("route", ""),
                "evidence": item.get("evidence", ""),
                "checked_at": item.get("checked_at", ""),
            }
            for name, item in statuses.items()
        },
        "products": groups,
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def write_csv(rows, path):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=kaspi_search.FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return p


def status_line(name, status):
    state = availability(status.get("status", ""))
    if status.get("status") == "ok":
        return f"{name:<12} {state:<9} {status['rows']} rows"
    text = f"{name:<12} {state:<9} {status.get('reason', '')}".rstrip()
    if status.get("note"):
        text += f" ({status['note']})"
    return text


def main():
    parser = argparse.ArgumentParser(description="Collect marketplace rows for a query")
    parser.add_argument("query")
    parser.add_argument("--save", default=None)
    parser.add_argument("--status", default=str(STATUS_FILE))
    args = parser.parse_args()

    rows, statuses = collect(args.query)
    for name in ("kaspi",):
        print(status_line(name, statuses.get(name, {"status": "not run"})))

    groups = normalize.group_variants(rows)
    print(f"variants grouped: {len(groups)} base products from {len(rows)} rows")
    write_status(args.status, args.query, statuses, rows)
    print(f"status -> {args.status}")

    if not rows:
        sys.exit("\nNo rows collected. Nothing saved; the report would have no data.")
    path = args.save or (ROOT / "data" / f"search_{slug(args.query)}.csv")
    write_csv(rows, path)
    print(f"{len(rows)} rows -> {path}")


if __name__ == "__main__":
    main()
