# Handover: Khmer Menu Intelligence Challenge

Use this file to pick up the work locally (for example in Claude Code: "read HANDOVER.md and continue from the first unchecked step").
`PLAN.md` and `ASSUMPTIONS.md` are ready-to-commit drafts of the 15-minute deliverables.

---

## 1. Status at handover

- **Done:**
  - Strategy and architecture decided (§3).
  - Plan and assumptions drafted.
  - here.now proxy and variable details checked against the official docs (§5).
- **Not done:**
  - Dataset not inspected yet.
  - No code written.
  - Nothing deployed.
- **Next action:** Step 1 in §4 (look at the data). Then adjust and send `PLAN.md` at the 15-minute mark.

## 2. The task in one paragraph

About 30 Khmer restaurant menus. Build a live here.now web app that answers *"$10 budget, chicken, some vegetables, a couple of beers: what should I order and from where?"* Every recommended item must cite:
- the source menu,
- the item and price exactly as printed,
- the total against the budget.

The data must come from my extraction, not hardcoded answers. No API key may be visible in the page.

They grade judgement and calibrated self-assessment, not polish. The required deliverables are:
- plan and accuracy prediction (15 min)
- assumptions list
- live permanent link
- "what I don't trust" section with a revised accuracy estimate
- repo with benchmarks and AI usage logs
- 15-minute debrief

## 3. Key decisions and why

| Decision | Why |
|---|---|
| Extract menus **offline** into one `menus.json` | The hard, uncertain part stays in one place I can measure. The live app has nothing fragile in it. |
| Recommender is **deterministic JavaScript in the browser** | It checks every combination exactly, gives the same answer every time, and its citations are fields from real rows, so they can't be hallucinated. |
| **One** live LLM call, for parsing the user's request, through a here.now proxy route | The key stays server-side. A regex parser takes over if the proxy fails, so the app never depends on it. |
| Benchmark **two models on hand-labelled menus** before running all 30 | Pick the model by measurement and get real numbers for the accuracy estimate. |
| Hand-verify **only chicken, vegetable and beer candidate rows** | Human time goes where it changes the answer. The correction rate becomes evidence for the revised accuracy estimate. |
| An order comes from a **single restaurant** | "From where" implies one place. |
| **No RAG** | See §12. Short version: this is a filter-and-optimize problem over a table, not a relevance-retrieval problem. |

## 4. Step-by-step checklist (times are relative to clock start)

- [ ] **0:00–0:10 Look at the data.** Count the files, note their formats (photo, scan, PDF, text), and skim about 5 menus for currency style, handwriting, and bilingual versus Khmer-only. Don't process anything yet. Write `notes/data_first_look.md`.
  - If the dataset is **text or PDF rather than images**, check for legacy Khmer font encodings (Limon etc.). These show up as Latin gibberish and need conversion or a switch to image OCR.
- [ ] **0:10–0:15 Finalize `PLAN.md` and `ASSUMPTIONS.md`.** Set your own accuracy numbers, commit, and send.
- [ ] **0:15–0:45 Deploy a skeleton** (§5). Publish `site/index.html` and a placeholder `menus.json` clearly labelled as dummy data. Set up the proxy route and test one call. View the deployed page source and confirm the key is not in it. Commit.
- [ ] **0:45–1:05 Ground truth.** Hand-label 3 different menus (one clean print, one photo, one dual-currency or handwritten) into `bench/ground_truth/<menu>.json` (§9).
- [ ] **1:05–1:20 Model bake-off.** Run two vision models with `prompts/extract_v1.txt` on those 3 menus. Score them with `bench/score.py`, save `bench/results/bakeoff.csv`, and pick the winner.
- [ ] **1:20–1:45 Full extraction.** Run the winner over all menus in parallel. Save each response untouched to `raw/<model>/<menu>.json`.
- [ ] **1:45–2:00 Normalize and validate** (§8). Write `scripts/normalize.py`, which produces `data/menus.json` and `data/flags.csv`.
- [ ] **2:00–2:15 Targeted hand-verification.** For each restaurant, check the cheapest few chicken, vegetable and beer rows against the image. Set `verified: true` and log every fix in `data/corrections.csv` (menu, item, field, old value, new value).
- [ ] **2:15–2:30 Recommender and UI** (§10). Copy `data/menus.json` to `site/` and redeploy.
- [ ] **2:30–2:45 Write the README:** "What I don't trust" (ranked), revised accuracy with n and interval, how it was built, and which data was hand-corrected. Mirror the trust section in the app.
- [ ] **2:45–3:00 Buffer and submit** (§14).

## 5. here.now setup (checked against here.now/docs)

**Install and authenticate**
```bash
npx skills add heredotnow/skill --skill here-now -g        # gives the agent scripts/publish.sh
# Get an API key: dashboard sign-in at https://here.now/dashboard, or the agent email-code flow in the docs
mkdir -p ~/.herenow && echo "<HERENOW_API_KEY>" > ~/.herenow/credentials && chmod 600 ~/.herenow/credentials
```
An authenticated publish is permanent. An anonymous one expires after 24 hours and counts as a missing link. Proxy routes only work on authenticated sites.

**Store the model key as an account variable.** It never goes in the repo or the page.
```bash
curl -sS -X PUT https://here.now/api/v1/me/variables/ANTHROPIC_API_KEY \
  -H "Authorization: Bearer $(cat ~/.herenow/credentials)" \
  -H "content-type: application/json" \
  -d '{"value":"<MODEL_API_KEY>","allowedUpstreams":["api.anthropic.com"]}'
```
Names must be uppercase letters, digits and underscores. `allowedUpstreams` pins the key so it can only be sent to that host.

**`site/.herenow/proxy.json`.** The top-level `"proxies"` wrapper is required, and keys must start with `/`.
```json
{
  "proxies": {
    "/api/parse": {
      "upstream": "https://api.anthropic.com/v1/messages",
      "method": "POST",
      "headers": {
        "x-api-key": "${ANTHROPIC_API_KEY}",
        "anthropic-version": "2023-06-01"
      },
      "rateLimit": "30/hour/ip"
    }
  }
}
```
The docs' own example uses OpenRouter (`"upstream": "https://openrouter.ai/api/v1/chat/completions"` with `"Authorization": "Bearer ${OPENROUTER_API_KEY}"`). If the Anthropic route misbehaves, switch to that, since it's the documented path. If Anthropic returns an error about CORS or browser access, add `"anthropic-dangerous-direct-browser-access": "true"` to the headers. That's safe here because the key is injected server-side.

**Call it from the browser** with a relative URL and a fallback:
```js
async function parseQuery(text) {
  try {
    const ctrl = new AbortController(); setTimeout(() => ctrl.abort(), 8000);
    const r = await fetch('/api/parse', { method: 'POST', signal: ctrl.signal,
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ model: 'claude-haiku-5-5', max_tokens: 300,
        messages: [{ role: 'user', content: PARSE_PROMPT + text }] }) });
    if (!r.ok) throw new Error(r.status);
    return { ...JSON.parse((await r.json()).content[0].text), parser: 'llm' };
  } catch (e) { return { ...regexParse(text), parser: 'fallback' }; }   // always works
}
```
Check the current model ID before deploying.

**Gotchas from the docs**
- **An invalid `proxy.json` does not fail the publish.** Routes are silently disabled and return 404. Always read the `warnings` in the finalize response.
- **Proxy routes don't carry over between versions.** Include `.herenow/proxy.json` in every publish.
- **Rate limits:** the default is 100 requests per hour per IP; the per-route `rateLimit` above overrides it. Request bodies are capped at 10 MB.
- **`proxy.json` is never served to visitors.** It only contains `${VAR}` references anyway.
- **The browser controls the request body,** so a visitor could change the model or max_tokens. Mitigate with a dedicated key that has a spend cap, plus the rate limit. Mention this in the trust section.
- **If a key ever leaks into a published version,** rotate it and delete that version (`DELETE /api/v1/publish/:slug/versions/:versionId`).

## 6. Data contract

**Raw extraction output** (one per menu, from the model):
```json
{
  "menu_id": "<filename>",
  "restaurant_name_raw": "string|null",
  "restaurant_name_en": "string|null",
  "currency_notes": "e.g. 'prices in riel, no symbol'",
  "items": [{
    "name_km": "verbatim Khmer",
    "name_en": "translation",
    "section_raw": "heading it sits under, verbatim",
    "price_raw": "exactly as printed, incl. symbols / Khmer digits",
    "price_value": 12000,
    "currency": "USD|KHR|unknown",
    "size_or_unit": "can/bottle/glass/small/large/bucket/null",
    "tags": ["chicken","vegetable"],
    "multi_unit": false,
    "confidence": 0.8,
    "notes": ""
  }]
}
```

**Normalized row in `menus.json`** adds:
- `id`
- `restaurant` (falls back to `menu_id`)
- `source_image`
- `price_usd`
- `currency_inferred` (bool)
- `flags` (list)
- `verified` (bool)
- `corrected` (bool)

**Tag taxonomy:** `chicken, pork, beef, fish, seafood, duck, egg, tofu, vegetable, salad, rice, noodle, soup, beer, soft_drink, water, coffee_tea, alcohol_other, dessert, other`

## 7. Extraction prompt (v1 starter; save it to `prompts/extract_v1.txt` and version every change)

```
You are extracting a restaurant menu photographed in Cambodia. Text is mostly Khmer.
Return ONLY JSON matching this schema: <paste schema from §6>.
Rules:
- One row per priced item. If an item has several sizes/prices, emit one row per price.
- name_km: copy the Khmer exactly as written. Do not translate or "fix" it.
- price_raw: copy the price exactly as printed, including $, ៛, រៀល, K, Khmer digits (០-៩), commas.
- price_value: the number only; convert Khmer digits; expand "K"/ពាន់ to ×1000. If unreadable, null.
- currency: USD only if $ / ដុល្លារ / an explicit USD column; KHR only if ៛ / រៀល / R / KHR or an
  explicit riel column; otherwise "unknown". Never guess silently; explain in notes.
- If a price is printed once for a whole section, apply it to each item and say so in notes.
- tags: from this list only: <taxonomy>. "chicken" means the dish's main protein is chicken
  (NOT chicken egg ស៊ុតមាន់). A stir-fry of chicken with vegetables gets both tags.
- multi_unit: true for buckets, towers, jugs, sets, "x6", cases, or anything clearly >1 serving of a drink.
- confidence: your honest 0–1 confidence that name, price and currency are all correct.
- Do not invent items. If part of the menu is unreadable, say so in currency_notes.
```

## 8. Normalization rules, Khmer cheat-sheet, traps

**Rules for `scripts/normalize.py`**
- **Khmer digits:** map `០១២៣៤៥៦៧៨៩` to `0-9` before parsing.
- **Currency inference** when the model says `unknown`:
  - a decimal point, or a value ≤ 50, means USD;
  - a value ≥ 500 means KHR;
  - anything in between gets the `currency_ambiguous` flag.
  - Set `currency_inferred: true` whenever the currency came from these rules.
- **Riel shorthand:** `K`/`k`/`ពាន់` means ×1000.
- **Conversion:** `price_usd = KHR / 4000` (assumption A5).
- **Range checks in USD:** flag a row as `out_of_range` when it falls outside these bands. A flagged beer is probably a bucket, tower or jug.

  | Tag | Low | High |
  |---|---|---|
  | Chicken dish | 1 | 15 |
  | Vegetable dish | 0.75 | 10 |
  | Single beer | 0.4 | 5 |

- **Tag cross-check:** if the model's tag and the keyword match disagree, add the `tag_disagree` flag.
- **Confidence:** take the model's confidence and subtract a penalty for each flag. Ranking uses the result.

**Keyword list** (fairly reliable; spot-check with Google Translate before leaning on any of them)

| Khmer | Meaning | Khmer | Meaning |
|---|---|---|---|
| មាន់ | chicken | ស៊ុត | egg (ស៊ុតមាន់ = chicken **egg**) |
| សាច់ | meat | បន្លែ | vegetables |
| ត្រកួន | morning glory / water spinach | សាឡាដ | salad |
| ស្រាបៀរ | beer | ដប / កំប៉ុង | bottle / can |
| ឆា | stir-fry | បំពង | deep-fried |
| អាំង | grilled | សម្ល | soup/stew |
| ជ្រូក / គោ / ត្រី / ទា | pork / beef / fish / duck | បង្គា | shrimp |
| បាយ / មី / គុយទាវ | rice / noodles / noodle soup | ៛ / រៀល / ដុល្លារ / ពាន់ | riel / riel / dollar / thousand |

Beer brands usually appear in Latin script: Angkor, Cambodia, Anchor, ABC, Ganzberg, Klang, Tiger, Heineken.

**Traps**
- Dual-currency menus.
- A section-level price printed once for several items.
- Khmer has no spaces between words, so use substring matching rather than tokenization.
- Restaurant name missing from the menu: use the filename.
- Beer buckets and promos.
- Crossed-out or handwritten price changes.
- Small/large size columns.
- Prices "+VAT".

## 9. Benchmark design

**Ground truth:** 3 menus, every item. Record:
- `price_raw`
- `price_value`
- `currency`
- target tags (chicken, vegetable, beer)
- rough `name_en`
- the Khmer name taken from **Google Lens OCR**, independent of the models under test, with obvious errors fixed.

**`bench/score.py`**
- **Matching:** pair each predicted item with a ground-truth item by `price_value` plus Khmer name similarity (`difflib` ratio ≥ 0.7).
- **Metrics:**
  - item recall
  - hallucination rate (unmatched predictions)
  - price exact-match among matched items
  - currency accuracy
  - chicken/vegetable/beer tag precision and recall
  - name similarity ≥ 0.9 counted as "name correct"
- **Logging:** write one row per (model, menu, metric) to CSV. Keep the raw numbers; don't only summarize.

**Reporting the revised accuracy:**
- Always give n.
- With about 50 items at about 80%, the 95% interval is roughly ±11 points. Say so; that's a calibration point in your favour.
- Add a second source of evidence: the correction rate on the hand-verified target rows.

## 10. Recommender spec (`site/app.js`)

1. **Parse** the request into `{budget, wants:[{tag, qty}]}`, using the LLM via the proxy or the regex fallback.
   - Fallback rules: `$N` or "N dollars" is the budget. chicken goes to `chicken`; veg, vegetables, greens or salad go to `vegetable`; beer or beers go to `beer`.
   - Quantity words: "a couple" or "two" is 2, "a few" is 3, otherwise 1.
   - Show which parser was used.
2. **For each restaurant**, build a candidate list per want: rows with that tag, a `price_usd`, and `multi_unit = false`.
3. **Enumerate combinations.** A quantity of 2 can repeat the same item (2× the same beer). Different wants must use different rows unless the user allows a combined dish (toggle, default off).
4. **Keep combinations within budget.** Rank by:
   - (a) number of unverified items, ascending;
   - (b) minimum confidence, descending;
   - (c) total, ascending.
5. **Show the top 3 overall,** at most one per restaurant. Each line shows:
   - `name_km` and `name_en`
   - `price_raw` as printed, plus the USD value
   - quantity and line total
   - restaurant or menu, with a link to the source image
   - a verified or low-confidence badge

   Then the total, the budget, and what's left over.
6. **No valid combination?** Say so, show the nearest options over budget, and say what's missing (for example "no restaurant lists beer").
7. **Footer:** the exchange rate, the assumptions, and a link to "What I don't trust".

## 11. Repo layout

```
README.md            # how it works, what I don't trust (ranked), accuracy predicted vs measured, hand-corrections
PLAN.md  ASSUMPTIONS.md  HANDOVER.md
notes/               # data_first_look.md, decisions log
prompts/             # extract_v1.txt, parse_v1.txt (version every change)
scripts/             # extract.py, normalize.py
raw/<model>/         # untouched model outputs
bench/ground_truth/  bench/score.py  bench/results/*.csv
data/                # menus.json, flags.csv, corrections.csv
site/                # index.html, app.js, menus.json, .herenow/proxy.json, menu images (if allowed)
ai_logs/             # exported agent sessions, chat transcripts, tool logs
.gitignore           # .env, *.key, credentials
```
Commit after every step. Small commits tell the story better than one big one.

## 12. Debrief notes

**Six-beat story**
1. **Framing:** two problems, reading Khmer (hard and uncertain) and picking a combination under budget (easy and deterministic). I kept them separate.
2. **The live app is simple on purpose:** static data plus code, one optional model call with a fallback.
3. **I measured before I scaled:** a bake-off on hand-labelled menus.
4. **Human verification went where it changes the answer.**
5. **Prediction versus measured accuracy,** with n and the interval, and why they differ.
6. **Second attempt and scale:** batch API, confidence-routed human review queue, entity normalization (beer brands, dish types), dedupe and location, menu freshness, a real database, continuous sampled audits.

**Why not RAG.** One line: RAG answers "what's relevant?", but this question is "what's the best combination under a budget?", so I built a table and searched it exhaustively.
- **The bottleneck is reading Khmer.** RAG needs extracted text first, so it adds a layer on top of the hardest problem without solving it.
- **Top-k retrieval silently drops candidates.** If the cheapest beer isn't retrieved, it's never considered, and nothing tells you.
- **LLMs are unreliable at arithmetic and combinatorial search.** Code is exact and gives the same answer every time.
- **Citations must be exact.** Computed from rows they're just fields; generated from chunks they can be misquoted.
- **It has to be measurable.** A table can be scored field by field. RAG mixes extraction, chunking, retrieval and generation errors together.
- **The data is tiny:** a few thousand rows, scanned in milliseconds.
- **Khmer embeddings are weak,** and the lack of word spaces makes chunking noisy.
- **Extra infrastructure** on static hosting for no accuracy gain.
- **When I would use retrieval:** at scale, for fuzzy wants like "something spicy near the riverside", to generate candidates. The budget math stays in code.

**Likely challenge: "Why not put every menu in one long prompt?"** It's a valid baseline and a useful cross-check, but it has the same problems: no guarantee every candidate was checked, unreliable sums, citations that can be wrong, different answers on repeat runs, and no field-level measurement.

## 13. Questions to ask the evaluators (questions are free)

- What format is the dataset (photos, PDFs, text)? Can the menu images go in a public repo or site?
- Is ordering from more than one restaurant acceptable, or should it be a single place?
- Should the budget include VAT, service charge or tip?
- Do you have a preferred KHR/USD rate?
- Does "a couple of beers" have to be two singles (cans or bottles)?
- Will you try queries other than the example one?

## 14. Submission checklist

- [ ] Link opens in an incognito window, recommendation works, and it's published from the signed-in account (no `claimUrl` and no expiry in `publishStatus`).
- [ ] No secrets in deployed files: `grep -rE "sk-|api[_-]?key" site/` returns nothing sensitive, and the deployed source has been checked in the browser.
- [ ] README has the trust section, predicted versus revised accuracy, and which data was hand-corrected.
- [ ] `bench/` has the scripts and raw CSVs.
- [ ] `ai_logs/` contains:
  - Claude Code session JSONL files from `~/.claude/projects/<this-project>/`
  - the claude.ai planning chat (export or share link)
  - prompts
  - tool logs
- [ ] Link sent **before** the clock stops.
