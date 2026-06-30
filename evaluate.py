"""Compare results against the ground truth.

Usage:
    python evaluate.py data/ground_truth.json
    python evaluate.py data/ground_truth.json --output_dir data/output
    python evaluate.py data/ground_truth.json --strict
    python evaluate.py data/ground_truth.json --save_report

ground_truth.json format (your format):
{
  "samples": [
    {
      "merchant_name": "BEMED (SP) SDN. BHD.",
      "date": "2017-04-15",
      "total_amount": 635.0,
      "items": [
        {"description": "ITEM NAME", "quantity": 1.0, "unit_price": 300.0, "price": 300.0}
      ],
      "source_file": "img_01.jpg"
    },
    ...
  ]
}

Scoring:
  - merchant_name : partial match (without --strict, OK if 50% of words match)
  - date          : compared after normalizing to YYYY-MM-DD
  - total_amount  : +-5% tolerance (--strict: +-0%)
  - items         : what percentage of the GT items were found in the prediction
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field as dc_field
from typing import Any

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

DEFAULT_OUTPUT_DIR = os.path.join("data", "output")
AMOUNT_TOLERANCE   = 0.05


# ─────────────────────────── helper functions ────────────────────────────────

def normalize_date(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = str(raw).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    m = re.fullmatch(r"(\d{2})[./](\d{2})[./](\d{4})", raw)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = re.fullmatch(r"(\d{4})[./](\d{2})[./](\d{2})", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return raw


def normalize_amount(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = re.sub(r"[^\d.]", "", str(val).replace(",", "."))
    try:
        return float(s)
    except ValueError:
        return None


def clean_word(w: str) -> str:
    """Strip punctuation and brackets, keeping only alphanumerics."""
    return re.sub(r"[^A-Z0-9]", "", w.upper())


def match_merchant(pred: str | None, gt: str | None, strict: bool) -> bool:
    if not gt:
        return True
    if not pred:
        return False
    if strict:
        return pred.strip().upper() == gt.strip().upper()
    # Split into punctuation-free words (length >= 3)
    gt_words   = [clean_word(w) for w in gt.split()]
    gt_words   = [w for w in gt_words if len(w) >= 3]
    pred_clean = clean_word(pred)
    if not gt_words:
        return clean_word(pred) == clean_word(gt)
    matched = sum(1 for w in gt_words if w in pred_clean)
    return matched / len(gt_words) >= 0.5


def match_amount(pred: Any, gt: Any, strict: bool) -> bool:
    pf, gf = normalize_amount(pred), normalize_amount(gt)
    if gf is None:
        return True   # no GT — not evaluated
    if pf is None:
        return False
    if strict:
        return abs(pf - gf) < 0.01
    if gf == 0:
        return pf == 0
    return abs(pf - gf) / gf <= AMOUNT_TOLERANCE


def match_date(pred: str | None, gt: str | None) -> bool:
    if not gt:
        return True
    if not pred:
        return False
    return normalize_date(pred) == normalize_date(gt)


def match_items(pred_items: list | None, gt_items: list | None, strict: bool) -> float:
    """What fraction of the GT items were found in the prediction (0.0..1.0)."""
    if not gt_items:
        return 1.0
    if not pred_items:
        return 0.0

    # Collect the predicted names
    pred_names = []
    for it in pred_items:
        if isinstance(it, dict):
            name = it.get("name") or it.get("description") or ""
        else:
            name = str(it)
        pred_names.append(name)
    pred_blob = " ".join(pred_names).upper()

    found = 0
    for gt_item in gt_items:
        if isinstance(gt_item, dict):
            gt_name = gt_item.get("description") or gt_item.get("name") or ""
        else:
            gt_name = str(gt_item)
        if not gt_name:
            found += 1
            continue
        if strict:
            if any(gt_name.strip().upper() == p.strip().upper() for p in pred_names):
                found += 1
        else:
            # Is the first significant word present in the prediction?
            words = [w for w in gt_name.upper().split() if len(w) > 2]
            if words and words[0] in pred_blob:
                found += 1
            elif gt_name.upper() in pred_blob:
                found += 1
    return found / len(gt_items)


# ────────────────────────────── result class ─────────────────────────────────

@dataclass
class FileResult:
    fname:        str
    merchant_ok:  bool | None  = None
    date_ok:      bool | None  = None
    amount_ok:    bool | None  = None
    items_score:  float | None = None
    gt_missing:   bool = False
    json_missing: bool = False
    notes: list[str] = dc_field(default_factory=list)

    # raw values (for notes)
    pred_merchant: str | None = None
    gt_merchant:   str | None = None
    pred_date:     str | None = None
    gt_date:       str | None = None
    pred_amount:   Any        = None
    gt_amount:     Any        = None


# ────────────────────────────── evaluation ───────────────────────────────────

def evaluate_file(fname, pred, gt, strict) -> FileResult:
    r = FileResult(fname=fname)

    # Save the values
    r.pred_merchant = pred.get("merchant_name")
    r.gt_merchant   = gt.get("merchant_name")
    r.pred_date     = pred.get("date")
    r.gt_date       = gt.get("date")
    r.pred_amount   = pred.get("total_amount")
    r.gt_amount     = gt.get("total_amount")

    r.merchant_ok  = match_merchant(r.pred_merchant, r.gt_merchant, strict)
    r.date_ok      = match_date(r.pred_date, r.gt_date)
    r.amount_ok    = match_amount(r.pred_amount, r.gt_amount, strict)
    r.items_score  = match_items(pred.get("items"), gt.get("items"), strict)

    if not r.merchant_ok:
        r.notes.append(f"merchant: '{r.pred_merchant}' != '{r.gt_merchant}'")
    if not r.date_ok:
        r.notes.append(
            f"date: '{r.pred_date}'→'{normalize_date(r.pred_date)}'"
            f" != '{r.gt_date}'→'{normalize_date(r.gt_date)}'"
        )
    if not r.amount_ok:
        r.notes.append(f"total: pred={r.pred_amount} | gt={r.gt_amount}")
    if r.items_score is not None and r.items_score < 1.0:
        n = len(gt.get("items") or [])
        r.notes.append(f"items: {round(r.items_score*n)}/{n}")

    return r


# ────────────────────────────── output ───────────────────────────────────────

def mark(v):
    if v is None: return "  —"
    return "  ✓" if v else "  ✗"


def print_table(results: list[FileResult]) -> None:
    print(f"\n{'File':<16}{'Merchant':>10}{'Date':>7}{'Total':>8}{'Items':>9}  Notes")
    print("─" * 90)
    for r in results:
        if r.json_missing:
            print(f"{r.fname:<16}  ⚠  JSON file not found")
            continue
        if r.gt_missing:
            print(f"{r.fname:<16}  ⚠  GT entry not found")
            continue
        items_s = f"{r.items_score*100:>6.0f}%" if r.items_score is not None else "     —"
        note = " | ".join(r.notes[:2])
        print(f"{r.fname:<16}{mark(r.merchant_ok)}{mark(r.date_ok)}{mark(r.amount_ok)}{items_s}  {note}")


def print_summary(results: list[FileResult], strict: bool) -> dict:
    valid = [r for r in results if not r.gt_missing and not r.json_missing]
    n = len(valid)
    if n == 0:
        print("\nNo files to evaluate were found.")
        return {}

    m_ok = sum(1 for r in valid if r.merchant_ok)
    d_ok = sum(1 for r in valid if r.date_ok)
    a_ok = sum(1 for r in valid if r.amount_ok)
    i_sc = [r.items_score for r in valid if r.items_score is not None]
    i_avg = sum(i_sc) / len(i_sc) if i_sc else 0.0

    def pct(k): return k / n * 100

    mode = "STRICT (±0%)" if strict else "LENIENT (±5% tolerance)"
    print()
    print("═" * 90)
    print(f"  OVERALL RESULT  [{mode}]   ({n} files)")
    print("═" * 90)
    print(f"  merchant_name : {m_ok}/{n}  ({pct(m_ok):.0f}%)")
    print(f"  date          : {d_ok}/{n}  ({pct(d_ok):.0f}%)")
    print(f"  total_amount  : {a_ok}/{n}  ({pct(a_ok):.0f}%)")
    print(f"  items (avg)   : {i_avg*100:.0f}%")
    overall = (m_ok + d_ok + a_ok) / (3 * n) * 100
    print(f"\n  Overall accuracy (merchant+date+total) : {overall:.1f}%")

    ac2 = pct(d_ok) >= 70 and pct(a_ok) >= 70
    print(f"  AC-2 (date≥70% and total≥70%)          : {'✅ PASSED' if ac2 else '❌ FAILED'}")

    # List of incorrect ones
    wrong_date   = [r.fname for r in valid if not r.date_ok]
    wrong_amount = [r.fname for r in valid if not r.amount_ok]
    if wrong_date:
        print(f"\n  Date incorrect   : {', '.join(wrong_date)}")
    if wrong_amount:
        print(f"  Total incorrect  : {', '.join(wrong_amount)}")

    return {
        "mode": mode, "files": n,
        "merchant_pct": round(pct(m_ok), 1),
        "date_pct":     round(pct(d_ok), 1),
        "total_pct":    round(pct(a_ok), 1),
        "items_avg_pct": round(i_avg * 100, 1),
        "overall_pct":  round(overall, 1),
        "ac2_passed":   ac2,
    }


# ────────────────────────────── main ─────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Compares pipeline results against the ground truth.",
        epilog=(
            "Example:\n"
            "  python evaluate.py data/ground_truth.json\n"
            "  python evaluate.py data/ground_truth.json --strict\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("ground_truth",
                    help="path to the ground_truth.json file")
    ap.add_argument("--output_dir", "-o", default=DEFAULT_OUTPUT_DIR,
                    help=f"folder with the pipeline JSON results (default: {DEFAULT_OUTPUT_DIR})")
    ap.add_argument("--strict", "-s", action="store_true",
                    help="Strict mode: ±0%% tolerance, exact merchant name")
    ap.add_argument("--save_report", "-r", action="store_true",
                    help="Save the report to _gt_report.json")
    args = ap.parse_args()

    # ── Load ground truth ─────────────────────────────────────────────────────
    if not os.path.exists(args.ground_truth):
        print(f"ERROR: ground_truth not found: {args.ground_truth}", file=sys.stderr)
        return 1

    with open(args.ground_truth, encoding="utf-8") as fh:
        raw_gt = json.load(fh)

    # Support two formats:
    #   Format A: {"samples": [...]}   ← your format
    #   Format B: {"img_01": {...}, "img_02": {...}}
    if "samples" in raw_gt and isinstance(raw_gt["samples"], list):
        gt_map: dict[str, dict] = {}
        for entry in raw_gt["samples"]:
            src = entry.get("source_file", "")
            key = os.path.splitext(src)[0]   # "img_01.jpg" → "img_01"
            gt_map[key] = entry
    else:
        gt_map = {k: v for k, v in raw_gt.items() if not k.startswith("_")}

    # ── Collect the predicted JSON files from the output folder ───────────────
    if not os.path.isdir(args.output_dir):
        print(f"ERROR: output folder not found: {args.output_dir}", file=sys.stderr)
        return 1

    pred_map: dict[str, str] = {
        os.path.splitext(f)[0]: os.path.join(args.output_dir, f)
        for f in os.listdir(args.output_dir)
        if f.endswith(".json") and not f.startswith("_")
    }

    # ── Evaluate for all keys ─────────────────────────────────────────────────
    all_keys = sorted(set(gt_map) | set(pred_map))
    results: list[FileResult] = []

    for key in all_keys:
        r = FileResult(fname=key)
        if key not in gt_map:
            r.gt_missing = True
            results.append(r)
            continue
        if key not in pred_map:
            r.json_missing = True
            results.append(r)
            continue
        try:
            with open(pred_map[key], encoding="utf-8") as fh:
                pred = json.load(fh)
        except (json.JSONDecodeError, OSError) as e:
            r.json_missing = True
            r.notes.append(str(e))
            results.append(r)
            continue

        results.append(evaluate_file(key, pred, gt_map[key], args.strict))

    # ── Output ────────────────────────────────────────────────────────────────
    print_table(results)
    summary = print_summary(results, args.strict)

    # ── Save the report ───────────────────────────────────────────────────────
    if args.save_report and summary:
        report_path = os.path.join(args.output_dir, "_gt_report.json")
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump({
                "summary": summary,
                "per_file": [
                    {
                        "file":          r.fname,
                        "merchant_ok":   r.merchant_ok,
                        "date_ok":       r.date_ok,
                        "amount_ok":     r.amount_ok,
                        "items_score":   r.items_score,
                        "pred_merchant": r.pred_merchant,
                        "gt_merchant":   r.gt_merchant,
                        "pred_date":     r.pred_date,
                        "gt_date":       r.gt_date,
                        "pred_amount":   r.pred_amount,
                        "gt_amount":     r.gt_amount,
                        "notes":         r.notes,
                    }
                    for r in results
                ],
            }, fh, ensure_ascii=False, indent=2)
        print(f"\n  Report saved: {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
