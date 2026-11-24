import unittest
from availability import candidate_stock, validated_stock
from expert import recommend_two

class CandidateStockTests(unittest.TestCase):
    def test_candidates_are_not_confirmed(self):
        ids, info = candidate_stock()
        strict, _ = validated_stock()
        self.assertGreaterEqual(len(ids), 18)
        self.assertEqual(len(strict), 0)

    def test_game_candidate_build(self):
        res = recommend_two({"budget": 180000, "tasks": ["gaming"], "resolution": "1440p"})
        self.assertIsNotNone(res["local"])
        self.assertIn("STOCK-DEMO", [a["rule"] for a in res["local"]["advice"]])
        self.assertIn("DDR", next(p["name"] for p in res["local"]["parts"] if p["kind"] == "ram"))

    def test_office_candidate_build(self):
        res = recommend_two({"budget": 100000, "tasks": ["office"]})
        self.assertIsNotNone(res["local"])

    def test_confirmed_mode_does_not_fake_stocks(self):
        res = recommend_two({"budget": 180000, "tasks": ["gaming"], "stock_mode": "confirmed"})
        self.assertIsNone(res["local"])
