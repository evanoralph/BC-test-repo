# Khmer Menu Intelligence

Budget order finder over extracted Khmer restaurant menus: pick a chicken + vegetable + beer (etc.) combination under a dollar budget.

**Live app:** [https://sandy-aurora-3fby.here.now/](https://sandy-aurora-3fby.here.now/)

## How it works

Vision models extract items from menu images → `scripts/normalize.py` builds `data/menus.json` (prices in USD, tags, confidence flags) → the static app in `site/` enumerates combinations under budget, ranking verified / high-confidence items first. Free-text requests are parsed via an optional here.now LLM proxy; a keyword fallback runs if the proxy fails.

## Pros and cons of this design

In general terms: two problems were split — **reading menus** (uncertain, model-heavy) and **picking a combo under budget** (deterministic, code). The app searches a table; it does not ask a model to invent the order.

### Pros

- **Exact budget math.** Combinations and sums are computed in code, so they are repeatable and easy to audit.
- **Nothing is silently dropped.** Every priced, tagged row can be considered; there is no top-k retrieval that might hide the cheapest beer.
- **Measurable field by field.** Prices, currency, tags, and names can be scored against hand labels; errors stay attributable to extraction, not to a mixed RAG pipeline.
- **Simple to host and debug.** Static JSON + browser logic + one optional parse call. Works offline via keyword fallback.
- **Trust signals in ranking.** Verified / high-confidence items surface first; weak extracts can be flagged instead of papered over.

### Cons

- **Quality is capped by extraction.** Bad OCR/vision (wrong tags, missing currency, truncated menus) flows straight into recommendations.
- **Rigid wants.** Tag-based matching (“chicken”, “vegetable”, “beer”) struggles with fuzzy intent (“something spicy near the river”) without extra layers.
- **Coverage gaps hurt loudly.** Thin beer tagging or symbol-less menus show up as “missing,” not as a soft answer.
- **Human review does not scale by itself.** Hand-corrections and bake-offs improve trust locally; the full catalog still needs a review queue at larger size.
- **Client-controlled parse path.** The browser can alter the LLM request body (mitigated with a spend-capped key); fallback parsing is coarser.

**When a different design fits better:** at much larger scale, or for open-ended discovery, retrieval could propose candidates — but budget arithmetic should stay in code.

## Changelog

- **2026-10-16:** Stronger 7-menu model bake-off summary (this README); Flash remains catalog winner.
- **2026-10-16:** Added ranked “What I don’t trust” (this README) and mirrored it in the app footer (`site/index.html` `#trust`).
- **2026-10-16:** Added general pros/cons of the extract-then-search design.
- **2026-10-16:** Linked the live here.now app URL at the top of this README.

## Model bake-off (summary)

Compared four OpenRouter vision models on **7 hand-labelled menus** (3 samples + hard cases: no prices, beer, dense dual-price, stamp overlays). Full tables: [`notes/bakeoff_stronger.md`](notes/bakeoff_stronger.md). CSV: `bench/results/bakeoff.csv`.

| Model | Avg composite (n=7) |
|---|---:|
| **`google/gemini-2.5-flash`** | **0.959** (winner — catalog model) |
| `google/gemini-2.5-pro` | 0.851 |
| `openai/gpt-4o` | 0.795 |
| `anthropic/claude-sonnet-4.5` | 0.622 |

Flash also led on dense/truncated (`menu_06`) and currency-missing (`menu_01`) boards. On the beer menu (`menu_05`), Flash and Claude both hit beer recall 1.0. No full-catalog re-extract — Flash stays the shipped extractor.

## What I don’t trust

Ranked weakest first. Evidence: stronger bake-off on 7 hand-labelled menus (`bench/results/bakeoff.csv`, [`notes/bakeoff_stronger.md`](notes/bakeoff_stronger.md)), full-set extraction ranking (`notes/extraction_ranking.md`), auto flags (`data/flags.csv`), and sample hand fixes (`data/corrections.csv`).

1. **Currency-missing menus** — `menu_01` and `menu_21` (Independence Monument) score 0.245 quality: every item is `currency_unknown` (18 rows). Recommendations that need those prices are unusable until someone reads the image and assigns KHR/USD.
2. **Low-confidence / incomplete extracts** — `menu_30` has avg confidence 0.66 with all 17 items low-conf; several names are generic `item`. Truncated model responses (`finish_reason=length`) on `menu_27`, `menu_02`, `menu_06` mean later sections may be missing.
3. **Tag noise (especially vegetable)** — ~98 `tag_disagree` flags across the catalog. Bake-off vegetable precision ~0.17 (macro over 3 samples). Sample hand review flipped `special_taro` from vegetable → fish. Chicken tags are better on samples; vegetable over-tagging will pull wrong dishes into “veg” wants.
4. **Suspect prices** — 3 `out_of_range` flags: `menu_17` chicken feet at 22.5 USD; `menu_22` dual-size soup/rice rows at 12.5. Dual-price rows on `menu_06` / `menu_22` (same dish, two sizes) can look like duplicates or wrong unit.
5. **Beer coverage and parse path** — Only ~1 menu in the extract set is tagged beer, so beer wants often report “missing.” LLM parse depends on a here.now proxy; the browser controls the request body (mitigated with a spend-capped key + rate limit). Offline / failed calls use a keyword fallback that may misread quantities.
6. **Khmer / English names** — Exact name match on the bake-off is ~24% weighted (n=21 matched items) vs a predicted 60%. Meaning is often recognizable enough to browse, but citations and fuzzy matching stay noisy.

### Verify first (with more time)

1. Source images for `menu_01`, `menu_21`, then `menu_30`.
2. Every `out_of_range` price row (`menu_17`, `menu_22`).
3. High-impact chicken / vegetable / beer candidates that the recommender would pick (especially vegetable-tagged salads and “special” dishes).
4. Truncated menus (`menu_27`, `menu_02`, `menu_06`) — re-extract with higher token limits.
5. Beer-bearing menus if any were under-tagged.

## Accuracy: predicted vs revised

Predicted numbers were set in [`docs/PLAN.md`](docs/PLAN.md) **before** any menu was processed.

| Field | Predicted | Revised (evidence) |
|---|---|---|
| Prices (numeric) | ~85% | ~95–100% on matched bake-off items (**n=21** matched across 3 sample menus); 1 hand price fix (4.55→4.5). Full set still has 3 `out_of_range` rows and dual-price ambiguity. |
| Currency | ~85% | ~100% when a currency symbol is present (bake-off). Fails hard when menus omit symbols (`menu_01` / `menu_21`). Usable USD across the ~627-item catalog is closer to **~80–90%** once unknowns are counted. |
| Tags (chicken / vegetable / beer) | ~85% | **Lower than predicted.** Vegetable especially weak (bake-off veg precision ~0.17; many `tag_disagree`). Chicken better on samples after hand review. Beer: too few positives to claim a %. |
| Names (exact / recognizably correct) | ~60% / ~75% | Exact ~**24%** (n=21). Meaning still usable for browsing but below the 75% prediction. |

**Intervals:** with n ≈ 20–50 items, a 95% confidence interval is roughly **±10–15 points** (see [`docs/HANDOVER.md`](docs/HANDOVER.md) calibration). Treat these as directional, not precise.

**Why revised differs from the prediction:** the pre-processing estimate assumed uniform difficulty. Measurement showed **prices and currency are stronger when symbols exist**, while **tags and exact Khmer transcription are weaker**, and **symbol-less menus** drag currency usability down. Correction rate on hand-verified sample rows (7 edits: restaurant rename, one tag/name, one price) is a second, small-n signal — not a full audit of 627 items.

## Hand-corrected data

Logged in [`data/corrections.csv`](data/corrections.csv) (sample menus only; chicken/vegetable/beer-relevant review, not the full catalog):

| Menu | Item / scope | Field | Change | Reason |
|---|---|---|---|---|
| `sample_01` | `*` | restaurant | → House Specials (BEST SELLER) | Model left restaurant null |
| `sample_01` | `special_taro` | tags | vegetable → fish | Image review |
| `sample_01` | `special_taro` | name_en | → Fish triangles (hand-corrected) | Image vs Khmer label |
| `sample_01` | `special_taro` | flags | cleared `tag_disagree` | After tag fix |
| `sample_02` | `fried_beef_pork_chicken` | price_value / price_usd / price_raw | 4.55 → 4.5 | Print ~4.5$ |

## Related docs

- Plan + original prediction: [`docs/PLAN.md`](docs/PLAN.md)
- Assumptions: [`docs/ASSUMPTIONS.md`](docs/ASSUMPTIONS.md)
- Playbook: [`docs/HANDOVER.md`](docs/HANDOVER.md)
- Extraction ranking: [`notes/extraction_ranking.md`](notes/extraction_ranking.md)
- Sample bake-off: [`notes/bakeoff_sample.md`](notes/bakeoff_sample.md)
- Stronger 7-menu bake-off (Flash vs Pro / GPT-4o / Claude): [`notes/bakeoff_stronger.md`](notes/bakeoff_stronger.md)
