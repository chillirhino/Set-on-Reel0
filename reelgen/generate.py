"""Генерация лент: сборка стеков, жадная укладка, локальный поиск."""

import random
import time
from dataclasses import dataclass, field

from . import strips
from .rules import (
    DistanceRule,
    ReelRules,
    StackRule,
    Violation,
    blocks_of,
    matches,
    penalty,
    violations,
)


def assemble_sizes(stack: StackRule, rng: random.Random) -> list[int]:
    """Размеры стеков для символа. Сумма всегда ровно stack.count.

    Сама сборка живёт в strips.py: обе половины инструмента считают стеки по
    одному правилу «количество — закон, шансы — ориентир», и расходиться им
    незачем.
    """
    return strips.assemble_sizes(stack.count, stack.sizes, rng)


@dataclass
class GenResult:
    """Результат генерации одного рила.

    merges — сколько раз два блока одного символа встали вплотную и слиплись.
    Это порча заказанной раскладки стеков, поэтому движок такого не допускает;
    ненулевое значение бывает только у неудачной генерации (stage == 'failed').
    """

    strip: list[int] = field(default_factory=list)
    seed: int = 0
    stage: str = "greedy"
    attempts: int = 0
    violations: list[Violation] = field(default_factory=list)
    stack_actual: dict[int, dict[int, int]] = field(default_factory=dict)
    merges: int = 0


def count_merges(order: list[tuple[int, int]]) -> int:
    """Сколько соседних пар блоков одного символа по кольцу.

    Такие пары сливаются в один стек, ломая заказанную раскладку размеров.
    """
    if len(order) < 2:
        return 0
    return sum(
        1
        for index in range(len(order))
        if order[index][0] == order[(index + 1) % len(order)][0]
    )


def _build_blocks(rules: ReelRules, rng: random.Random) -> list[tuple[int, int]]:
    """Мультимножество блоков (символ, размер) по всем правилам состава."""
    blocks: list[tuple[int, int]] = []
    for stack in rules.stacks:
        for size in assemble_sizes(stack, rng):
            blocks.append((stack.symbol_id, size))
    return blocks


def _expand(order: list[tuple[int, int]]) -> list[int]:
    strip: list[int] = []
    for symbol_id, size in order:
        strip.extend([symbol_id] * size)
    return strip


def _stack_actual(strip: list[int]) -> dict[int, dict[int, int]]:
    actual: dict[int, dict[int, int]] = {}
    for block in blocks_of(strip):
        by_size = actual.setdefault(block.symbol_id, {})
        by_size[block.size] = by_size.get(block.size, 0) + 1
    return actual


def _pair_ok(
    rule: DistanceRule,
    classes: dict[int, str],
    strip: list[int],
    gap_start: int,
    gap: int,
) -> bool:
    """Промежуток длины gap, начинающийся с gap_start, удовлетворяет правилу?"""
    if gap < rule.min_gap:
        return False
    if not rule.filler:
        return True
    length = len(strip)
    seen = 0
    for step in range(gap):
        if classes.get(strip[(gap_start + step) % length]) == rule.filler:
            seen += 1
            if seen >= rule.min_gap:
                return True
    return seen >= rule.min_gap


def _greedy_once(
    blocks: list[tuple[int, int]],
    rules: ReelRules,
    classes: dict[int, str],
    rng: random.Random,
) -> list[tuple[int, int]] | None:
    """Одна попытка жадной укладки. None — не сошлось."""
    total = sum(size for _, size in blocks)
    remaining: dict[tuple[int, int], int] = {}
    for item in blocks:
        remaining[item] = remaining.get(item, 0) + 1

    order: list[tuple[int, int]] = []
    strip: list[int] = []
    # для каждого правила — последний и первый уложенный блок, подходящий под a или b
    last_rel: dict[int, tuple[int, int, int]] = {}
    first_rel: dict[int, tuple[int, int, int]] = {}

    def relevant(rule: DistanceRule, symbol_id: int) -> tuple[bool, bool]:
        return (
            matches(rule.a, symbol_id, classes),
            matches(rule.b, symbol_id, classes),
        )

    while remaining:
        # Порядок кандидатов — случайный с весами по остатку символов. Это как
        # тянуть из мешка без возврата: пропорции держатся ровными по всей ленте.
        # Простая сортировка по остатку тут была бы ошибкой — она выложила бы
        # сначала все младшие символы, а спешиалы слиплись бы в хвосте.
        pool = [
            (item, float(remaining[item] * item[1]))
            for item, count in remaining.items()
            if count > 0
        ]
        candidates: list[tuple[int, int]] = []
        while pool:
            total_weight = sum(weight for _, weight in pool)
            pick = rng.random() * total_weight
            running = 0.0
            for index, (item, weight) in enumerate(pool):
                running += weight
                if pick <= running:
                    candidates.append(item)
                    pool.pop(index)
                    break
            else:
                candidates.append(pool.pop()[0])

        placed = False
        for item in candidates:
            symbol_id, size = item
            # Два блока одного символа вплотную слиплись бы в один стек —
            # заказанная раскладка размеров была бы нарушена.
            if order and order[-1][0] == symbol_id:
                continue
            start = len(strip)
            probe = strip + [symbol_id] * size
            ok = True
            for index, rule in enumerate(rules.distances):
                is_a, is_b = relevant(rule, symbol_id)
                if not (is_a or is_b):
                    continue
                previous = last_rel.get(index)
                if previous is None:
                    continue
                prev_sym, prev_start, prev_size = previous
                prev_a, prev_b = relevant(rule, prev_sym)
                if not ((prev_a and is_b) or (prev_b and is_a)):
                    continue
                gap_start = prev_start + prev_size
                gap = start - gap_start
                if not _pair_ok(rule, classes, probe, gap_start, gap):
                    ok = False
                    break
            if not ok:
                continue

            order.append(item)
            strip = probe
            for index, rule in enumerate(rules.distances):
                is_a, is_b = relevant(rule, symbol_id)
                if is_a or is_b:
                    last_rel[index] = (symbol_id, start, size)
                    first_rel.setdefault(index, (symbol_id, start, size))
            remaining[item] -= 1
            if remaining[item] == 0:
                del remaining[item]
            placed = True
            break

        if not placed:
            return None

    # замыкаем кольцо: хвост и голова тоже не должны быть одним символом
    if len(order) > 1 and order[0][0] == order[-1][0]:
        return None

    for index, rule in enumerate(rules.distances):
        head = first_rel.get(index)
        tail = last_rel.get(index)
        if head is None or tail is None or head == tail:
            continue
        head_a, head_b = relevant(rule, head[0])
        tail_a, tail_b = relevant(rule, tail[0])
        if not ((tail_a and head_b) or (tail_b and head_a)):
            continue
        gap_start = (tail[1] + tail[2]) % total
        gap = (head[1] - gap_start) % total
        if not _pair_ok(rule, classes, strip, gap_start, gap):
            return None

    return order


# Слипание стеков ломает заказанную раскладку размеров, поэтому в локальном
# поиске оно стоит дороже недостающего символа дистанции.
_MERGE_COST = 5


def _score(
    order: list[tuple[int, int]], rules: ReelRules, classes: dict[int, str]
) -> tuple[int, list[int]]:
    strip = _expand(order)
    total = penalty(strip, rules.distances, classes)
    total += _MERGE_COST * count_merges(order)
    return total, strip


def _repair(
    blocks: list[tuple[int, int]],
    rules: ReelRules,
    classes: dict[int, str],
    rng: random.Random,
    seconds: float,
) -> tuple[list[tuple[int, int]], int]:
    """Локальный поиск свопами. Возвращает (порядок блоков, штраф)."""
    order = list(blocks)
    rng.shuffle(order)
    score, _ = _score(order, rules, classes)
    if score == 0 or len(order) < 2:
        return order, score

    best_order, best_score = list(order), score
    deadline = time.monotonic() + seconds
    stall = 0

    while score > 0 and time.monotonic() < deadline:
        i, j = rng.randrange(len(order)), rng.randrange(len(order))
        if i == j:
            continue
        order[i], order[j] = order[j], order[i]
        candidate_score, _ = _score(order, rules, classes)

        if candidate_score <= score:
            stall = stall + 1 if candidate_score == score else 0
            score = candidate_score
            if score < best_score:
                best_order, best_score = list(order), score
        else:
            order[i], order[j] = order[j], order[i]
            stall += 1

        if stall > 300:
            # выбиваемся с плато случайной перетасовкой
            rng.shuffle(order)
            score, _ = _score(order, rules, classes)
            stall = 0

    if score < best_score:
        best_order, best_score = list(order), score
    return best_order, best_score


def generate_reel(
    rules: ReelRules,
    classes: dict[int, str],
    seed: int,
    greedy_attempts: int = 200,
    repair_seconds: float = 8.0,
) -> GenResult:
    """Сгенерировать одну ленту. Стадии: жадная укладка → repair → failed."""
    rng = random.Random(seed)
    if rules.length == 0:
        return GenResult(strip=[], seed=seed, stage="greedy", attempts=0)

    blocks: list[tuple[int, int]] = []
    for attempt in range(1, greedy_attempts + 1):
        # Стеки пересобираются на каждой попытке: неудачная случайная сборка
        # (слишком много мелких блоков одного символа) не должна валить рил.
        blocks = _build_blocks(rules, rng)
        if not blocks:
            return GenResult(strip=[], seed=seed, stage="greedy", attempts=0)
        order = _greedy_once(blocks, rules, classes, rng)
        if order is not None:
            strip = _expand(order)
            return GenResult(
                strip=strip,
                seed=seed,
                stage="greedy",
                attempts=attempt,
                violations=violations(strip, rules.distances, classes),
                stack_actual=_stack_actual(strip),
                merges=count_merges(order),
            )

    order, score = _repair(blocks, rules, classes, rng, repair_seconds)
    strip = _expand(order)
    return GenResult(
        strip=strip,
        seed=seed,
        stage="repair" if score == 0 else "failed",
        attempts=greedy_attempts,
        violations=violations(strip, rules.distances, classes),
        stack_actual=_stack_actual(strip),
        merges=count_merges(order),
    )


def generate_reelset(
    reel_rules: list[ReelRules],
    classes: dict[int, str],
    seed: int,
    greedy_attempts: int = 200,
    repair_seconds: float = 8.0,
) -> list[GenResult]:
    """Сгенерировать все рилы рилсета. Один сид воспроизводит весь набор."""
    return [
        generate_reel(
            rules,
            classes,
            seed=seed * 1000 + index,
            greedy_attempts=greedy_attempts,
            repair_seconds=repair_seconds,
        )
        for index, rules in enumerate(reel_rules)
    ]
