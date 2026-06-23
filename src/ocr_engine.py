"""PaddleOCR ustidan o'ralgan (wrapper) qatlam.

PaddleOCR 3.x (`predict`) va 2.x (`ocr`) API'larining ikkalasini ham
qo'llab-quvvatlaydi, natijani bir xil `OcrLine` ro'yxatiga keltiradi.

`parser.py` strukturalangan maydonlarni xom MATNdan (qatorma-qator string)
ajratadi — xuddi boshqa oddiy OCR modeli chiqargani kabi. Shu sabab bu yerda
`read_text()` metodi PaddleOCR'ning quti (box) koordinatalaridan foydalanib,
aniqlangan bloklarni fazoviy tartibda (yuqoridan pastga, chapdan o'ngga)
bitta matnga birlashtirib beradi.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .config import OCR_LANG, ROW_GROUP_TOLERANCE


@dataclass
class OcrLine:
    """OCR tomonidan aniqlangan bitta matn bloki (so'z/ibora) va uning joylashuvi."""

    text: str
    score: float
    box: List[List[float]]  # 4 ta nuqta: [[x,y], [x,y], [x,y], [x,y]]

    @property
    def xs(self) -> List[float]:
        return [p[0] for p in self.box]

    @property
    def ys(self) -> List[float]:
        return [p[1] for p in self.box]

    @property
    def x_min(self) -> float:
        return min(self.xs)

    @property
    def x_max(self) -> float:
        return max(self.xs)

    @property
    def y_min(self) -> float:
        return min(self.ys)

    @property
    def y_max(self) -> float:
        return max(self.ys)

    @property
    def cx(self) -> float:
        return (self.x_min + self.x_max) / 2

    @property
    def cy(self) -> float:
        return (self.y_min + self.y_max) / 2

    @property
    def height(self) -> float:
        return self.y_max - self.y_min


class OcrEngine:
    """PaddleOCR modelini bir marta yuklab, qayta-qayta ishlatadigan klass."""

    def __init__(self, lang: str = OCR_LANG, use_gpu: bool = False):
        self.lang = lang
        self.use_gpu = use_gpu
        self._ocr = None  # lazy: faqat kerak bo'lganda yuklanadi
        self._api = None  # "v3" yoki "v2"

    def _load(self):
        """PaddleOCR modelini yuklash. API versiyasi avtomatik aniqlanadi."""
        if self._ocr is not None:
            return

        from paddleocr import PaddleOCR

        # Avval yangi (3.x) API parametrlari bilan urinib ko'ramiz.
        # enable_mkldnn=False — paddle 3.x oneDNN/PIR backendidagi
        # "ConvertPirAttribute2RuntimeAttribute" xatosini chetlab o'tadi.
        v3_kwargs = dict(
            lang=self.lang,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=True,
            enable_mkldnn=False,
        )
        for kwargs in (v3_kwargs, {k: v for k, v in v3_kwargs.items() if k != "enable_mkldnn"}):
            try:
                self._ocr = PaddleOCR(**kwargs)
                self._api = "v3"
                return
            except (TypeError, ValueError):
                continue

        # Eski (2.x) API'ga qaytamiz.
        try:
            self._ocr = PaddleOCR(use_angle_cls=True, lang=self.lang, show_log=False)
        except TypeError:
            self._ocr = PaddleOCR(use_angle_cls=True, lang=self.lang)
        self._api = "v2"

    def read(self, image_path: str) -> List[OcrLine]:
        """Rasmni o'qib, `OcrLine` ro'yxatini qaytaradi (quti koordinatalari bilan)."""
        self._load()
        if self._api == "v3":
            return self._read_v3(image_path)
        return self._read_v2(image_path)

    def read_text(self, image_path: str) -> str:
        """Rasmni o'qib, fazoviy tartibga keltirilgan xom MATN qaytaradi.

        `parser.py` aynan shu formatdagi matn bilan ishlaydi: har bir qator
        ajratilgan, bir qatordagi bloklar chapdan o'ngga tartiblangan.
        """
        return self.lines_to_text(self.read(image_path))

    @staticmethod
    def lines_to_text(
        lines: List[OcrLine],
        row_tolerance: float = ROW_GROUP_TOLERANCE,
    ) -> str:
        """`OcrLine` bloklarini fazoviy tartibda bitta matnga birlashtiradi.

        Bloklar vertikal markazi (cy) bo'yicha qatorlarga guruhlanadi:
        ikki blok markazi farqi qator balandligining `row_tolerance` ulushidan
        kichik bo'lsa — ular bir qatorda deb hisoblanadi. Har bir qator ichida
        bloklar chap chetidan (x_min) o'ngga qarab tartiblanadi.
        """
        if not lines:
            return ""

        ordered = sorted(lines, key=lambda l: l.cy)
        rows: List[List[OcrLine]] = [[ordered[0]]]
        for line in ordered[1:]:
            current = rows[-1]
            avg_h = sum(l.height for l in current) / len(current)
            ref_cy = sum(l.cy for l in current) / len(current)
            # Balandlik 0 bo'lib qolsa ham bo'linish ishlashi uchun kichik chegara
            threshold = max(avg_h, 1.0) * row_tolerance
            if abs(line.cy - ref_cy) <= threshold:
                current.append(line)
            else:
                rows.append([line])

        text_rows: List[str] = []
        for row in rows:
            row_sorted = sorted(row, key=lambda l: l.x_min)
            text_rows.append(" ".join(l.text for l in row_sorted).strip())
        return "\n".join(text_rows)

    def _read_v3(self, image_path: str) -> List[OcrLine]:
        result = self._ocr.predict(image_path)
        lines: List[OcrLine] = []
        for page in result:
            # page — dict-ga o'xshash ob'yekt: 'rec_texts', 'rec_scores', 'rec_polys'
            data = page if isinstance(page, dict) else getattr(page, "json", page)
            if isinstance(data, dict) and "res" in data:
                data = data["res"]
            texts = data.get("rec_texts", [])
            scores = data.get("rec_scores", [])
            polys = data.get("rec_polys", data.get("dt_polys", []))
            for i, text in enumerate(texts):
                score = float(scores[i]) if i < len(scores) else 0.0
                box = polys[i] if i < len(polys) else [[0, 0]] * 4
                box = [[float(p[0]), float(p[1])] for p in box]
                if text and text.strip():
                    lines.append(OcrLine(text=text.strip(), score=score, box=box))
        return lines

    def _read_v2(self, image_path: str) -> List[OcrLine]:
        try:
            result = self._ocr.ocr(image_path, cls=True)
        except TypeError:
            result = self._ocr.ocr(image_path)
        lines: List[OcrLine] = []
        # 2.x: result = [page1, page2, ...]; har bir page = [[box, (text, score)], ...]
        for page in result or []:
            if page is None:
                continue
            for det in page:
                box = det[0]
                text, score = det[1][0], det[1][1]
                box = [[float(p[0]), float(p[1])] for p in box]
                if text and str(text).strip():
                    lines.append(OcrLine(text=str(text).strip(), score=float(score), box=box))
        return lines
