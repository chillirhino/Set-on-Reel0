"""Правила ленты: состав, стеки, дистанции. Проверка нарушений на кольце."""

from dataclasses import dataclass, field

from .model import GameConfig

LOW = "low"
MIDDLE = "middle"
HIGH = "high"
SPECIAL = "special"
CLASSES = (LOW, MIDDLE, HIGH, SPECIAL)


@dataclass(frozen=True)
class Block:
    """Стек одинаковых символов на ленте."""

    symbol_id: int
    start: int
    size: int


@dataclass
class StackRule:
    """Сколько символа на риле и какими стеками его класть.

    sizes: {размер стека: вес в процентах}. Веса нормализуются при генерации.
    """

    symbol_id: int
    count: int
    sizes: dict[int, float] = field(default_factory=lambda: {1: 100.0})


@dataclass
class DistanceRule:
    """Минимальная дистанция между блоками A и B.

    Селектор — 'class:<имя класса>' или 'id:<номер символа>'.
    filler: если задан, в промежутке должно быть не меньше min_gap символов
    этого класса.
    """

    a: str
    b: str
    min_gap: int
    filler: str | None = None


@dataclass
class ReelRules:
    """Правила одного рила."""

    stacks: list[StackRule] = field(default_factory=list)
    distances: list[DistanceRule] = field(default_factory=list)

    @property
    def length(self) -> int:
        return sum(stack.count for stack in self.stacks)


@dataclass
class RuleSet:
    """Правила всей игры: классы символов и правила по рилам каждого рилсета."""

    classes: dict[int, str] = field(default_factory=dict)
    reels: dict[str, list[ReelRules]] = field(default_factory=dict)


@dataclass(frozen=True)
class Violation:
    """Нарушенное правило дистанции для конкретной пары блоков."""

    rule_index: int
    a: Block
    b: Block
    gap: int
    filler_count: int
    deficit: int


def default_classes(game: GameConfig) -> dict[int, str]:
    """Классы по умолчанию: 1-4 low, 5-6 middle, 7-8 high, спецсимволы special."""
    classes: dict[int, str] = {}
    for sid, symbol in game.symbols.items():
        if symbol.kind != "line":
            classes[sid] = SPECIAL
        elif sid <= 4:
            classes[sid] = LOW
        elif sid <= 6:
            classes[sid] = MIDDLE
        else:
            classes[sid] = HIGH
    return classes


def blocks_of(strip: list[int]) -> list[Block]:
    """Блоки ленты в порядке кольца. Хвост и голова слипаются, если символ один."""
    n = len(strip)
    if n == 0:
        return []
    if len(set(strip)) == 1:
        return [Block(strip[0], 0, n)]

    start = next(i for i in range(n) if strip[i] != strip[i - 1])
    blocks: list[Block] = []
    pos = start
    covered = 0
    while covered < n:
        sym = strip[pos % n]
        size = 0
        while covered + size < n and strip[(pos + size) % n] == sym:
            size += 1
        blocks.append(Block(sym, pos % n, size))
        pos += size
        covered += size
    return blocks


def matches(selector: str, symbol_id: int, classes: dict[int, str]) -> bool:
    kind, _, value = selector.partition(":")
    if kind == "id":
        return symbol_id == int(value)
    if kind == "class":
        return classes.get(symbol_id) == value
    return False


def gap_between(a: Block, b: Block, length: int) -> tuple[int, int]:
    """Начало промежутка после блока a и его длина до начала блока b."""
    gap_start = (a.start + a.size) % length
    return gap_start, (b.start - gap_start) % length


def violations(
    strip: list[int], distances: list[DistanceRule], classes: dict[int, str]
) -> list[Violation]:
    """Нарушения по всем правилам. Проверяются только ближайшие пары."""
    n = len(strip)
    if n == 0:
        return []
    blocks = blocks_of(strip)
    found: list[Violation] = []

    for index, rule in enumerate(distances):
        relevant = [
            block
            for block in blocks
            if matches(rule.a, block.symbol_id, classes)
            or matches(rule.b, block.symbol_id, classes)
        ]
        if len(relevant) < 2:
            continue
        for i, left in enumerate(relevant):
            right = relevant[(i + 1) % len(relevant)]
            left_a = matches(rule.a, left.symbol_id, classes)
            left_b = matches(rule.b, left.symbol_id, classes)
            right_a = matches(rule.a, right.symbol_id, classes)
            right_b = matches(rule.b, right.symbol_id, classes)
            if not ((left_a and right_b) or (left_b and right_a)):
                continue

            gap_start, gap = gap_between(left, right, n)
            filler_count = 0
            if rule.filler:
                filler_count = sum(
                    1
                    for step in range(gap)
                    if classes.get(strip[(gap_start + step) % n]) == rule.filler
                )

            deficit = max(0, rule.min_gap - gap)
            if rule.filler:
                deficit += max(0, rule.min_gap - filler_count)
            if deficit:
                found.append(Violation(index, left, right, gap, filler_count, deficit))
    return found


def penalty(
    strip: list[int], distances: list[DistanceRule], classes: dict[int, str]
) -> int:
    return sum(v.deficit for v in violations(strip, distances, classes))
