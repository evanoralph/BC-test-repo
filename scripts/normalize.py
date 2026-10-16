#!/usr/bin/env python3
"""
Normalize raw/<model>/*.json → data/menus.json + data/flags.csv

Applies HANDOVER §8 rules. Default model dir from bake-off winner file if present.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

from enrich import enrich

ROOT = Path(__file__).resolve().parents[1]
KHR_PER_USD = 4000.0

KHMER_DIGITS = str.maketrans("០១២៣៤៥៦៧៨៩", "0123456789")

TAG_RANGES_USD = {
    "chicken": (1.0, 15.0),
    "vegetable": (0.75, 10.0),
    "beer": (0.4, 5.0),
}

# substring keywords (Khmer has no word spaces)
KEYWORDS = {
    "chicken": ["មាន់"],
    "vegetable": ["បន្លែ", "ត្រកួន", "សាឡាដ"],
    "beer": ["ស្រាបៀរ", "បៀរ"],
    "egg": ["ស៊ុត", "ពង"],
    "pork": ["ជ្រូក"],
    "beef": ["គោ"],
    "fish": ["ត្រី"],
    "duck": ["ទា"],
    "salad": ["សាឡាដ", "បុក"],
}

BEER_LATIN = ["angkor", "cambodia", "anchor", "abc", "ganzberg", "klang", "tiger", "heineken"]

EGG_CHICKEN = "ស៊ុតមាន់"  # chicken egg — not chicken meat


def log(msg: str) -> None:
    print(f"[normalize] {msg}", file=sys.stderr, flush=True)


def khmer_to_ascii_digits(s: str) -> str:
    return s.translate(KHMER_DIGITS)


def parse_number(raw: str | None, value) -> float | None:
    if value is not None:
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
    if not raw:
        return None
    s = khmer_to_ascii_digits(str(raw))
    s = s.replace(",", "").replace(" ", "")
    # European-style thousands: 15.000 → 15000 if looks like KHR
    m = re.search(r"(\d+)[.](\d{3})\b", s)
    if m and "$" not in str(raw):
        s = s.replace(m.group(0), m.group(1) + m.group(2), 1)
    mult = 1.0
    if re.search(r"[Kk]|ពាន់", str(raw)):
        mult = 1000.0
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    if not nums:
        return None
    try:
        n = float(nums[0]) * mult
        return n
    except ValueError:
        return None


def infer_currency(currency: str | None, price_value: float | None, price_raw: str | None) -> tuple[str, bool, list[str]]:
    flags: list[str] = []
    cur = (currency or "unknown").upper()
    if cur in ("USD", "KHR"):
        return cur, False, flags
    raw = str(price_raw or "")
    if "$" in raw or "ដុល្លារ" in raw or "USD" in raw.upper():
        return "USD", True, flags
    if "៛" in raw or "រៀល" in raw or "KHR" in raw.upper():
        return "KHR", True, flags
    if price_value is None:
        flags.append("currency_unknown")
        return "unknown", True, flags
    # A9
    if "." in raw and price_value <= 50:
        return "USD", True, flags
    if price_value <= 50:
        return "USD", True, flags
    if price_value >= 500:
        return "KHR", True, flags
    flags.append("currency_ambiguous")
    return "unknown", True, flags


def to_usd(currency: str, price_value: float | None) -> float | None:
    if price_value is None:
        return None
    if currency == "USD":
        return float(price_value)
    if currency == "KHR":
        return float(price_value) / KHR_PER_USD
    return None


def keyword_tags(name_km: str, name_en: str) -> set[str]:
    km = name_km or ""
    en = (name_en or "").lower()
    found: set[str] = set()
    # chicken egg trap
    if EGG_CHICKEN in km:
        found.add("egg")
    for tag, words in KEYWORDS.items():
        for w in words:
            if w in km:
                if tag == "chicken" and EGG_CHICKEN in km:
                    continue
                found.add(tag)
    for brand in BEER_LATIN:
        if brand in en or brand in km.lower():
            found.add("beer")
    if "chicken" in en and "egg" not in en:
        found.add("chicken")
    if any(x in en for x in ("vegetable", "veg ", "salad", "greens", "bean")):
        found.add("vegetable")
    if "beer" in en:
        found.add("beer")
    return found


def slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s.strip().lower()).strip("_")
    return s[:40] or "item"


def normalize_item(raw_item: dict, menu: dict, idx: int) -> dict:
    flags: list[str] = []
    name_km = raw_item.get("name_km") or ""
    name_en = raw_item.get("name_en") or ""
    price_raw = raw_item.get("price_raw")
    price_value = parse_number(price_raw, raw_item.get("price_value"))
    currency, inferred, cflags = infer_currency(
        raw_item.get("currency"), price_value, price_raw
    )
    flags.extend(cflags)
    price_usd = to_usd(currency, price_value)

    model_tags = [t for t in (raw_item.get("tags") or []) if isinstance(t, str)]
    kw = keyword_tags(name_km, name_en)
    for t in ("chicken", "vegetable", "beer"):
        model_has = t in model_tags
        kw_has = t in kw
        if model_has != kw_has and (model_has or kw_has):
            flags.append("tag_disagree")
            break

    for tag, (lo, hi) in TAG_RANGES_USD.items():
        if tag in model_tags and price_usd is not None:
            if price_usd < lo or price_usd > hi:
                flags.append("out_of_range")
                break

    conf = raw_item.get("confidence")
    try:
        conf = float(conf) if conf is not None else 0.5
    except (TypeError, ValueError):
        conf = 0.5
    conf = max(0.0, conf - 0.1 * len(flags))

    restaurant = (
        menu.get("restaurant_name_en")
        or menu.get("restaurant_name_raw")
        or menu.get("menu_id")
    )
    menu_id = menu.get("menu_id") or "unknown"
    item_id = f"{menu_id}_{idx:03d}_{slugify(name_en or name_km)}"

    return {
        "id": item_id,
        "menu_id": menu_id,
        "restaurant": restaurant,
        "source_image": menu.get("_source_file") or menu_id,
        "name_km": name_km,
        "name_en": name_en,
        "section_raw": raw_item.get("section_raw"),
        "price_raw": price_raw,
        "price_value": price_value,
        "price_usd": price_usd,
        "currency": currency,
        "currency_inferred": inferred,
        "size_or_unit": raw_item.get("size_or_unit"),
        "tags": model_tags,
        "multi_unit": bool(raw_item.get("multi_unit")),
        "confidence": round(conf, 3),
        "verified": False,
        "corrected": False,
        "flags": flags,
        "notes": raw_item.get("notes") or "",
    }


def load_raw_menus(raw_model_dir: Path) -> list[dict]:
    files = sorted(raw_model_dir.glob("*.json"))
    files = [f for f in files if not f.name.endswith(".raw_response.json")]
    menus = []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        menus.append(data)
        log(f"loaded {f.name} items={len(data.get('items') or [])}")
    return menus


def group_restaurants(rows: list[dict]) -> list[dict]:
    order: list[str] = []
    by_rest: dict[str, list[dict]] = {}
    for row in rows:
        key = row["restaurant"]
        if key not in by_rest:
            by_rest[key] = []
            order.append(key)
        by_rest[key].append(row)

    restaurants = []
    for key in order:
        items = by_rest[key]
        restaurants.append(
            {
                "id": slugify(key),
                "restaurant": key,
                "source_image": items[0].get("source_image"),
                "menu_ids": sorted({i["menu_id"] for i in items}),
                "items": items,
            }
        )
    return restaurants


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--raw-model-dir",
        type=Path,
        default=None,
        help="e.g. raw/openai__gpt-4o-mini",
    )
    ap.add_argument("--winner-file", type=Path, default=ROOT / "bench" / "results" / "winner.txt")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "menus.json")
    ap.add_argument("--flags-csv", type=Path, default=ROOT / "data" / "flags.csv")
    args = ap.parse_args()

    raw_dir = args.raw_model_dir
    if raw_dir is None:
        if args.winner_file.exists():
            slug = args.winner_file.read_text(encoding="utf-8").strip()
            raw_dir = ROOT / "raw" / slug
            log(f"using winner from {args.winner_file}: {slug}")
        else:
            # prefer first existing raw/* dir
            cands = sorted((ROOT / "raw").glob("*"))
            cands = [c for c in cands if c.is_dir()]
            if not cands:
                raise SystemExit("No raw model dir found; run extract.py first")
            raw_dir = cands[0]
            log(f"no winner file; using {raw_dir}")

    menus = load_raw_menus(raw_dir)
    rows: list[dict] = []
    flag_rows: list[dict] = []
    for menu in menus:
        for i, item in enumerate(menu.get("items") or [], start=1):
            row = normalize_item(item, menu, i)
            rows.append(row)
            for fl in row["flags"]:
                flag_rows.append(
                    {
                        "menu_id": row["menu_id"],
                        "item_id": row["id"],
                        "flag": fl,
                        "price_usd": row["price_usd"],
                        "tags": "|".join(row["tags"]),
                    }
                )

    restaurants = group_restaurants(rows)
    out = {
        "_meta": {
            "dummy": False,
            "source": str(raw_dir.relative_to(ROOT)),
            "item_count": len(rows),
            "restaurant_count": len(restaurants),
            "khr_per_usd": KHR_PER_USD,
            "note": "Normalized from sample extraction; see data/flags.csv and data/corrections.csv",
        },
        "restaurants": restaurants,
    }
    enrich(out)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"wrote {args.out} restaurants={len(restaurants)} items={len(rows)}")

    args.flags_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.flags_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["menu_id", "item_id", "flag", "price_usd", "tags"]
        )
        w.writeheader()
        w.writerows(flag_rows)
    log(f"wrote {args.flags_csv} flags={len(flag_rows)}")


if __name__ == "__main__":
    main()
