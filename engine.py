"""
Механизм логического вывода экспертной системы.

Реализует продукционную модель с прямой цепочкой рассуждений
(forward chaining) в стиле CLIPS:
  * рабочая память — множество фактов (тип + атрибуты);
  * правило — набор образцов (условий) и действие;
  * повестка (agenda) — множество активаций, из которых на каждом шаге
    выбирается одна по стратегии разрешения конфликтов:
    1) наибольший приоритет (salience), 2) новизна фактов (recency);
  * рефракция — одна и та же активация (правило + набор фактов)
    срабатывает не более одного раза;
  * поддержка истинности (TMS) — при удалении факта автоматически
    удаляются все факты, выведенные из него;
  * трассировка — журнал сработавших правил и дерево вывода каждого
    факта для подсистемы объяснений.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable


class Fact:
    """Факт рабочей памяти."""

    __slots__ = ("id", "kind", "data", "rule", "premises", "note", "alive")

    def __init__(self, fid: int, kind: str, data: dict, rule: str | None,
                 premises: tuple[int, ...], note: str = ""):
        self.id = fid
        self.kind = kind
        self.data = data
        self.rule = rule            # код правила, выведшего факт (None — исходный)
        self.premises = premises    # id фактов-посылок
        self.note = note            # пояснение на естественном языке
        self.alive = True

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)

    def __repr__(self):
        attrs = ", ".join(f"{k}={v!r}" for k, v in self.data.items())
        return f"f-{self.id} ({self.kind} {attrs})"


@dataclass
class Pattern:
    """Образец условия: факт заданного типа с ограничениями на атрибуты.

    Ограничение — либо конкретное значение, либо функция-предикат.
    alias — имя, под которым найденный факт передаётся в действие.
    negated=True означает условие отсутствия (NOT) такого факта.
    """
    alias: str | None
    kind: str
    constraints: dict = field(default_factory=dict)
    negated: bool = False

    def matches(self, fact: Fact) -> bool:
        if fact.kind != self.kind:
            return False
        for key, cond in self.constraints.items():
            if key not in fact.data:
                return False
            value = fact.data[key]
            if callable(cond):
                if not cond(value):
                    return False
            elif value != cond:
                return False
        return True


def P(alias: str, kind: str, **constraints) -> Pattern:
    """Позитивный образец (факт должен существовать)."""
    return Pattern(alias, kind, constraints)


def NOT(kind: str, **constraints) -> Pattern:
    """Негативный образец (такого факта быть не должно)."""
    return Pattern(None, kind, constraints, negated=True)


@dataclass
class Rule:
    code: str
    title: str
    group: str
    salience: int
    patterns: list[Pattern]
    action: Callable
    test: Callable | None = None   # доп. условие над связанными фактами
    description: str = ""


@dataclass
class TraceEntry:
    step: int
    code: str
    title: str
    matched: list[str]
    message: str = ""
    asserted: list[int] = field(default_factory=list)
    retracted: list[int] = field(default_factory=list)


class KnowledgeBase:
    """Контейнер правил; правила регистрируются декоратором @kb.rule."""

    def __init__(self):
        self.rules: list[Rule] = []

    def rule(self, code: str, title: str, *, group: str, salience: int = 0,
             when: Iterable[Pattern] = (), test: Callable | None = None):
        def decorator(func):
            self.rules.append(Rule(code, title, group, salience, list(when),
                                   func, test, (func.__doc__ or "").strip()))
            return func
        return decorator


class Context:
    """Объект, передаваемый в действие правила: доступ к рабочей памяти."""

    def __init__(self, engine: "Engine", rule: Rule, matched: dict[str, Fact],
                 entry: TraceEntry):
        self.engine = engine
        self.rule = rule
        self.matched = matched
        self.entry = entry

    # --- изменение рабочей памяти ---
    def declare(self, kind: str, note: str = "", premises=None, **data) -> Fact:
        if premises is None:
            premises = [f for f in self.matched.values()]
        fact = self.engine._assert(kind, data, self.rule.code,
                                   tuple(f.id for f in premises), note)
        self.entry.asserted.append(fact.id)
        return fact

    def retract(self, fact: Fact):
        removed = self.engine._retract(fact)
        self.entry.retracted.extend(removed)

    def explain(self, message: str):
        self.entry.message = (self.entry.message + " " + message).strip()

    def halt(self):
        self.engine.halted = True

    # --- запросы к рабочей памяти (аналог find-all-facts в CLIPS) ---
    def facts(self, kind: str, **constraints) -> list[Fact]:
        pat = Pattern(None, kind, constraints)
        return [f for f in self.engine.facts() if pat.matches(f)]

    def first(self, kind: str, **constraints) -> Fact | None:
        found = self.facts(kind, **constraints)
        return found[0] if found else None


class Engine:
    def __init__(self, kb: KnowledgeBase, max_steps: int = 2000):
        self.kb = kb
        self.max_steps = max_steps
        self.reset()

    def reset(self):
        self._facts: dict[int, Fact] = {}
        self._all: dict[int, Fact] = {}   # включая удалённые (для объяснений)
        self._ids = itertools.count(1)
        self._fired: set[tuple] = set()
        self.trace: list[TraceEntry] = []
        self.halted = False

    # ---------- рабочая память ----------
    def facts(self) -> list[Fact]:
        return list(self._facts.values())

    def fact(self, fid: int) -> Fact:
        return self._all[fid]

    def declare(self, kind: str, **data) -> Fact:
        """Добавление исходного факта (ввод пользователя)."""
        return self._assert(kind, data, None, (), "")

    def _assert(self, kind, data, rule, premises, note) -> Fact:
        fact = Fact(next(self._ids), kind, dict(data), rule, premises, note)
        self._facts[fact.id] = fact
        self._all[fact.id] = fact
        return fact

    def _retract(self, fact: Fact) -> list[int]:
        """Удаление факта и (по TMS) всех зависящих от него фактов."""
        removed = []
        stack = [fact]
        while stack:
            f = stack.pop()
            if not f.alive:
                continue
            f.alive = False
            self._facts.pop(f.id, None)
            removed.append(f.id)
            for other in list(self._facts.values()):
                if f.id in other.premises:
                    stack.append(other)
        return removed

    # ---------- сопоставление с образцами ----------
    def _activations(self):
        facts = self.facts()
        by_kind: dict[str, list[Fact]] = {}
        for f in facts:
            by_kind.setdefault(f.kind, []).append(f)

        for rule in self.kb.rules:
            positive = [p for p in rule.patterns if not p.negated]
            negative = [p for p in rule.patterns if p.negated]
            if any(any(p.matches(f) for f in by_kind.get(p.kind, ()))
                   for p in negative):
                continue
            candidates = []
            for p in positive:
                cands = [f for f in by_kind.get(p.kind, ()) if p.matches(f)]
                if not cands:
                    break
                candidates.append(cands)
            else:
                for combo in itertools.product(*candidates):
                    if len({f.id for f in combo}) != len(combo):
                        continue
                    key = (rule.code,) + tuple(f.id for f in combo)
                    if key in self._fired:
                        continue
                    bound = {p.alias: f for p, f in zip(positive, combo)}
                    if rule.test and not rule.test(**bound):
                        continue
                    yield rule, bound, key

    def _select(self):
        """Разрешение конфликтов: salience, затем новизна фактов."""
        best = None
        best_rank = None
        for rule, bound, key in self._activations():
            recency = max((f.id for f in bound.values()), default=0)
            rank = (rule.salience, recency, -self.kb.rules.index(rule))
            if best_rank is None or rank > best_rank:
                best, best_rank = (rule, bound, key), rank
        return best

    # ---------- цикл вывода ----------
    def run(self) -> int:
        steps = 0
        while not self.halted and steps < self.max_steps:
            selected = self._select()
            if selected is None:
                break
            rule, bound, key = selected
            self._fired.add(key)
            steps += 1
            entry = TraceEntry(steps, rule.code, rule.title,
                               [f"f-{f.id}" for f in bound.values()])
            self.trace.append(entry)
            rule.action(Context(self, rule, bound, entry), **bound)
        if steps >= self.max_steps:
            raise RuntimeError("Превышено число шагов вывода — возможен цикл правил")
        return steps

    # ---------- объяснения ----------
    def derivation(self, fact: Fact, _seen=None) -> dict:
        """Дерево вывода факта: правило и рекурсивно его посылки."""
        _seen = _seen or set()
        node = {"fact": fact, "rule": None, "children": []}
        if fact.rule:
            node["rule"] = next(r for r in self.kb.rules if r.code == fact.rule)
        if fact.id in _seen:
            return node
        _seen = _seen | {fact.id}
        for pid in fact.premises:
            node["children"].append(self.derivation(self._all[pid], _seen))
        return node

    def chain(self, fact: Fact) -> list[str]:
        """Упорядоченная цепочка кодов правил, приведших к факту."""
        order: list[str] = []

        def walk(node):
            for ch in node["children"]:
                walk(ch)
            if node["rule"] and node["rule"].code not in order:
                order.append(node["rule"].code)
        walk(self.derivation(fact))
        return order
