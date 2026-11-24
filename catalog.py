"""Справочник комплектующих и запросы к нему."""
import json
import contextvars
from pathlib import Path

_PATH = Path(__file__).parent / "data" / "catalog.json"

with open(_PATH, encoding="utf-8") as fh:
    CATALOG = json.load(fh)

CPU = CATALOG["cpu"]
GPU = CATALOG["gpu"]
MB = CATALOG["motherboard"]
RAM = CATALOG["ram"]
SSD = CATALOG["ssd"]
HDD = CATALOG["hdd"]
PSU = CATALOG["psu"]
CASE = CATALOG["case"]
COOLER = CATALOG["cooler"]

# Фильтр местного наличия действует только на один запуск механизма вывода.
# В основном режиме None означает отсутствие ограничений по наличию.
_STOCK_IDS = contextvars.ContextVar("irkutsk_stock_ids", default=None)


def stock(items):
    """Список с подтверждённым наличием в выбранном снимке Иркутска."""
    allowed = _STOCK_IDS.get()
    return list(items) if allowed is None else [x for x in items if x["id"] in allowed]


def set_stock_ids(ids):
    return _STOCK_IDS.set(frozenset(ids) if ids is not None else None)


def reset_stock(token):
    _STOCK_IDS.reset(token)


# Платформы, на которые больше не выйдут новые процессоры
DEAD_END_SOCKETS = {"AM4", "LGA1700"}
# Процессоры 13–14 поколения Intel, требующие обновления микрокода
RAPTOR_LAKE_REFRESH = {"i5-14400f", "i5-14600kf", "i7-14700kf"}


def mb_power_class(cpu: dict) -> int:
    """Минимальный класс питания платы для процессора."""
    if cpu["power"] <= 120:
        return 1
    if cpu["power"] <= 200:
        return 2
    return 3


def cpu_candidates(spec: dict) -> list[dict]:
    """Процессоры, удовлетворяющие жёстким требованиям спецификации."""
    res = []
    for c in stock(CPU):
        if c["cores"] < spec["cores_min"]:
            continue
        if spec["need_igpu"] and not c["igpu"]:
            continue
        if spec["cpu_brand"] and c["brand"] != spec["cpu_brand"]:
            continue
        if spec["sockets"] and c["socket"] not in spec["sockets"]:
            continue
        if spec["cpu_max_power"] and c["power"] > spec["cpu_max_power"]:
            continue
        res.append(c)
    return res


def gpu_candidates(spec: dict) -> list[dict]:
    res = []
    for g in stock(GPU):
        if g["perf"] < spec["gpu_perf_min"] or g["vram"] < spec["vram_min"]:
            continue
        if spec["gpu_brand"] and g["brand"] != spec["gpu_brand"]:
            continue
        res.append(g)
    return res


def best(items: list[dict], limit: float, key: str) -> dict | None:
    """Наилучший по показателю key среди укладывающихся в лимит цены."""
    fit = [i for i in items if i["price"] <= limit]
    if not fit:
        return None
    return max(fit, key=lambda i: (i[key], -i["price"]))


def cheapest(items: list[dict]) -> dict | None:
    return min(items, key=lambda i: i["price"]) if items else None


def mb_candidates(spec: dict, cpu: dict, any_form=False) -> list[dict]:
    res = []
    for m in stock(MB):
        if m["socket"] != cpu["socket"]:
            continue
        if m["power_class"] < mb_power_class(cpu):
            continue
        if spec["wifi"] and not m["wifi"]:
            continue
        if not any_form and spec["forms"] and m["form"] not in spec["forms"]:
            continue
        res.append(m)
    return res


def psu_need(cpu: dict, gpu_power: int, upgrade: bool) -> int:
    """Требуемая мощность БП: (CPU + GPU + остальное 75 Вт) × 1,3 запаса."""
    watt = (cpu["power"] + gpu_power + 75) * 1.3
    if upgrade:
        watt += 150
    return int(-(-watt // 50) * 50)   # округление вверх до 50 Вт


# Совместимость поколения памяти определяется и процессором, и конкретной платой.
# Для LGA1700 существуют отдельные платы DDR4 и DDR5, разъёмы не взаимозаменяемы.
SOCKET_MEMORY = {
    "AM4": {"DDR4"}, "AM5": {"DDR5"},
    "LGA1700": {"DDR4", "DDR5"}, "LGA1851": {"DDR5"},
}


def memory_candidates(board: dict, minimum_gb: int) -> list[dict]:
    """Подходящие наборы ОЗУ строго нужного типа и достаточной ёмкости."""
    return [r for r in stock(RAM) if r["type"] == board["memory"]
            and r["capacity"] >= minimum_gb]


def platform_options(spec: dict, cpu: dict, any_form=False) -> list[dict]:
    """Сравниваем цену всей пары плата+RAM, не нарушая совместимость."""
    result = []
    for board in mb_candidates(spec, cpu, any_form=any_form):
        if board["memory"] not in SOCKET_MEMORY.get(cpu["socket"], set()):
            continue
        ram = cheapest(memory_candidates(board, spec["ram_min"]))
        if ram is None:
            continue
        result.append({"board": board, "ram": ram,
                       "cost": board["price"] + ram["price"]})
    return result


def choose_platform(spec: dict, cpu: dict, budget: int, any_form=False) -> dict | None:
    """Стоимость платформы — основной критерий при ограниченном бюджете.

    Если пользователь хочет апгрейд, DDR5 допускается с премией не более 10% бюджета,
    при условии поддержки со стороны CPU. Это эвристика, не жёсткая привязка к рублям.
    """
    options = platform_options(spec, cpu, any_form=any_form)
    if not options:
        return None
    if spec.get("upgrade"):
        atx = [o for o in options if o["board"]["form"] == "ATX"]
        options = atx or options
    cheapest_option = min(options, key=lambda o: (o["cost"], o["board"]["price"]))
    modern = [o for o in options if o["board"]["memory"] == "DDR5"
              and o["cost"] <= cheapest_option["cost"] + budget * 0.10]
    if spec.get("upgrade") and modern:
        return min(modern, key=lambda o: (o["cost"], o["board"]["price"]))
    return cheapest_option
