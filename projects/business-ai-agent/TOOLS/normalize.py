"""Normalisation for collected marketplace rows: base product vs variant."""

import re

COLORS = {
    "черный", "чёрный", "белый", "зеленый", "зелёный", "синий", "красный",
    "серый", "розовый", "голубой", "желтый", "жёлтый", "фиолетовый",
    "black", "white", "green", "blue", "red", "grey", "gray", "pink",
}

SIZE_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s?(гб|gb|тб|tb|мл|ml|л|l|см|cm|мм|mm|вт|w|мач|mah)\b",
    re.IGNORECASE,
)

STOPWORDS = {"наушники", "смартфон", "чехол", "купить", "новый", "новая"}


def variant_of(title):
    """Return {'color': ..., 'size': ...} found in the title ('' when absent)."""
    lowered = title.lower()
    color = next((c for c in COLORS if re.search(rf"\b{re.escape(c)}\b", lowered)), "")
    sizes = [m.group(0).replace(" ", "").lower() for m in SIZE_RE.finditer(lowered)]
    return {"color": color, "size": ", ".join(sizes)}


def base_title(title):
    """Title with colour and size words removed, lowercased and compacted."""
    lowered = re.sub(r"\[sample\]", "", title.lower())
    lowered = SIZE_RE.sub(" ", lowered)
    words = [w for w in re.split(r"[^a-zа-я0-9.]+", lowered) if w]
    words = [w for w in words if w not in COLORS and w not in STOPWORDS]
    return " ".join(words)


def canonical_key(row):
    """Key that groups variants of one product across marketplaces."""
    brand = (row.get("brand") or "").strip().lower()
    model = (row.get("model") or "").strip().lower()
    if brand and model:
        return f"{brand} {model}"
    return base_title(row["title"])


def group_variants(rows):
    """Group rows by canonical product key, keeping the variants inside each group."""
    groups = {}
    for row in rows:
        key = canonical_key(row)
        group = groups.setdefault(key, {"key": key, "marketplaces": set(), "offers": 0, "variants": []})
        group["marketplaces"].add(row["marketplace"])
        group["offers"] += 1
        variant = variant_of(row["title"])
        label = " / ".join(v for v in (variant["color"], variant["size"]) if v)
        if label and label not in group["variants"]:
            group["variants"].append(label)
    for group in groups.values():
        group["marketplaces"] = sorted(group["marketplaces"])
    return list(groups.values())
