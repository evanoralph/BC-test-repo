# Stronger bake-off (7 gold menus)

**Date:** 2026-10-16  
**Gold:** 3 samples + 4 hard full-set menus (`menu_01`, `menu_05`, `menu_06`, `menu_30`)  
**Prompt:** `prompts/extract_v1.txt`  
**Orchestrator:** `python3 scripts/bakeoff.py`  
**Raw metrics:** `bench/results/bakeoff.csv`  
**Winner file:** `bench/results/winner.txt` → `google__gemini-2.5-flash`  
**Log:** `ai_logs/bakeoff_stronger.log`

## Why these menus

| Menu | Stress |
|---|---|
| `sample_01`–`03` | Existing hand labels (clean / dual-price / bilingual) |
| `menu_01` | No printed prices → currency must be `unknown` |
| `menu_05` | Beer-bearing drinks section |
| `menu_06` | Dense dual-price + truncation risk |
| `menu_30` | Handwritten/stamp overlays on USD dual sizes |

## Models

| Model | Notes |
|---|---|
| `google/gemini-2.5-flash` | Current catalog baseline |
| `google/gemini-2.5-pro` | Stronger Gemini; often truncated on dense menus |
| `openai/gpt-4o` | Re-run with `frequency_penalty=0` (0.4 caused mid-JSON key loops) |
| `anthropic/claude-sonnet-4.5` | Plan named `claude-sonnet-4`; that slug 404s on OpenRouter |

## Avg composite (n=7 menus)

| Model | Avg composite | Item recall | Price | Currency | Name | Chick R | Veg R | Beer R | Halluc |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **`google/gemini-2.5-flash`** | **0.959** | 0.82 | 0.84 | 1.00 | 0.52 | 0.71 | 0.54 | 0.14 | 0.31 |
| `google/gemini-2.5-pro` | 0.851 | 0.63 | 0.83 | 1.00 | 0.47 | 0.52 | 0.50 | 0.00 | 0.27 |
| `openai/gpt-4o` | 0.795 | 0.66 | 0.85 | 0.85 | 0.37 | 0.40 | 0.34 | 0.12 | 0.28 |
| `anthropic/claude-sonnet-4.5` | 0.622 | 0.59 | 0.68 | 0.71 | 0.33 | 0.14 | 0.10 | 0.14 | 0.49 |

Beer recall is near zero in the macro average because only `menu_05` / `menu_06` have beer gold; on **`menu_05` alone** Flash and Claude both hit **beer_recall = 1.0**, GPT-4o **0.86**, Pro **0.0** (truncated before drinks).

## Per-menu composite

| Menu | Flash | Pro | GPT-4o | Claude 4.5 |
|---|---:|---:|---:|---:|
| sample_01 | 1.143 | 1.143 | 0.968 | 0.857 |
| sample_02 | 0.878 | 0.983 | 0.990 | 0.000 |
| sample_03 | 0.857 | 0.857 | 0.821 | 0.857 |
| menu_01 | 0.683 | 0.651 | 0.317 | 0.317 |
| menu_05 | 1.143 | 0.845 | 1.082 | 1.000 |
| menu_06 | 1.097 | 0.576 | 0.395 | 0.794 |
| menu_30 | 0.914 | 0.905 | 0.989 | 0.529 |

## Decision

**Keep `google/gemini-2.5-flash` as the catalog model.** It leads on average composite and especially on dense/truncated menus (`menu_06`) and currency-missing boards (`menu_01`). No full `data-sets/` re-extract.

GPT-4o wins a couple of individual menus (`sample_02`, `menu_30`) but loses overall. Claude over-extracts dual-price rows (high hallucination; `sample_02` composite 0). Pro truncates large menus hard (`menu_06` salvaged to 1 item).

## Tooling changes (non-breaking)

- `scripts/bakeoff.py` — extract gold ids → score → log
- `scripts/extract.py` — stronger JSON salvage; `frequency_penalty=0` for OpenAI

## Re-run

```bash
python3 scripts/bakeoff.py
# score only:
python3 scripts/bakeoff.py --skip-extract
```

Prior sample-only bake-off: [`bakeoff_sample.md`](bakeoff_sample.md)
