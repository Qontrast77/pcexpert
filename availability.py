"""Проверяемый локальный снимок наличия DNS для Иркутска.

Статус available устанавливается только вручную после проверки конкретного
предложения магазина. Неизвестный статус нельзя трактовать как наличие.
"""
import csv
from datetime import date
from pathlib import Path
import catalog as cat

PATH = Path(__file__).parent / "data" / "irkutsk_stock.csv"
CATEGORIES = tuple(k for k, v in cat.CATALOG.items() if isinstance(v, list))


def load_snapshot(path=PATH):
    rows = []
    if not Path(path).exists():
        return rows
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return rows


def validated_stock(path=PATH, *, today=None, max_age_days=7):
    """Только подтверждённые позиции с датой проверки не старше max_age_days."""
    today = today or date.today()
    valid_ids = {item["id"] for catname in CATEGORIES for item in cat.CATALOG[catname]}
    allowed, rejected = set(), []
    rows = load_snapshot(path)
    for row in rows:
        ident = (row.get("id") or "").strip()
        if ident not in valid_ids or (row.get("status") or "").strip().lower() != "available":
            continue
        try:
            age = (today - date.fromisoformat(row["checked_at"])).days
        except (ValueError, KeyError, TypeError):
            rejected.append(ident)
            continue
        if 0 <= age <= max_age_days and (row.get("source_url") or "").strip().startswith("https://"):
            allowed.add(ident)
        else:
            rejected.append(ident)
    return allowed, {"rows": len(rows), "confirmed": len(allowed), "stale_or_incomplete": len(rejected),
                     "city": "Иркутск", "max_age_days": max_age_days}


def candidate_stock(path=PATH):
    """Вариант для демонстрации: товары, найденные в DNS, но без подтверждения остатков.

    Статус candidate не является available: проверку реального наличия нельзя
    заменить фактом существования карточки в онлайн-каталоге.
    """
    valid_ids = {item["id"] for catname in CATEGORIES for item in cat.CATALOG[catname]}
    rows = load_snapshot(path)
    ids = {r.get("id", "") for r in rows if r.get("id") in valid_ids
           and r.get("status", "").strip().lower() in ("candidate", "available")
           and r.get("source_url", "").startswith("https://www.dns-shop.ru/")}
    return ids, {"rows": len(rows), "confirmed": 0, "candidates": len(ids),
                 "city": "Иркутск", "source": "Карточки DNS, наличие НЕ проверено"}


def create_empty_snapshot(path=PATH):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["category", "id", "name", "status", "checked_at", "source_url", "store", "comment"])
        writer.writeheader()
        for category in CATEGORIES:
            for item in cat.CATALOG[category]:
                writer.writerow({"category": category, "id": item["id"], "name": item["name"], "status": "unknown", "checked_at": "", "source_url": "", "store": "", "comment": "Требуется проверка для Иркутска"})


if __name__ == "__main__":
    create_empty_snapshot()
    print("Создан шаблон наличия:", PATH)
