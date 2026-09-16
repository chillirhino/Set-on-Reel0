"""Состав ленты: сколько какого символа и какими стеками."""

from collections import Counter

from .model import GameConfig
from .rules import blocks_of


def reel_composition(
    strip: list[int], classes: dict[int, str], game: GameConfig
) -> list[dict]:
    """По записи на каждый присутствующий символ, отсортировано по id."""
    if not strip:
        return []
    counts = Counter(strip)
    stacks: dict[int, dict[int, int]] = {}
    for block in blocks_of(strip):
        by_size = stacks.setdefault(block.symbol_id, {})
        by_size[block.size] = by_size.get(block.size, 0) + 1

    total = len(strip)
    rows = []
    for symbol_id in sorted(counts):
        symbol = game.symbols.get(symbol_id)
        rows.append(
            {
                "symbol_id": symbol_id,
                "kind": symbol.kind if symbol else "unknown",
                "asset": symbol.asset if symbol else "",
                "symbol_class": classes.get(symbol_id, ""),
                "count": counts[symbol_id],
                "share": counts[symbol_id] / total,
                "stacks": dict(sorted(stacks.get(symbol_id, {}).items())),
            }
        )
    return rows


def reelset_composition(
    strips: list[list[int]], classes: dict[int, str], game: GameConfig
) -> dict:
    """Состав по каждому рилу плюс сводка по всему рилсету.

    В сводке значимы count и share: стеки в ней считаются по склеенным лентам,
    поэтому на стыках рилов могут слипнуться. В UI колонка стеков показывается
    только по отдельным рилам.
    """
    reels = [reel_composition(strip, classes, game) for strip in strips]
    merged: list[int] = []
    for strip in strips:
        merged.extend(strip)
    return {
        "reels": reels,
        "totals": reel_composition(merged, classes, game),
        "lengths": [len(strip) for strip in strips],
    }
