"""Тестовые сценарии экспертной системы (запуск: python -m unittest -v)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from expert import recommend  # noqa: E402

SCENARIOS = {
    1: dict(budget=45000, tasks=["office"]),
    2: dict(budget=120000, tasks=["gaming"], resolution="1440p"),
    3: dict(budget=110000, tasks=["gaming"], resolution="4K", form="ITX", cpu_brand="Intel"),
    4: dict(budget=180000, tasks=["ml", "dev"], virtualization=True, upgrade=True),
    5: dict(budget=95000, tasks=["video"], quiet=True, form="mATX"),
    6: dict(budget=250000, tasks=["gaming", "stream"], resolution="4K"),
    7: dict(budget=40000, tasks=["render3d"]),
    8: dict(budget=20000, tasks=["office"]),
}


def part(res, kind):
    return next((p for p in res["parts"] if p["kind"] == kind), None)


def levels(res, level):
    return [a for a in res["advice"] if a["level"] == level]


class Scenarios(unittest.TestCase):

    def test_1_office_igpu(self):
        r = recommend(SCENARIOS[1])
        self.assertTrue(r["ok"])
        self.assertEqual(r["profile"], "офисный")
        self.assertEqual(part(r, "gpu")["name"], "Встроенная графика процессора")
        self.assertLessEqual(r["total"], 45000 * 1.03)

    def test_2_gaming_1440p(self):
        r = recommend(SCENARIOS[2])
        self.assertEqual(r["profile"], "игровой")
        e = r["engine"]
        gpu = next(f for f in e.facts() if f.kind == "gpu")
        self.assertGreaterEqual(gpu["perf"], 55)
        self.assertGreaterEqual(gpu["vram"], 12)
        self.assertGreaterEqual(part(r, "ram")["name"].count("32"), 1)
        self.assertLessEqual(r["total"], SCENARIOS[2]["budget"] * 1.03)  # при новых ценах апгрейд GPU может не поместиться

    def test_3_conflict_4k_itx(self):
        r = recommend(SCENARIOS[3])
        self.assertEqual(r["resolution"], "1440p")          # R08 понизил разрешение
        self.assertIn("Mini-ITX", part(r, "mb")["name"])
        self.assertIn("SFX", part(r, "psu")["name"])
        cpu = next(f for f in r["engine"].facts() if f.kind == "cpu")
        self.assertEqual(cpu["brand"], "Intel")
        self.assertLessEqual(cpu["power"], 130)

    def test_4_ml_nvidia_upgrade(self):
        r = recommend(SCENARIOS[4])
        e = r["engine"]
        gpu = next(f for f in e.facts() if f.kind == "gpu")
        cpu = next(f for f in e.facts() if f.kind == "cpu")
        self.assertEqual(gpu["brand"], "NVIDIA")
        self.assertGreaterEqual(gpu["vram"], 16)
        self.assertIn(cpu["socket"], ("AM5", "LGA1851"))

    def test_5_quiet_video(self):
        r = recommend(SCENARIOS[5])
        e = r["engine"]
        case = next(f for f in e.facts() if f.kind == "case")
        gpu = next(f for f in e.facts() if f.kind == "gpu")
        self.assertTrue(case["quiet"])
        self.assertEqual(gpu["brand"], "NVIDIA")

    def test_6_premium_gaming_x3d(self):
        r = recommend(SCENARIOS[6])
        self.assertEqual(r["profile"], "универсальный")
        self.assertIn("X3D", part(r, "cpu")["name"])

    def test_7_budget_insufficient(self):
        r = recommend(SCENARIOS[7])
        self.assertTrue(any(a["rule"] == "R68" for a in levels(r, "warning")))

    def test_8_budget_too_low(self):
        r = recommend(SCENARIOS[8])
        self.assertFalse(r["ok"])
        self.assertEqual(levels(r, "error")[0]["rule"], "R01")

    def test_explanation_chain(self):
        r = recommend(SCENARIOS[2])
        for p in r["parts"]:
            self.assertTrue(p["chain"], p["title"])
            self.assertEqual(p["chain"][-1], p["rule"])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class MemoryPlatformTests(unittest.TestCase):
    """Проверка аргументации DDR4/DDR5 и совместимости."""

    def test_platform_cost_comparison_lga1700(self):
        import catalog as cat
        spec = dict(cores_min=6, ram_min=32, forms=[], wifi=False, upgrade=False)
        cpu = next(c for c in cat.CPU if c['socket'] == 'LGA1700')
        choices = cat.platform_options(spec, cpu)
        self.assertTrue(any(o['board']['memory'] == 'DDR4' for o in choices))
        self.assertTrue(any(o['board']['memory'] == 'DDR5' for o in choices))
        chosen = cat.choose_platform(spec, cpu, 80000)
        self.assertEqual(chosen['cost'], min(o['cost'] for o in choices))
        self.assertEqual(chosen['ram']['type'], chosen['board']['memory'])

    def test_am5_only_ddr5(self):
        import catalog as cat
        spec = dict(ram_min=16, forms=[], wifi=False, upgrade=False)
        cpu = next(c for c in cat.CPU if c['socket'] == 'AM5')
        options = cat.platform_options(spec, cpu)
        self.assertTrue(options)
        self.assertEqual({o['ram']['type'] for o in options}, {'DDR5'})

    def test_upgrade_preference_ddr5_when_affordable(self):
        import catalog as cat
        cpu = next(c for c in cat.CPU if c['socket'] == 'LGA1700')
        spec = dict(ram_min=32, forms=[], wifi=False, upgrade=True)
        selected = cat.choose_platform(spec, cpu, 300000)
        self.assertEqual(selected['board']['memory'], 'DDR5')

    def test_no_fake_dns_claims(self):
        result = recommend(dict(budget=45000, tasks=['office']))
        self.assertFalse(result['pricing_verified'])
        self.assertTrue(any('НЕ подтверждены DNS' in x['text'] for x in result['advice']))

class DualConfigurationTests(unittest.TestCase):
    def test_unknown_stock_is_not_available(self):
        from expert import recommend_two
        r = recommend_two({'budget': 100000, 'tasks': ['office'], 'stock_mode': 'confirmed'})
        self.assertTrue(r['ideal']['ok'])
        self.assertIsNone(r['local'])
        self.assertEqual(r['stock_metadata']['confirmed'], 0)

    def test_two_independent_runs_with_confirmed_fixture(self):
        from expert import recommend_two
        import catalog as cat
        ids = {x['id'] for values in cat.CATALOG.values() if isinstance(values,list) for x in values}
        r = recommend_two({'budget':100000,'tasks':['office']}, stock_ids=ids)
        self.assertTrue(r['ideal']['ok'])
        self.assertIsNotNone(r['local'])
        self.assertEqual(r['ideal']['total'],r['local']['total'])

    def test_sparse_stock_is_not_misrepresented(self):
        from expert import recommend_two
        r = recommend_two({'budget': 100000, 'tasks': ['office']}, stock_ids={'i3-12100f'})
        self.assertIsNone(r['local'])
        self.assertIn('Недостаточно',r['local_reason'])
