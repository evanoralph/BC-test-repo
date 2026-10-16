#!/usr/bin/env python3
"""
Orchestrate a multi-model extraction bake-off against bench/ground_truth/.

Runs extract.py on gold menu ids (samples + hard menus), then score.py.
Does NOT touch data/menus.json or site/. Logs every step.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DEFAULT_MODELS = [
    "google/gemini-2.5-flash",
    "openai/gpt-4o",
    "google/gemini-2.5-pro",
    # Plan named claude-sonnet-4; OpenRouter slug is 4.5 (4 returns 404).
    "anthropic/claude-sonnet-4.5",
]
SAMPLE_DIR = ROOT / "data-sets-sample"
FULL_DIR = ROOT / "data-sets"
TRUTH_DIR = ROOT / "bench" / "ground_truth"
LOG_PATH = ROOT / "ai_logs" / "bakeoff_stronger.log"


def log(msg: str) -> None:
    line = f"[bakeoff] {msg}"
    print(line, file=sys.stderr, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def gold_menu_ids(truth_dir: Path) -> list[str]:
    ids = []
    for p in sorted(truth_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            mid = data.get("menu_id") or p.stem
        except Exception as e:
            log(f"WARN skip broken gold {p.name}: {e}")
            continue
        ids.append(mid)
    return ids


def run_extract(
    input_dir: Path,
    only: list[str],
    models: list[str],
    workers: int,
    force: bool,
) -> int:
    if not only:
        log(f"skip extract for {input_dir.name}: no matching gold ids")
        return 0
    cmd = [
        sys.executable,
        str(SCRIPTS / "extract.py"),
        "--input-dir",
        str(input_dir),
        "--models",
        *models,
        "--only",
        *only,
        "--workers",
        str(workers),
    ]
    if force:
        cmd.append("--force")
    log(f"extract cmd: {' '.join(cmd)}")
    # Continue bake-off even if some models fail (404 / rate limit).
    proc = subprocess.run(cmd, cwd=str(ROOT))
    log(f"extract exit={proc.returncode} input={input_dir.name} only={only}")
    return proc.returncode


def run_score(models: list[str], out: Path, winner_out: Path) -> str:
    cmd = [
        sys.executable,
        str(SCRIPTS / "score.py"),
        "--models",
        *models,
        "--out",
        str(out),
        "--winner-out",
        str(winner_out),
    ]
    log(f"score cmd: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if proc.stderr:
        for line in proc.stderr.strip().splitlines():
            log(f"score: {line}")
    if proc.returncode != 0:
        log(f"score FAILED exit={proc.returncode}")
        if proc.stdout:
            log(f"score stdout: {proc.stdout.strip()}")
        raise SystemExit(proc.returncode)
    winner = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
    log(f"score winner={winner}")
    return winner


def summarize_csv(csv_path: Path) -> None:
    if not csv_path.exists():
        return
    import csv
    from collections import defaultdict

    composites: dict[str, list[float]] = defaultdict(list)
    with csv_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("metric") == "composite":
                try:
                    composites[row["model"]].append(float(row["value"]))
                except (KeyError, ValueError):
                    continue
    for model, vals in sorted(composites.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
        avg = sum(vals) / len(vals)
        log(f"summary avg_composite {model} = {avg:.4f} n={len(vals)}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Multi-model bake-off vs ground truth")
    ap.add_argument(
        "--models",
        nargs="+",
        default=DEFAULT_MODELS,
        help="OpenRouter model ids",
    )
    ap.add_argument("--truth-dir", type=Path, default=TRUTH_DIR)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument(
        "--force",
        action="store_true",
        help="Re-extract even if raw JSON already exists",
    )
    ap.add_argument(
        "--skip-extract",
        action="store_true",
        help="Only score existing raw predictions",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=ROOT / "bench" / "results" / "bakeoff.csv",
    )
    ap.add_argument(
        "--winner-out",
        type=Path,
        default=ROOT / "bench" / "results" / "winner.txt",
    )
    args = ap.parse_args()

    log(f"=== bakeoff start models={args.models} force={args.force} ===")
    ids = gold_menu_ids(args.truth_dir)
    if not ids:
        raise SystemExit(f"No gold menus in {args.truth_dir}")
    log(f"gold menus ({len(ids)}): {ids}")

    sample_ids = [m for m in ids if m.startswith("sample_")]
    hard_ids = [m for m in ids if m.startswith("menu_")]

    extract_rc = 0
    if not args.skip_extract:
        if sample_ids and SAMPLE_DIR.is_dir():
            rc = run_extract(SAMPLE_DIR, sample_ids, args.models, args.workers, args.force)
            extract_rc = max(extract_rc, rc)
        if hard_ids and FULL_DIR.is_dir():
            rc = run_extract(FULL_DIR, hard_ids, args.models, args.workers, args.force)
            extract_rc = max(extract_rc, rc)
        if extract_rc != 0:
            log(
                f"WARN extract had failures (exit={extract_rc}); "
                "continuing to score whatever raw files exist"
            )
    else:
        log("skip-extract: scoring existing raw only")

    winner = run_score(args.models, args.out, args.winner_out)
    summarize_csv(args.out)
    log(f"=== bakeoff done winner={winner} csv={args.out} ===")
    print(winner)


if __name__ == "__main__":
    main()
