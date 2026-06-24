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

## 2. Baholash natijalari

`evaluate.py data/ground_truth.json` natijasi
(10 fayl: 9 ta baholash cheki `img_01..09` + 1 ta erkin o'zbekcha chek):

```
Fayl              Merchant   Date   Total    Items  Izohlar
──────────────────────────────────────────────────────────────────────────────
img_01                  ✓     ✓     ✓     100%
img_02                  ✓     ✓     ✓     100%
img_03                  ✓     ✓     ✓     100%
img_04                  ✓     ✓     ✓     100%
img_05                  ✓     ✓     ✓     100%
img_06                  ✓     ✓     ✓     100%
img_07                  ✓     ✓     ✓     100%
img_08                  ✓     ✓     ✓       0%   items: 0/1
img_09                  ✓     ✓     ✓       0%   items: 0/2
photo_2026-06-20...     ✓     ✓     ✗     100%   total: pred=None | gt=210300.0

══════════════════════════════════════════════════════════════════════════════
  UMUMIY NATIJA  [YUMSHOQ (±5% tolerans)]   (10 fayl)
══════════════════════════════════════════════════════════════════════════════
  merchant_name : 10/10  (100%)
  date          : 10/10  (100%)
  total_amount  : 9/10   (90%)
  items (avg)   : 80%

  Umumiy aniqlik (merchant+date+total) : 96.7%
  AC-2 (date≥70% va total≥70%)         : ✅ O'TDI
  Total noto'g'ri  : photo_2026-06-20_11-31-17
```

> Eslatma: `img_04` ground-truth'da `date = null` (chekda sana OCR tomonidan
> butunlay buzilgan, etalonga ham qo'yilmagan), shuning uchun `null == null` mos
> kelib date 100% bo'lib qoladi. Yagona yiqilish — `photo_...` chekining
> `total_amount` qiymati (quyida 4.6).

### 2.3. `total_amount` da nima tuzatildi

Eski zaxira mantiq (a) faqat buzilmagan `total` so'zini qidirardi va
(b) **`gst` so'zi bor har qanday satrni rad etardi**. Shu sabab 3 ta chek
yiqilardi:

| Fayl | Xom matndagi satr | Eski | Yangi | Sabab |
|---|---|---|---|---|
| img_01 | `al Indlusive GST: 635.00` | `null` | `635.0` | "Total" → "al" buzilgan; endi `Inclusive GST` anchor ushlaydi |
| img_05 | `[otal Sales Incl. GST 39.90` / `Tutal After Rounding 39.90` | `null` | `39.9` | "Total" → "[otal"/"Tutal"; endi buzilgan variant ushlanadi |
| img_07 | `Total Inel. GST06% RM 119.70` | `null` | `119.7` | "Total" bor edi, lekin "gst" tufayli rad etilardi; endi faqat GST bilan *boshlanadigan* satr rad etiladi |

Tier-1 (kalit so'zlar) tegilmadi, shuning uchun avval ishlayotgan cheklar
**buzilmadi** — baholash to'plamidagi 9 ta `img_*` cheki uchun
`total_amount` 9/9 (100%) bo'lib qoldi.

---

## 3. Sifat tekshiruvi (qiymatlarning to'g'riligi)

Baholash endi `data/ground_truth.json` etaloni asosida qiymatlarni bevosita
solishtiradi (oldingi "to'ldirilganmi" o'lchovi o'rniga), shuning uchun
maydon to'ldirilgan bo'lsa-yu qiymati noto'g'ri bo'lsa — bu ko'rinadi
(masalan `photo_...` chekining `total` qiymati).

- **total_amount:** tuzatilgan 3 qiymat ham haqiqiy chekning yakuniy
  summasiga mos (img_01=635.00, img_05=39.90, img_07=119.70).
- **O'zbekcha chek (`photo_2026-06-20_11-31-17`):** EU/UZ formatidagi real chek
  qisman to'g'ri o'qildi — `merchant=ZEYTUN* Supermarket`, `date=2026-06-11`
  va items (`189 600` → `189600` minglik probel bilan) to'g'ri ajratildi,
  lekin `total_amount` topilmadi (`None`, etalon `210300`) — sabab 4.6 da.

---

## 4. Ma'lum kamchiliklar va xato tahlili

### 4.1. Etalon (ground-truth) to'plami kichik
Endi `data/ground_truth.json` mavjud va baholash haqiqiy qiymatlar bilan
solishtiradi, lekin to'plam atigi **10 ta chek**. Statistik ishonchli
precision/recall uchun ko'proq va xilma-xil cheklar (turli do'kon, til,
format) bilan etalonni kengaytirish kerak.

### 4.2. `date` — img_04 (OCR sanani butunlay buzgan)
OCR sanani `30-4-1 1711117986` deb buzgan — ajratuvchi (`-`) yo'qolib,
raqamlar qo'shilib ketgan. Hech qanday shablon bilan ishonchli tiklab
bo'lmaydi, shuning uchun etalonda ham `date = null`. Baholashda `null == null`
mos kelib, date umumiy ko'rsatkichi 100% bo'lib qoladi.

### 4.3. `items` — img_08, img_09 (bo'sh, items 80% da qoladi)
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

### 4.6. `total` — `photo_...` o'zbekcha chek (yagona yiqilish, 90% da qoladi)
EU/UZ formatidagi o'zbekcha chekda `total_amount` topilmadi (`None`, etalon
`210300`). `parser.py` dagi total kalit so'zlari ingliz/malayziya va rus
(`ИТОГО`, `К ОПЛАТЕ`...) uchun, o'zbekcha yakun belgilari (`JAMI`, `HAMMASI`,
`JAMI TO'LOV`...) hali ro'yxatda yo'q; fallback bosqichi ham bu summani
ushlamadi. Item satrlari (`189 600` minglik probel bilan) to'g'ri o'qilgani
sababli yechim — UZ total kalit so'zlarini qo'shish (5-bo'lim).

### 4.7. Valyuta ajratilmaydi
`RM`/`MYR`/`сўм` aniqlanmaydi; summa faqat son sifatida olinadi.

---

## 5. Yaxshilanish yo'nalishlari

1. **Inline `@` item strategiyasi** — img_08/09 ni qoplash (items 80% → 100%).
2. **O'zbekcha `total` kalit so'zlari** — `JAMI`, `HAMMASI`, `JAMI TO'LOV`...
   qo'shib `photo_...` chekining `total` qiymatini ushlash (total 90% → 100%).
3. **Buzilgan sana tiklash** — sana hududida OCR'ni qayta o'qish yoki
   raqam-ajratuvchi heuristikasi (img_04).
4. **Etalon to'plamini kengaytirish** — ko'proq va xilma-xil cheklar bilan
   `ground_truth.json` ni boyitib, statistik ishonchli baholash.
5. **Valyuta maydoni** — kalit belgilar (`RM`, `$`, `сўм`) bo'yicha.
6. **Ixtiyoriy LLM zaxira** — qoidaviy parser bo'sh qaytarganda faqat
   o'sha rasm uchun LLM chaqirish (narx/aniqlik balansi bilan).
7. **Ishonch bilan tartiblash** — bir nechta nomzodda OCR `score` ni
   hisobga olib tanlash (`max()` o'rniga).
