"""
База знаний экспертной системы подбора конфигурации ПК.

Правила сгруппированы по этапам вывода; порядок этапов задаётся
приоритетом (salience): чем выше число, тем раньше срабатывает правило.

  100–97  проверка и нормализация входных данных
  95      определение профиля пользователя
  90–86   требования задач и ограничения пользователя
  84      формирование спецификации
  80      распределение бюджета
  70–60   подбор комплектующих и проверка совместимости
  50      балансировка бюджета
  40      проверки и рекомендации
  10–5    итоговая конфигурация
"""
from engine import KnowledgeBase, P, NOT
import catalog as cat

kb = KnowledgeBase()

PRO_TASKS = {"video", "render3d", "ml", "stream"}
TASK_NAMES = {
    "office": "офисная работа и учёба",
    "dev": "программирование",
    "gaming": "компьютерные игры",
    "video": "видеомонтаж",
    "render3d": "3D-моделирование и рендеринг",
    "ml": "машинное обучение",
    "stream": "стриминг",
}
PROFILE_NAMES = {
    "office": "офисный", "dev": "разработчик", "gaming": "игровой",
    "workstation": "рабочая станция", "universal": "универсальный",
}
MIN_BUDGET = 25000


def rub(x) -> str:
    return f"{int(x):,}".replace(",", " ") + " ₽"


def warn(ctx, level: str, text: str, premises=None):
    """level: error | warning | info"""
    ctx.declare("advice", level=level, text=text, premises=premises)
    ctx.explain(text)


# =====================================================================
# 1. Проверка и нормализация входных данных
# =====================================================================

@kb.rule("R01", "Бюджет ниже минимально допустимого", group="Проверка входных данных",
         salience=100, when=[P("u", "user", budget=lambda b: b < MIN_BUDGET)])
def r01(ctx, u):
    warn(ctx, "error", f"Бюджет {rub(u['budget'])} недостаточен: минимальная работоспособная "
                       f"сборка стоит около {rub(MIN_BUDGET)}.")
    ctx.halt()


@kb.rule("R02", "Не указано ни одной задачи", group="Проверка входных данных",
         salience=100, when=[P("u", "user"), NOT("task")])
def r02(ctx, u):
    ctx.declare("task", name="office", note="задача по умолчанию")
    warn(ctx, "info", "Задачи не выбраны — система подбирает офисный компьютер.")


@kb.rule("R03", "Класс бюджета: эконом", group="Проверка входных данных", salience=99,
         when=[P("u", "user", budget=lambda b: MIN_BUDGET <= b < 60000)])
def r03(ctx, u):
    ctx.declare("budget_class", value="economy", note="до 60 000 ₽")


@kb.rule("R04", "Класс бюджета: средний", group="Проверка входных данных", salience=99,
         when=[P("u", "user", budget=lambda b: 60000 <= b < 120000)])
def r04(ctx, u):
    ctx.declare("budget_class", value="middle", note="60 000 – 120 000 ₽")


@kb.rule("R05", "Класс бюджета: высокий", group="Проверка входных данных", salience=99,
         when=[P("u", "user", budget=lambda b: 120000 <= b < 200000)])
def r05(ctx, u):
    ctx.declare("budget_class", value="high", note="120 000 – 200 000 ₽")


@kb.rule("R06", "Класс бюджета: премиум", group="Проверка входных данных", salience=99,
         when=[P("u", "user", budget=lambda b: b >= 200000)])
def r06(ctx, u):
    ctx.declare("budget_class", value="premium", note="от 200 000 ₽")


@kb.rule("R07", "Определение целевого разрешения для игр", group="Проверка входных данных",
         salience=98, when=[P("u", "user"), P("t", "task", name="gaming"), NOT("resolution")])
def r07(ctx, u, t):
    res = u.get("resolution") or "1080p"
    ctx.declare("resolution", value=res,
                note="указано пользователем" if u.get("resolution") else "по умолчанию 1080p")


@kb.rule("R08", "Конфликт: 4K при бюджете менее 150 000 ₽", group="Проверка входных данных",
         salience=97, when=[P("u", "user", budget=lambda b: b < 150000),
                            P("r", "resolution", value="4K")])
def r08(ctx, u, r):
    ctx.retract(r)
    ctx.declare("resolution", value="1440p", premises=[u], note="понижено с 4K из-за бюджета")
    warn(ctx, "warning", "Для игр в 4K нужен бюджет от 150 000 ₽ — целевое разрешение "
                         "понижено до 1440p.", premises=[u])


@kb.rule("R09", "Конфликт: 1440p при бюджете менее 80 000 ₽", group="Проверка входных данных",
         salience=97, when=[P("u", "user", budget=lambda b: b < 80000),
                            P("r", "resolution", value="1440p")])
def r09(ctx, u, r):
    ctx.retract(r)
    ctx.declare("resolution", value="1080p", premises=[u], note="понижено с 1440p из-за бюджета")
    warn(ctx, "warning", "Для 1440p нужен бюджет от 80 000 ₽ — целевое разрешение "
                         "понижено до 1080p.", premises=[u])


@kb.rule("R10", "Игровая сборка в эконом-бюджете", group="Проверка входных данных",
         salience=97, when=[P("u", "user", budget=lambda b: b < 65000),
                            P("t", "task", name="gaming")])
def r10(ctx, u, t):
    warn(ctx, "warning", "Бюджет ниже 65 000 ₽ — современная игровая сборка с дискретной "
                         "видеокартой может не уложиться в него; рассмотрите увеличение бюджета.")


# =====================================================================
# 2. Определение профиля пользователя
# =====================================================================

def _is_pro(n):
    return n in PRO_TASKS


@kb.rule("R11", "Профиль «офисный»", group="Определение профиля", salience=95,
         when=[P("t", "task", name="office"), NOT("task", name="gaming"),
               NOT("task", name="dev"), NOT("task", name=_is_pro), NOT("profile")])
def r11(ctx, t):
    ctx.declare("profile", value="office")


@kb.rule("R12", "Профиль «игровой»", group="Определение профиля", salience=95,
         when=[P("t", "task", name="gaming"), NOT("task", name=_is_pro), NOT("profile")])
def r12(ctx, t):
    ctx.declare("profile", value="gaming")


@kb.rule("R13", "Профиль «рабочая станция»", group="Определение профиля", salience=95,
         when=[P("t", "task", name=_is_pro), NOT("task", name="gaming"), NOT("profile")])
def r13(ctx, t):
    ctx.declare("profile", value="workstation")


@kb.rule("R14", "Профиль «универсальный» (игры + профессиональные задачи)",
         group="Определение профиля", salience=95,
         when=[P("g", "task", name="gaming"), P("t", "task", name=_is_pro), NOT("profile")])
def r14(ctx, g, t):
    ctx.declare("profile", value="universal")


@kb.rule("R15", "Профиль «разработчик»", group="Определение профиля", salience=95,
         when=[P("t", "task", name="dev"), NOT("task", name="gaming"),
               NOT("task", name=_is_pro), NOT("profile")])
def r15(ctx, t):
    ctx.declare("profile", value="dev")


# =====================================================================
# 3. Требования задач (каждое требование — отдельный факт req)
# =====================================================================

def req(ctx, param, value, reason):
    ctx.declare("req", param=param, value=value, note=reason)


@kb.rule("R16", "Требования офисной работы", group="Требования задач", salience=90,
         when=[P("t", "task", name="office")])
def r16(ctx, t):
    req(ctx, "cores_min", 4, "офисным приложениям и браузеру достаточно 4 ядер")
    req(ctx, "ram_min", 16, "16 ГБ — комфортный минимум для браузера с множеством вкладок")
    req(ctx, "ssd_min", 500, "система и документы помещаются на SSD 500 ГБ")
    ctx.explain("4 ядра, 16 ГБ ОЗУ, SSD 500 ГБ")


@kb.rule("R17", "Требования программирования", group="Требования задач", salience=90,
         when=[P("t", "task", name="dev")])
def r17(ctx, t):
    req(ctx, "cores_min", 6, "компиляция и IDE хорошо масштабируются по ядрам")
    req(ctx, "ram_min", 16, "IDE + браузер + сервер разработки")
    req(ctx, "ssd_min", 1000, "репозитории, зависимости, SDK")
    ctx.explain("6 ядер, 16 ГБ ОЗУ, SSD 1 ТБ")


@kb.rule("R18", "Программирование с виртуализацией / Docker", group="Требования задач",
         salience=90, when=[P("t", "task", name="dev"), P("u", "user", virtualization=True)])
def r18(ctx, t, u):
    req(ctx, "cores_min", 8, "виртуальным машинам и контейнерам выделяются ядра")
    req(ctx, "ram_min", 32, "каждая ВМ/контейнер резервирует память")
    ctx.explain("8 ядер, 32 ГБ ОЗУ")


@kb.rule("R19", "Требования игр в 1080p", group="Требования задач", salience=90,
         when=[P("t", "task", name="gaming"), P("r", "resolution", value="1080p")])
def r19(ctx, t, r):
    req(ctx, "gpu_perf_min", 45, "уровень RTX 5060 — высокие настройки в 1080p")
    req(ctx, "vram_min", 8, "современным играм в 1080p нужно не менее 8 ГБ видеопамяти")
    req(ctx, "cores_min", 6, "игровые движки используют 6 и более потоков")
    req(ctx, "ram_min", 16, "минимум для современных игр")
    req(ctx, "ssd_min", 1000, "одна современная игра занимает 100–150 ГБ")
    ctx.explain("GPU ≥ 45, VRAM ≥ 8 ГБ, 6 ядер, 16 ГБ, SSD 1 ТБ")


@kb.rule("R20", "Требования игр в 1440p", group="Требования задач", salience=90,
         when=[P("t", "task", name="gaming"), P("r", "resolution", value="1440p")])
def r20(ctx, t, r):
    req(ctx, "gpu_perf_min", 55, "уровень RX 9060 XT / RTX 5060 Ti для 1440p")
    req(ctx, "vram_min", 12, "текстуры высокого разрешения требуют 12+ ГБ")
    req(ctx, "cores_min", 6, "игровые движки используют 6 и более потоков")
    req(ctx, "ram_min", 32, "32 ГБ исключают подгрузки в тяжёлых проектах")
    req(ctx, "ssd_min", 1000, "библиотека игр")
    ctx.explain("GPU ≥ 55, VRAM ≥ 12 ГБ, 32 ГБ ОЗУ")


@kb.rule("R21", "Требования игр в 4K", group="Требования задач", salience=90,
         when=[P("t", "task", name="gaming"), P("r", "resolution", value="4K")])
def r21(ctx, t, r):
    req(ctx, "gpu_perf_min", 85, "4K требует видеокарту уровня RX 9070 XT / RTX 5070 Ti и выше")
    req(ctx, "vram_min", 16, "текстуры 4K занимают более 12 ГБ")
    req(ctx, "cores_min", 8, "высокий FPS требует производительного CPU")
    req(ctx, "ram_min", 32, "тяжёлые проекты в 4K")
    req(ctx, "ssd_min", 2000, "игры с 4K-текстурами занимают много места")
    ctx.explain("GPU ≥ 85, VRAM ≥ 16 ГБ, 8 ядер, 32 ГБ, SSD 2 ТБ")


@kb.rule("R22", "Требования видеомонтажа", group="Требования задач", salience=90,
         when=[P("t", "task", name="video")])
def r22(ctx, t):
    req(ctx, "cores_min", 8, "кодирование и эффекты хорошо распараллеливаются")
    req(ctx, "ram_min", 32, "таймлайн 4K и кэш превью")
    req(ctx, "ssd_min", 2000, "исходники и кэш монтажа")
    req(ctx, "gpu_perf_min", 45, "аппаратное ускорение эффектов и кодирования")
    req(ctx, "vram_min", 8, "GPU-эффекты в DaVinci Resolve / Premiere")
    ctx.explain("8 ядер, 32 ГБ, SSD 2 ТБ, дискретная GPU")


@kb.rule("R23", "Видеомонтаж: предпочтение NVIDIA", group="Требования задач", salience=90,
         when=[P("t", "task", name="video")])
def r23(ctx, t):
    req(ctx, "gpu_brand", "NVIDIA", "NVENC и CUDA лучше всего поддерживаются монтажными программами")


@kb.rule("R24", "Требования 3D-рендеринга", group="Требования задач", salience=90,
         when=[P("t", "task", name="render3d")])
def r24(ctx, t):
    req(ctx, "cores_min", 12, "CPU-рендер (Cycles, V-Ray CPU) масштабируется по ядрам")
    req(ctx, "ram_min", 64, "сложные сцены и симуляции")
    req(ctx, "gpu_perf_min", 55, "GPU-рендер и вьюпорт")
    req(ctx, "vram_min", 12, "сцена должна помещаться в видеопамять")
    req(ctx, "ssd_min", 1000, "ассеты и кэш")
    ctx.explain("12 ядер, 64 ГБ, GPU ≥ 55, VRAM ≥ 12 ГБ")


@kb.rule("R25", "3D-рендеринг: предпочтение NVIDIA", group="Требования задач", salience=90,
         when=[P("t", "task", name="render3d")])
def r25(ctx, t):
    req(ctx, "gpu_brand", "NVIDIA", "OptiX/CUDA — стандарт GPU-рендера в Blender, V-Ray, Octane")


@kb.rule("R26", "Требования машинного обучения", group="Требования задач", salience=90,
         when=[P("t", "task", name="ml")])
def r26(ctx, t):
    req(ctx, "gpu_brand", "NVIDIA", "PyTorch и TensorFlow ориентированы на CUDA")
    req(ctx, "vram_min", 16, "объём VRAM ограничивает размер модели и батча")
    req(ctx, "gpu_perf_min", 55, "скорость обучения")
    req(ctx, "ram_min", 32, "загрузка и предобработка датасетов")
    req(ctx, "ssd_min", 2000, "датасеты и чекпоинты")
    req(ctx, "cores_min", 8, "загрузчики данных работают в нескольких процессах")
    ctx.explain("NVIDIA, VRAM ≥ 16 ГБ, 32 ГБ ОЗУ, SSD 2 ТБ")


@kb.rule("R27", "Требования стриминга", group="Требования задач", salience=90,
         when=[P("t", "task", name="stream")])
def r27(ctx, t):
    req(ctx, "cores_min", 8, "игра и кодирование трансляции одновременно")
    req(ctx, "ram_min", 32, "OBS, браузерные источники, чат")
    req(ctx, "gpu_perf_min", 45, "аппаратный кодировщик видеокарты")
    ctx.explain("8 ядер, 32 ГБ, дискретная GPU")


@kb.rule("R28", "Большой объём файлов → дополнительный HDD", group="Требования задач",
         salience=90, when=[P("u", "user", big_storage=True)])
def r28(ctx, u):
    req(ctx, "hdd_min", 4000, "архив файлов дешевле хранить на HDD")


@kb.rule("R29", "Нужен встроенный Wi-Fi", group="Требования задач", salience=90,
         when=[P("u", "user", wifi=True)])
def r29(ctx, u):
    req(ctx, "wifi", 1, "пользователь подключается к сети без кабеля")


@kb.rule("R30", "Объединение требований: остаётся наиболее строгое",
         group="Требования задач", salience=88,
         when=[P("a", "req"), P("b", "req")],
         test=lambda a, b: a["param"] == b["param"] and (
             (isinstance(a["value"], (int, float)) and a["value"] < b["value"])
             or (a["value"] == b["value"] and a.id < b.id)))
def r30(ctx, a, b):
    ctx.explain(f"{a['param']}: {a['value']} → {b['value']}")
    ctx.retract(a)


@kb.rule("R31", "Нет требований к видеокарте → встроенная графика",
         group="Требования задач", salience=86,
         when=[P("u", "user"), NOT("req", param="gpu_perf_min"), NOT("req", param="need_igpu")])
def r31(ctx, u):
    req(ctx, "need_igpu", 1, "задачи не требуют дискретной видеокарты — экономим бюджет")


# =====================================================================
# 4. Ограничения и предпочтения пользователя
# =====================================================================

def constraint(ctx, param, value, reason):
    ctx.declare("constraint", param=param, value=value, note=reason)


@kb.rule("R32", "Приоритет расширяемости → актуальная платформа",
         group="Ограничения и предпочтения", salience=87,
         when=[P("u", "user", upgrade=True, budget=lambda b: b >= 60000)])
def r32(ctx, u):
    constraint(ctx, "sockets", ["AM5", "LGA1851"],
               "AM4 и LGA1700 больше не получат новых процессоров")
    ctx.explain("допустимы только сокеты AM5 и LGA1851")


@kb.rule("R33", "Расширяемость в эконом-бюджете недостижима",
         group="Ограничения и предпочтения", salience=87,
         when=[P("u", "user", upgrade=True, budget=lambda b: b < 60000)])
def r33(ctx, u):
    warn(ctx, "warning", "При бюджете до 60 000 ₽ приоритет расширяемости не учитывается: "
                         "платформы AM5/LGA1851 занимают слишком большую долю бюджета.")


@kb.rule("R34", "Приоритет тишины → ограничение тепловыделения CPU",
         group="Ограничения и предпочтения", salience=87, when=[P("u", "user", quiet=True)])
def r34(ctx, u):
    constraint(ctx, "cpu_max_power", 170, "горячий процессор требует шумного охлаждения")
    constraint(ctx, "quiet", 1, "подбирать тихие корпус и кулер")
    ctx.explain("CPU ≤ 170 Вт, тихий корпус и кулер")


@kb.rule("R35", "Предпочтение производителя процессора",
         group="Ограничения и предпочтения", salience=87,
         when=[P("u", "user", cpu_brand=lambda v: v in ("AMD", "Intel"))])
def r35(ctx, u):
    constraint(ctx, "cpu_brand", u["cpu_brand"], "указано пользователем")


@kb.rule("R36", "Компактный корпус (mATX)", group="Ограничения и предпочтения",
         salience=87, when=[P("u", "user", form="mATX")])
def r36(ctx, u):
    constraint(ctx, "forms", ["mATX", "ITX"], "пользователь хочет компактный корпус")


@kb.rule("R37", "Минимальный корпус (Mini-ITX)", group="Ограничения и предпочтения",
         salience=87, when=[P("u", "user", form="ITX")])
def r37(ctx, u):
    constraint(ctx, "forms", ["ITX"], "пользователь хочет минимальный корпус")
    constraint(ctx, "cpu_max_power", 130,
               "в корпус Mini-ITX помещается только низкопрофильный кулер (до 130 Вт)")
    ctx.explain("плата Mini-ITX, CPU ≤ 130 Вт")


@kb.rule("R38", "Игровой/универсальный профиль → игровой индекс CPU",
         group="Ограничения и предпочтения", salience=87,
         when=[P("p", "profile", value=lambda v: v in ("gaming", "universal"))])
def r38(ctx, p):
    constraint(ctx, "criterion", "game",
               "в играх важнее частота и кэш, чем число ядер (в т.ч. 3D V-Cache)")


@kb.rule("R39", "Mini-ITX и мощная видеокарта → предупреждение о нагреве",
         group="Ограничения и предпочтения", salience=86,
         when=[P("u", "user", form="ITX"), P("r", "req", param="gpu_perf_min",
                                             value=lambda v: v >= 85)])
def r39(ctx, u, r):
    warn(ctx, "warning", "Мощная видеокарта в корпусе Mini-ITX сильно греется и шумит; "
                         "при возможности выберите mATX.")


@kb.rule("R40", "Тишина + ресурсоёмкий рендер → компромисс",
         group="Ограничения и предпочтения", salience=86,
         when=[P("u", "user", quiet=True), P("t", "task", name=lambda n: n in ("render3d", "ml"))])
def r40(ctx, u, t):
    warn(ctx, "info", "Длительная 100% нагрузка (рендер, обучение моделей) несовместима с "
                      "полной тишиной: подобран тихий корпус, но под нагрузкой шум неизбежен.")


# =====================================================================
# 5. Формирование спецификации и распределение бюджета
# =====================================================================

SPEC_DEFAULTS = dict(cores_min=4, ram_min=8, ssd_min=500, hdd_min=0, gpu_perf_min=0,
                     vram_min=0, gpu_brand=None, need_igpu=False, cpu_brand=None,
                     sockets=None, forms=None, quiet=False, wifi=False, upgrade=False,
                     cpu_max_power=None, criterion="perf")


@kb.rule("R41", "Формирование спецификации требований", group="Распределение бюджета",
         salience=84, when=[P("u", "user"), P("p", "profile"), NOT("spec")])
def r41(ctx, u, p):
    spec = dict(SPEC_DEFAULTS)
    sources = [u, p]
    for f in ctx.facts("req") + ctx.facts("constraint"):
        val = f["value"]
        if f["param"] in ("need_igpu", "wifi", "quiet"):
            val = bool(val)
        if f["param"] == "cpu_max_power" and spec["cpu_max_power"]:
            val = min(val, spec["cpu_max_power"])   # остаётся наиболее строгое
        spec[f["param"]] = val
        sources.append(f)
    spec["upgrade"] = bool(u.get("upgrade"))
    ctx.declare("spec", premises=sources, **spec)
    ctx.explain(", ".join(f"{k}={v}" for k, v in spec.items() if v not in (None, False, 0)))


SHARES = {  # доли бюджета на CPU и GPU
    "gaming": (0.22, 0.42), "universal": (0.27, 0.35), "workstation": (0.32, 0.25),
    "office": (0.35, 0.0), "dev": (0.35, 0.0),
}


@kb.rule("R42", "Распределение бюджета: игровой профиль", group="Распределение бюджета",
         salience=80, when=[P("u", "user"), P("p", "profile", value="gaming"),
                            P("s", "spec"), NOT("budget_cpu")])
def r42(ctx, u, p, s):
    _alloc(ctx, u, "gaming")


@kb.rule("R43", "Распределение бюджета: универсальный профиль", group="Распределение бюджета",
         salience=80, when=[P("u", "user"), P("p", "profile", value="universal"),
                            P("s", "spec"), NOT("budget_cpu")])
def r43(ctx, u, p, s):
    _alloc(ctx, u, "universal")


@kb.rule("R44", "Распределение бюджета: рабочая станция", group="Распределение бюджета",
         salience=80, when=[P("u", "user"), P("p", "profile", value="workstation"),
                            P("s", "spec"), NOT("budget_cpu")])
def r44(ctx, u, p, s):
    _alloc(ctx, u, "workstation")


@kb.rule("R45", "Распределение бюджета: офис / разработка (без видеокарты)",
         group="Распределение бюджета", salience=80,
         when=[P("u", "user"), P("p", "profile", value=lambda v: v in ("office", "dev")),
               P("s", "spec"), NOT("budget_cpu")])
def r45(ctx, u, p, s):
    _alloc(ctx, u, p["value"])


def _alloc(ctx, u, profile):
    cpu_share, gpu_share = SHARES[profile]
    b = u["budget"]
    ctx.declare("budget_cpu", limit=int(b * cpu_share), note=f"{int(cpu_share*100)}% бюджета")
    ctx.declare("budget_gpu", limit=int(b * gpu_share), note=f"{int(gpu_share*100)}% бюджета")
    ctx.explain(f"CPU — {int(cpu_share*100)}% ({rub(b*cpu_share)}), "
                f"GPU — {int(gpu_share*100)}% ({rub(b*gpu_share)})")


# =====================================================================
# 6. Подбор комплектующих
# =====================================================================

def pick(ctx, kind, item, note=""):
    ctx.declare(kind, note=note, **item)
    ctx.explain(f"{item['name']} — {rub(item['price'])}" + (f" ({note})" if note else ""))


@kb.rule("R46", "Выбор процессора в рамках доли бюджета", group="Подбор комплектующих",
         salience=70, when=[P("s", "spec"), P("bc", "budget_cpu"), NOT("cpu")],
         test=lambda s, bc: cat.best(cat.cpu_candidates(s.data), bc["limit"],
                                     s["criterion"]) is not None)
def r46(ctx, s, bc):
    item = cat.best(cat.cpu_candidates(s.data), bc["limit"], s["criterion"])
    pick(ctx, "cpu", item, "лучший по " + ("игровому индексу" if s["criterion"] == "game"
                                           else "производительности") + " в пределах лимита")


@kb.rule("R47", "Процессор не укладывается в долю бюджета → самый дешёвый подходящий",
         group="Подбор комплектующих", salience=70,
         when=[P("s", "spec"), P("bc", "budget_cpu"), NOT("cpu")],
         test=lambda s, bc: cat.cpu_candidates(s.data) and cat.best(
             cat.cpu_candidates(s.data), bc["limit"], s["criterion"]) is None)
def r47(ctx, s, bc):
    item = cat.cheapest(cat.cpu_candidates(s.data))
    pick(ctx, "cpu", item, "минимально подходящий по требованиям")


@kb.rule("R48", "Нет процессора, удовлетворяющего требованиям", group="Подбор комплектующих",
         salience=70, when=[P("s", "spec"), NOT("cpu")],
         test=lambda s: not cat.cpu_candidates(s.data))
def r48(ctx, s):
    relax = {"cpu_brand": "предпочтение производителя", "sockets": "приоритет расширяемости",
             "cpu_max_power": "компактность/тишину (ограничение тепловыделения)",
             "need_igpu": "отказ от видеокарты"}
    helps = [txt for key, txt in relax.items()
             if s[key] and cat.cpu_candidates({**s.data, key: None if key != "need_igpu"
                                               else False})]
    hint = (" Снимите " + " или ".join(helps) + ".") if helps else ""
    warn(ctx, "error", f"Нет процессора, удовлетворяющего всем ограничениям одновременно "
                       f"(не менее {s['cores_min']} ядер и выбранные предпочтения).{hint}")
    ctx.halt()


@kb.rule("R49", "Выбор видеокарты в рамках доли бюджета", group="Подбор комплектующих",
         salience=70, when=[P("s", "spec", gpu_perf_min=lambda v: v > 0),
                            P("bg", "budget_gpu"), NOT("gpu")],
         test=lambda s, bg: cat.best(cat.gpu_candidates(s.data), bg["limit"], "perf") is not None)
def r49(ctx, s, bg):
    item = cat.best(cat.gpu_candidates(s.data), bg["limit"], "perf")
    pick(ctx, "gpu", item, "самая производительная в пределах лимита")


@kb.rule("R50", "Видеокарта не укладывается в долю бюджета → самая дешёвая подходящая",
         group="Подбор комплектующих", salience=70,
         when=[P("s", "spec", gpu_perf_min=lambda v: v > 0), P("bg", "budget_gpu"), NOT("gpu")],
         test=lambda s, bg: cat.best(cat.gpu_candidates(s.data), bg["limit"], "perf") is None)
def r50(ctx, s, bg):
    item = cat.cheapest(cat.gpu_candidates(s.data))
    pick(ctx, "gpu", item, "минимально подходящая по требованиям")


IGPU = {"id": "igpu", "name": "Встроенная графика процессора", "brand": None, "vram": 0,
        "perf": 0, "power": 0, "length": 0, "price": 0}


@kb.rule("R51", "Дискретная видеокарта не нужна", group="Подбор комплектующих", salience=70,
         when=[P("s", "spec", gpu_perf_min=0), NOT("gpu")])
def r51(ctx, s):
    pick(ctx, "gpu", IGPU, "выбран процессор со встроенным графическим ядром")


@kb.rule("R52", "Выбор экономически обоснованной платформы (плата + RAM)",
         group="Подбор комплектующих", salience=68,
         when=[P("s", "spec"), P("c", "cpu"), P("u", "user"), NOT("mb")],
         test=lambda s, c, u: cat.choose_platform(s.data, c.data, u["budget"]) is not None)
def r52(ctx, s, c, u):
    option = cat.choose_platform(s.data, c.data, u["budget"])
    item, ram = option["board"], option["ram"]
    alternatives = cat.platform_options(s.data, c.data)
    compared = "; ".join(f"{x['board']['memory']}: {rub(x['cost'])}"
                         for x in sorted(alternatives, key=lambda x: x["cost"])[:5])
    pick(ctx, "mb", item,
         f"сокет {c['socket']}; {item['memory']}; плата + {ram['capacity']} ГБ RAM "
         f"= {rub(option['cost'])}. Сравнение платформ: {compared}. "
         f"Учитываются бюджет {rub(u['budget'])} и апгрейд={s['upgrade']}")


@kb.rule("R53", "Нет платы нужного форм-фактора → снять ограничение",
         group="Подбор комплектующих", salience=68,
         when=[P("s", "spec"), P("c", "cpu"), P("u", "user"), NOT("mb")],
         test=lambda s, c, u: cat.choose_platform(s.data, c.data, u["budget"]) is None
         and cat.choose_platform(s.data, c.data, u["budget"], any_form=True) is not None)
def r53(ctx, s, c, u):
    option = cat.choose_platform(s.data, c.data, u["budget"], any_form=True)
    item = option["board"]
    pick(ctx, "mb", item, "ограничение форм-фактора снято; "
         f"выбрана совместимая {item['memory']} платформа стоимостью "
         f"{rub(option['cost'])} с ОЗУ")
    warn(ctx, "warning", f"Для сокета {c['socket']} нет платформы выбранного "
                         f"форм-фактора с подходящей памятью — выбрана {item['form']}.")


@kb.rule("R54", "Выбор ОЗУ по совместимости и экономике платформы",
         group="Подбор комплектующих", salience=66,
         when=[P("s", "spec"), P("c", "cpu"), P("m", "mb"), NOT("ram")],
         test=lambda s, c, m: m["memory"] in cat.SOCKET_MEMORY.get(c["socket"], set())
         and bool(cat.memory_candidates(m.data, s["ram_min"])))
def r54(ctx, s, c, m):
    item = cat.cheapest(cat.memory_candidates(m.data, s["ram_min"]))
    pick(ctx, "ram", item, f"совместимая {m['memory']} для {c['socket']}, "
         f"не менее {s['ram_min']} ГБ; сравнение стоимости платы + ОЗУ выполнено R52/R53")


@kb.rule("R55", "Выбор SSD", group="Подбор комплектующих", salience=66,
         when=[P("s", "spec"), NOT("ssd")])
def r55(ctx, s):
    item = cat.cheapest([d for d in cat.stock(cat.SSD) if d["capacity"] >= s["ssd_min"]])
    pick(ctx, "ssd", item, f"объём ≥ {s['ssd_min']} ГБ")


@kb.rule("R56", "Выбор HDD для архива", group="Подбор комплектующих", salience=66,
         when=[P("s", "spec", hdd_min=lambda v: v > 0), NOT("hdd")])
def r56(ctx, s):
    item = cat.cheapest([d for d in cat.stock(cat.HDD) if d["capacity"] >= s["hdd_min"]])
    pick(ctx, "hdd", item, f"объём ≥ {s['hdd_min']} ГБ")


@kb.rule("R57", "Высокое тепловыделение системы", group="Подбор комплектующих", salience=65,
         when=[P("c", "cpu"), P("g", "gpu"), NOT("heat")],
         test=lambda c, g: c["power"] + g["power"] > 400)
def r57(ctx, c, g):
    ctx.declare("heat", high=True, watt=c["power"] + g["power"])
    ctx.explain(f"CPU + GPU = {c['power'] + g['power']} Вт — нужен продуваемый корпус")


@kb.rule("R58", "Нормальное тепловыделение системы", group="Подбор комплектующих", salience=65,
         when=[P("c", "cpu"), P("g", "gpu"), NOT("heat")],
         test=lambda c, g: c["power"] + g["power"] <= 400)
def r58(ctx, c, g):
    ctx.declare("heat", high=False, watt=c["power"] + g["power"])


def case_candidates(s, m, g, h, c=None, relax=0):
    """relax=0 — все требования; 1 — без ограничения размера;
    2 — без требований к тишине и вентиляции."""
    res = []
    for k in cat.stock(cat.CASE):
        if m["form"] not in k["forms"] or k["gpu_max"] < g["length"]:
            continue
        if relax < 1 and s["forms"] and k["forms"][0] not in s["forms"]:
            continue   # корпус больше, чем хочет пользователь
        if relax < 2 and s["quiet"] and not k["quiet"]:
            continue
        if relax < 2 and h["high"] and not k["rad360"]:
            continue
        if relax < 2 and c is not None and not _cooler_fits(s, c, k):
            continue   # в корпус не помещается достаточный кулер
        res.append(k)
    return res


def _cooler_fits(s, c, k):
    """Помещается ли в корпус k кулер, способный охладить процессор c."""
    if not _needs_cooler(s, c):
        return True
    return bool(cooler_candidates(s, c, k))


@kb.rule("R59", "Выбор корпуса", group="Подбор комплектующих", salience=64,
         when=[P("s", "spec"), P("m", "mb"), P("g", "gpu"), P("h", "heat"), P("c", "cpu"),
               NOT("case")],
         test=lambda s, m, g, h, c: bool(case_candidates(s, m, g, h, c)))
def r59(ctx, s, m, g, h, c):
    item = cat.cheapest(case_candidates(s, m, g, h, c))
    pick(ctx, "case", item, f"плата {m['form']}, видеокарта {g['length']} мм"
                            + (", шумоизоляция" if s["quiet"] else "")
                            + (", усиленная вентиляция" if h["high"] else ""))


@kb.rule("R60", "Нет корпуса с нужными свойствами → ослабить требования",
         group="Подбор комплектующих", salience=64,
         when=[P("s", "spec"), P("m", "mb"), P("g", "gpu"), P("h", "heat"), P("c", "cpu"),
               NOT("case")],
         test=lambda s, m, g, h, c: not case_candidates(s, m, g, h, c))
def r60(ctx, s, m, g, h, c):
    cands = case_candidates(s, m, g, h, c, relax=1)
    if cands:
        item = cat.cheapest(cands)
        pick(ctx, "case", item, "ограничение размера снято")
        warn(ctx, "warning", f"Корпус желаемого размера не подходит (видеокарта {g['length']} мм, "
                             f"тишина или вентиляция) — выбран «{item['name']}».")
    else:
        item = cat.cheapest(case_candidates(s, m, g, h, c, relax=2))
        pick(ctx, "case", item, "требования к тишине и вентиляции ослаблены")
        warn(ctx, "warning", f"Нет корпуса, одновременно тихого и подходящего по размерам — "
                             f"выбран «{item['name']}».")


@kb.rule("R61", "Расчёт мощности блока питания", group="Подбор комплектующих", salience=64,
         when=[P("s", "spec"), P("c", "cpu"), P("g", "gpu"), NOT("psu_need")])
def r61(ctx, s, c, g):
    gpu_power = g["power"]
    if g["id"] == "igpu" and s["upgrade"]:
        gpu_power = 200   # резерв под будущую видеокарту
    watt = cat.psu_need(c.data, gpu_power, s["upgrade"])
    ctx.declare("psu_need", watt=watt)
    ctx.explain(f"({c['power']} + {gpu_power} + 75) × 1,3"
                + (" + 150 (запас на апгрейд)" if s["upgrade"] else "") + f" ≈ {watt} Вт")


@kb.rule("R62", "Выбор блока питания", group="Подбор комплектующих", salience=62,
         when=[P("s", "spec"), P("n", "psu_need"), P("k", "case"), P("g", "gpu"), NOT("psu")])
def r62(ctx, s, n, k, g):
    cands = [p for p in cat.stock(cat.PSU) if p["form"] == k["psu"] and p["watt"] >= n["watt"]]
    gold = g["power"] >= 250 or s["quiet"]
    if gold:
        cands = [p for p in cands if p["cert"] != "Bronze"] or cands
    item = cat.cheapest(cands) or max((p for p in cat.stock(cat.PSU) if p["form"] == k["psu"]),
                                      key=lambda p: p["watt"])
    pick(ctx, "psu", item, f"≥ {n['watt']} Вт, формат {k['psu']}"
                           + (", сертификат не ниже Gold" if gold else ""))


@kb.rule("R63", "Боксового кулера достаточно", group="Подбор комплектующих", salience=62,
         when=[P("s", "spec", quiet=False), P("c", "cpu", box_cooler=True,
                                              power=lambda w: w <= 120), NOT("cooler")])
def r63(ctx, s, c):
    pick(ctx, "cooler", {"id": "box", "name": "Комплектный (боксовый) кулер", "type": "box",
                         "tdp_max": 120, "height": 60, "quiet": False, "price": 0},
         f"тепловыделение CPU {c['power']} Вт")


def cooler_candidates(s, c, k):
    return [x for x in cat.stock(cat.COOLER)
            if x["tdp_max"] >= c["power"]
            and (x["type"] != "aio" or k["rad360"])
            and (x["type"] == "aio" or x["height"] <= k["cooler_max"])
            and (not s["quiet"] or x["quiet"])]


def _needs_cooler(s, c):
    return s["quiet"] or not c["box_cooler"] or c["power"] > 120


@kb.rule("R64", "Подбор башенного кулера или СЖО", group="Подбор комплектующих", salience=62,
         when=[P("s", "spec"), P("c", "cpu"), P("k", "case"), NOT("cooler")],
         test=lambda s, c, k: _needs_cooler(s, c) and bool(cooler_candidates(s, c, k)))
def r64(ctx, s, c, k):
    item = cat.cheapest(cooler_candidates(s, c, k))
    pick(ctx, "cooler", item, f"рассеивает ≥ {c['power']} Вт, высота ≤ {k['cooler_max']} мм"
                              + (", тихий" if s["quiet"] else ""))


@kb.rule("R65", "Подходящего кулера нет → максимально возможный + предупреждение",
         group="Подбор комплектующих", salience=62,
         when=[P("s", "spec"), P("c", "cpu"), P("k", "case"), NOT("cooler")],
         test=lambda s, c, k: _needs_cooler(s, c) and not cooler_candidates(s, c, k))
def r65(ctx, s, c, k):
    loud = cooler_candidates({**s.data, "quiet": False}, c, k)
    if loud:
        item = cat.cheapest(loud)
        pick(ctx, "cooler", item, "тихой модели подходящего размера нет")
        warn(ctx, "warning", f"Тихий кулер для {c['name']} не помещается в корпус — выбран "
                             f"обычный; уменьшите обороты вентилятора в BIOS.")
        return
    fit = [x for x in cat.stock(cat.COOLER) if x["type"] != "aio" and x["height"] <= k["cooler_max"]]
    item = max(fit, key=lambda x: x["tdp_max"])
    pick(ctx, "cooler", item, "лучший из помещающихся в корпус")
    warn(ctx, "warning", f"В корпус помещается кулер не выше {k['cooler_max']} мм — "
                         f"процессор ({c['power']} Вт) будет снижать частоты под нагрузкой.")


# =====================================================================
# 7. Балансировка бюджета
# =====================================================================

PARTS = ["cpu", "gpu", "mb", "ram", "ssd", "psu", "case", "cooler"]
ALL_PARTS = [P(k, k) for k in PARTS]
BAL = ALL_PARTS + [P("u", "user"), P("p", "profile"), P("s", "spec"),
                   P("bc", "budget_cpu"), P("bg", "budget_gpu"), NOT("balance_done")]


def total(ctx_or_facts) -> int:
    if hasattr(ctx_or_facts, "facts"):
        parts = [f for k in PARTS + ["hdd"] for f in ctx_or_facts.facts(k)]
    else:
        parts = ctx_or_facts
    return sum(f["price"] for f in parts)


def _sum(kw):
    return sum(kw[k]["price"] for k in PARTS)


def _over(kw):
    hdd = 0 if "s" not in kw or kw["s"]["hdd_min"] == 0 else min(
        d["price"] for d in cat.stock(cat.HDD) if d["capacity"] >= kw["s"]["hdd_min"])
    return _sum(kw) + hdd - kw["u"]["budget"]


def _gpu_down(kw):
    g = kw["gpu"]
    return g["id"] != "igpu" and any(x["price"] < g["price"]
                                     for x in cat.gpu_candidates(kw["s"].data))


def _cpu_down(kw):
    c = kw["cpu"]
    return any(x["price"] < c["price"] for x in cat.cpu_candidates(kw["s"].data))


def _rebudget(ctx, fact, kind, limit, p, reason):
    ctx.retract(fact)
    ctx.declare(kind, limit=int(limit), note=reason, premises=[p])


@kb.rule("R66", "Перерасход бюджета → понизить видеокарту", group="Балансировка бюджета",
         salience=50, when=BAL,
         test=lambda **kw: _over(kw) > kw["u"]["budget"] * 0.03 and _gpu_down(kw)
         and (kw["p"]["value"] != "gaming" or not _cpu_down(kw)))
def r66(ctx, **kw):
    ctx.explain(f"превышение на {rub(_over(kw))}; лимит GPU < {rub(kw['gpu']['price'])}")
    _rebudget(ctx, kw["bg"], "budget_gpu", kw["gpu"]["price"] - 1, kw["p"],
              "снижен из-за перерасхода бюджета")


@kb.rule("R67", "Перерасход бюджета → понизить процессор", group="Балансировка бюджета",
         salience=50, when=BAL,
         test=lambda **kw: _over(kw) > kw["u"]["budget"] * 0.03 and _cpu_down(kw)
         and (kw["p"]["value"] == "gaming" or not _gpu_down(kw)))
def r67(ctx, **kw):
    ctx.explain(f"превышение на {rub(_over(kw))}; лимит CPU < {rub(kw['cpu']['price'])}")
    _rebudget(ctx, kw["bc"], "budget_cpu", kw["cpu"]["price"] - 1, kw["p"],
              "снижен из-за перерасхода бюджета")


@kb.rule("R68", "Перерасход, понижать нечего → бюджет недостаточен",
         group="Балансировка бюджета", salience=50, when=BAL,
         test=lambda **kw: _over(kw) > kw["u"]["budget"] * 0.03
         and not _gpu_down(kw) and not _cpu_down(kw))
def r68(ctx, **kw):
    ctx.declare("balance_done", reason="over")
    warn(ctx, "warning", f"Минимальная сборка под выбранные задачи дороже бюджета на "
                         f"{rub(_over(kw))}. Увеличьте бюджет или уменьшите требования.")


def _gpu_up(kw):
    g, left = kw["gpu"], -_over(kw)
    return g["id"] != "igpu" and any(
        g["price"] < x["price"] <= g["price"] + left and x["perf"] > g["perf"]
        for x in cat.gpu_candidates(kw["s"].data))


def _cpu_up(kw):
    c, left, crit = kw["cpu"], -_over(kw), kw["s"]["criterion"]
    return any(c["price"] < x["price"] <= c["price"] + left and x[crit] > c[crit]
               for x in cat.cpu_candidates(kw["s"].data))


def _surplus(kw):
    return -_over(kw) > kw["u"]["budget"] * 0.10


@kb.rule("R69", "Остаток бюджета → улучшить видеокарту (игровой приоритет)",
         group="Балансировка бюджета", salience=50,
         when=BAL + [NOT("upgraded", part="gpu")],
         test=lambda **kw: kw["p"]["value"] in ("gaming", "universal") and _surplus(kw)
         and _gpu_up(kw))
def r69(ctx, **kw):
    left = -_over(kw)
    ctx.declare("upgraded", part="gpu", premises=[kw["u"]])
    ctx.explain(f"остаток {rub(left)} направлен на видеокарту")
    _rebudget(ctx, kw["bg"], "budget_gpu", kw["gpu"]["price"] + left, kw["p"],
              f"увеличен на остаток бюджета {rub(left)}")


@kb.rule("R70", "Остаток бюджета → улучшить процессор", group="Балансировка бюджета",
         salience=49, when=BAL + [NOT("upgraded", part="cpu")],
         test=lambda **kw: _surplus(kw) and _cpu_up(kw)
         and (kw["p"]["value"] not in ("gaming", "universal") or not _gpu_up(kw)))
def r70(ctx, **kw):
    left = -_over(kw)
    ctx.declare("upgraded", part="cpu", premises=[kw["u"]])
    ctx.explain(f"остаток {rub(left)} направлен на процессор")
    _rebudget(ctx, kw["bc"], "budget_cpu", kw["cpu"]["price"] + left, kw["p"],
              f"увеличен на остаток бюджета {rub(left)}")


@kb.rule("R71", "Остаток бюджета рабочей станции → улучшить видеокарту",
         group="Балансировка бюджета", salience=48,
         when=BAL + [NOT("upgraded", part="gpu")],
         test=lambda **kw: kw["p"]["value"] == "workstation" and _surplus(kw) and _gpu_up(kw))
def r71(ctx, **kw):
    left = -_over(kw)
    ctx.declare("upgraded", part="gpu", premises=[kw["u"]])
    ctx.explain(f"остаток {rub(left)} направлен на видеокарту")
    _rebudget(ctx, kw["bg"], "budget_gpu", kw["gpu"]["price"] + left, kw["p"],
              f"увеличен на остаток бюджета {rub(left)}")


@kb.rule("R72", "Остаток бюджета → увеличить объём памяти", group="Балансировка бюджета",
         salience=47, when=BAL + [NOT("upgraded", part="ram")],
         test=lambda **kw: _surplus(kw) and kw["p"]["value"] in ("workstation", "dev", "universal")
         and any(r["type"] == kw["mb"]["memory"] and r["capacity"] > kw["ram"]["capacity"]
                 and r["price"] - kw["ram"]["price"] <= -_over(kw) for r in cat.stock(cat.RAM)))
def r72(ctx, **kw):
    ram = kw["ram"]
    left = -_over(kw)
    better = max((r for r in cat.stock(cat.RAM) if r["type"] == ram["type"]
                  and r["capacity"] > ram["capacity"] and r["price"] - ram["price"] <= left),
                 key=lambda r: r["capacity"])
    ctx.declare("upgraded", part="ram", premises=[kw["u"]])
    ctx.retract(ram)
    ctx.declare("ram", note="увеличен на остаток бюджета", premises=[kw["mb"], kw["s"]], **better)
    ctx.explain(f"{ram['capacity']} → {better['capacity']} ГБ")


# =====================================================================
# 8. Проверки и рекомендации
# =====================================================================

@kb.rule("R73", "Дисбаланс: процессор ограничивает видеокарту",
         group="Проверки и рекомендации", salience=40,
         when=[P("c", "cpu"), P("g", "gpu")], test=lambda c, g: g["perf"] - c["game"] > 40)
def r73(ctx, c, g):
    warn(ctx, "warning", f"{c['name']} может ограничивать {g['name']} в играх с высоким FPS "
                         f"(«бутылочное горлышко»).")


@kb.rule("R74", "Платформа без перспективы обновления", group="Проверки и рекомендации",
         salience=40, when=[P("c", "cpu", socket=lambda s: s in cat.DEAD_END_SOCKETS)])
def r74(ctx, c):
    warn(ctx, "info", f"Сокет {c['socket']} больше не получит новых процессоров: при апгрейде "
                      f"придётся менять плату и, возможно, память.")


@kb.rule("R75", "Intel 14-го поколения → обновить BIOS", group="Проверки и рекомендации",
         salience=40, when=[P("c", "cpu", id=lambda i: i in cat.RAPTOR_LAKE_REFRESH)])
def r75(ctx, c):
    warn(ctx, "info", "Для процессоров Intel 13–14 поколения обязательно обновите BIOS платы до "
                      "версии с исправленным микрокодом — это предотвращает деградацию CPU.")


@kb.rule("R76", "Процессор без встроенной графики", group="Проверки и рекомендации",
         salience=40, when=[P("c", "cpu", igpu=False)])
def r76(ctx, c):
    warn(ctx, "info", f"{c['name']} не имеет встроенной графики: монитор подключается только "
                      f"к видеокарте.")


@kb.rule("R77", "Мало памяти для современных игр", group="Проверки и рекомендации",
         salience=40, when=[P("t", "task", name="gaming"), P("r", "ram", capacity=16)])
def r77(ctx, t, r):
    warn(ctx, "info", "16 ГБ достаточно для большинства игр, но при возможности переходите на "
                      "32 ГБ — новые проекты всё чаще требуют больше.")


@kb.rule("R78", "Длинная видеокарта → держатель от провисания",
         group="Проверки и рекомендации", salience=40,
         when=[P("g", "gpu", length=lambda l: l >= 300)])
def r78(ctx, g):
    warn(ctx, "info", f"Видеокарта длиной {g['length']} мм тяжёлая — используйте держатель "
                      f"(anti-sag) во избежание повреждения слота PCIe.")


@kb.rule("R79", "Тихая сборка с мощной видеокартой", group="Проверки и рекомендации",
         salience=40, when=[P("s", "spec", quiet=True), P("g", "gpu", power=lambda w: w >= 250)])
def r79(ctx, s, g):
    warn(ctx, "warning", f"{g['name']} потребляет {g['power']} Вт: даже в тихом корпусе под "
                         f"игровой нагрузкой она будет слышна. Ограничьте лимит мощности в драйвере.")


@kb.rule("R80", "Сборка без видеокарты — путь апгрейда", group="Проверки и рекомендации",
         salience=40, when=[P("g", "gpu", id="igpu"), P("n", "psu_need")])
def r80(ctx, g, n):
    warn(ctx, "info", "Видеокарту можно добавить позже: проверьте, что мощности блока питания "
                      "хватит на её потребление.")


@kb.rule("R81", "Проверка совместимости итоговой сборки", group="Проверки и рекомендации",
         salience=12, when=ALL_PARTS + [P("n", "psu_need"), NOT("compat")])
def r81(ctx, cpu, gpu, mb, ram, ssd, psu, case, cooler, n):
    problems = []
    if cpu["socket"] != mb["socket"]:
        problems.append("сокет процессора не совпадает с сокетом платы")
    if ram["type"] != mb["memory"]:
        problems.append("тип памяти не поддерживается платой")
    if mb["form"] not in case["forms"]:
        problems.append("плата не помещается в корпус")
    if gpu["length"] > case["gpu_max"]:
        problems.append("видеокарта не помещается в корпус")
    if psu["watt"] < n["watt"] and psu["watt"] < cpu["power"] + gpu["power"] + 75:
        problems.append("мощности блока питания недостаточно")
    if psu["form"] != case["psu"]:
        problems.append("формат блока питания не подходит к корпусу")
    if cooler["type"] == "air" and cooler["height"] > case["cooler_max"]:
        problems.append("кулер не помещается в корпус")
    ctx.declare("compat", ok=not problems, problems=problems)
    if problems:
        warn(ctx, "error", "Нарушена совместимость: " + "; ".join(problems))
    else:
        ctx.explain("сокет, тип памяти, форм-фактор, длина GPU, мощность и формат БП, высота "
                    "кулера — совместимы")


@kb.rule("R82", "Итоговая конфигурация", group="Итог", salience=10,
         when=ALL_PARTS + [P("u", "user"), P("ok", "compat", ok=True), NOT("result")])
def r82(ctx, cpu, gpu, mb, ram, ssd, psu, case, cooler, u, ok):
    hdd = ctx.first("hdd")
    parts = [cpu, gpu, mb, ram, ssd, psu, case, cooler] + ([hdd] if hdd else [])
    t = total(parts)
    ctx.declare("result", total=t, left=u["budget"] - t,
                premises=parts + [u, ok])
    ctx.explain(f"итого {rub(t)} при бюджете {rub(u['budget'])}")


@kb.rule("R83", "Значительный остаток бюджета", group="Итог", salience=5,
         when=[P("r", "result", left=lambda v: v >= 8000)])
def r83(ctx, r):
    warn(ctx, "info", f"Остаток {rub(r['left'])} можно направить на монитор, периферию или "
                      f"SSD большего объёма — дальнейшее улучшение ключевых компонентов "
                      f"не укладывается в остаток.")


@kb.rule("R84", "Превышение бюджета в пределах допуска", group="Итог", salience=5,
         when=[P("r", "result", left=lambda v: v < 0), NOT("balance_done", reason="over")])
def r84(ctx, r):
    warn(ctx, "info", f"Сборка дороже бюджета на {rub(-r['left'])} — это в пределах допуска 3%, "
                      f"принятого при балансировке.")
