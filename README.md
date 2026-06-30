# Receipt Parser (PaddleOCR)

A project that extracts the following fields from receipt images using
PaddleOCR:

- **merchant_name** — seller/company name
- **date** — receipt date (normalized to ISO `YYYY-MM-DD`)
- **total_amount** — final payable amount (`float`)
- **items** — list of products, each with: `description`, `quantity`,
  `unit_price`, `price`
- **source_file** — source image file name

> Extraction is fully **rule-based** — built on regex and heuristics.
> No LLM / generative AI is used at runtime
> (see: [AI transparency](#ai-transparency)).

## Project structure

```
PaddleOCR/
├── main.py                 # CLI entry point (image/folder -> JSON)
├── evaluate.py             # compare against ground truth (field accuracy)
├── requirements.txt
├── src/
│   ├── ocr_engine.py       # PaddleOCR wrapper (2.x & 3.x API) + line reconstruction
│   ├── parser.py           # field extraction (merchant/date/total/items) logic
│   ├── models.py           # Item, Receipt data models
│   ├── pipeline.py         # orchestration: image -> OCR -> parser -> JSON
│   └── config.py           # OCR language and row-grouping settings
└── data/
    ├── input/              # evaluation set (img_01..img_09)
    ├── test_input/         # free-form test images (photo_2026-...)
    ├── ground_truth.json   # manually labeled correct answers (for evaluation)
    └── output/             # result JSON files + _gt_report.json
```

## Installation

The repo contains **code only** — the virtual environment (`paddle_env`) is
not committed (`.gitignore`), so you create it yourself after cloning.
Python 3.8–3.12 is required.

```bash
# 1. Clone the repo
git clone https://github.com/MukhriddinAI/paddle-ocr.git
cd paddle-ocr

# 2. Create a virtual environment
python -m venv paddle_env

# 3. Install the required libraries
#    Windows:
paddle_env/Scripts/python.exe -m pip install -r requirements.txt
#    Linux / macOS:
#    paddle_env/bin/python -m pip install -r requirements.txt
```

> **On the first run** PaddleOCR automatically downloads the
> detection/recognition models from the internet (a few hundred MB) — so an
> internet connection is needed the first time. After that it works offline.
>
> For GPU, install `paddlepaddle-gpu` instead of `paddlepaddle` and use the
> `--gpu` flag.

## Usage

```bash
# Default: data/input -> data/output
paddle_env/Scripts/python main.py

# Process a different folder (e.g. the free-form test images)
paddle_env/Scripts/python main.py -i data/test_input -o data/output

# Single image (result is printed to screen and also saved to the folder)
paddle_env/Scripts/python main.py -i data/input/img_01.jpg

# Also include the raw OCR text in the result (useful for debugging)
paddle_env/Scripts/python main.py --raw

# Parser/OCR language (en or ru)
paddle_env/Scripts/python main.py -l en
```

CLI flags: `-i/--input` (default `data/input`),
`-o/--output` (default `data/output`), `-l/--lang` (default `en`),
`--raw`, `--gpu`.

## Output example

`data/output/img_01.json`:

```json
{
  "merchant_name": "BEMED (SP) SDN. BHD.",
  "date": "2017-04-15",
  "total_amount": 635.0,
  "items": [
    {
      "description": "PRISTIN OMEGA-3 FISH OIL 2X150S(VIP)",
      "quantity": 1.0,
      "unit_price": 300.0,
      "price": 300.0
    }
  ],
  "source_file": "img_01.jpg"
}
```

> When run with `--raw`, a `raw_text` field (spatially ordered raw OCR text)
> is also added to the result. Fields that are not found are `null`
> (or an empty list for `items`).

## How it works

1. **OCR** (`ocr_engine.py`) — PaddleOCR reads the image and returns, for
   each text block, the text, a confidence score (`score`) and the location
   (bounding box). The wrapper supports both the PaddleOCR 2.x (`ocr`) and
   3.x (`predict`) APIs.
2. **Line reconstruction** (`ocr_engine.lines_to_text`) — blocks are grouped
   into rows by their vertical center (`cy`) (`ROW_GROUP_TOLERANCE`), sorted
   left-to-right within each row, and joined into a single raw text.
3. **Field extraction** (`parser.py`) — based on heuristics:
   - **merchant**: the header line containing a company marker
     (`SDN BHD`, `ENTERPRISE`, `ООО` ...); if none, the first "clean" line.
   - **date**: month-name (`27 March 2018`, `27 марта 2018`) and numeric
     (`29/03/2018`, `19-04-18`) patterns → normalized to ISO `YYYY-MM-DD`.
   - **total**: first the priority keywords (`Total Payable`,
     `Grand Total`, `Total After Rounding`, `ИТОГО`, `К ОПЛАТЕ` ...); if not
     found, a fallback also searches for garbled OCR variants (`[otal`,
     `Tutal`, `Indlusive GST`) and skips `subtotal`/change/tax lines.
   - **items**: 4 format strategies are tried in sequence —
     `qty X unit total` (MR.DIY/TONYMOLY), `qty code unit total` (BEMED),
     the `"@"` style, and `qty X unit=total` (Uzbek/Russian EU POS style).

## Accuracy evaluation

`evaluate.py` compares the pipeline results (`data/output/*.json`) against the
manually labeled `data/ground_truth.json` and reports an accuracy percentage
for each field.

```bash
# Evaluate the results (table + overall result on screen)
# --output_dir defaults to `data/output` — exactly where main.py writes
paddle_env/Scripts/python evaluate.py data/ground_truth.json

# Also save the report to a file (data/output/_gt_report.json)
paddle_env/Scripts/python evaluate.py data/ground_truth.json --save_report

# Strict mode: total ±0% tolerance, merchant name must match exactly
paddle_env/Scripts/python evaluate.py data/ground_truth.json --strict
```

Evaluation criteria: **merchant** — ≥50% word overlap (lenient mode),
**date** — compared after normalizing to ISO `YYYY-MM-DD`, **total** — ±5%
tolerance (lenient), **items** — what percentage of the GT products were
found in the result.

On the current evaluation set (`data/ground_truth.json`, 10 files):

```
══════════════════════════════════════════════════════════════════════════════════════════
  UMUMIY NATIJA  [YUMSHOQ (±5% tolerans)]   (10 fayl)
══════════════════════════════════════════════════════════════════════════════════════════
  merchant_name : 10/10  (100%)
  date          : 10/10  (100%)
  total_amount  : 9/10   (90%)
  items (avg)   : 80%

  Umumiy aniqlik (merchant+date+total) : 96.7%
  AC-2 (date≥70% va total≥70%)         : ✅ O'TDI
```

> The block above is the verbatim console output of `evaluate.py` (the tool
> prints in Uzbek): `UMUMIY NATIJA` = OVERALL RESULT, `YUMSHOQ` = LENIENT,
> `fayl` = file(s), `Umumiy aniqlik` = overall accuracy, `O'TDI` = PASSED.

Detailed analysis and error breakdown — [`RESULTS.md`](RESULTS.md).

## AI transparency

**At runtime:** the project **uses no generative AI**. The only neural model
is **PaddleOCR** (a computer-vision model for text detection/recognition).
The field extraction logic (`parser.py`) is entirely **deterministic regex
and rules** — offline, reproducible, with no LLM calls.

**During development:** an AI assistant (Claude Code — an LLM-based coding
agent) was used for:

- designing the module structure (`ocr_engine` / `parser` / `pipeline` /
  `models`);
- writing and iterating on the regex patterns and heuristics;
- analyzing the raw OCR text to debug extraction errors (e.g. hardening the
  `total_amount` fallback logic for garbled "Total" variants);
- writing `README.md`, `RESULTS.md` and the code comments.

The final logic and decisions were reviewed; all regex/heuristics remain
open and inspectable inside `parser.py`.

## Limitations

Because of OCR noise and the variety of receipts, extraction is **heuristic**
and not 100% accurate. For new receipt types, adjust the keywords and patterns
in `parser.py`. Reviewing the raw text with `--raw` is useful for checking
accuracy. Full limitations analysis — [`RESULTS.md`](RESULTS.md).
