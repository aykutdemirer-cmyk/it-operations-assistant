# OUI Vendor Dataset

**Kaynak:** [https://standards-oui.ieee.org/oui/oui.csv](https://standards-oui.ieee.org/oui/oui.csv)
— IEEE Registration Authority'nin resmi MA-L (24-bit / 3-octet OUI)
kaydı.

**Elde edilme tarihi:** 2026-08-25

**İçerik:** `oui.json` — `{"AABBCC": "Organizasyon Adı"}` biçiminde,
6 hex karakterlik (ayraçsız, büyük harf) OUI → üretici adı eşlemesi.
40.007 benzersiz kayıt.

**İşleme:**
- Yalnızca `Assignment` (OUI) ve `Organization Name` sütunları alınır;
  `Organization Address` sütunu atılır (uygulama yalnızca vendor adına
  ihtiyaç duyar, adres dataset boyutunu gereksiz büyütür).
- 3 OUI (`080030`, `0001C8`) kayıtta birden fazla organizasyon adına
  sahip (çok eski/tarihsel tahsisler). Dosyada karşılaşılan ilk
  organizasyon adı tutulur, diğerleri atılır.
- Üretim script'i: `build_oui_dataset.py` (runtime'da çalışmaz, yalnızca
  dataset güncellenirken elle çalıştırılır).

**Runtime davranışı:** Uygulama yalnızca `oui.json`'ı okur; hiçbir
zaman IEEE'ye veya başka bir internet kaynağına istek atmaz.

**Güncelleme (ileride ayrı bir bakım işlemi):**
```bash
curl -o oui_raw.csv https://standards-oui.ieee.org/oui/oui.csv
python build_oui_dataset.py
rm oui_raw.csv
```
`oui_raw.csv` geçici bir ara dosyadır, repoya eklenmez (bkz. `.gitignore`).
