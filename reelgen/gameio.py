"""Чтение и запись .py-формата игры: символы, линии, рилсеты."""

import ast
import re
from pathlib import Path

from .model import GameConfig, Symbol


class ParseError(Exception):
    """Файл игры не разобрался."""


_SYMBOL_RE = re.compile(r"^symbol_(\d+)\s*=\s*(.+?)\s*$", re.MULTILINE)
_PAYLINE_RE = re.compile(r"^payline_(\d+)\s*=\s*(\[[^\]]*\])\s*$", re.MULTILINE)
_REELSET_RE = re.compile(r"^reels_(\w+)\s*=\s*'''(.*?)'''", re.MULTILINE | re.DOTALL)


def parse_text(text: str, path: str = "") -> GameConfig:
    symbols: dict[int, Symbol] = {}
    for match in _SYMBOL_RE.finditer(text):
        sid = int(match.group(1))
        try:
            parts = ast.literal_eval("(" + match.group(2) + ")")
        except (ValueError, SyntaxError) as exc:
            raise ParseError(f"symbol_{sid:02d}: не разобрался: {exc}") from exc
        if not isinstance(parts, tuple) or len(parts) != 3:
            raise ParseError(
                f"symbol_{sid:02d}: ожидались три поля (вид, выплаты, ассет), "
                f"получено {len(parts) if isinstance(parts, tuple) else 1}"
            )
        kind, pays, asset = parts
        symbols[sid] = Symbol(id=sid, kind=str(kind), pays=dict(pays), asset=str(asset))

    paylines = [
        ast.literal_eval(match.group(2))
        for match in sorted(_PAYLINE_RE.finditer(text), key=lambda m: int(m.group(1)))
    ]

    reelsets: dict[str, list[list[int]]] = {}
    for match in _REELSET_RE.finditer(text):
        name = match.group(1)
        reels = []
        for line in match.group(2).strip().splitlines():
            line = line.strip()
            if line:
                reels.append([int(token) for token in line.split()])
        reelsets[name] = reels

    if not symbols:
        raise ParseError("в файле не найдено ни одного symbol_NN")

    return GameConfig(
        symbols=symbols,
        paylines=paylines,
        reelsets=reelsets,
        source_text=text,
        source_path=str(path),
    )


def parse_file(path: str | Path) -> GameConfig:
    path = Path(path)
    return parse_text(path.read_text(encoding="utf-8"), str(path))


def render_reelset(reels: list[list[int]]) -> str:
    """Тело блока reels_<name> = '''...''' — по строке на рил."""
    lines = [" ".join(str(sid) for sid in reel) for reel in reels]
    return "\n" + "\n".join(lines) + "\n"


def export_text(source_text: str, reelsets: dict[str, list[list[int]]]) -> str:
    """Подменяет содержимое блоков reels_<name>, остальной файл не трогает."""

    def replace(match: re.Match) -> str:
        name = match.group(1)
        if name not in reelsets:
            return match.group(0)
        return f"reels_{name} = '''{render_reelset(reelsets[name])}'''"

    return _REELSET_RE.sub(replace, source_text)
