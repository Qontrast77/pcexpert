"""Импорт проверенных вручную предложений DNS для Иркутска.
Пример: python pricing/import_dns_prices.py pricing/dns_irkutsk_template.csv
Без URL, даты и цены строка пропускается. Исторические данные не подменяются.
"""
import csv
import json
import re
import sys
from pathlib import Path
from datetime import date
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog.json"


def apply_prices(csv_path: Path, output: Path | None = None) -> tuple[int, int]:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    index = {(kind, row["id"]): row for kind, arr in data.items()
             if isinstance(arr, list) for row in arr}
    updated, skipped = 0, 0
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        for entry in csv.DictReader(stream):
            key = (entry["category"].strip(), entry["id"].strip())
            url = entry["dns_product_url"].strip()
            price = entry["price_rub"].strip()
            checked = entry["checked_at"].strip()
            city = entry["city"].strip()
            dns_name = entry["dns_product_name"].strip()
            if not (url or price or checked or dns_name):
                skipped += 1
                continue
            if key not in index:
                raise ValueError(f"Неизвестный товар {key}")
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.hostname not in ("dns-shop.ru", "www.dns-shop.ru") or not parsed.path.startswith("/product/"):
                raise ValueError(f"Неверная карточка DNS: {key}")
            if not re.fullmatch(r"[1-9]\d*", price):
                raise ValueError(f"Неверная цена: {key}")
            if date.fromisoformat(checked) > date.today():
                raise ValueError(f"Дата в будущем: {key}")
            if city.casefold() != "иркутск" or not dns_name:
                raise ValueError(f"Нужны Иркутск и точное название DNS: {key}")
            record = index[key]
            record.update(price=int(price), name=dns_name,
                          price_verified=True, price_source="DNS",
                          price_city="Иркутск", price_checked_at=checked,
                          product_url=url)
            updated += 1
    total = len(index)
    verified = sum(int(item.get("price_verified", False)) for item in index.values())
    data["_meta"].update(city="Иркутск", verified_count=verified,
                         total_count=total,
                         price_status="verified" if verified == total else "partial_unverified")
    target = output or CATALOG
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return updated, skipped


if __name__ == "__main__":
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "pricing/dns_irkutsk_template.csv"
    n, skipped = apply_prices(source)
    print(f"Проверенных цен загружено: {n}; незаполненных строк: {skipped}")
