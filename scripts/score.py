#!/usr/bin/env python3
"""Score predicted raw extractions against bench/ground_truth/*.json"""
from __future__ import annotations

import argparse
import csv
import difflib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def log(msg: str) -> None:
    print(f"[score] {msg}", file=sys.stderr, flush=True)


def similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a or "", b or "").ratio()


def match_items(pred: list[dict], truth: list[dict]) -> list[tuple[dict | None, dict | None]]:
    used = set()
    pairs = []
    for p in pred:
        best_j, best_score = None, 0.0
        for j, t in enumerate(truth):
            if j in used:
                continue
            pv = p.get("price_value")
            tv = t.get("price_value")
            price_ok = pv is not None and tv is not None and abs(float(pv) - float(tv)) < 0.01
            name_sim = similar(str(p.get("name_km") or ""), str(t.get("name_km") or ""))
            # also try English for bilingual menus
            name_sim = max(
                name_sim,
                similar(str(p.get("name_en") or "").lower(), str(t.get("name_en") or "").lower()),
            )
            score = (0.5 if price_ok else 0.0) + 0.5 * name_sim
            if price_ok and name_sim >= 0.7:
                score += 0.2
            elif name_sim >= 0.7:
                score += 0.1
            if score > best_score:
                best_score, best_j = score, j
        if best_j is not None and best_score >= 0.55:
            used.add(best_j)
            pairs.append((p, truth[best_j]))
        else:
            pairs.append((p, None))  # hallucination candidate
    for j, t in enumerate(truth):
        if j not in used:
            pairs.append((None, t))  # miss
    return pairs


def metrics_for_menu(pred_items: list[dict], truth_items: list[dict]) -> dict:
    pairs = match_items(pred_items, truth_items)
    matched = [(p, t) for p, t in pairs if p and t]
    hallucinations = sum(1 for p, t in pairs if p and not t)
    misses = sum(1 for p, t in pairs if t and not p)
    n_truth = len(truth_items) or 1
    n_pred = len(pred_items) or 1

    price_exact = 0
    currency_ok = 0
    name_ok = 0
    tag_stats = {k: {"tp": 0, "fp": 0, "fn": 0} for k in ("chicken", "vegetable", "beer")}

    for p, t in matched:
        if p.get("price_value") is not None and t.get("price_value") is not None:
            if abs(float(p["price_value"]) - float(t["price_value"])) < 0.01:
                price_exact += 1
        if (p.get("currency") or "").upper() == (t.get("currency") or "").upper():
            currency_ok += 1
        if similar(str(p.get("name_km") or ""), str(t.get("name_km") or "")) >= 0.9 or similar(
            str(p.get("name_en") or "").lower(), str(t.get("name_en") or "").lower()
        ) >= 0.9:
            name_ok += 1
        pt = set(p.get("tags") or [])
        tt = set(t.get("tags") or [])
        for tag in tag_stats:
            if tag in pt and tag in tt:
                tag_stats[tag]["tp"] += 1
            elif tag in pt and tag not in tt:
                tag_stats[tag]["fp"] += 1
            elif tag not in pt and tag in tt:
                tag_stats[tag]["fn"] += 1

    n_m = len(matched) or 1
    out = {
        "item_recall": len(matched) / n_truth,
        "hallucination_rate": hallucinations / n_pred,
        "price_exact": price_exact / n_m,
        "currency_acc": currency_ok / n_m,
        "name_correct": name_ok / n_m,
        "n_truth": len(truth_items),
        "n_pred": len(pred_items),
        "n_matched": len(matched),
        "n_miss": misses,
    }
    for tag, s in tag_stats.items():
        prec = s["tp"] / (s["tp"] + s["fp"]) if (s["tp"] + s["fp"]) else 0.0
        rec = s["tp"] / (s["tp"] + s["fn"]) if (s["tp"] + s["fn"]) else 0.0
        out[f"{tag}_precision"] = prec
        out[f"{tag}_recall"] = rec
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth-dir", type=Path, default=ROOT / "bench" / "ground_truth")
    ap.add_argument("--raw-root", type=Path, default=ROOT / "raw")
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--out", type=Path, default=ROOT / "bench" / "results" / "bakeoff.csv")
    ap.add_argument("--winner-out", type=Path, default=ROOT / "bench" / "results" / "winner.txt")
    args = ap.parse_args()

    truth_files = sorted(args.truth_dir.glob("*.json"))
    if not truth_files:
        raise SystemExit(f"No ground truth in {args.truth_dir}")

    rows = []
    model_scores: dict[str, list[float]] = {m: [] for m in args.models}

    for tf in truth_files:
        truth = json.loads(tf.read_text(encoding="utf-8"))
        menu_id = truth.get("menu_id") or tf.stem
        for model in args.models:
            slug = model.replace("/", "__")
            pred_path = args.raw_root / slug / f"{menu_id}.json"
            if not pred_path.exists():
                log(f"missing prediction {pred_path}")
                continue
            pred = json.loads(pred_path.read_text(encoding="utf-8"))
            m = metrics_for_menu(pred.get("items") or [], truth.get("items") or [])
            # composite for winner: price + currency + tag chicken/veg/beer recall
            composite = (
                m["price_exact"]
                + m["currency_acc"]
                + m["item_recall"]
                + 0.5 * (m["chicken_recall"] + m["vegetable_recall"] + m["beer_recall"])
            ) / 3.5
            model_scores[model].append(composite)
            for metric, val in m.items():
                rows.append(
                    {
                        "model": model,
                        "menu_id": menu_id,
                        "metric": metric,
                        "value": round(val, 4) if isinstance(val, float) else val,
                    }
                )
            rows.append(
                {
                    "model": model,
                    "menu_id": menu_id,
                    "metric": "composite",
                    "value": round(composite, 4),
                }
            )
            log(f"{model} {menu_id} composite={composite:.3f} recall={m['item_recall']:.2f}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["model", "menu_id", "metric", "value"])
        w.writeheader()
        w.writerows(rows)
    log(f"wrote {args.out}")

    avgs = {}
    for model, scores in model_scores.items():
        avgs[model] = sum(scores) / len(scores) if scores else -1
        log(f"avg composite {model} = {avgs[model]:.4f} n={len(scores)}")
    winner = max(avgs, key=avgs.get)
    slug = winner.replace("/", "__")
    args.winner_out.write_text(slug + "\n", encoding="utf-8")
    log(f"winner={winner} -> {args.winner_out}")
    print(winner)


if __name__ == "__main__":
    main()
