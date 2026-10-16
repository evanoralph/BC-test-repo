# Data first look

**Date:** 2026-10-16  
**Scope for this pass:** `data-sets-sample/` (3 PNGs) — full `data-sets/` has 31 PNGs, deferred until sample pipeline works.

## Full dataset (`data-sets/`)

| Field | Value |
|---|---|
| Count | 31 files |
| Format | PNG screenshots (macOS Screenshot naming) |
| Size | ~1.2–5.7 MB each (~125 MB total) |
| Text | Mostly Khmer; some bilingual Khmer+English |
| Prices | Mix of KHR (`៛`), USD (`$`), dual-currency, and some photo menus with weak/no prices |
| Noise | Handwriting, glare, spiral binding, multi-page layouts |

## Sample set (`data-sets-sample/`) — used for testing

| ID | File | Notes |
|---|---|---|
| `sample_01` | Screenshot 2026-07-21 at 11.15.35 AM.png | Photo grid, house specials, **KHR only**, includes chicken feet + green bean dish |
| `sample_02` | Screenshot 2026-07-21 at 11.16.25 AM.png | **Reatry Battambong** — bilingual table, **USD**, dual size columns, red handwriting |
| `sample_03` | Screenshot 2026-07-21 at 11.16.46 AM.png | Same restaurant, grilled page — **USD**, dual prices, some handwritten |

## Observations that affect extraction

1. Sample_02 / sample_03 are the same restaurant (multi-page) — normalize should allow shared `restaurant` name.
2. Dual price columns = one row per size (assumption A12).
3. Handwritten red corrections override printed prices when readable.
4. Sample_01 has a "big plate ×2" note — flag multi_unit / size carefully.
5. Beer may be scarce in this 3-image sample; recommender may need to say "no beer listed" until full set is extracted.

## Decision

Run extract → bake-off → normalize → ship on **sample only**. Point `--input-dir data-sets-sample`. Full 31-menu run is a later switch of the same flag.
