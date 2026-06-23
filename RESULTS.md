# RESULTS — natijalar, tanlovlar va kamchiliklar tahlili

Bu hujjat loyihadagi muhandislik qarorlarini, baholash natijalarini
(Report 1 → Report 2 yaxshilanishi) va ma'lum kamchiliklarni mustaqil
tahlil qiladi.

---

## 1. Yondashuv va asosiy tanlovlar

### 1.1. Qoidaviy (rule-based) parser — LLM emas

Maydon ajratish uchun **deterministik regex + heuristika** tanlandi,
ajratishni LLM'ga topshirish o'rniga.

| Mezon | Rule-based (tanlangan) | LLM ekstraksiya |
|---|---|---|
| Narx / bog'liqlik | Bepul, offline, API'siz | Token to'lovi, internet/kalit kerak |
| Takrorlanuvchanlik | To'liq deterministik | Stoxastik, versiyaga bog'liq |
| Shaffoflik | Har qoida `parser.py` da ko'rinadi | "Qora quti" |
| Tezlik | Bir necha ms | Tarmoq kechikishi |
| Kamchiligi | Har format uchun sozlash kerak | Sozlashsiz moslashuvchan |

Topshiriq aniq 4 maydon va cheklangan chek turlari bilan chegaralangani
uchun qoidaviy yondashuv yetarli, arzon va tushuntirib beriladigan.
LLM faqat *ixtiyoriy zaxira* sifatida kelajakda qo'shilishi mumkin
(1-bo'lim, "Yaxshilanish yo'nalishlari").

### 1.2. OCR — PaddleOCR

PaddleOCR ko'p tilli, har blok uchun **matn + ishonch bali + bounding box**
qaytaradi va 2.x/3.x API'lari bor. Bounding box ayniqsa muhim — usiz
"chapda tavsif, o'ngda narx" tuzilishini tiklab bo'lmaydi.

### 1.3. Fazoviy qator tiklash (`ocr_engine.lines_to_text`)

OCR bloklarni tartibsiz qaytaradi. Ularni **vertikal markaz (`cy`)** bo'yicha
qatorlarga guruhlab, har qator ichida **chapdan o'ngga** tartiblab, bitta
"o'qiladigan" matnga aylantiramiz. Shu qaror tufayli parser oddiy
satr-asosli regex bilan ishlay oladi (`ROW_GROUP_TOLERANCE` matn
balandligiga nisbatan sozlanadi).

### 1.4. items — ko'p strategiyali

Har do'kon mahsulot satrini boshqacha yozadi. 4 strategiya ketma-ket
sinaladi, **birinchi natija bergani g'olib**:

1. `qty X unit total` — MR.DIY / TONYMOLY
2. `qty kod unit total` — BEMED (X belgisisiz)
3. `"@"` uslubi — keyingi qatorlardagi narxlar
4. `qty X unit=total` — O'zbek/Rus EU POS uslubi (`1,000 X 189 600=189 600,00`)

### 1.5. total — ikki bosqichli (bu yerda yaxshilandi)

- **1-bosqich (kuchli):** prioritetli kalit so'zlar — `Total Payable`,
  `Grand Total`, `Total After Rounding`, `Total Incl GST`, `ИТОГО`,
  `К ОПЛАТЕ` ...
- **2-bosqich (zaxira):** kalit so'z topilmasa, **buzilgan OCR variantlari**
  ham qidiriladi (`[otal`, `Tutal`, `Iotal`, `Indlusive GST`), `subtotal` /
  qaytim / to'lov turi / GST-xulosa satrlari chetlab o'tiladi.

---

## 2. Baholash natijalari: Report 1 → Report 2

Baholash to'plami: `data/input` dagi 9 ta chek (`img_01..img_09`).
Etalon (ground-truth) yo'qligi sababli o'lchov — maydonning **to'ldirilish
foizi** (qarang: 4-bo'lim, cheklov).

### 2.1. Umumiy taqqoslash

| Ko'rsatkich | Report 1 | Report 2 | O'zgarish |
|---|---|---|---|
| OCR ishonch darajasi | 95.1% | 95.1% | — |
| **Maydon to'liqligi** | **83.3%** (30/36) | **91.7%** (33/36) | **+8.4 p.p.** |

### 2.2. Maydon bo'yicha

| Maydon | Report 1 | Report 2 | Holat |
|---|---|---|---|
| merchant_name | 9/9 (100%) | 9/9 (100%) | ✅ |
| date | 8/9 (89%) | 8/9 (89%) | ✅ ≥70% |
| **total_amount** | **6/9 (67%)** ❌ | **9/9 (100%)** ✅ | **+3 fayl** |
| items | 7/9 (78%) | 7/9 (78%) | ✅ |

Acceptance mezoni (`total_amount` va `date` ≥ 70%) **bajarildi**:
total 67% → 100%, date 89%.

### 2.3. `total_amount` da nima tuzatildi

Eski zaxira mantiq (a) faqat buzilmagan `total` so'zini qidirardi va
(b) **`gst` so'zi bor har qanday satrni rad etardi**. Shu sabab 3 ta chek
yiqilardi:

| Fayl | Xom matndagi satr | Eski | Yangi | Sabab |
|---|---|---|---|---|
| img_01 | `al Indlusive GST: 635.00` | `null` | `635.0` | "Total" → "al" buzilgan; endi `Inclusive GST` anchor ushlaydi |
| img_05 | `[otal Sales Incl. GST 39.90` / `Tutal After Rounding 39.90` | `null` | `39.9` | "Total" → "[otal"/"Tutal"; endi buzilgan variant ushlanadi |
| img_07 | `Total Inel. GST06% RM 119.70` | `null` | `119.7` | "Total" bor edi, lekin "gst" tufayli rad etilardi; endi faqat GST bilan *boshlanadigan* satr rad etiladi |

Tier-1 (kalit so'zlar) tegilmadi, shuning uchun avval ishlayotgan 5 ta
chek (img_02/03/04/06/08) **buzilmadi** — 9/9 birlik test bilan tasdiqlandi.

---

## 3. Sifat tekshiruvi (qiymatlarning to'g'riligi)

To'liqlik = "to'ldirilganmi", lekin qiymat to'g'rimi? Qo'lda tekshiruv:

- **total_amount:** tuzatilgan 3 qiymat ham haqiqiy chekning yakuniy
  summasiga mos (img_01=635.00, img_05=39.90, img_07=119.70).
- **Ko'rilmagan rasm (live):** `data/test_input` dagi real o'zbekcha chek
  to'g'ri o'qildi — `merchant=ZEYTUN* Supermarket`, `date=2026-06-11`,
  `total=210300`, EU/UZ formati (`189 600` → `189600`) bilan items.

---

## 4. Ma'lum kamchiliklar va xato tahlili

### 4.1. Etalon (ground-truth) yo'q
"Aniqlik" o'rniga "to'ldirilish foizi" o'lchanadi: maydon *to'ldirilgan*
bo'lsa-yu qiymati *noto'g'ri* bo'lsa, o'lchov buni ko'rmaydi. To'liq
precision/recall uchun har maydonga qo'lda etalon yorliq kerak.

### 4.2. `date` — img_04 (1 ta yiqilish, 89% da qoladi)
OCR sanani `30-4-1 1711117986` deb butunlay buzgan — ajratuvchi (`-`)
yo'qolib, raqamlar qo'shilib ketgan. Hech qanday shablon bilan ishonchli
tiklab bo'lmaydi. Date baribir 89% (talab 70% dan yuqori).

### 4.3. `items` — img_08, img_09 (bo'sh, 78% da qoladi)
Bu cheklarda format `A4 BW Simili 80gsm @ 7.00 7.42` — ya'ni `@` belgisi
narxlar bilan **bitta satrda** (oxirida emas). Joriy `"@"` strategiyasi esa
satr **oxirida** turgan `@` ni kutadi (`desc @` → keyingi qatorda narxlar),
shu sabab bu format ushlanmaydi.

### 4.4. OCR shovqini — keng tarqalgan ildiz sabab
Yiqilishlarning aksariyati noto'g'ri ajratish emas, balki **OCR'ning o'zi
xato o'qishi**: `Total`→`[otal`, `635`→`035`, `Incl`→`Inel`, sana
ajratuvchilarining yo'qolishi. Zaxira mantiq buzilgan *so'zlarni* tuzatadi,
lekin buzilgan *raqamlarni* tuzata olmaydi.

### 4.5. `total` da `max()` evristikasi
Zaxira bosqichda bir nechta nomzoddan eng kattasi olinadi. Odatda to'g'ri
(yakuniy summa subtotal/soliqdan katta), lekin g'ayrioddiy joylashuvda
xato qiymat tanlanishi mumkin.

### 4.6. Valyuta ajratilmaydi
`RM`/`MYR`/`сўм` aniqlanmaydi; summa faqat son sifatida olinadi.

---

## 5. Yaxshilanish yo'nalishlari

1. **Inline `@` item strategiyasi** — img_08/09 ni qoplash (items 78% → 100%).
2. **Buzilgan sana tiklash** — sana hududida OCR'ni qayta o'qish yoki
   raqam-ajratuvchi heuristikasi (img_04).
3. **Etalon yorliqlar** — har maydon uchun ground-truth, haqiqiy
   precision/recall o'lchash.
4. **Valyuta maydoni** — kalit belgilar (`RM`, `$`, `сўм`) bo'yicha.
5. **Ixtiyoriy LLM zaxira** — qoidaviy parser bo'sh qaytarganda faqat
   o'sha rasm uchun LLM chaqirish (narx/aniqlik balansi bilan).
6. **Ishonch bilan tartiblash** — bir nechta nomzodda OCR `score` ni
   hisobga olib tanlash (`max()` o'rniga).
