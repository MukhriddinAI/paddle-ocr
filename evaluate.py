"""Natijalarni baholash: OCR ishonch darajasi + maydon ajratish to'liqligi.

DIQQAT: loyihada etalon (ground-truth) javoblar yo'q, shuning uchun maydonlar
qiymatining haqiqiy "to'g'ri/noto'g'ri" aniqligini hisoblab bo'lmaydi. Bu skript
ikki o'lchovni beradi:

  1) OCR confidence  — PaddleOCR aniqlagan bloklarning o'rtacha ishonch bali
                       (modelning o'z bashoratiga ishonchi, 0..100%).
  2) Completeness    — 4 ta maqsadli maydon (merchant_name, date,
                       total_amount, items) qanchasi to'ldirilgani (0..100%).
"""

from __future__ import annotations

import json
import os
import sys

# Windows konsoli uchun UTF-8
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ocr_engine import OcrEngine

INPUT_DIR = os.path.join("data", "input")
OUTPUT_DIR = os.path.join("data", "output", "PaddleOCR")
FIELDS = ["merchant_name", "date", "total_amount", "items"]


def field_completeness(rec: dict) -> tuple[int, dict]:
    """Nechta maydon to'ldirilgan (bo'sh emas)? -> (soni, har-maydon holati)."""
    status = {}
    for f in FIELDS:
        val = rec.get(f)
        if f == "items":
            ok = bool(val)  # bo'sh bo'lmagan ro'yxat
        else:
            ok = val not in (None, "", [])
        status[f] = ok
    return sum(status.values()), status


def main() -> int:
    engine = OcrEngine(lang="en")

    files = sorted(
        f for f in os.listdir(INPUT_DIR)
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"))
    )

    rows = []
    total_conf_sum = 0.0
    total_conf_n = 0
    total_fields_ok = 0

    print(f"{'Fayl':<14}{'OCR conf':>10}{'Bloklar':>9}{'Maydon':>9}   Ajratilgan maydonlar")
    print("-" * 78)

    for fname in files:
        img_path = os.path.join(INPUT_DIR, fname)
        json_path = os.path.join(OUTPUT_DIR, os.path.splitext(fname)[0] + ".json")

        # OCR confidence (ikkinchi yengil o'qish — faqat ballar uchun)
        lines = engine.read(img_path)
        if lines:
            mean_conf = sum(l.score for l in lines) / len(lines)
        else:
            mean_conf = 0.0
        total_conf_sum += sum(l.score for l in lines)
        total_conf_n += len(lines)

        # Maydon to'liqligi (saqlangan JSON dan)
        if os.path.exists(json_path):
            with open(json_path, encoding="utf-8") as fh:
                rec = json.load(fh)
        else:
            rec = {}
        n_ok, status = field_completeness(rec)
        total_fields_ok += n_ok

        ok_names = ", ".join(f for f, v in status.items() if v) or "(yo'q)"
        print(f"{fname:<14}{mean_conf*100:>9.1f}%{len(lines):>9}{n_ok:>6}/4   {ok_names}")

        rows.append({
            "file": fname,
            "ocr_confidence": round(mean_conf * 100, 1),
            "blocks": len(lines),
            "fields_extracted": n_ok,
            "field_status": status,
            "merchant_name": rec.get("merchant_name"),
            "date": rec.get("date"),
            "total_amount": rec.get("total_amount"),
            "items_count": len(rec.get("items") or []),
        })

    n_files = len(files)
    overall_conf = (total_conf_sum / total_conf_n * 100) if total_conf_n else 0.0
    overall_completeness = (total_fields_ok / (n_files * len(FIELDS)) * 100) if n_files else 0.0

    print("-" * 78)
    print(f"{'JAMI/O‘RTACHA':<14}{overall_conf:>9.1f}%{total_conf_n:>9}{total_fields_ok:>4}/{n_files*4}")
    print()
    print(f"O'rtacha OCR ishonch darajasi : {overall_conf:.1f}%")
    print(f"Maydon ajratish to'liqligi    : {overall_completeness:.1f}%  ({total_fields_ok}/{n_files*len(FIELDS)} maydon)")

    # Har bir maydon bo'yicha topilish foizi
    print("\nHar bir maydon bo'yicha topilish foizi:")
    for f in FIELDS:
        cnt = sum(1 for r in rows if r["field_status"][f])
        print(f"  {f:<14}: {cnt}/{n_files}  ({cnt/n_files*100:.0f}%)")

    # Hisobotni JSON ga saqlash
    report_path = os.path.join(OUTPUT_DIR, "_accuracy_report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump({
            "summary": {
                "files": n_files,
                "avg_ocr_confidence_pct": round(overall_conf, 1),
                "field_completeness_pct": round(overall_completeness, 1),
                "fields_extracted": total_fields_ok,
                "fields_total": n_files * len(FIELDS),
            },
            "per_file": rows,
        }, fh, ensure_ascii=False, indent=2)
    print(f"\nHisobot saqlandi: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
