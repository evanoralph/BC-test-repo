#!/usr/bin/env python3
"""
Enrich data/menus.json in place with derived categories:

  dish_key     — normalized dish identity, shared across restaurants
                 ("Grilled Beef" and "Beef grilled" → "beef_grilled")
  price_tiers  — {tag: "budget" | "mid" | "premium"} per item, by tercile of
                 price_usd among priced single-unit items carrying that tag

Idempotent: safe to re-run after verify_sample.py; does not touch other fields.
Also called from normalize.py so fresh builds get the same fields.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TIERS = ("budget", "mid", "premium")
MIN_ITEMS_PER_TAG = 6  # fewer priced items than this → no tiers for that tag

STOPWORDS = {"with", "and", "the", "in", "of", "a", "on", "style", "&"}
KHMER_DIGITS = "០១២៣៤៥៦៧៨៩"


def log(msg: str) -> None:
    print(f"[enrich] {msg}", file=sys.stderr, flush=True)


def _singular(tok: str) -> str:
    if len(tok) > 3 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def dish_key(name_en: str | None, name_km: str | None) -> str | None:
    """Order-insensitive token key from the English name; Khmer fallback."""
    en = re.sub(r"[^a-z0-9]+", " ", (name_en or "").lower())
    toks = sorted({_singular(t) for t in en.split() if t not in STOPWORDS and not t.isdigit()})
    if toks:
        return "_".join(toks)
    km = re.sub(rf"[\s\d{KHMER_DIGITS}().,/\-]+", "", name_km or "")
    return f"km_{km}" if km else None


def _percentile(sorted_vals: list[float], q: float) -> float:
    pos = (len(sorted_vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def _tierable(item: dict) -> bool:
    return isinstance(item.get("price_usd"), (int, float)) and not item.get("multi_unit")


def tag_thresholds(items: list[dict]) -> dict[str, dict]:
    prices: dict[str, list[float]] = {}
    for it in items:
        if not _tierable(it):
            continue
        for tag in it.get("tags") or []:
            prices.setdefault(tag, []).append(float(it["price_usd"]))
    out = {}
    for tag, vals in sorted(prices.items()):
        if len(vals) < MIN_ITEMS_PER_TAG:
            continue
        vals.sort()
        out[tag] = {
            "n": len(vals),
            "p33": round(_percentile(vals, 1 / 3), 2),
            "p67": round(_percentile(vals, 2 / 3), 2),
        }
    return out


def tier_for(price: float, th: dict) -> str:
    if price <= th["p33"]:
        return TIERS[0]
    if price <= th["p67"]:
        return TIERS[1]
    return TIERS[2]


def enrich(data: dict) -> dict:
    items = [it for r in data["restaurants"] for it in r["items"]]
    thresholds = tag_thresholds(items)
    for it in items:
        it["dish_key"] = dish_key(it.get("name_en"), it.get("name_km"))
        tiers = {}
        if _tierable(it):
            for tag in it.get("tags") or []:
                if tag in thresholds:
                    tiers[tag] = tier_for(float(it["price_usd"]), thresholds[tag])
        it["price_tiers"] = tiers

    keys = [it["dish_key"] for it in items if it["dish_key"]]
    shared = {k for k in keys if len({i["restaurant"] for i in items if i["dish_key"] == k}) > 1}
    data["_meta"]["price_tier_thresholds_usd"] = thresholds
    data["_meta"]["dish_key_count"] = len(set(keys))
    data["_meta"]["dish_keys_multi_restaurant"] = len(shared)
    log(
        f"items={len(items)} dish_keys={len(set(keys))} "
        f"shared_across_restaurants={len(shared)} tiered_tags={len(thresholds)}"
    )
    return data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--menus", type=Path, default=ROOT / "data" / "menus.json")
    ap.add_argument("--site-copy", type=Path, default=ROOT / "site" / "menus.json")
    args = ap.parse_args()

    data = json.loads(args.menus.read_text(encoding="utf-8"))
    text = json.dumps(enrich(data), ensure_ascii=False, indent=2)
    args.menus.write_text(text, encoding="utf-8")
    log(f"wrote {args.menus}")
    if args.site_copy:
        args.site_copy.write_text(text, encoding="utf-8")
        log(f"copied to {args.site_copy}")


if __name__ == "__main__":
    main()
