"""IEEE OUI registry'sinden `oui.json` dataset dosyasını üretir.

Bu bir bakım (maintenance) script'idir; runtime'da uygulama tarafından
çalıştırılmaz veya import edilmez. Dataset'i güncellemek için:

    curl -o oui_raw.csv https://standards-oui.ieee.org/oui/oui.csv
    python build_oui_dataset.py

Kaynak: https://standards-oui.ieee.org/oui/oui.csv (IEEE Registration
Authority resmi MA-L / 24-bit OUI kaydı).

Yalnızca "Assignment" (OUI, 6 hex karakter) ve "Organization Name"
sütunları kullanılır; adres bilgisi (Organization Address) atılır —
uygulamanın ihtiyacı yalnızca vendor adıdır ve adres sütunu dataset
boyutunu gereksiz yere büyütür.

Bilinen anomali: IEEE kaydında 2 OUI (080030, 0001C8), çok eski/tarihsel
tahsislere ait birden fazla organizasyon adına sahip. Bu script, dosyada
karşılaşılan ilk organizasyon adını tutar ve diğerlerini atar.
"""

import csv
import json
from pathlib import Path

RAW_CSV = Path(__file__).parent / "oui_raw.csv"
OUTPUT_JSON = Path(__file__).parent / "oui.json"


def build() -> None:
    entries: dict[str, str] = {}
    duplicate_count = 0

    with RAW_CSV.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            oui = row["Assignment"].strip().upper()
            organization = row["Organization Name"].strip()

            if len(oui) != 6:
                continue
            if oui in entries:
                duplicate_count += 1
                continue

            entries[oui] = organization

    OUTPUT_JSON.write_text(
        json.dumps(entries, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    print(f"{len(entries)} OUI kaydı yazıldı -> {OUTPUT_JSON}")
    print(f"{duplicate_count} tekrarlanan OUI atlandı (ilk kayıt tutuldu)")


if __name__ == "__main__":
    build()
