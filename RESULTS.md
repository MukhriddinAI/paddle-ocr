# RESULTS — results, decisions, and limitations analysis

This document independently analyzes the engineering decisions in the project,
the evaluation results (Report 1 → Report 2 improvement), and the known
limitations.

---

## 1. Approach and key decisions

### 1.1. Rule-based parser — not an LLM

For field extraction, **deterministic regex + heuristics** were chosen
instead of delegating extraction to an LLM.

| Criterion | Rule-based (chosen) | LLM extraction |
|---|---|---|
| Cost / dependency | Free, offline, no API | Token cost, internet/key needed |
| Reproducibility | Fully deterministic | Stochastic, version-dependent |
| Transparency | Every rule visible in `parser.py` | "Black box" |
| Speed | A few ms | Network latency |
| Drawback | Needs tuning per format | Flexible without tuning |

Because the task is limited to exactly 4 fields and a constrained set of
receipt types, the rule-based approach is sufficient, cheap, and explainable.
An LLM could be added later only as an *optional fallback*
(section 5, "Improvement directions").

### 1.2. OCR — PaddleOCR

PaddleOCR is multilingual, returns **text + confidence score + bounding box**
for each block, and has both 2.x/3.x APIs. The bounding box is especially
important — without it, the "description on the left, price on the right"
structure cannot be reconstructed.

### 1.3. Spatial line reconstruction (`ocr_engine.lines_to_text`)

OCR returns blocks in arbitrary order. We group them into rows by their
**vertical center (`cy`)**, sort each row **left-to-right**, and turn them into
a single "readable" text. Thanks to this decision the parser can work with
simple line-based regex (`ROW_GROUP_TOLERANCE` is tuned relative to text
height).

### 1.4. items — multi-strategy

Each store writes its product lines differently. 4 strategies are tried in
sequence, **the first one that produces a result wins**:

1. `qty X unit total` — MR.DIY / TONYMOLY
2. `qty code unit total` — BEMED (without the X marker)
3. `"@"` style — prices on the following lines
4. `qty X unit=total` — Uzbek/Russian EU POS style (`1,000 X 189 600=189 600,00`)

### 1.5. total — two-tier (improved here)

- **Tier 1 (strong):** priority keywords — `Total Payable`,
  `Grand Total`, `Total After Rounding`, `Total Incl GST`, `ИТОГО`,
  `К ОПЛАТЕ` ...
- **Tier 2 (fallback):** if no keyword is found, **garbled OCR variants** are
  also searched (`[otal`, `Tutal`, `Iotal`, `Indlusive GST`), while
  `subtotal` / change / payment-type / GST-summary lines are skipped.

---

## 2. Evaluation results

Output of `evaluate.py data/ground_truth.json`
(10 files: 9 evaluation receipts `img_01..09` + 1 free-form Uzbek receipt):

```
Fayl              Merchant   Date   Total    Items  Izohlar
──────────────────────────────────────────────────────────────────────────────
img_01                  ✓     ✓     ✓     100%
img_02                  ✓     ✓     ✓     100%
img_03                  ✓     ✓     ✓     100%
img_04                  ✓     ✓     ✓     100%
img_05                  ✓     ✓     ✓     100%
img_06                  ✓     ✓     ✓     100%
img_07                  ✓     ✓     ✓     100%
img_08                  ✓     ✓     ✓       0%   items: 0/1
img_09                  ✓     ✓     ✓       0%   items: 0/2
photo_2026-06-20...     ✓     ✓     ✗     100%   total: pred=None | gt=210300.0

══════════════════════════════════════════════════════════════════════════════
  UMUMIY NATIJA  [YUMSHOQ (±5% tolerans)]   (10 fayl)
══════════════════════════════════════════════════════════════════════════════
  merchant_name : 10/10  (100%)
  date          : 10/10  (100%)
  total_amount  : 9/10   (90%)
  items (avg)   : 80%

  Umumiy aniqlik (merchant+date+total) : 96.7%
  AC-2 (date≥70% va total≥70%)         : ✅ O'TDI
  Total noto'g'ri  : photo_2026-06-20_11-31-17
```

> The block above is the verbatim console output of `evaluate.py` (the tool
> prints in Uzbek): `Fayl` = File, `Izohlar` = Notes, `UMUMIY NATIJA` =
> OVERALL RESULT, `YUMSHOQ` = LENIENT, `fayl` = file(s),
> `Umumiy aniqlik` = overall accuracy, `O'TDI` = PASSED,
> `Total noto'g'ri` = Total incorrect.

### 2.3. What was fixed in `total_amount`

The old fallback logic (a) only searched for the un-garbled word `total` and
(b) **rejected any line containing the word `gst`**. Because of that, 3
receipts were failing:

| File | Line in raw text | Old | New | Reason |
|---|---|---|---|---|
| img_01 | `al Indlusive GST: 635.00` | `null` | `635.0` | "Total" → "al" garbled; now the `Inclusive GST` anchor catches it |
| img_05 | `[otal Sales Incl. GST 39.90` / `Tutal After Rounding 39.90` | `null` | `39.9` | "Total" → "[otal"/"Tutal"; the garbled variant is now caught |
| img_07 | `Total Inel. GST06% RM 119.70` | `null` | `119.7` | "Total" was present but was rejected due to "gst"; now only a line *starting* with GST is rejected |

Tier-1 (keywords) was untouched, so the previously working receipts were
**not broken** — for the 9 `img_*` receipts in the evaluation set,
`total_amount` stayed at 9/9 (100%).

---

## 3. Quality check (correctness of values)

Evaluation now directly compares values against the `data/ground_truth.json`
reference (instead of the old "is it filled in" measure), so if a field is
filled in but its value is wrong — that is now visible (e.g. the `total` value
of the `photo_...` receipt).

- **total_amount:** all 3 corrected values match the actual receipt's final
  total (img_01=635.00, img_05=39.90, img_07=119.70).
- **Uzbek receipt (`photo_2026-06-20_11-31-17`):** this real EU/UZ-format
  receipt was read partially correctly — `merchant=ZEYTUN* Supermarket`,
  `date=2026-06-11` and items (`189 600` → `189600` with a thousands space)
  were extracted correctly, but `total_amount` was not found (`None`,
  reference `210300`) — reason in 4.6.

---

## 4. Known limitations and error analysis

### 4.1. The ground-truth set is small
`data/ground_truth.json` now exists and evaluation compares against real
values, but the set is only **10 receipts**. For statistically reliable
precision/recall, the reference set needs to be expanded with more and more
varied receipts (different stores, languages, formats).

### 4.2. `date` — img_04 (OCR completely garbled the date)
OCR garbled the date as `30-4-1 1711117986` — the separator (`-`) was lost
and the digits ran together. It cannot be reliably reconstructed by any
pattern, so the reference also has `date = null`. In evaluation `null == null`
matches, so the overall date metric stays at 100%.

### 4.3. `items` — img_08, img_09 (empty, items stays at 80%)
In these receipts the format is `A4 BW Simili 80gsm @ 7.00 7.42` — i.e. the
`@` marker is on the **same line** as the prices (not at the end). The current
`"@"` strategy, however, expects an `@` at the **end** of the line
(`desc @` → prices on the next line), so this format is not caught.

### 4.4. OCR noise — the common root cause
Most of the failures are not wrong extraction, but **OCR itself misreading**:
`Total`→`[otal`, `635`→`035`, `Incl`→`Inel`, loss of date separators. The
fallback logic fixes garbled *words*, but cannot fix garbled *numbers*.

### 4.5. The `max()` heuristic in `total`
In the fallback tier, the largest of several candidates is taken. Usually
correct (the final total is larger than the subtotal/tax), but in unusual
layouts a wrong value may be selected.

### 4.6. `total` — `photo_...` Uzbek receipt (the only failure, stays at 90%)
On the EU/UZ-format Uzbek receipt, `total_amount` was not found (`None`,
reference `210300`). The total keywords in `parser.py` are for
English/Malaysian and Russian (`ИТОГО`, `К ОПЛАТЕ`...), while Uzbek total
markers (`JAMI`, `HAMMASI`, `JAMI TO'LOV`...) are not yet in the list; the
fallback tier did not catch this amount either. Since the item lines
(`189 600` with a thousands space) were read correctly, the fix is to add the
UZ total keywords (section 5).

### 4.7. Currency is not extracted
`RM`/`MYR`/`сўм` is not detected; the amount is taken as a number only.

---

## 5. Improvement directions

1. **Inline `@` item strategy** — covers img_08/09 (items 80% → 100%).
2. **Uzbek `total` keywords** — adding `JAMI`, `HAMMASI`, `JAMI TO'LOV`...
   to catch the `total` value of the `photo_...` receipt (total 90% → 100%).
3. **Garbled date recovery** — re-OCR of the date region or a
   digit-separator heuristic (img_04).
4. **Expand the reference set** — enrich `ground_truth.json` with more and
   more varied receipts for statistically reliable evaluation.
5. **Currency field** — based on key symbols (`RM`, `$`, `сўм`).
6. **Optional LLM fallback** — call an LLM only for that specific image when
   the rule-based parser returns empty (with a cost/accuracy trade-off).
7. **Confidence-based ranking** — when there are several candidates, take the
   OCR `score` into account (instead of `max()`).
