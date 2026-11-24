"""
Проверка полноты и непротиворечивости базы знаний.

Система прогоняется на большой выборке комбинаций входных данных.
Для каждого прогона проверяется:
  1. вывод завершается (нет зацикливания правил);
  2. результат определён: либо собрана конфигурация, либо выдана ошибка;
  3. в рабочей памяти нет противоречий: ровно один экземпляр каждого
     компонента, один профиль, одна спецификация;
  4. сборка совместима (сокет, память, форм-фактор, длина GPU, БП, кулер);
  5. соблюдены жёсткие требования спецификации (ядра, ОЗУ, VRAM, бренд…).
Дополнительно считается покрытие: какие правила хотя бы раз сработали.
"""
import itertools
import random
import time
from collections import Counter

from expert import recommend
from knowledge_base import kb, TASK_NAMES

BUDGETS = [20000, 30000, 45000, 60000, 80000, 100000, 130000, 170000, 220000, 300000, 400000]
TASKS = list(TASK_NAMES)
TASK_SETS = [list(c) for n in range(0, 3) for c in itertools.combinations(TASKS, n)]


def check(res) -> list[str]:
    eng = res["engine"]
    facts = eng.facts()
    kinds = Counter(f.kind for f in facts)
    errors = []
    has_error = any(a["level"] == "error" for a in res["advice"])
    if not res["ok"] and not has_error:
        errors.append("нет ни результата, ни сообщения об ошибке")
    for k in ("profile", "spec", "cpu", "gpu", "mb", "ram", "ssd", "psu", "case", "cooler"):
        if kinds[k] > 1:
            errors.append(f"противоречие: {kinds[k]} факта типа {k}")
    if res["ok"]:
        f = {k: next(x for x in facts if x.kind == k)
             for k in ("cpu", "gpu", "mb", "ram", "ssd", "psu", "case", "cooler", "spec")}
        s = f["spec"]
        if f["cpu"]["socket"] != f["mb"]["socket"]:
            errors.append("сокет")
        if f["ram"]["type"] != f["mb"]["memory"]:
            errors.append("тип памяти")
        if f["mb"]["form"] not in f["case"]["forms"]:
            errors.append("форм-фактор платы")
        if f["gpu"]["length"] > f["case"]["gpu_max"]:
            errors.append("длина видеокарты")
        if f["psu"]["form"] != f["case"]["psu"]:
            errors.append("формат БП")
        if f["psu"]["watt"] < (f["cpu"]["power"] + f["gpu"]["power"] + 75):
            errors.append("мощность БП")
        if f["cpu"]["cores"] < s["cores_min"]:
            errors.append("ядра CPU")
        if s["gpu_perf_min"] and f["gpu"]["perf"] < s["gpu_perf_min"]:
            errors.append("производительность GPU")
        if f["gpu"]["vram"] < s["vram_min"]:
            errors.append("VRAM")
        if s["gpu_brand"] and f["gpu"]["brand"] != s["gpu_brand"]:
            errors.append("бренд GPU")
        if s["need_igpu"] and not f["cpu"]["igpu"]:
            errors.append("нет видеовыхода (iGPU)")
        if f["ram"]["capacity"] < s["ram_min"]:
            errors.append("объём ОЗУ")
        if s["cpu_brand"] and f["cpu"]["brand"] != s["cpu_brand"]:
            errors.append("бренд CPU")
    return errors


def main(sample=4000, seed=1):
    rnd = random.Random(seed)
    grid = list(itertools.product(BUDGETS, range(len(TASK_SETS)), ["1080p", "1440p", "4K"],
                                  ["any", "mATX", "ITX"], [0, 1], [0, 1],
                                  ["any", "AMD", "Intel"], [0, 1], [0, 1]))
    combos = rnd.sample(grid, min(sample, len(grid)))
    fired, failures, ok, refused, steps = Counter(), [], 0, 0, []
    t0 = time.time()
    for b, ti, res_, form, quiet, upg, brand, wifi, storage in combos:
        inp = dict(budget=b, tasks=TASK_SETS[ti], resolution=res_, form=form, quiet=quiet,
                   upgrade=upg, cpu_brand=brand, wifi=wifi, big_storage=storage,
                   virtualization=rnd.random() < 0.5)
        try:
            res = recommend(inp)
        except RuntimeError as e:
            failures.append((inp, [str(e)]))
            continue
        steps.append(res["steps"])
        for e in res["trace"]:
            fired[e["code"]] += 1
        errs = check(res)
        if errs:
            failures.append((inp, errs))
        ok += res["ok"]
        refused += not res["ok"]
    dt = time.time() - t0

    print(f"Прогонов: {len(combos)}  (из {len(grid)} возможных комбинаций), время {dt:.1f} с, "
          f"в среднем {dt / len(combos) * 1000:.1f} мс")
    print(f"Сборка получена: {ok}; обоснованный отказ: {refused}")
    print(f"Шагов вывода: мин {min(steps)}, сред {sum(steps) / len(steps):.1f}, макс {max(steps)}")
    print(f"Нарушений: {len(failures)}")
    for inp, errs in failures[:10]:
        print("   ", errs, inp)
    never = [r.code for r in kb.rules if fired[r.code] == 0]
    print(f"Правил в базе: {len(kb.rules)}; сработали хотя бы раз: {len(kb.rules) - len(never)}")
    if never:
        print("   не сработали:", ", ".join(never))
    return fired, failures


if __name__ == "__main__":
    main()
