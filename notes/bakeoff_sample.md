# Bake-off (sample set)

**Input:** `data-sets-sample/` (3 PNGs)  
**Prompt:** `prompts/extract_v1.txt`  
**Models:** `openai/gpt-4o-mini` vs `google/gemini-2.5-flash`

## Results (composite avg)

| Model | Avg composite | Notes |
|---|---|---|
| openai/gpt-4o-mini | 0.53 | Missed most of sample_02 dual-price rows |
| **google/gemini-2.5-flash** | **0.96** | Winner — saved in `bench/results/winner.txt` |

Raw metrics: `bench/results/bakeoff.csv`  
Full-dataset extraction ranking: [`notes/extraction_ranking.md`](extraction_ranking.md)

## Downstream

- Normalized winner → `data/menus.json` (57 items, 2 restaurants)
- Hand corrections → `data/corrections.csv` (7 rows)
- Shipped → `site/menus.json` (`sample_only: true`)

## Known sample gap

No beer items appear in these 3 menus. Example query needing beers will report missing beer until `data-sets/` (31) is extracted:

```bash
python3 scripts/extract.py --input-dir data-sets --models google/gemini-2.5-flash
python3 scripts/normalize.py
python3 scripts/verify_sample.py   # or a fuller verify pass
cp data/menus.json site/menus.json
```
