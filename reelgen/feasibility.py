"""Проверка правил на заведомую невыполнимость до запуска генерации.

Все проверки — гарантированные нижние границы: если тут пусто, генерация
всё ещё может не сойтись, но если тут что-то есть — она точно не сойдётся.
"""

import math
from dataclasses import dataclass

from .rules import DistanceRule, ReelRules, StackRule, matches


@dataclass(frozen=True)
class Problem:
    kind: str
    message: str


def _selector_symbols(
    selector: str, rules: ReelRules, classes: dict[int, str]
) -> list[StackRule]:
    return [
        stack
        for stack in rules.stacks
        if stack.count > 0 and matches(selector, stack.symbol_id, classes)
    ]


def _check_stacks(rules: ReelRules) -> list[Problem]:
    problems = []
    for stack in rules.stacks:
        if stack.count <= 0:
            continue
        sizes = {size: weight for size, weight in stack.sizes.items() if weight > 0}
        if not sizes:
            problems.append(
                Problem(
                    "stack",
                    f"символ {stack.symbol_id}: количество {stack.count}, "
                    f"но не выбран ни один размер стека",
                )
            )
            continue
        smallest = min(sizes)
        if smallest > stack.count:
            problems.append(
                Problem(
                    "stack",
                    f"символ {stack.symbol_id}: минимальный размер стека "
                    f"{smallest} больше заданного количества {stack.count}",
                )
            )
    return problems


def _check_self_distance(
    rule: DistanceRule, rules: ReelRules, classes: dict[int, str]
) -> Problem | None:
    if rule.a != rule.b:
        return None
    stacks = _selector_symbols(rule.a, rules, classes)
    if not stacks:
        return None
    total = sum(stack.count for stack in stacks)
    max_size = max(
        (
            size
            for stack in stacks
            for size, weight in stack.sizes.items()
            if weight > 0
        ),
        default=1,
    )
    max_size = max(1, min(max_size, total))
    blocks = math.ceil(total / max_size)
    needed = total + blocks * rule.min_gap
    if needed <= rules.length:
        return None
    return Problem(
        "distance",
        f"правило {rule.a} ↔ {rule.b} ≥ {rule.min_gap}: "
        f"{total} символов лягут минимум в {blocks} стеков и потребуют "
        f"минимум {needed} позиций, а длина ленты {rules.length}. "
        f"Ослабь дистанцию, увеличь стеки или убери "
        f"{needed - rules.length} символов",
    )


def _min_blocks(stack: StackRule) -> int:
    """Наименьшее возможное число блоков символа — при самых крупных стеках."""
    sizes = [size for size, weight in stack.sizes.items() if weight > 0]
    largest = max(sizes) if sizes else 1
    largest = max(1, min(largest, stack.count))
    return math.ceil(stack.count / largest)


def _max_blocks(stack: StackRule) -> int:
    """Наибольшее возможное число блоков символа — при самых мелких стеках."""
    sizes = [size for size, weight in stack.sizes.items() if weight > 0]
    smallest = min(sizes) if sizes else 1
    smallest = max(1, min(smallest, stack.count))
    return stack.count // smallest


def _check_separation(rules: ReelRules) -> list[Problem]:
    """Блоки одного символа нельзя ставить вплотную — каждому нужен разделитель.

    На кольце из B блоков, где K принадлежат одному символу, разложить без
    слипания можно только при K ≤ B - K. Берём самый благоприятный случай:
    у проверяемого символа блоков минимум, у всех прочих — максимум.
    """
    live = [stack for stack in rules.stacks if stack.count > 0]
    problems = []
    for stack in live:
        mine = _min_blocks(stack)
        others = sum(_max_blocks(other) for other in live if other is not stack)
        if mine <= others:
            continue
        problems.append(
            Problem(
                "separation",
                f"символ {stack.symbol_id}: {stack.count} символов лягут минимум "
                f"в {mine} стеков, а разделить их могут максимум {others} чужих "
                f"стеков. Стеки одного символа нельзя ставить вплотную — они "
                f"слиплись бы в один. Увеличь размер стеков этого символа или "
                f"добавь других символов",
            )
        )
    return problems


def _check_filler(
    rule: DistanceRule, rules: ReelRules, classes: dict[int, str]
) -> Problem | None:
    if not rule.filler:
        return None
    if not _selector_symbols(rule.a, rules, classes):
        return None
    if not _selector_symbols(rule.b, rules, classes):
        return None
    available = sum(
        stack.count
        for stack in rules.stacks
        if stack.count > 0 and classes.get(stack.symbol_id) == rule.filler
    )
    if available:
        return None
    return Problem(
        "filler",
        f"правило {rule.a} ↔ {rule.b} требует наполнитель класса "
        f"'{rule.filler}', но символов этого класса на риле нет",
    )


def check_reel(rules: ReelRules, classes: dict[int, str]) -> list[Problem]:
    problems = _check_stacks(rules)
    if problems:
        # состав символов сам по себе битый — остальные проверки бессмысленны
        return problems
    problems.extend(_check_separation(rules))
    for rule in rules.distances:
        problem = _check_self_distance(rule, rules, classes)
        if problem:
            problems.append(problem)
        problem = _check_filler(rule, rules, classes)
        if problem:
            problems.append(problem)
    return problems
