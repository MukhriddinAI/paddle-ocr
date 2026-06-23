"""CLI kirish nuqtasi: cheklardan ma'lumot ajratib oluvchi dastur.

Foydalanish:
    python main.py                          # data/input -> data/output/PaddleOCR
    python main.py -i rasm.jpg              # bitta rasm (natija ekranga)
    python main.py -i data/input -o out/    # papkani qayta ishlash
    python main.py --raw                    # natijaga raw_text ham qo'shiladi
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Windows konsoli (cp1252) Unicode belgilarni chiqara olishi uchun.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from src.ocr_engine import OcrEngine
from src.pipeline import process_folder, process_image

DEFAULT_INPUT = os.path.join("data", "test_input")
DEFAULT_OUTPUT = os.path.join("data", "output", "PaddleOCR")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PaddleOCR yordamida cheklardan merchant_name, date, "
                    "total_amount va items ajratib oladi.",
    )
    parser.add_argument(
        "-i", "--input", default=DEFAULT_INPUT,
        help=f"Kirish rasm yoki papka (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "-o", "--output", default=DEFAULT_OUTPUT,
        help=f"Chiqish papkasi (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument("-l", "--lang", default="en", help="OCR tili (default: en)")
    parser.add_argument("--raw", action="store_true", help="Natijaga raw_text qo'shish")
    parser.add_argument("--gpu", action="store_true", help="GPU dan foydalanish")
    args = parser.parse_args()

    engine = OcrEngine(lang=args.lang, use_gpu=args.gpu)

    # OCR tili parser ham qo'llab-quvvatlasa (en/ru), parserga ham uzatamiz;
    # aks holda parser "auto" rejimida ikkala tilni ham sinaydi.
    parser_lang = args.lang if args.lang in ("en", "ru") else "auto"

    if os.path.isfile(args.input):
        # Bitta rasm: natijani ekranga chiqaramiz va papkaga ham saqlaymiz.
        result = process_image(
            args.input, engine, language=parser_lang, keep_raw_text=args.raw
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        os.makedirs(args.output, exist_ok=True)
        out_path = os.path.join(
            args.output, os.path.splitext(os.path.basename(args.input))[0] + ".json"
        )
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
        print(f"\nSaqlandi: {out_path}")
        return 0

    if os.path.isdir(args.input):
        results = process_folder(
            args.input, args.output, engine=engine,
            keep_raw_text=args.raw, lang=args.lang, language=parser_lang,
        )
        print(f"\nBajarildi: {len(results)} ta fayl -> {args.output}")
        return 0

    print(f"XATO: kirish topilmadi: {args.input}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
