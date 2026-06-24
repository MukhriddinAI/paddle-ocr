"""
Lokal qoidaviy parser — PaddleOCR xom matnidan strukturalangan
maydonlarni (merchant_name, date, total_amount, items) ajratadi.

Bu regex + heuristikaga asoslangan "best-effort" parser. U turli chek
formatlariga (MR.DIY, TONYMOLY, BEMED, ... shuningdek rus/o'zbek kirill
cheklari) moslashishga harakat qiladi, lekin g'ayrioddiy cheklarda
xatolar bo'lishi mumkin.

Til (`language`):
  • "auto" (standart) — ingliz va rus/kirill kalit so'zlarini ham sinaydi.
  • "en"            — g'arb (ingliz/malayziya) kalit so'zlariga urg'u.
  • "ru"            — rus/kirill (ИТОГО, СУММА, руб, сўм...) kalit so'zlariga urg'u.
"""

from __future__ import annotations

import re
from typing import Optional

from .models import Item, Receipt

# Qo'llab-quvvatlanadigan tillar
LANGUAGES = ("auto", "en", "ru")

# --------------------------------------------------------------------------
# Yordamchi regexlar
# --------------------------------------------------------------------------

# Minglik ajratuvchi sifatida ishlatiladigan probel turlari (oddiy, uzilmas,
# yupqa va h.k.). EU/UZ uslubidagi summalarni ("189 600,00") to'g'ri o'qish uchun.
_SPACES = "     "

# Pul summasi (US/MY uslubi): ixtiyoriy "RM"/"$" prefiks + 1234.56 yoki 1,234.56
MONEY_RE = re.compile(r"(?:RM|MYR|\$|USD)?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})|\d+\.\d{1,2})")

# Pul summasi (EU/UZ uslubi): probel = minglik, vergul = kasr -> "189 600,00", "210 300"
EU_MONEY_RE = re.compile(
    r"\d{1,3}(?:[     ]\d{3})+(?:,\d{1,2})?|\d+,\d{1,2}"
)

# "1 X 25.90 25.90" yoki "2 * 19.90 39.80" — qty X unit total
QTY_UNIT_TOTAL_RE = re.compile(
    r"(?P<qty>\d+(?:\.\d+)?)\s*[Xx*]\s*"
    r"(?P<unit>\d{1,3}(?:,\d{3})*\.\d{2})\s+"
    r"(?P<total>\d{1,3}(?:,\d{3})*\.\d{2})\b"
)

# "1 269250 300.00 300 SR" — qty code unit total [taxcode] (BEMED uslubi).
# unit albatta .NN bilan tugaydi, total butun son ham bo'lishi mumkin.
QTY_CODE_UNIT_TOTAL_RE = re.compile(
    r"^\s*(?P<qty>\d{1,3})\s+(?P<code>\d{3,})\s+"
    r"(?P<unit>\d{1,3}(?:,\d{3})*\.\d{2})\s+"
    r"(?P<total>\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\b"
)

# "1,000 X 189 600=189 600,00" — qty X unit=total (O'zbek/Rus EU POS uslubi)
EU_ITEM_RE = re.compile(
    r"(?P<qty>\d[\d     ]*(?:,\d+)?)\s*[Xx]\s*"
    r"(?P<unit>\d[\d     ]*(?:,\d{1,2})?)\s*=\s*"
    r"(?P<total>\d[\d     ]*(?:,\d{1,2})?)"
)

# Faqat raqam/kod satrlari (barcode, mahsulot kodi, "WA29 - 20" kabi)
CODE_LINE_RE = re.compile(r"^[\d\s\-/.#*]+$")

# Oydagi nomlar (qisqartmasi ham yetadi: "Apri" -> apr, "Января" -> янв)
MONTHS = {
    # Ingliz
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    # Rus (3 harfli o'zak)
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5, "мая": 5, "июн": 6,
    "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
}


def _to_float(text: str) -> Optional[float]:
    """US/MY uslubi: '1,234.56' -> 1234.56 (vergul = minglik)."""
    if text is None:
        return None
    cleaned = text.replace(",", "").replace(" ", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _eu_float(text: str) -> Optional[float]:
    """EU/UZ uslubi: '189 600,00' -> 189600.0 (probel = minglik, vergul = kasr)."""
    if text is None:
        return None
    cleaned = re.sub(r"[     ]", "", text).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Merchant nomi
# --------------------------------------------------------------------------

# Tipik kompaniya belgilari (Malayziya + rus/o'zbek)
COMPANY_HINT_RE = re.compile(
    r"\b(SDN\.?\s*BHD|SDN\.?\s*BKD|BERHAD|ENTERPRISE|TRADING|RESTAURANT|"
    r"CAFE|MART|SUPERMARKET|PHARMACY|SDN|ООО|ОАО|ЗАО|ПАО|АО|ИП|МЧЖ|ХК)\b",
    re.IGNORECASE,
)

# Merchant bo'la olmaydigan satrlar (manzil, telefon, GST, kassa rekvizitlari)
NON_MERCHANT_RE = re.compile(
    r"(GST|TAX\s*INVOICE|CASH\s*RECEIPT|RECEIPT|CO\.?\s*REG|REG\s*NO|"
    r"TEL[:.]|JALAN|LOT\b|NO\.?\s*\d|UNIT\b|FLOOR|\d{5}\b|INVOICE|"
    r"ТЕЛ|ВРЕМЯ|ДАТА|ЧЕК|КАССИР|КАССА|ИНН|АДРЕС|№\s*\d)",
    re.IGNORECASE,
)


def extract_merchant(lines: list[str]) -> Optional[str]:
    """Chek sarlavhasidan sotuvchi nomini topadi.

    Strategiya:
      1. Birinchi ~8 satr ichida kompaniya belgisi ("SDN BHD", "ООО"...) bor satrni ol.
      2. Topilmasa — manzil/telefon/raqam bo'lmagan birinchi mazmunli satrni ol.
    """
    head = [ln.strip() for ln in lines[:8] if ln.strip()]
    if not head:
        return None

    # 1) Kompaniya belgisi bor satr
    for ln in head:
        if COMPANY_HINT_RE.search(ln):
            return _clean_merchant(ln)

    # 2) Birinchi "toza" satr
    for ln in head:
        if NON_MERCHANT_RE.search(ln):
            continue
        # Kamida 3 ta harf bo'lsin, asosan raqam bo'lmasin
        letters = sum(ch.isalpha() for ch in ln)
        if letters >= 3:
            return _clean_merchant(ln)

    return _clean_merchant(head[0])


def _clean_merchant(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" -*:")
    return text


# --------------------------------------------------------------------------
# Sana
# --------------------------------------------------------------------------

# 29/03/2018 , 19-04-18 , 2018-03-29 , 11.06.2026
NUMERIC_DATE_RE = re.compile(r"\b(\d{1,4})[/\-.](\d{1,2})[/\-.](\d{2,4})\b")
# 15/April/2017 , "27 March, 2018" , "15/Apri2017" , "27 марта 2018"
MONTH_DATE_RE = re.compile(
    r"\b(\d{1,2})\s*[/\-.\s]\s*([A-Za-zА-Яа-яЁё]{3,9})\s*[/\-.,\s]\s*(\d{4})\b"
)


def _normalize_numeric(a: int, b: int, c: int) -> Optional[str]:
    """Uchta sondan ISO sana (YYYY-MM-DD) yasaydi. Tartibni aniqlaydi."""
    # YYYY-MM-DD
    if a > 31:
        year, month, day = a, b, c
    else:
        # DD-MM-YY(YY) deb taxmin qilamiz (Malayziya/EU/rus uslubi)
        day, month, year = a, b, c
        if year < 100:  # 18 -> 2018
            year += 2000
        # Agar "kun" 12 dan katta bo'lmasa-yu "oy" 12 dan katta bo'lsa, almashtiramiz
        if month > 12 and day <= 12:
            day, month = month, day
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    if year < 1990 or year > 2100:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def extract_date(text: str) -> Optional[str]:
    """Matndan birinchi ishonchli sanani topib, ISO formatga keltiradi."""
    # 1) Oy nomi bilan: "27 March 2018", "15/Apri2017", "27 марта 2018"
    m = MONTH_DATE_RE.search(text)
    if m:
        day = int(m.group(1))
        mon = MONTHS.get(m.group(2)[:3].lower())
        year = int(m.group(3))
        if mon and 1 <= day <= 31:
            return f"{year:04d}-{mon:02d}-{day:02d}"

    # 2) Raqamli sana
    for m in NUMERIC_DATE_RE.finditer(text):
        iso = _normalize_numeric(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if iso:
            return iso
    return None


# --------------------------------------------------------------------------
# Yakuniy summa (total)
# --------------------------------------------------------------------------

# Prioritet tartibida: yuqoridagilar kuchliroq signal.
# Ingliz/Malayziya kalit so'zlari
TOTAL_KEYWORDS_EN = [
    r"total\s*amt\s*payable", r"amount\s*payable", r"total\s*payable",
    r"grand\s*total", r"amount\s*due", r"net\s*total",
    r"total\s*after\s*round", r"total\s*round",
    r"total\s*incl", r"total\s*inclusive", r"total\s*sales\s*incl",
    r"total\s*amt\s*incl", r"inclusive\s*gst", r"nett\s*total",
]
# Rus/kirill kalit so'zlari: "ИТОГО К ОПЛАТЕ", "К ОПЛАТЕ", "ВСЕГО", "ИТОГ(О)", "СУММА"
TOTAL_KEYWORDS_RU = [
    r"итого?\s*к\s*оплате", r"\bк\s*оплате\b", r"всего\s*к\s*оплате",
    r"\bитого?\b", r"\bвсего\b", r"\bсумма\b",
]

# --- Tier-2 (fallback): "total/итого" so'zi — buzilgan OCR variantlari bilan ---
# OCR ko'pincha "Total" ni "Iotal", "lotal", "[otal", "Tutal", "T0tal" deb o'qiydi
# (T->I/l/[/(, o->0/u). Satr boshi / probel / ikki nuqtadan keyin keladigan, ixtiyoriy
# adashtiruvchi bош harf + "otal/utal/0tal" ni qamrab olamiz. "итого/всего/сумма" — rus.
FUZZY_TOTAL_RE = re.compile(
    r"(?:^|[\s:])[til1\[(]?[o0u]tal\b|\bитого?\b|\bвсего\b|\bсумма\b",
    re.IGNORECASE,
)
# "Inclusive GST" (img_01: "Indlusive" — c->d) — jami uchun yana bir kuchli anchor.
# "included" ni qamramaydi (in[cd]lus -> 's' talab qilinadi, "includ" da 'd').
FUZZY_INCL_RE = re.compile(r"in[cd]lus\w*", re.IGNORECASE)
# Jami satri "sub total" / "подытог" BO'LMASLIGI kerak.
SUBTOTAL_RE = re.compile(r"sub\s*[til1\[(]?[o0u]tal|подытог", re.IGNORECASE)
# Jami EMAS satrlar (jami so'zi bo'lsa ham): qaytim, to'lov turi, soni, chegirma, ballar.
TOTAL_REJECT_RE = re.compile(
    r"\b(change|tender|qty|item|saving|discount|disc|rounding\s*adj|points?|"
    r"balance|сдач|наличн|карт|скидк|дисконт)\b",
    re.IGNORECASE,
)
# "GST Summary", "GST @6% included in total", "CST summary" — gst/tax bilan BOSHLANADI.
GST_START_RE = re.compile(r"^\s*(f?g\s*s\s*t|c\s*s\s*t|got|gs[ti])\b", re.IGNORECASE)


def _total_keywords(language: str) -> list[str]:
    """Tilga qarab total kalit so'zlari ro'yxatini (prioritet bilan) qaytaradi."""
    if language == "en":
        return TOTAL_KEYWORDS_EN + TOTAL_KEYWORDS_RU
    if language == "ru":
        return TOTAL_KEYWORDS_RU + TOTAL_KEYWORDS_EN
    return TOTAL_KEYWORDS_EN + TOTAL_KEYWORDS_RU  # auto


def _money_in_line(line: str) -> Optional[float]:
    """Satrdagi oxirgi (eng o'ngdagi) pul summasini qaytaradi.

    Avval US/MY uslubini (.NN kasr), topilmasa EU/UZ uslubini ("189 600,00")
    sinaydi.
    """
    matches = MONEY_RE.findall(line)
    if matches:
        return _to_float(matches[-1])
    eu = EU_MONEY_RE.findall(line)
    if eu:
        return _eu_float(eu[-1])
    return None


def extract_total(lines: list[str], language: str = "auto") -> Optional[float]:
    """Yakuniy to'lov summasini topadi."""
    # 1) Aniq kalit so'zlar bo'yicha (prioritet tartibida). Bu kalit so'zlar
    #    ("К ОПЛАТЕ", "ИТОГО"...) o'zi kuchli signal — istisnoni qo'llamaymiz
    #    (aks holda "К ОПЛАТЕ" ichidagi "оплат" uni bloklab qo'yardi).
    for kw in _total_keywords(language):
        kw_re = re.compile(kw, re.IGNORECASE)
        for ln in lines:
            if kw_re.search(ln):
                val = _money_in_line(ln)
                if val is not None:
                    return val

    # 2) Fallback: "total/итого" (buzilgan OCR variantlari) yoki "inclusive GST"
    #    bo'lgan satrlardan eng katta summani olamiz. Sub-total, qaytim, to'lov
    #    turi, GST/tax xulosa satrlari ("GST ... included in total") chiqariladi.
    #    Buzilgan "Total"/"Inclusive" ham ushlanadi: "[otal", "Tutal", "Indlusive".
    candidates: list[float] = []
    for ln in lines:
        if SUBTOTAL_RE.search(ln) or TOTAL_REJECT_RE.search(ln) or GST_START_RE.search(ln):
            continue
        if FUZZY_TOTAL_RE.search(ln) or FUZZY_INCL_RE.search(ln):
            val = _money_in_line(ln)
            if val is not None:
                candidates.append(val)
    if candidates:
        return max(candidates)
    return None


# --------------------------------------------------------------------------
# Mahsulotlar ro'yxati (items)
# --------------------------------------------------------------------------

# Item BO'LMAGAN satrlar (chegirma, jami, qaytim va h.k.) — bularni o'tkazib yuboramiz
SKIP_ITEM_RE = re.compile(
    r"(disc(ount)?\b|rounding|sub\s*total|\btotal\b|change|tender|paid|"
    r"balance|gst\s*summary|item\s*count|item\(s\)|qty\(s\)|"
    r"\bитого?\b|\bвсего\b|\bсумма\b|оплат|наличн|\bкарт|сдач|скидк|дисконт)",
    re.IGNORECASE,
)
# "Plastic Lamination A4 @" uslubidagi description satri (img_09 kabi cheklar)
AT_DESC_RE = re.compile(r"@\s*$")
# Satr oxirida ikkita pul: "... 2.00 4.24" (unit + total)
TWO_MONEY_TAIL_RE = re.compile(
    r"(\d{1,3}(?:,\d{3})*\.\d{2})\s+(\d{1,3}(?:,\d{3})*\.\d{2})(?:\s+\S+)?\s*$"
)
# Mahsulot nomidagi tartib raqami prefiksi: "1. LI 9 PULTLIK KATTA" -> "LI 9 PULTLIK KATTA"
LEADING_NUM_RE = re.compile(r"^\s*\d{1,3}[.)]\s*")


def _is_price_line(line: str) -> bool:
    """Satr mahsulotning narx satrimi (har qanday formatda)?"""
    return bool(
        QTY_UNIT_TOTAL_RE.search(line)
        or QTY_CODE_UNIT_TOTAL_RE.match(line)
        or EU_ITEM_RE.search(line)
    )


def _looks_like_description(line: str) -> bool:
    """Satr mahsulot nomiga o'xshaydimi?

    Ikki sharddan biri bo'lsa — ha:
      • kamida bitta toza so'z (faqat harf, >= 3 belgi), yoki
      • harflar ulushi yuqori (buzilgan/qavsli nomlar: "8O-(DERMAPRO OINT)").
    Shu sabab "FLO2001600", "2 184810 105.00 330 SR" kabi kod/narx satrlari
    description deb olinmaydi.
    """
    s = LEADING_NUM_RE.sub("", line).strip()
    if len(s) < 3 or CODE_LINE_RE.match(s):
        return False
    if any(len(tok) >= 3 and tok.isalpha() for tok in re.split(r"[\s/]+", s)):
        return True
    letters = sum(ch.isalpha() for ch in s)
    return letters >= 4 and letters / len(s) >= 0.4


def _find_description(lines: list[str], price_idx: int, prefix: str) -> str:
    """Narx satridan oldin yoki yuqorisidan mahsulot nomini topadi."""
    # 1) Narx satrining o'zidagi matnli prefiks (masalan "WONDER CHEESE ... 1 * ..")
    if _looks_like_description(prefix):
        return prefix
    # 2) Yuqoridagi satrlar (kod/barcode satrlarini o'tkazib)
    for j in range(price_idx - 1, max(price_idx - 5, -1), -1):
        # Boshqa mahsulotning narx satriga yetib bormaymiz
        if _is_price_line(lines[j]):
            break
        if _looks_like_description(lines[j]):
            return lines[j].strip()
    return ""


def _make_description(text: str) -> str:
    text = LEADING_NUM_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip(" -*:") or "(noma'lum mahsulot)"


def _items_qty_x_unit_total(lines: list[str]) -> list[Item]:
    """1-strategiya: "qty X unit total" (MR.DIY, TONYMOLY...)."""
    items: list[Item] = []
    for i, ln in enumerate(lines):
        m = QTY_UNIT_TOTAL_RE.search(ln)
        if not m:
            continue
        prefix = ln[: m.start()].strip()
        description = _find_description(lines, i, prefix)
        if SKIP_ITEM_RE.search(ln) or SKIP_ITEM_RE.search(description):
            continue
        items.append(Item(
            description=_make_description(description),
            quantity=_to_float(m.group("qty")),
            unit_price=_to_float(m.group("unit")),
            price=_to_float(m.group("total")),
        ))
    return items


def _items_qty_code_unit_total(lines: list[str]) -> list[Item]:
    """2-strategiya: "qty code unit total" (BEMED uslubi, X belgisisiz)."""
    items: list[Item] = []
    for i, ln in enumerate(lines):
        m = QTY_CODE_UNIT_TOTAL_RE.match(ln)
        if not m:
            continue
        description = _find_description(lines, i, "")
        if SKIP_ITEM_RE.search(ln) or SKIP_ITEM_RE.search(description):
            continue
        items.append(Item(
            description=_make_description(description),
            quantity=_to_float(m.group("qty")),
            unit_price=_to_float(m.group("unit")),
            price=_to_float(m.group("total")),
        ))
    return items


def _items_at_style(lines: list[str]) -> list[Item]:
    """3-strategiya: "Plastic Lamination A4 @" + keyingi qator(lar)dagi narxlar.

    Narxlar bitta ("2.00 2.00 4.24") yoki bir necha ("1.00" / "7.00 7.42")
    qatorga bo'lingan bo'lishi mumkin — keyingi 3 qatorgacha yig'amiz.
    """
    items: list[Item] = []
    for i, ln in enumerate(lines):
        if not AT_DESC_RE.search(ln):
            continue
        desc = _make_description(ln.rstrip(" @"))
        moneys: list[float] = []
        for nxt in lines[i + 1: i + 4]:
            if AT_DESC_RE.search(nxt) or SKIP_ITEM_RE.search(nxt):
                break
            found = [_to_float(x) for x in MONEY_RE.findall(nxt)]
            moneys.extend(x for x in found if x is not None)
            if len(moneys) >= 2:
                break
        if len(moneys) >= 2:
            items.append(Item(
                description=desc,
                quantity=moneys[0] if len(moneys) >= 3 else None,
                unit_price=moneys[-2],
                price=moneys[-1],
            ))
    return items


def _items_eu_style(lines: list[str]) -> list[Item]:
    """4-strategiya: "qty X unit=total" (O'zbek/Rus EU POS uslubi).

    Narx satri:  "1,000 X 189 600=189 600,00"
    Mahsulot nomi odatda narx satridan YUQORIDAGI satrda bo'ladi
    (masalan "1. LI 9 PULTLIK KATTA").
    """
    items: list[Item] = []
    for i, ln in enumerate(lines):
        m = EU_ITEM_RE.search(ln)
        if not m:
            continue
        prefix = ln[: m.start()].strip()
        description = _find_description(lines, i, prefix)
        if SKIP_ITEM_RE.search(ln) or SKIP_ITEM_RE.search(description):
            continue
        items.append(Item(
            description=_make_description(description),
            quantity=_eu_float(m.group("qty")),
            unit_price=_eu_float(m.group("unit")),
            price=_eu_float(m.group("total")),
        ))
    return items


def extract_items(lines: list[str], language: str = "auto") -> list[Item]:
    """Mahsulot satrlarini ajratadi.

    Bir necha chek formati uchun strategiyalarni ketma-ket sinaydi; birinchi
    natija bergani g'olib. Shu sabab har xil do'kon formatlari qo'llanadi.
    "ru" tilida EU/UZ uslubi ("X ... = ...") avval sinaladi.
    """
    eu = (_items_eu_style,)
    other = (_items_qty_x_unit_total, _items_qty_code_unit_total, _items_at_style)
    strategies = eu + other if language == "ru" else other + eu

    for strategy in strategies:
        items = strategy(lines)
        if items:
            return items
    return []


# --------------------------------------------------------------------------
# Asosiy kirish nuqtasi
# --------------------------------------------------------------------------

def parse_receipt(
    raw_text: str,
    source_file: Optional[str] = None,
    language: str = "auto",
) -> Receipt:
    """Xom OCR matnidan to'liq Receipt obyektini yig'adi.

    `language`: "auto" (standart), "en" yoki "ru".
    """
    lines = [ln.rstrip() for ln in raw_text.splitlines()]
    non_empty = [ln for ln in lines if ln.strip()]

    return Receipt(
        merchant_name=extract_merchant(non_empty),
        date=extract_date(raw_text),
        total_amount=extract_total(non_empty, language),
        items=extract_items(non_empty, language),
        source_file=source_file,
        raw_text=raw_text,
    )
