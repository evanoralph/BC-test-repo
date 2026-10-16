# Plan: Khmer Menu Intelligence Challenge

**Approach.** I'll treat this as two separate problems:
- **Reading the menus.** This is hard and uncertain. I'll extract every menu **offline** with a vision LLM into structured JSON. Each item keeps the Khmer name verbatim, the price exactly as printed, the parsed price, the currency, category tags and a confidence score.
- **Choosing the order.** This is easy and deterministic. The live app is static: it loads the extracted JSON and runs an exhaustive search in the browser. For each restaurant it tries every combination that meets the request and the budget. Every recommended item then traces back to a real row, with the menu, the item and price as printed, and the total against the budget.

Before running all menus, I'll hand-label 3 different menus and benchmark two vision models on them, choosing by measured accuracy. After extraction I'll:
- normalize Khmer numerals and currency (riel converted at 4,000 per dollar);
- apply price-range checks and a Khmer keyword cross-check;
- hand-verify the chicken, vegetable and beer rows, since they drive the answer, and log every correction.

**Fallback and scope.** If extraction quality on Khmer is poor, I'll narrow scope to prices plus keyword-tagged chicken, vegetable and beer items. If needed I'll hand-transcribe a subset of menus, and the app and README will say exactly which rows were hand-entered or corrected. I'm deliberately not doing:
- custom OCR or fine-tuning;
- RAG or a vector store (this is a budget optimization over a small table, not a retrieval problem);
- a backend or database;
- live exchange rates;
- design polish;
- verification of items that can't affect the answer.

**Getting it live.** I'll publish a bare page to here.now from a signed-in account within the first 45 minutes, so the link is permanent, and improve it from there.
- **In the browser:** the data, the search and the rendering.
- **Through a proxy route:** one model call, which turns the user's free-text request into structured constraints (budget, items, quantities). The model API key is stored as a here.now account variable and injected server-side via `.herenow/proxy.json`, so it never appears in the page. A keyword parser takes over if the proxy fails, so the app works without it.

**Accuracy prediction (made before processing any menu):**

| Field | Expected accuracy |
|---|---|
| Prices (numeric value) | ~85% |
| Currency | ~85% (I expect errors to come from ambiguous menus with no symbol, not misreading) |
| Category tags (chicken / vegetable / beer) | ~85% |
| Item names, exact Khmer transcription | ~60% |
| Item names, recognizably correct meaning | ~75% |

I'll report the measured figures with sample sizes and compare.
