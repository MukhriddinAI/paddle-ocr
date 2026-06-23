"""Sozlamalar: OCR engine va qator guruhlash uchun konstantalar.

Eslatma: maydon ajratish (merchant, sana, total, items) bilan bog'liq barcha
heuristikalar va regexlar `parser.py` ichida — bu yerda faqat OCR va OCR
natijasini matnga aylantirish (`lines_to_text`) uchun sozlamalar qoladi.
"""

# --- OCR sozlamalari ---------------------------------------------------------

# PaddleOCR tili. Cheklar asosan inglizcha bo'lgani uchun "en".
OCR_LANG = "en"

# Bitta qatorni (row) aniqlashda vertikal markazlar farqi shu nisbatdan
# kichik bo'lsa, ular bitta qatorga birlashtiriladi (matn balandligiga nisbatan).
ROW_GROUP_TOLERANCE = 0.6
