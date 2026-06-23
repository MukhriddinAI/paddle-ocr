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
├── evaluate.py             # aniqlik hisoboti (confidence + maydon to'liqligi)
├── requirements.txt
├── src/
│   ├── ocr_engine.py       # PaddleOCR wrapper (2.x va 3.x API) + qator tiklash
│   ├── parser.py           # maydon ajratish (merchant/date/total/items) mantiqi
│   ├── models.py           # Item, Receipt ma'lumot modellari
│   ├── pipeline.py         # orkestratsiya: rasm -> OCR -> parser -> JSON
│   └── config.py           # OCR tili va qator guruhlash sozlamalari
└── data/
    ├── input/              # baholash to'plami (img_01..img_09)
    ├── test_input/         # erkin sinov rasmlari
    └── output/PaddleOCR/   # natija JSON fayllar
```

## O'rnatish

Loyiha bilan birga `paddle_env` virtual muhiti keladi. Kerakli
kutubxonalar:

```bash
paddle_env/Scripts/python.exe -m pip install -r requirements.txt
```

> GPU uchun `paddlepaddle` o'rniga `paddlepaddle-gpu` o'rnating va
> `--gpu` bayrog'ini ishlating.

## Ishlatish

```bash
# Standart: data/test_input -> data/output/PaddleOCR
paddle_env/Scripts/python.exe main.py

# Baholash to'plamini qayta ishlash: data/input -> data/output/PaddleOCR
paddle_env/Scripts/python.exe main.py -i data/input -o data/output/PaddleOCR

# Bitta rasm (natija ekranga chiqadi va papkaga ham saqlanadi)
paddle_env/Scripts/python.exe main.py -i data/input/img_01.jpg

# Natijaga xom OCR matnini ham qo'shish (debug uchun foydali)
paddle_env/Scripts/python.exe main.py --raw

# Parser/OCR tili (en yoki ru)
paddle_env/Scripts/python.exe main.py -l en
```

CLI bayroqlari: `-i/--input` (default `data/test_input`),
`-o/--output` (default `data/output/PaddleOCR`), `-l/--lang` (default `en`),
`--raw`, `--gpu`.

## Chiqish (output) namunasi

`data/output/PaddleOCR/img_01.json`:

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

`evaluate.py` `data/input` rasmlarini qayta o'qib, ikki o'lchov beradi:
OCR ishonch darajasi va 4 ta maydonning to'ldirilish foizi. Natija
`data/output/PaddleOCR/_accuracy_report.json` ga saqlanadi.

```bash
paddle_env/Scripts/python.exe evaluate.py
```

Joriy natija: OCR ishonchi **95.1%**, maydon to'liqligi **91.7%**
(`total_amount` 100%, `date` 89%). Batafsil tahlil — [`RESULTS.md`](RESULTS.md).

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
