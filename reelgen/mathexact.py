"""Точная математика по лентам: RTP линий, распределения скаттера и бонуса.

Ключевой факт: для конкретной линии видимый символ на барабане — равномерный
выбор из всей ленты (позиция остановки равномерна, ряд фиксирован), а барабаны
независимы. Значит распределение по линии одинаково для всех линий, и RTP
считается один раз.
"""

import random
from collections import Counter

from .model import GameConfig, Symbol


def symbol_probs(strip: list[int]) -> dict[int, float]:
    """Вероятность каждого символа в одной видимой ячейке этого барабана."""
    if not strip:
        return {}
    total = len(strip)
    return {sid: count / total for sid, count in Counter(strip).items()}


def _pay(symbol: Symbol, length: int) -> float:
    value = symbol.pays.get(length, 0)
    return float(value) if isinstance(value, (int, float)) else 0.0


def line_report(
    strips: list[list[int]], game: GameConfig, num_lines: int | None = None
) -> dict:
    """Точный RTP линий с разбивкой по символам и длинам.

    Перебор идёт слева направо с отсечением: как только ни у одного символа
    серия уже не тянется, остаток барабанов на выигрыш не влияет и ветка
    закрывается.
    """
    reels = len(strips)
    paying = {symbol.id: symbol for symbol in game.paying_symbols()}
    wild_id = game.id_of_kind("wild")
    dists = [symbol_probs(strip) for strip in strips]

    per_symbol: dict[int, float] = {}
    per_length: dict[int, float] = {}
    total = 0.0
    hit_prob = 0.0

    def finalize(prob: float, best: tuple[float, int, int]) -> None:
        nonlocal total, hit_prob
        win, symbol_id, length = best
        if win <= 0:
            return
        total += prob * win
        hit_prob += prob
        per_symbol[symbol_id] = per_symbol.get(symbol_id, 0.0) + prob * win
        per_length[length] = per_length.get(length, 0.0) + prob * win

    def walk(
        reel: int, alive: frozenset, best: tuple[float, int, int], prob: float
    ) -> None:
        if prob == 0.0:
            return
        if reel == reels or not alive:
            if reel == reels:
                for symbol_id in alive:
                    win = _pay(paying[symbol_id], reels)
                    if win > best[0]:
                        best = (win, symbol_id, reels)
            finalize(prob, best)
            return

        for visible, chance in dists[reel].items():
            still = frozenset(
                symbol_id
                for symbol_id in alive
                if visible == symbol_id or visible == wild_id
            )
            dropped_best = best
            for symbol_id in alive - still:
                win = _pay(paying[symbol_id], reel)
                if win > dropped_best[0]:
                    dropped_best = (win, symbol_id, reel)
            walk(reel + 1, still, dropped_best, prob * chance)

    if reels and all(strips):
        walk(0, frozenset(paying), (0.0, 0, 0), 1.0)

    return {
        "rtp": total,
        "per_symbol": per_symbol,
        "per_length": per_length,
        "line_hit_prob": hit_prob,
        "line_hit_one_in": (1.0 / hit_prob) if hit_prob else 0.0,
        "num_lines": num_lines if num_lines is not None else len(game.paylines),
    }


def window_count_dist(strip: list[int], symbol_id: int, rows: int) -> dict[int, float]:
    """Распределение числа символов symbol_id в видимом окне одного барабана."""
    length = len(strip)
    if length == 0:
        return {}
    counts: dict[int, int] = {}
    for stop in range(length):
        seen = sum(1 for row in range(rows) if strip[(stop + row) % length] == symbol_id)
        counts[seen] = counts.get(seen, 0) + 1
    return {seen: hits / length for seen, hits in counts.items()}


def feature_dist(
    strips: list[list[int]], symbol_id: int, rows: int
) -> dict[int, float]:
    """Свёртка распределений по всем барабанам: P(всего k символов на экране)."""
    total: dict[int, float] = {0: 1.0}
    for strip in strips:
        reel = window_count_dist(strip, symbol_id, rows)
        if not reel:
            continue
        merged: dict[int, float] = {}
        for have, p_have in total.items():
            for seen, p_seen in reel.items():
                merged[have + seen] = merged.get(have + seen, 0.0) + p_have * p_seen
        total = merged
    return total


def feature_report(
    strips: list[list[int]], symbol_id: int, rows: int, threshold: int = 3
) -> dict:
    dist = feature_dist(strips, symbol_id, rows)
    prob = sum(p for seen, p in dist.items() if seen >= threshold)
    return {
        "dist": dist,
        "prob": prob,
        "one_in": (1.0 / prob) if prob else 0.0,
        "threshold": threshold,
    }


def scatter_rtp(
    strips: list[list[int]], game: GameConfig, rows: int, threshold: int = 3
) -> float:
    """Вклад скаттера в RTP. Выплата задана в общих ставках (ключ 'tb')."""
    scat_id = game.id_of_kind("scat")
    if scat_id is None:
        return 0.0
    symbol = game.symbols[scat_id]
    dist = feature_dist(strips, scat_id, rows)

    def payout(seen: int) -> float:
        applicable = [k for k in symbol.pays if isinstance(k, int) and k <= seen]
        if not applicable:
            return 0.0
        value = symbol.pays[max(applicable)]
        if isinstance(value, dict):
            return float(value.get("tb", 0))
        return float(value)

    return sum(p * payout(seen) for seen, p in dist.items() if seen >= threshold)


def _line_wins(
    window: list[list[int]], line: list[int], paying: dict[int, Symbol], wild_id
) -> bool:
    """Есть ли выигрыш на этой линии."""
    visible = [window[reel][line[reel]] for reel in range(len(line))]
    for symbol_id, symbol in paying.items():
        run = 0
        for value in visible:
            if value == symbol_id or value == wild_id:
                run += 1
            else:
                break
        if run >= 3 and symbol.pays.get(run):
            return True
    return False


def simulate_hit_rate(
    strips: list[list[int]], game: GameConfig, spins: int = 50000, seed: int = 0
) -> dict:
    """Оценка доли спинов хотя бы с одним выигрышем по линии.

    Точно посчитать нельзя: 20 линий смотрят на одни и те же барабаны и не
    независимы, а полный перебор — это произведение длин лент.
    """
    rng = random.Random(seed)
    rows = game.rows
    paying = {symbol.id: symbol for symbol in game.paying_symbols()}
    wild_id = game.id_of_kind("wild")
    windows = [
        [
            [strip[(stop + row) % len(strip)] for row in range(rows)]
            for stop in range(len(strip))
        ]
        for strip in strips
    ]

    hits = 0
    for _ in range(spins):
        window = [reel[rng.randrange(len(reel))] for reel in windows]
        for line in game.paylines:
            if _line_wins(window, line, paying, wild_id):
                hits += 1
                break

    prob = hits / spins if spins else 0.0
    error = ((prob * (1 - prob)) / spins) ** 0.5 if spins else 0.0
    return {
        "prob": prob,
        "one_in": (1.0 / prob) if prob else 0.0,
        "spins": spins,
        "error": error,
        "estimated": True,
    }


def full_report(
    strips: list[list[int]],
    game: GameConfig,
    bonus_threshold: int = 3,
    scatter_threshold: int = 3,
    sim_spins: int = 50000,
    seed: int = 0,
    simulate: bool = True,
) -> dict:
    """Полный отчёт: точные линии, скаттер, бонус плюс оценка общего hit rate."""
    rows = game.rows
    lines = line_report(strips, game)
    scat_id = game.id_of_kind("scat")
    bonus_id = game.id_of_kind("bonus")

    scatter = (
        feature_report(strips, scat_id, rows, scatter_threshold)
        if scat_id is not None
        else None
    )
    bonus = (
        feature_report(strips, bonus_id, rows, bonus_threshold)
        if bonus_id is not None
        else None
    )
    scat_rtp = scatter_rtp(strips, game, rows, scatter_threshold)

    return {
        "lines": lines,
        "scatter": scatter,
        "bonus": bonus,
        "scatter_rtp": scat_rtp,
        "total_rtp": lines["rtp"] + scat_rtp,
        "overall_hit": simulate_hit_rate(strips, game, sim_spins, seed)
        if simulate
        else None,
    }
