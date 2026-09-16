"""Модель конфига игры: символы, линии, рилсеты."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Symbol:
    """Один символ игры.

    pays: для обычных символов {длина: выплата}; для скаттера значение может быть
    вложенным словарём вида {'tb': 2, 'fs': 8}.
    asset: имя ассета в игре ('el_01'), не путь к картинке.
    """

    id: int
    kind: str
    pays: dict
    asset: str


@dataclass
class GameConfig:
    """Полный конфиг игры, разобранный из .py-файла."""

    symbols: dict[int, Symbol] = field(default_factory=dict)
    paylines: list[list[int]] = field(default_factory=list)
    reelsets: dict[str, list[list[int]]] = field(default_factory=dict)
    source_text: str = ""
    source_path: str = ""

    @property
    def rows(self) -> int:
        if not self.paylines:
            return 0
        return max(max(line) for line in self.paylines) + 1

    @property
    def reels_count(self) -> int:
        return len(self.paylines[0]) if self.paylines else 0

    def id_of_kind(self, kind: str) -> int | None:
        for sid in sorted(self.symbols):
            if self.symbols[sid].kind == kind:
                return sid
        return None

    def paying_symbols(self) -> list[Symbol]:
        return [
            self.symbols[sid]
            for sid in sorted(self.symbols)
            if self.symbols[sid].kind in ("line", "wild") and self.symbols[sid].pays
        ]
