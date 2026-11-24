"""Проверки двухколоночного интерфейса без зависимости от Flask."""
import unittest
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from expert import recommend_two
from knowledge_base import TASK_NAMES, kb, rub

ROOT = Path(__file__).resolve().parents[1]


class InterfaceTests(unittest.TestCase):
    def render(self, mode):
        env = Environment(loader=FileSystemLoader(str(ROOT / 'templates')), autoescape=True)
        env.filters['rub'] = rub
        form = {'budget': '100000', 'tasks': ['office'], 'stock_mode': mode}
        result = recommend_two(form)
        html = env.get_template('index.html').render(
            form=form, res=result, tasks=TASK_NAMES, nrules=len(kb.rules),
            url_for=lambda *_args, **_kwargs: '/static/style.css')
        return result, html

    def test_two_builds_and_independent_collapsible_logs(self):
        result, html = self.render('candidate')
        self.assertIsNotNone(result['ideal'])
        self.assertIsNotNone(result['local'])
        self.assertEqual(html.count('class="configuration"'), 2)
        self.assertEqual(html.count('class="panel inference-log"'), 2)
        self.assertIn('class="configuration-grid"', html)
        self.assertEqual(html.count('Журнал логического вывода'), 2)

    def test_strict_mode_explains_missing_stock(self):
        result, html = self.render('confirmed')
        self.assertIsNone(result['local'])
        self.assertEqual(html.count('class="configuration"'), 1)
        self.assertIn('Вариант 2 — наличие в Иркутске', html)
        self.assertEqual(html.count('class="panel inference-log"'), 1)
