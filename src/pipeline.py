"""Quvur (pipeline): rasm(lar)ni OCR qilib, maydonlarni ajratib, JSON saqlash."""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from .ocr_engine import OcrEngine
from .parser import parse_receipt

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def process_image(
    image_path: str,
    engine: OcrEngine,
    language: str = "auto",
    keep_raw_text: bool = False,
) -> Dict:
    """Bitta rasmni qayta ishlab, natija dict'ini qaytaradi.

    `language`: parser tili — "auto" (standart), "en" yoki "ru".
    """
    raw_text = engine.read_text(image_path)
    receipt = parse_receipt(
        raw_text,
        source_file=os.path.basename(image_path),
        language=language,
    )
    return receipt.to_dict(keep_raw_text=keep_raw_text)


def process_folder(
    input_dir: str,
    output_dir: str,
    engine: Optional[OcrEngine] = None,
    keep_raw_text: bool = False,
    lang: str = "en",
    language: str = "auto",
) -> List[Dict]:
    """Papkadagi barcha rasmlarni qayta ishlaydi va har biri uchun JSON saqlaydi.

    `lang`     — PaddleOCR tanib olish tili (en, ru, ...).
    `language` — parser maydonlarni ajratish tili (auto, en, ru).
    """
    engine = engine or OcrEngine(lang=lang)
    os.makedirs(output_dir, exist_ok=True)

    files = sorted(
        f for f in os.listdir(input_dir)
        if os.path.splitext(f)[1].lower() in IMAGE_EXTS
    )

    results: List[Dict] = []
    for idx, fname in enumerate(files, 1):
        path = os.path.join(input_dir, fname)
        print(f"[{idx}/{len(files)}] {fname} ...", flush=True)
        try:
            result = process_image(
                path, engine, language=language, keep_raw_text=keep_raw_text
            )
        except Exception as exc:  # noqa: BLE001 — bitta rasm xatosi butun jarayonni to'xtatmasin
            print(f"    XATO: {exc}")
            result = {"source_file": fname, "error": str(exc)}

        out_path = os.path.join(output_dir, os.path.splitext(fname)[0] + ".json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
        results.append(result)

    return results
