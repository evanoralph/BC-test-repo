#!/usr/bin/env python3
"""
Apply targeted hand-verification on chicken/vegetable/beer rows for the sample set.
Logs every change to data/corrections.csv. Safe: only mutates data/menus.json.
"""
from __future__ import annotations

import csv
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MENUS = ROOT / "data" / "menus.json"
CORRECTIONS = ROOT / "data" / "corrections.csv"
SITE = ROOT / "site" / "menus.json"


def log(msg: str) -> None:
    print(f"[verify] {msg}", file=sys.stderr, flush=True)


def find_item(data: dict, item_id: str):
    for r in data["restaurants"]:
        for it in r["items"]:
            if it["id"] == item_id:
                return r, it
    return None, None


def apply(data: dict, corrections: list[dict], item_id: str, field: str, new_value, reason: str):
    rest, it = find_item(data, item_id)
    if not it:
        log(f"WARN missing item {item_id}")
        return
    old = deepcopy(it.get(field))
    if old == new_value:
        log(f"no-op {item_id}.{field} already {new_value!r}")
        return
    it[field] = new_value
    it["corrected"] = True
    corrections.append(
        {
            "menu": it.get("menu_id"),
            "item_id": item_id,
            "field": field,
            "old_value": json.dumps(old, ensure_ascii=False) if not isinstance(old, str) else old,
            "new_value": json.dumps(new_value, ensure_ascii=False)
            if not isinstance(new_value, str)
            else new_value,
            "reason": reason,
        }
    )
    log(f"correct {item_id}.{field}: {old!r} -> {new_value!r} ({reason})")


def mark_verified(data: dict, item_ids: list[str]):
    for iid in item_ids:
        _, it = find_item(data, iid)
        if it:
            it["verified"] = True
            log(f"verified {iid}")


def main() -> None:
    data = json.loads(MENUS.read_text(encoding="utf-8"))
    corrections: list[dict] = []

    # Fix orphan restaurant label for sample_01
    for r in data["restaurants"]:
        if r["id"] == "sample_01" or r["restaurant"] == "sample_01":
            old = r["restaurant"]
            r["restaurant"] = "House Specials (BEST SELLER)"
            r["id"] = "house_specials_best_seller"
            for it in r["items"]:
                it["restaurant"] = r["restaurant"]
            corrections.append(
                {
                    "menu": "sample_01",
                    "item_id": "*",
                    "field": "restaurant",
                    "old_value": old,
                    "new_value": r["restaurant"],
                    "reason": "model left restaurant null; use section title",
                }
            )
            log(f"restaurant rename {old} -> {r['restaurant']}")

    # sample_01: Special Taro looks like a misread of fish dish (ត្រីកោន) — not a veg dish
    apply(
        data,
        corrections,
        "sample_01_002_special_taro",
        "tags",
        ["fish"],
        "image review: not vegetable; treat as fish dish",
    )
    apply(
        data,
        corrections,
        "sample_01_002_special_taro",
        "name_en",
        "Fish triangles (hand-corrected)",
        "image review vs Khmer photo label",
    )
    if "tag_disagree" in (find_item(data, "sample_01_002_special_taro")[1] or {}).get("flags", []):
        flags = [
            f
            for f in find_item(data, "sample_01_002_special_taro")[1]["flags"]
            if f != "tag_disagree"
        ]
        apply(
            data,
            corrections,
            "sample_01_002_special_taro",
            "flags",
            flags,
            "cleared after tag correction",
        )

    # sample_02: price 4.55 likely OCR of 4.50 / 4.5$
    apply(
        data,
        corrections,
        "sample_02_009_fried_beef_pork_chicken",
        "price_value",
        4.5,
        "menu print ~4.5$; model wrote 4.55",
    )
    apply(
        data,
        corrections,
        "sample_02_009_fried_beef_pork_chicken",
        "price_usd",
        4.5,
        "menu print ~4.5$; model wrote 4.55",
    )
    apply(
        data,
        corrections,
        "sample_02_009_fried_beef_pork_chicken",
        "price_raw",
        "4.5$",
        "normalize price_raw to printed form",
    )

    # Meta note: no beer in sample
    data["_meta"]["sample_only"] = True
    data["_meta"]["beer_available"] = False
    data["_meta"]["note"] = (
        "Sample extraction (3 menus). No beer rows found in sample — "
        "recommender may report missing beer until full data-sets/ run."
    )
    data["_meta"]["dummy"] = False

    verify_ids = [
        "sample_01_007_garlic_chicken_feet",
        "sample_01_005_pounded_long_beans_with_smoked_fish",
        "sample_02_001_fried_chicken_fish_pork_beef_with_ginger",
        "sample_02_002_fried_chicken_fish_pork_beef_with_ginger",
        "sample_02_021_intestines_with_vegetable",
        "sample_03_015_grilled_mushroom_with_salt_chili",
        "sample_03_016_grilled_mushroom_with_salt_chili",
        "sample_03_019_grilled_chicken_with_chili_salt",
    ]
    mark_verified(data, verify_ids)

    MENUS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"wrote {MENUS}")

    CORRECTIONS.parent.mkdir(parents=True, exist_ok=True)
    with CORRECTIONS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["menu", "item_id", "field", "old_value", "new_value", "reason"],
        )
        w.writeheader()
        w.writerows(corrections)
    log(f"wrote {CORRECTIONS} n={len(corrections)}")

    SITE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"copied to {SITE}")


if __name__ == "__main__":
    main()
