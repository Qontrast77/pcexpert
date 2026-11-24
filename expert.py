"""Фасад экспертной системы: ввод → факты → вывод → результат с объяснениями."""
import catalog as cat
from engine import Engine
from knowledge_base import kb, PARTS, TASK_NAMES, PROFILE_NAMES, rub

PART_TITLES = {
    "cpu": "Процессор", "gpu": "Видеокарта", "mb": "Материнская плата",
    "ram": "Оперативная память", "ssd": "Накопитель SSD", "hdd": "Накопитель HDD",
    "psu": "Блок питания", "case": "Корпус", "cooler": "Охлаждение CPU",
}

KIND_TITLES = {
    "user": "Ввод пользователя", "task": "Задача", "budget_class": "Класс бюджета",
    "resolution": "Разрешение", "profile": "Профиль", "req": "Требование",
    "constraint": "Ограничение", "spec": "Спецификация", "budget_cpu": "Лимит на CPU",
    "budget_gpu": "Лимит на GPU", "heat": "Тепловыделение", "psu_need": "Требуемая мощность БП",
    "compat": "Проверка совместимости", "result": "Итог", "advice": "Рекомендация",
    "upgraded": "Улучшение", "balance_done": "Балансировка завершена",
}


def normalize(form: dict) -> dict:
    """Приведение данных формы/JSON к входным фактам."""
    tasks = form.get("tasks") or []
    if isinstance(tasks, str):
        tasks = [tasks]
    return {
        "budget": int(form.get("budget") or 0),
        "tasks": [t for t in tasks if t in TASK_NAMES],
        "resolution": form.get("resolution") or None,
        "form": form.get("form") or "any",
        "cpu_brand": form.get("cpu_brand") or "any",
        "wifi": _bool(form.get("wifi")),
        "quiet": _bool(form.get("quiet")),
        "upgrade": _bool(form.get("upgrade")),
        "virtualization": _bool(form.get("virtualization")),
        "big_storage": _bool(form.get("big_storage")),
    }


def _bool(v):
    return v in (True, 1, "1", "on", "true", "yes")


def describe(fact) -> str:
    """Человекочитаемое описание факта для дерева объяснений."""
    d, k = fact.data, fact.kind
    if k == "user":
        return f"бюджет {rub(d['budget'])}"
    if k == "task":
        return TASK_NAMES.get(d["name"], d["name"])
    if k == "profile":
        return PROFILE_NAMES[d["value"]]
    if k in ("req", "constraint"):
        return f"{d['param']} = {d['value']}" + (f" — {fact.note}" if fact.note else "")
    if k in ("budget_cpu", "budget_gpu"):
        return f"до {rub(d['limit'])}" + (f" ({fact.note})" if fact.note else "")
    if k in PART_TITLES:
        return f"{d['name']} — {rub(d['price'])}"
    if k == "psu_need":
        return f"{d['watt']} Вт"
    if k == "heat":
        return f"{d['watt']} Вт ({'высокое' if d['high'] else 'нормальное'})"
    if k == "spec":
        keys = ["cores_min", "ram_min", "ssd_min", "gpu_perf_min", "vram_min", "gpu_brand"]
        return ", ".join(f"{x}={d[x]}" for x in keys if d.get(x))
    if k in ("resolution", "budget_class"):
        return str(d["value"]) + (f" ({fact.note})" if fact.note else "")
    if k == "advice":
        return d["text"]
    if k == "compat":
        return "совместимо" if d["ok"] else "; ".join(d["problems"])
    return ", ".join(f"{a}={b}" for a, b in d.items())


def tree_to_dict(engine, node, depth=0, max_depth=6, seen=None):
    """Дерево вывода для интерфейса. Уже показанный факт повторно не раскрывается,
    исходные факты (задачи, ввод) показываются один раз."""
    seen = set() if seen is None else seen
    f = node["fact"]
    repeat = f.id in seen
    seen.add(f.id)
    out = {
        "id": f.id, "kind": KIND_TITLES.get(f.kind, PART_TITLES.get(f.kind, f.kind)),
        "text": describe(f) + (" (см. выше)" if repeat and node["children"] else ""),
        "rule": f"{node['rule'].code}: {node['rule'].title}" if node["rule"] else None,
        "children": [],
    }
    if depth < max_depth and not repeat:
        out["children"] = [tree_to_dict(engine, ch, depth + 1, max_depth, seen)
                           for ch in node["children"]
                           if ch["fact"].kind != "user"
                           and not (ch["fact"].rule is None and ch["fact"].id in seen)]
    return out


def recommend(form: dict) -> dict:
    data = normalize(form)
    engine = Engine(kb)
    tasks = data.pop("tasks")
    engine.declare("user", **data)
    for t in tasks:
        engine.declare("task", name=t)
    steps = engine.run()

    facts = engine.facts()
    first = lambda kind: next((f for f in facts if f.kind == kind), None)

    parts = []
    for kind in PARTS[:4] + ["ssd", "hdd", "psu", "case", "cooler"]:
        f = first(kind)
        if f:
            parts.append({
                "kind": kind, "id": f.data.get("id"), "title": PART_TITLES[kind], "name": f["name"],
                "price": f["price"], "note": f.note,
                "price_verified": f.data.get("price_verified", False),
                "product_url": f.data.get("product_url"),
                "rule": f.rule, "chain": engine.chain(f),
                "tree": tree_to_dict(engine, engine.derivation(f)),
            })

    advice = [{"level": f["level"], "text": f["text"], "rule": f.rule,
               "chain": engine.chain(f)}
              for f in facts if f.kind == "advice"]
    order = {"error": 0, "warning": 1, "info": 2}
    advice.sort(key=lambda a: order[a["level"]])

    result = first("result")
    profile = first("profile")
    resolution = first("resolution")
    trace = []
    for e in engine.trace:
        alive = [i for i in e.asserted if engine.fact(i).alive]
        trace.append({"step": e.step, "code": e.code, "title": e.title,
                      "matched": e.matched, "message": e.message,
                      "asserted": [f"f-{i}" for i in e.asserted],
                      "retracted": [f"f-{i}" for i in e.retracted],
                      "revised": len(alive) < len(e.asserted)})

    unverified = [p for p in parts if p["price"] > 0 and not p["price_verified"]]
    if unverified:
        advice.insert(0, {"level": "warning",
            "text": f"Цены {len(unverified)} позиций НЕ подтверждены DNS для Иркутска: "
                    "используются приблизительные рыночные оценки, ориентированные на уровень DNS; итог не является ценой магазина.",
            "rule": "PRICE-CHECK", "chain": []})

    return {
        "pricing_verified": not bool(unverified),
        "input": {**data, "tasks": tasks},
        "ok": result is not None,
        "profile": PROFILE_NAMES[profile["value"]] if profile else None,
        "resolution": resolution["value"] if resolution else None,
        "parts": parts,
        "total": result["total"] if result else sum(p["price"] for p in parts),
        "left": result["left"] if result else None,
        "advice": advice,
        "trace": trace,
        "steps": steps,
        "rules_fired": len({e.code for e in engine.trace}),
        "engine": engine,
    }


def summary(res: dict) -> str:
    """Текстовый отчёт (для консоли и тестов)."""
    lines = [f"Профиль: {res['profile']}  |  шагов вывода: {res['steps']}"]
    for p in res["parts"]:
        lines.append(f"  {p['title']:<20} {p['name']:<40} {rub(p['price']):>10}  "
                     f"[{p['rule']}; цепочка: {' → '.join(p['chain'])}]")
    lines.append(f"  {'ИТОГО':<61} {rub(res['total']):>10}")
    for a in res["advice"]:
        lines.append(f"  ({a['level']}) {a['text']}  [{a['rule']}]")
    return "\n".join(lines)


if __name__ == "__main__":
    demo = {"budget": 120000, "tasks": ["gaming"], "resolution": "1440p"}
    print(summary(recommend(demo)))


def recommend_two(form: dict, stock_path=None, *, stock_ids=None, stock_metadata=None, stock_mode=None) -> dict:
    """Независимые прогоны 84 правил: идеальный каталог и локальный снимок.

    Передача stock_ids предназначена исключительно для тестов / подготовленных
    подтверждённых снимков. В пользовательском режиме читается CSV.
    """
    from availability import validated_stock, candidate_stock
    ideal = recommend(form)
    mode = stock_mode or form.get("stock_mode") or "candidate"
    if mode not in ("candidate", "confirmed"):
        mode = "candidate"
    if stock_ids is None:
        loader = validated_stock if mode == "confirmed" else candidate_stock
        stock_ids, metadata = loader(stock_path) if stock_path is not None else loader()
    else:
        metadata = stock_metadata or {"confirmed": len(stock_ids), "city": "Иркутск", "source": "тестовый снимок"}
    essential = {"cpu", "motherboard", "ram", "ssd", "psu", "case", "cooler"}
    available_categories = {category for category, items in cat.CATALOG.items()
                            if isinstance(items, list) and any(item["id"] in stock_ids for item in items)}
    missing = sorted(essential - available_categories)
    local = None
    reason = None
    if missing:
        reason = "Недостаточно подтверждённых позиций для подбора: " + ", ".join(missing)
    else:
        token = cat.set_stock_ids(stock_ids)
        try:
            local = recommend(form)
            if not local["ok"]:
                reason = ("Не найдена полная совместимая сборка среди найденных товаров DNS." if mode == "candidate"
                          else "Не найдена полная совместимая сборка из подтверждённых позиций.")
                local = None
            else:
                selected = {f["id"] for f in local["engine"].facts()
                            if f.kind in PART_TITLES and f.data.get("id") not in ("igpu", "box")}
                if not selected.issubset(stock_ids):
                    reason = "В сборку попала позиция вне выбранного реестра DNS."
                    local = None
                else:
                    required = {"cpu", "mb", "ram", "ssd", "psu", "case", "cooler"}
                    present = {p["kind"] for p in local["parts"]}
                    if not required.issubset(present):
                        reason = "Не найдены все обязательные комплектующие в Иркутске."
                        local = None
        except (ValueError, TypeError, RuntimeError, KeyError, StopIteration) as exc:
            reason = "Подбор из подтверждённых остатков невозможен: " + str(exc)
            local = None
        finally:
            cat.reset_stock(token)
    if local is not None and mode == "candidate":
        from availability import load_snapshot
        records = {r["id"]: r for r in (load_snapshot(stock_path) if stock_path is not None else load_snapshot())}
        for part in local["parts"]:
            ref = records.get(part["id"])
            if ref and ref.get("status") in ("candidate", "available"):
                part["product_url"] = ref.get("source_url") or part.get("product_url")
                part["availability_status"] = "Наличие не подтверждено"
                part["dns_analogue"] = ref.get("comment", "")
        local["advice"].insert(0, {"level": "warning", "rule": "STOCK-DEMO", "chain": [],
            "text": "Ориентировочная сборка по карточкам DNS. Наличие этих товаров в Иркутске НЕ подтверждено; "
                    "перед покупкой необходима проверка остатков в выбранном магазине."})
    return {"ideal": ideal, "local": local, "local_reason": reason, "stock_metadata": metadata,
            "stock_mode": mode,
            "availability_policy": ("Найденные карточки DNS без проверки остатков" if mode == "candidate"
                                    else "Только available с URL и датой проверки не старше 7 дней")}
