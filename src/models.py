"""Chek (receipt) ma'lumotlari uchun ma'lumot modellari.

`parser.py` xom OCR matnidan shu yerdagi `Item` va `Receipt` obyektlarini
yig'adi. `to_dict()` metodi JSON ga saqlash uchun toza dict qaytaradi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Item:
    """Chekdagi bitta mahsulot satri."""

    description: str
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    price: Optional[float] = None

    def to_dict(self) -> Dict:
        return {
            "description": self.description,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "price": self.price,
        }


@dataclass
class Receipt:
    """Bitta chekdan ajratilgan strukturalangan ma'lumot."""

    merchant_name: Optional[str] = None
    date: Optional[str] = None
    total_amount: Optional[float] = None
    items: List[Item] = field(default_factory=list)
    source_file: Optional[str] = None
    raw_text: Optional[str] = None

    def to_dict(self, keep_raw_text: bool = True) -> Dict:
        """Receipt ni JSON-mos dict ga aylantiradi.

        `keep_raw_text=False` bo'lsa, hajmni kichraytirish uchun xom matn
        chiqarib tashlanadi.
        """
        data: Dict = {
            "merchant_name": self.merchant_name,
            "date": self.date,
            "total_amount": self.total_amount,
            "items": [it.to_dict() for it in self.items],
            "source_file": self.source_file,
        }
        if keep_raw_text:
            data["raw_text"] = self.raw_text
        return data
