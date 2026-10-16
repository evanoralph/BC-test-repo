# Assumptions

These are stated up front and refined as the data is inspected. Any that change get a note explaining why.

## About the question
1. **A1. One restaurant.** The order comes from a single restaurant: "from where" implies one place to go.
2. **A2. Two beers.** "A couple of beers" means exactly 2 single servings (a can, bottle or glass). Buckets, towers, jugs and sets don't count as one beer.
3. **A3. A separate vegetable dish.** "Some vegetables" means at least one vegetable dish separate from the chicken dish. A chicken-and-vegetable stir-fry doesn't count as both unless the user turns that option on.
4. **A4. Pre-tax budget.** The $10 budget covers menu prices only. It excludes VAT, service charge and tips.
5. **A5. Exchange rate.** 4,000 KHR = 1 USD, the common conventional rate. No live rate is used.
6. **A6. Best combination.** "Best" means the most trustworthy combination within budget: verified and high-confidence items first, then the lowest total. The app shows the top 3 and how much budget is left.

## About the data
7. **A7. Prices.** Menu prices are current and are per single serving unless the menu says otherwise.
8. **A8. Restaurant identity.** Each file is one restaurant. When the menu shows no restaurant name, the filename is used as its identifier.
9. **A9. Currency without a symbol.** A small number with a decimal point (≤ 50) is USD. A large number (≥ 500) is riel. Anything in between is flagged as ambiguous.
10. **A10. Khmer numerals.** Khmer digits (០–៩) mean the same as Western digits.
11. **A11. Shared prices.** When a price is printed once for a section, it applies to every item in that section.
12. **A12. Several prices for one item.** Each size or price variant is a separate orderable item.
13. **A13. Chicken eggs.** "Chicken" means chicken meat as the main protein. Dishes based on chicken egg (ស៊ុតមាន់) are not chicken.
14. **A14. Unreadable menus.** Menus or sections that can't be read are left out rather than guessed. This is reported in the README.

## About the evaluation
15. **A15. Measuring accuracy.** Accuracy is measured on a small hand-labelled sample, plus the correction rate on hand-verified rows. With this n the estimates carry wide error bars, and I report them that way.
16. **A16. Hand corrections.** Hand-verification and hand-corrections are allowed if disclosed. Every one is logged in `data/corrections.csv` and marked in the app.
17. **A17. Request format.** Users will mostly ask for combinations of food categories plus a budget. Requests outside the tag taxonomy fall back to keyword search on the translated item names.
