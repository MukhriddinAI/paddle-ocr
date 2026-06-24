# Receipt Parser (PaddleOCR)

Kassa cheklari rasmidan PaddleOCR yordamida quyidagi maydonlarni ajratib
oluvchi loyiha:

- **merchant_name** — sotuvchi/korxona nomi
- **date** — chek sanasi (ISO `YYYY-MM-DD` ko'rinishida normallashtirilgan)
- **total_amount** — yakuniy to'lov summasi (`float`)
- **items** — mahsulotlar ro'yxati, har biri: `description`, `quantity`,
  `unit_price`, `price`
- **source_file** — manba rasm fayl nomi

> Ajratish to'liq **qoidaviy (rule-based)** — regex va heuristikalarga
> asoslangan. Ish vaqtida hech qanday LLM/generativ AI ishlatilmaydi
> (qarang: [AI shaffofligi](#ai-shaffofligi)).

## Loyiha tuzilmasi

```
PaddleOCR/
├── main.py                 # CLI kirish nuqtasi (rasm/papka -> JSON)
├── evaluate.py             # ground-truth bilan solishtirish (maydon aniqligi)
├── requirements.txt
├── src/
│   ├── ocr_engine.py       # PaddleOCR wrapper (2.x va 3.x API) + qator tiklash
│   ├── parser.py           # maydon ajratish (merchant/date/total/items) mantiqi
│   ├── models.py           # Item, Receipt ma'lumot modellari
│   ├── pipeline.py         # orkestratsiya: rasm -> OCR -> parser -> JSON
│   └── config.py           # OCR tili va qator guruhlash sozlamalari
└── data/
    ├── input/              # baholash to'plami (img_01..img_09)
    ├── test_input/         # erkin sinov rasmlari (photo_2026-...)
    ├── ground_truth.json   # qo'lda belgilangan to'g'ri javoblar (baholash uchun)
    └── output/             # natija JSON fayllar + _gt_report.json
```

## O'rnatish

Repo faqat **kodni** o'z ichiga oladi — virtual muhit (`paddle_env`) repoga
kirmaydi (`.gitignore`), shuning uchun clone qilgandan keyin uni o'zingiz
yaratasiz. Python 3.8–3.12 talab qilinadi.

```bash
# 1. Reponi clone qiling
git clone https://github.com/MukhriddinAI/paddle-ocr.git
cd paddle-ocr

# 2. Virtual muhit yarating
python -m venv paddle_env

# 3. Kerakli kutubxonalarni o'rnating
#    Windows:
paddle_env/Scripts/python.exe -m pip install -r requirements.txt
#    Linux / macOS:
#    paddle_env/bin/python -m pip install -r requirements.txt
```

> **Birinchi ishga tushirishda** PaddleOCR aniqlash/tanish modellarini
> avtomatik internetdan yuklab oladi (bir necha 100 MB) — shuning uchun
> birinchi marta internet ulanishi kerak. Keyin offline ishlaydi.
>
> GPU uchun `paddlepaddle` o'rniga `paddlepaddle-gpu` o'rnating va
> `--gpu` bayrog'ini ishlating.

## Ishlatish

```bash
# Standart: data/input -> data/output
paddle_env/Scripts/python main.py

# Boshqa papkani qayta ishlash (masalan erkin sinov rasmlari)
paddle_env/Scripts/python main.py -i data/test_input -o data/output

# Bitta rasm (natija ekranga chiqadi va papkaga ham saqlanadi)
paddle_env/Scripts/python main.py -i data/input/img_01.jpg

# Natijaga xom OCR matnini ham qo'shish (debug uchun foydali)
paddle_env/Scripts/python main.py --raw

# Parser/OCR tili (en yoki ru)
paddle_env/Scripts/python main.py -l en
```

CLI bayroqlari: `-i/--input` (default `data/input`),
`-o/--output` (default `data/output`), `-l/--lang` (default `en`),
`--raw`, `--gpu`.

## Chiqish (output) namunasi

`data/output/img_01.json`:

```json
{
  "merchant_name": "BEMED (SP) SDN. BHD.",
  "date": "2017-04-15",
  "total_amount": 635.0,
  "items": [
    {
      "description": "PRISTIN OMEGA-3 FISH OIL 2X150S(VIP)",
      "quantity": 1.0,
      "unit_price": 300.0,
      "price": 300.0
    }
  ],
  "source_file": "img_01.jpg"
}
```

> `--raw` bilan ishga tushirilsa, natijaga `raw_text` (fazoviy tartiblangan
> xom OCR matni) maydoni ham qo'shiladi. Topilmagan maydonlar `null`
> (yoki `items` uchun bo'sh ro'yxat) bo'ladi.

## Qanday ishlaydi

1. **OCR** (`ocr_engine.py`) — PaddleOCR rasmni o'qib, har bir matn bloki
   uchun matn, ishonchlilik bali (`score`) va joylashuv (bounding box)
   qaytaradi. Wrapper PaddleOCR 2.x (`ocr`) va 3.x (`predict`) API'larining
   ikkalasini ham qo'llab-quvvatlaydi.
2. **Qatorlarni tiklash** (`ocr_engine.lines_to_text`) — bloklar vertikal
   markazi (`cy`) bo'yicha qatorlarga guruhlanadi (`ROW_GROUP_TOLERANCE`),
   har qator ichida chapdan o'ngga tartiblanadi va bitta xom matnga
   aylantiriladi.
3. **Maydon ajratish** (`parser.py`) — heuristikalar asosida:
   - **merchant**: yuqoridagi qatorlardan korxona belgisi bor satr
     (`SDN BHD`, `ENTERPRISE`, `ООО` ...); topilmasa birinchi "toza" satr.
   - **date**: oy nomi (`27 March 2018`, `27 марта 2018`) va raqamli
     (`29/03/2018`, `19-04-18`) shablonlar → ISO `YYYY-MM-DD` ga
     normallashtiriladi.
   - **total**: avval prioritetli kalit so'zlar (`Total Payable`,
     `Grand Total`, `Total After Rounding`, `ИТОГО`, `К ОПЛАТЕ` ...); ular
     topilmasa zaxira mantiq buzilgan OCR variantlarini (`[otal`, `Tutal`,
     `Indlusive GST`) ham qidiradi va `subtotal`/qaytim/soliq satrlarini
     chetlab o'tadi.
   - **items**: 4 ta format strategiyasi ketma-ket sinaladi —
     `qty X unit total` (MR.DIY/TONYMOLY), `qty kod unit total` (BEMED),
     `"@"` uslubi, va `qty X unit=total` (O'zbek/Rus EU POS uslubi).

## Aniqlikni baholash

`evaluate.py` pipeline natijalarini (`data/output/*.json`) qo'lda belgilangan
`data/ground_truth.json` bilan solishtiradi va har maydon uchun aniqlik foizini
chiqaradi.

```bash
# Natijalarni baholash (ekranga jadval + umumiy natija)
# --output_dir default `data/output` — main.py ham aynan shu yerga yozadi
paddle_env/Scripts/python evaluate.py data/ground_truth.json

# Hisobotni faylga ham saqlash (data/output/_gt_report.json)
paddle_env/Scripts/python evaluate.py data/ground_truth.json --save_report

# Qat'iy rejim: total ±0% tolerans, merchant nomi aniq mos kelishi shart
paddle_env/Scripts/python evaluate.py data/ground_truth.json --strict
```

Baholash mezonlari: **merchant** — so'zlarning ≥50% mosligi (yumshoq rejim),
**date** — ISO `YYYY-MM-DD` ga normallashtirib solishtirish, **total** — ±5%
tolerans (yumshoq), **items** — GT mahsulotlarining necha foizi natijada
topilgani.

Joriy baholash to'plamida (`data/ground_truth.json`, 10 fayl):

```
══════════════════════════════════════════════════════════════════════════════════════════
  UMUMIY NATIJA  [YUMSHOQ (±5% tolerans)]   (10 fayl)
══════════════════════════════════════════════════════════════════════════════════════════
  merchant_name : 10/10  (100%)
  date          : 10/10  (100%)
  total_amount  : 9/10   (90%)
  items (avg)   : 80%

  Umumiy aniqlik (merchant+date+total) : 96.7%
  AC-2 (date≥70% va total≥70%)         : ✅ O'TDI
```

Batafsil tahlil va xatolar tahlili — [`RESULTS.md`](RESULTS.md).

## AI shaffofligi

**Ish vaqtida (runtime):** loyiha **generativ AI ishlatmaydi**. Yagona
neyron model — bu **PaddleOCR** (matnni aniqlash/tanish uchun computer-vision
model). Maydon ajratish mantig'i (`parser.py`) to'liq **deterministik
regex va qoidalar** — offline, takrorlanuvchi, LLM chaqiruvisiz.

**Ishlab chiqishda (development):** kod yozish va sozlashda AI yordamchisi
(Claude Code — LLM asosidagi koding agent) quyidagilarda ishlatilgan:

- modul tuzilmasini (`ocr_engine` / `parser` / `pipeline` / `models`)
  loyihalash;
- regex shablonlari va heuristikalarni yozish va iteratsiya qilish;
- xom OCR matnini tahlil qilib, ajratish xatolarini debug qilish
  (masalan, `total_amount` zaxira mantig'ini buzilgan "Total" variantlari
  uchun mustahkamlash);
- `README.md`, `RESULTS.md` va kod izohlarini yozish.

Yakuniy mantiq va qarorlar ko'rib chiqilgan; barcha regex/heuristikalar
`parser.py` ichida ochiq va tekshiriladigan holda turadi.

## Cheklovlar

OCR shovqini va cheklarning xilma-xilligi sababli ajratish **heuristik**
bo'lib, 100% aniq emas. Yangi chek turlari uchun `parser.py` dagi kalit
so'z va shablonlarni moslang. Aniqlikni tekshirish uchun `--raw` bilan xom
matnni ko'rib chiqish foydali. To'liq kamchiliklar tahlili — [`RESULTS.md`](RESULTS.md).
