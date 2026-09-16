# Reel Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Локальный инструмент, который генерирует ленты слота по заданным правилам (количества, стеки, дистанции), показывает раскладку картинками, состав по рилам и точный RTP.

**Architecture:** Python-ядро из узких модулей (парсинг формата игры → правила → генератор → точная математика → статистика) плюс тонкий локальный HTTP-сервер, отдающий JSON API и статику. Фронт — одна страница на чистом JS, без сборки. Каждый модуль тестируется отдельно; сервер логики не содержит.

**Tech Stack:** Python 3.12, только стандартная библиотека (`http.server`, `ast`, `re`, `json`, `random`, `unittest`). Фронт — vanilla JS + CSS, без зависимостей.

## Global Constraints

- Только стандартная библиотека Python. Никаких `pip install`.
- Целевой Python: 3.12 (доступен как `python3`).
- Все ленты считаются замкнутыми в кольцо.
- Длина ленты = сумма заданных количеств символов. Свободных позиций нет.
- Тесты: `unittest`, запуск `python3 -m unittest discover -s tests -t . -v` из корня проекта.
- Рабочая директория: `/Users/mark/2_Claude/Reel Generator`.
- Комментарии и сообщения интерфейса — по-русски, имена в коде — по-английски.
- Фикстура для тестов уже существует: `tests/fixtures/sample_game.py` (12 символов, 20 линий, рилсеты `spins_1` и `freespins_0`, ленты по 40 символов).
- Спека: `docs/superpowers/specs/2026-09-09-reel-generator-design.md`.
- Проект не под git. Шаги «Checkpoint» = прогнать весь набор тестов; коммитов в плане нет.

---

### Task 1: Модель данных

**Files:**
- Create: `reelgen/__init__.py`
- Create: `reelgen/model.py`
- Test: `tests/test_model.py`

**Interfaces:**
- Consumes: ничего
- Produces:
  - `Symbol(id: int, kind: str, pays: dict, asset: str)` — frozen dataclass
  - `GameConfig(symbols: dict[int, Symbol], paylines: list[list[int]], reelsets: dict[str, list[list[int]]], source_text: str = "", source_path: str = "")`
  - `GameConfig.rows -> int` — число рядов окна = `max(max(line) for line in paylines) + 1`
  - `GameConfig.reels_count -> int` — `len(paylines[0])`
  - `GameConfig.id_of_kind(kind: str) -> int | None` — первый id символа данного вида
  - `GameConfig.paying_symbols() -> list[Symbol]` — символы с `kind in ('line','wild')` и непустыми `pays`

- [ ] **Step 1: Написать падающий тест**

`tests/test_model.py`:

```python
import unittest

from reelgen.model import GameConfig, Symbol


def build_game():
    symbols = {
        1: Symbol(1, "line", {3: 2, 4: 5, 5: 10}, "el_01"),
        9: Symbol(9, "wild", {3: 15, 4: 70, 5: 300}, "el_wild"),
        10: Symbol(10, "scat", {3: {"tb": 2, "fs": 8}}, "el_scatter"),
        11: Symbol(11, "bonus", {}, "el_bonus"),
    }
    paylines = [[0, 0, 0, 0, 0], [3, 2, 1, 2, 3]]
    reelsets = {"spins_1": [[1, 9, 10], [1, 1, 11], [9, 9, 1], [1, 1, 1], [10, 1, 9]]}
    return GameConfig(symbols=symbols, paylines=paylines, reelsets=reelsets)


class TestGameConfig(unittest.TestCase):
    def test_rows_is_derived_from_paylines(self):
        self.assertEqual(build_game().rows, 4)

    def test_reels_count_is_payline_length(self):
        self.assertEqual(build_game().reels_count, 5)

    def test_id_of_kind_finds_special_symbols(self):
        game = build_game()
        self.assertEqual(game.id_of_kind("wild"), 9)
        self.assertEqual(game.id_of_kind("scat"), 10)
        self.assertEqual(game.id_of_kind("bonus"), 11)
        self.assertIsNone(game.id_of_kind("hide"))

    def test_paying_symbols_excludes_scat_and_bonus(self):
        ids = [s.id for s in build_game().paying_symbols()]
        self.assertEqual(ids, [1, 9])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `python3 -m unittest tests.test_model -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reelgen.model'`

- [ ] **Step 3: Реализация**

`reelgen/__init__.py` — пустой файл.

`reelgen/model.py`:

```python
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
```

- [ ] **Step 4: Тесты зелёные**

Run: `python3 -m unittest tests.test_model -v`
Expected: PASS, 4 теста

- [ ] **Step 5: Checkpoint**

Run: `python3 -m unittest discover -s tests -t . -v`
Expected: всё зелёное

---

### Task 2: Парсинг формата игры

**Files:**
- Create: `reelgen/gameio.py`
- Test: `tests/test_gameio_parse.py`

**Interfaces:**
- Consumes: `reelgen.model.Symbol`, `reelgen.model.GameConfig`
- Produces:
  - `parse_text(text: str, path: str = "") -> GameConfig`
  - `parse_file(path: str | Path) -> GameConfig`
  - `ParseError(Exception)`

- [ ] **Step 1: Написать падающий тест**

`tests/test_gameio_parse.py`:

```python
import unittest
from pathlib import Path

from reelgen.gameio import ParseError, parse_file, parse_text

FIXTURE = Path(__file__).parent / "fixtures" / "sample_game.py"


class TestParse(unittest.TestCase):
    def setUp(self):
        self.game = parse_file(FIXTURE)

    def test_parses_all_twelve_symbols(self):
        self.assertEqual(sorted(self.game.symbols), list(range(1, 13)))

    def test_symbol_fields(self):
        s5 = self.game.symbols[5]
        self.assertEqual(s5.kind, "line")
        self.assertEqual(s5.pays, {3: 5, 4: 25, 5: 50})
        self.assertEqual(s5.asset, "el_05")

    def test_scatter_pays_keep_nested_dict(self):
        self.assertEqual(self.game.symbols[10].pays, {3: {"tb": 2, "fs": 8}})

    def test_empty_pays_stay_empty(self):
        self.assertEqual(self.game.symbols[11].pays, {})

    def test_parses_twenty_paylines_in_order(self):
        self.assertEqual(len(self.game.paylines), 20)
        self.assertEqual(self.game.paylines[0], [0, 0, 0, 0, 0])
        self.assertEqual(self.game.paylines[19], [3, 2, 2, 2, 3])

    def test_parses_reelsets_in_file_order(self):
        self.assertEqual(list(self.game.reelsets), ["spins_1", "freespins_0"])

    def test_reelset_shape_and_content(self):
        reels = self.game.reelsets["spins_1"]
        self.assertEqual(len(reels), 5)
        self.assertTrue(all(len(r) == 40 for r in reels))
        self.assertEqual(reels[0][:5], [5, 5, 5, 5, 1])

    def test_source_text_is_kept_for_export(self):
        self.assertIn("reels_spins_1", self.game.source_text)

    def test_bad_symbol_line_raises(self):
        with self.assertRaises(ParseError):
            parse_text("symbol_01 = 'line', {3: 2}\n")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `python3 -m unittest tests.test_gameio_parse -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reelgen.gameio'`

- [ ] **Step 3: Реализация**

`reelgen/gameio.py`:

```python
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
```

- [ ] **Step 4: Тесты зелёные**

Run: `python3 -m unittest tests.test_gameio_parse -v`
Expected: PASS, 9 тестов

- [ ] **Step 5: Checkpoint**

Run: `python3 -m unittest discover -s tests -t . -v`

---

### Task 3: Экспорт лент обратно в файл игры

**Files:**
- Modify: `reelgen/gameio.py` (дописать функции экспорта)
- Test: `tests/test_gameio_export.py`

**Interfaces:**
- Consumes: `parse_text`, `GameConfig`
- Produces:
  - `render_reelset(reels: list[list[int]]) -> str` — тело блока между `'''`, с ведущим и завершающим переводом строки
  - `export_text(source_text: str, reelsets: dict[str, list[list[int]]]) -> str` — заменяет содержимое существующих блоков `reels_<name>`, остальной текст не трогает

- [ ] **Step 1: Написать падающий тест**

`tests/test_gameio_export.py`:

```python
import unittest
from pathlib import Path

from reelgen.gameio import export_text, parse_file, parse_text, render_reelset

FIXTURE = Path(__file__).parent / "fixtures" / "sample_game.py"


class TestExport(unittest.TestCase):
    def setUp(self):
        self.game = parse_file(FIXTURE)

    def test_render_reelset_is_space_separated_lines(self):
        body = render_reelset([[1, 2, 3], [9, 9, 10]])
        self.assertEqual(body, "\n1 2 3\n9 9 10\n")

    def test_round_trip_without_changes_is_identical(self):
        out = export_text(self.game.source_text, self.game.reelsets)
        self.assertEqual(out, self.game.source_text)

    def test_replacing_one_reelset_leaves_the_other_alone(self):
        new = dict(self.game.reelsets)
        new["spins_1"] = [[1] * 4 for _ in range(5)]
        out = export_text(self.game.source_text, new)
        reparsed = parse_text(out)
        self.assertEqual(reparsed.reelsets["spins_1"], [[1] * 4 for _ in range(5)])
        self.assertEqual(
            reparsed.reelsets["freespins_0"], self.game.reelsets["freespins_0"]
        )

    def test_symbols_and_paylines_survive_export(self):
        out = export_text(self.game.source_text, self.game.reelsets)
        reparsed = parse_text(out)
        self.assertEqual(reparsed.symbols, self.game.symbols)
        self.assertEqual(reparsed.paylines, self.game.paylines)

    def test_unknown_reelset_name_is_ignored(self):
        out = export_text(self.game.source_text, {"nope": [[1]]})
        self.assertEqual(out, self.game.source_text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `python3 -m unittest tests.test_gameio_export -v`
Expected: FAIL — `ImportError: cannot import name 'export_text'`

- [ ] **Step 3: Реализация**

Дописать в конец `reelgen/gameio.py`:

```python
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
```

- [ ] **Step 4: Тесты зелёные**

Run: `python3 -m unittest tests.test_gameio_export -v`
Expected: PASS, 6 тестов

Замечание: `test_round_trip_without_changes_is_identical` проверяет, что `render_reelset` даёт ровно тот формат, что в фикстуре (`'''\n<строки>\n'''`). Если тест упал на лишнем/недостающем переводе строки — чинить `render_reelset`, а не подгонять фикстуру.

- [ ] **Step 5: Checkpoint**

Run: `python3 -m unittest discover -s tests -t . -v`

---

### Task 4: Картинки символов

**Files:**
- Create: `reelgen/images.py`
- Test: `tests/test_images.py`

**Interfaces:**
- Consumes: ничего
- Produces:
  - `IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}`
  - `scan_folder(folder: str | Path) -> dict[int, list[str]]` — id → отсортированные имена файлов
  - `auto_map(folder: str | Path) -> dict[int, str]` — id → первое имя файла по алфавиту
  - `id_from_name(name: str) -> int | None` — первое целое число в имени файла

- [ ] **Step 1: Написать падающий тест**

`tests/test_images.py`:

```python
import tempfile
import unittest
from pathlib import Path

from reelgen.images import auto_map, id_from_name, scan_folder


class TestImages(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name)
        for name in [
            "sym1.png",
            "sym10.png",
            "sym11_1.png",
            "sym11_2.png",
            "sym2.png",
            "readme.txt",
            "background.png",
        ]:
            (self.path / name).write_bytes(b"")

    def tearDown(self):
        self.dir.cleanup()

    def test_id_from_name_takes_first_number(self):
        self.assertEqual(id_from_name("sym11_2.png"), 11)
        self.assertEqual(id_from_name("sym1.png"), 1)
        self.assertIsNone(id_from_name("background.png"))

    def test_scan_groups_variants_under_one_id(self):
        found = scan_folder(self.path)
        self.assertEqual(found[11], ["sym11_1.png", "sym11_2.png"])
        self.assertEqual(found[1], ["sym1.png"])

    def test_scan_ignores_non_images_and_nameless_files(self):
        found = scan_folder(self.path)
        self.assertNotIn(None, found)
        self.assertEqual(sorted(found), [1, 2, 10, 11])

    def test_auto_map_picks_first_variant(self):
        self.assertEqual(auto_map(self.path)[11], "sym11_1.png")

    def test_missing_folder_gives_empty_map(self):
        self.assertEqual(scan_folder(self.path / "nope"), {})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `python3 -m unittest tests.test_images -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reelgen.images'`

- [ ] **Step 3: Реализация**

`reelgen/images.py`:

```python
"""Поиск картинок символов в папке и маппинг на id по числу в имени файла."""

import re
from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_NUM_RE = re.compile(r"\d+")


def id_from_name(name: str) -> int | None:
    """Первое целое число в имени файла — считаем его id символа."""
    match = _NUM_RE.search(Path(name).stem)
    return int(match.group(0)) if match else None


def scan_folder(folder: str | Path) -> dict[int, list[str]]:
    """id символа → отсортированный список имён файлов-картинок."""
    folder = Path(folder)
    if not folder.is_dir():
        return {}
    found: dict[int, list[str]] = {}
    for entry in sorted(folder.iterdir()):
        if not entry.is_file() or entry.suffix.lower() not in IMAGE_EXTS:
            continue
        sid = id_from_name(entry.name)
        if sid is None:
            continue
        found.setdefault(sid, []).append(entry.name)
    return found


def auto_map(folder: str | Path) -> dict[int, str]:
    """id символа → одно имя файла (первое по алфавиту)."""
    return {sid: names[0] for sid, names in scan_folder(folder).items()}
```

- [ ] **Step 4: Тесты зелёные**

Run: `python3 -m unittest tests.test_images -v`
Expected: PASS, 5 тестов

- [ ] **Step 5: Checkpoint**

Run: `python3 -m unittest discover -s tests -t . -v`

---

### Task 5: Правила и проверка нарушений

**Files:**
- Create: `reelgen/rules.py`
- Test: `tests/test_rules.py`

**Interfaces:**
- Consumes: `reelgen.model.GameConfig`
- Produces:
  - Константы классов: `LOW = "low"`, `MIDDLE = "middle"`, `HIGH = "high"`, `SPECIAL = "special"`, `CLASSES = (LOW, MIDDLE, HIGH, SPECIAL)`
  - `Block(symbol_id: int, start: int, size: int)` — frozen dataclass
  - `StackRule(symbol_id: int, count: int, sizes: dict[int, float])`
  - `DistanceRule(a: str, b: str, min_gap: int, filler: str | None = None)` — селектор `a`/`b` в виде `"class:special"` или `"id:10"`
  - `ReelRules(stacks: list[StackRule], distances: list[DistanceRule])` с `.length -> int` (сумма count)
  - `RuleSet(classes: dict[int, str], reels: dict[str, list[ReelRules]])`
  - `default_classes(game: GameConfig) -> dict[int, str]`
  - `blocks_of(strip: list[int]) -> list[Block]` — блоки в порядке кольца, слипание через стык учтено
  - `matches(selector: str, symbol_id: int, classes: dict[int, str]) -> bool`
  - `Violation(rule_index: int, a: Block, b: Block, gap: int, filler_count: int, deficit: int)`
  - `violations(strip, distances, classes) -> list[Violation]`
  - `penalty(strip, distances, classes) -> int` — сумма `deficit`
  - `gap_between(a: Block, b: Block, length: int) -> tuple[int, int]` — `(позиция начала промежутка, длина промежутка)`

- [ ] **Step 1: Написать падающий тест**

`tests/test_rules.py`:

```python
import unittest

from reelgen.rules import (
    Block,
    DistanceRule,
    ReelRules,
    StackRule,
    blocks_of,
    default_classes,
    matches,
    penalty,
    violations,
)
from reelgen.gameio import parse_file
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "sample_game.py"

# 1 = low, 5 = middle, 7 = high, 10 = special
CLASSES = {1: "low", 2: "low", 5: "middle", 7: "high", 10: "special"}


class TestBlocks(unittest.TestCase):
    def test_splits_runs(self):
        self.assertEqual(
            blocks_of([1, 1, 2, 5, 5, 5]),
            [Block(1, 0, 2), Block(2, 2, 1), Block(5, 3, 3)],
        )

    def test_merges_across_the_seam(self):
        # хвост и голова — один и тот же символ, это один блок через стык
        self.assertEqual(
            blocks_of([1, 2, 2, 1, 1]),
            [Block(2, 1, 2), Block(1, 3, 3)],
        )

    def test_uniform_strip_is_one_block(self):
        self.assertEqual(blocks_of([7, 7, 7]), [Block(7, 0, 3)])

    def test_empty_strip(self):
        self.assertEqual(blocks_of([]), [])


class TestMatches(unittest.TestCase):
    def test_class_selector(self):
        self.assertTrue(matches("class:special", 10, CLASSES))
        self.assertFalse(matches("class:special", 1, CLASSES))

    def test_id_selector(self):
        self.assertTrue(matches("id:10", 10, CLASSES))
        self.assertFalse(matches("id:10", 7, CLASSES))


class TestViolations(unittest.TestCase):
    def test_two_specials_too_close(self):
        strip = [10, 1, 1, 10, 1, 1, 1, 1, 1, 1]
        rule = DistanceRule("class:special", "class:special", 5)
        found = violations(strip, [rule], CLASSES)
        # одна пара нарушена (промежуток 2 < 5), вторая через стык — 6, в норме
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].gap, 2)
        self.assertEqual(found[0].deficit, 3)

    def test_specials_far_enough_pass(self):
        strip = [10, 1, 1, 1, 1, 1, 10, 1, 1, 1, 1, 1]
        rule = DistanceRule("class:special", "class:special", 5)
        self.assertEqual(violations(strip, [rule], CLASSES), [])

    def test_seam_gap_is_measured_through_the_wrap(self):
        # блоки на позициях 0 и 8: слева между ними 7, через стык — всего 1
        strip = [10, 1, 1, 1, 1, 1, 1, 1, 10, 1]
        rule = DistanceRule("class:special", "class:special", 5)
        found = violations(strip, [rule], CLASSES)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].gap, 1)
        self.assertEqual(found[0].deficit, 4)

    def test_head_and_tail_of_one_symbol_are_a_single_block(self):
        # хвост и голова слиплись через стык — это один блок, нарушать нечего
        strip = [10, 1, 1, 1, 1, 1, 1, 1, 1, 10]
        rule = DistanceRule("class:special", "class:special", 5)
        self.assertEqual(violations(strip, [rule], CLASSES), [])

    def test_single_matching_block_never_violates(self):
        strip = [10, 1, 1, 1]
        rule = DistanceRule("class:special", "class:special", 5)
        self.assertEqual(violations(strip, [rule], CLASSES), [])

    def test_filler_must_be_present_in_the_gap(self):
        # между special и middle два символа, но это high, а не low
        strip = [10, 7, 7, 5, 1, 1, 1, 1, 1, 1]
        rule = DistanceRule("class:special", "class:middle", 2, filler="low")
        found = violations(strip, [rule], CLASSES)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].gap, 2)
        self.assertEqual(found[0].filler_count, 0)
        self.assertEqual(found[0].deficit, 2)

    def test_filler_present_passes(self):
        strip = [10, 1, 1, 5, 1, 1, 1, 1, 1, 1]
        rule = DistanceRule("class:special", "class:middle", 2, filler="low")
        self.assertEqual(violations(strip, [rule], CLASSES), [])

    def test_gap_longer_than_n_may_contain_anything(self):
        # промежуток 5, из них два low — требование «не меньше двух low» выполнено
        strip = [10, 7, 1, 7, 1, 7, 5, 1, 1, 1, 1, 1]
        rule = DistanceRule("class:special", "class:middle", 2, filler="low")
        self.assertEqual(violations(strip, [rule], CLASSES), [])

    def test_only_nearest_pairs_are_checked(self):
        # special .. middle . middle: между двумя middle всего один low, но пара
        # middle↔middle правилом не описана, а дальняя пара special↔второй middle
        # не проверяется, потому что между ними стоит другой middle
        strip = [10, 1, 1, 5, 1, 5, 1, 1, 1, 1, 1, 1]
        rule = DistanceRule("class:special", "class:middle", 2, filler="low")
        self.assertEqual(violations(strip, [rule], CLASSES), [])

    def test_penalty_sums_deficits(self):
        strip = [10, 1, 10, 1, 10, 1, 1, 1, 1, 1]
        rule = DistanceRule("class:special", "class:special", 4)
        self.assertEqual(penalty(strip, [rule], CLASSES), 3 + 3 + 0)


class TestDefaults(unittest.TestCase):
    def test_default_classes_from_paytable(self):
        classes = default_classes(parse_file(FIXTURE))
        self.assertEqual(classes[1], "low")
        self.assertEqual(classes[4], "low")
        self.assertEqual(classes[5], "middle")
        self.assertEqual(classes[6], "middle")
        self.assertEqual(classes[7], "high")
        self.assertEqual(classes[8], "high")
        self.assertEqual(classes[9], "special")
        self.assertEqual(classes[12], "special")


class TestReelRules(unittest.TestCase):
    def test_length_is_sum_of_counts(self):
        rules = ReelRules(
            stacks=[StackRule(1, 10, {1: 100.0}), StackRule(5, 6, {2: 100.0})],
            distances=[],
        )
        self.assertEqual(rules.length, 16)


if __name__ == "__main__":
    unittest.main()
```

Проверка ожидаемых чисел в `test_penalty_sums_deficits`: лента длины 10, блоки special на позициях 0, 2, 4. Промежутки по кольцу: 0→2 = 1, 2→4 = 1, 4→0 = 5. При `min_gap=4` дефициты 3, 3, 0 → сумма 6. Ожидание в тесте записано как `3 + 3 + 0`.

- [ ] **Step 2: Убедиться, что тест падает**

Run: `python3 -m unittest tests.test_rules -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reelgen.rules'`

- [ ] **Step 3: Реализация**

`reelgen/rules.py`:

```python
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
                found.append(
                    Violation(index, left, right, gap, filler_count, deficit)
                )
    return found


def penalty(
    strip: list[int], distances: list[DistanceRule], classes: dict[int, str]
) -> int:
    return sum(v.deficit for v in violations(strip, distances, classes))
```

- [ ] **Step 4: Тесты зелёные**

Run: `python3 -m unittest tests.test_rules -v`
Expected: PASS, 19 тестов

- [ ] **Step 5: Checkpoint**

Run: `python3 -m unittest discover -s tests -t . -v`

---

### Task 6: Диагностика невыполнимых правил

**Files:**
- Create: `reelgen/feasibility.py`
- Test: `tests/test_feasibility.py`

**Interfaces:**
- Consumes: `ReelRules`, `DistanceRule`, `StackRule`, `matches`, `CLASSES`
- Produces:
  - `Problem(kind: str, message: str)` — frozen dataclass; `kind` ∈ `{"stack", "distance", "filler"}`
  - `check_reel(rules: ReelRules, classes: dict[int, str]) -> list[Problem]`

Проверки, все — гарантированные нижние границы, ложных срабатываний быть не должно:

1. `stack` — у символа с `count > 0` пустые `sizes`, неположительные веса, либо минимальный разрешённый размер стека больше `count`.
2. `distance` — правило с одинаковыми селекторами (`a == b`). Пусть символы, подходящие под селектор, дают суммарно `C` символов, а максимальный разрешённый размер стека среди них — `m`. Тогда блоков будет не меньше `K = ceil(C / m)`, и нужно не меньше `C + K * min_gap` позиций. Если это больше длины ленты — невыполнимо.
3. `filler` — правило требует наполнитель класса `F`, на риле есть символы под `a` и под `b`, но символов класса `F` на риле ноль.

- [ ] **Step 1: Написать падающий тест**

`tests/test_feasibility.py`:

```python
import unittest

from reelgen.feasibility import check_reel
from reelgen.rules import DistanceRule, ReelRules, StackRule

CLASSES = {1: "low", 2: "low", 5: "middle", 10: "special", 11: "special"}


class TestFeasibility(unittest.TestCase):
    def test_clean_rules_have_no_problems(self):
        rules = ReelRules(
            stacks=[StackRule(1, 80, {1: 100.0}), StackRule(10, 4, {1: 100.0})],
            distances=[DistanceRule("class:special", "class:special", 5)],
        )
        self.assertEqual(check_reel(rules, CLASSES), [])

    def test_too_many_specials_for_the_distance(self):
        # 12 одиночных стеков special при дистанции 5 требуют 12 + 60 = 72 позиции
        rules = ReelRules(
            stacks=[StackRule(1, 30, {1: 100.0}), StackRule(10, 12, {1: 100.0})],
            distances=[DistanceRule("class:special", "class:special", 5)],
        )
        problems = check_reel(rules, CLASSES)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0].kind, "distance")
        self.assertIn("72", problems[0].message)
        self.assertIn("42", problems[0].message)

    def test_big_stacks_reduce_the_requirement(self):
        # те же 12 special, но стеками по 4 — это 3 блока, нужно 12 + 15 = 27
        rules = ReelRules(
            stacks=[StackRule(1, 30, {4: 100.0}), StackRule(10, 12, {4: 100.0})],
            distances=[DistanceRule("class:special", "class:special", 5)],
        )
        self.assertEqual(check_reel(rules, CLASSES), [])

    def test_missing_filler_class(self):
        rules = ReelRules(
            stacks=[StackRule(5, 10, {1: 100.0}), StackRule(10, 4, {1: 100.0})],
            distances=[
                DistanceRule("class:special", "class:middle", 2, filler="low")
            ],
        )
        problems = check_reel(rules, CLASSES)
        self.assertEqual([p.kind for p in problems], ["filler"])
        self.assertIn("low", problems[0].message)

    def test_stack_size_larger_than_count(self):
        rules = ReelRules(stacks=[StackRule(10, 2, {4: 100.0})], distances=[])
        problems = check_reel(rules, CLASSES)
        self.assertEqual([p.kind for p in problems], ["stack"])

    def test_empty_sizes(self):
        rules = ReelRules(stacks=[StackRule(10, 2, {})], distances=[])
        self.assertEqual([p.kind for p in check_reel(rules, CLASSES)], ["stack"])

    def test_zero_count_symbol_is_not_a_problem(self):
        rules = ReelRules(
            stacks=[StackRule(1, 10, {1: 100.0}), StackRule(10, 0, {})], distances=[]
        )
        self.assertEqual(check_reel(rules, CLASSES), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `python3 -m unittest tests.test_feasibility -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reelgen.feasibility'`

- [ ] **Step 3: Реализация**

`reelgen/feasibility.py`:

```python
"""Проверка правил на заведомую невыполнимость до запуска генерации.

Все проверки — гарантированные нижние границы: если тут пусто, генерация
всё ещё может не сойтись, но если тут что-то есть — она точно не сойдётся.
"""

import math
from dataclasses import dataclass

from .rules import DistanceRule, ReelRules, matches


@dataclass(frozen=True)
class Problem:
    kind: str
    message: str


def _selector_symbols(selector: str, rules: ReelRules, classes) -> list:
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
    index: int, rule: DistanceRule, rules: ReelRules, classes
) -> Problem | None:
    if rule.a != rule.b:
        return None
    stacks = _selector_symbols(rule.a, rules, classes)
    if not stacks:
        return None
    total = sum(stack.count for stack in stacks)
    max_size = max(
        (size for stack in stacks for size, weight in stack.sizes.items() if weight > 0),
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


def _check_filler(index: int, rule: DistanceRule, rules: ReelRules, classes):
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
    for index, rule in enumerate(rules.distances):
        problem = _check_self_distance(index, rule, rules, classes)
        if problem:
            problems.append(problem)
        problem = _check_filler(index, rule, rules, classes)
        if problem:
            problems.append(problem)
    return problems
```

- [ ] **Step 4: Тесты зелёные**

Run: `python3 -m unittest tests.test_feasibility -v`
Expected: PASS, 7 тестов

Проверка чисел в `test_too_many_specials_for_the_distance`: длина ленты = 30 + 12 = 42; 12 special одиночными стеками → 12 блоков → нужно 12 + 12×5 = 72 > 42. Сообщение содержит и 72, и 42.

- [ ] **Step 5: Checkpoint**

Run: `python3 -m unittest discover -s tests -t . -v`

---

### Task 7: Сборка стеков

**Files:**
- Create: `reelgen/generate.py`
- Test: `tests/test_assemble.py`

**Interfaces:**
- Consumes: `StackRule`
- Produces:
  - `assemble_sizes(stack: StackRule, rng: random.Random) -> list[int]` — размеры стеков, сумма ровно `stack.count`

Правило разрешения конфликта: размеры тянутся по весам, пока не наберётся `count`; если очередной размер не влезает в остаток — он подрезается до остатка.

- [ ] **Step 1: Написать падающий тест**

`tests/test_assemble.py`:

```python
import random
import unittest
from collections import Counter

from reelgen.generate import assemble_sizes
from reelgen.rules import StackRule


class TestAssemble(unittest.TestCase):
    def test_sum_is_always_exactly_the_count(self):
        for seed in range(50):
            rng = random.Random(seed)
            sizes = assemble_sizes(StackRule(5, 17, {1: 20.0, 2: 50.0, 3: 30.0}), rng)
            self.assertEqual(sum(sizes), 17)

    def test_single_size_only(self):
        rng = random.Random(0)
        self.assertEqual(assemble_sizes(StackRule(5, 8, {2: 100.0}), rng), [2, 2, 2, 2])

    def test_last_stack_is_trimmed_to_the_remainder(self):
        rng = random.Random(0)
        sizes = assemble_sizes(StackRule(5, 7, {3: 100.0}), rng)
        self.assertEqual(sizes, [3, 3, 1])

    def test_zero_count_gives_nothing(self):
        self.assertEqual(assemble_sizes(StackRule(5, 0, {1: 100.0}), random.Random(0)), [])

    def test_weights_are_respected_roughly(self):
        rng = random.Random(7)
        counts = Counter()
        for _ in range(400):
            counts.update(assemble_sizes(StackRule(5, 60, {1: 10.0, 4: 90.0}), rng))
        # четвёрок должно быть заметно больше единиц
        self.assertGreater(counts[4], counts[1])

    def test_same_seed_gives_same_result(self):
        a = assemble_sizes(StackRule(5, 20, {1: 30.0, 2: 40.0, 3: 30.0}), random.Random(3))
        b = assemble_sizes(StackRule(5, 20, {1: 30.0, 2: 40.0, 3: 30.0}), random.Random(3))
        self.assertEqual(a, b)

    def test_sizes_with_zero_weight_are_skipped(self):
        rng = random.Random(1)
        sizes = assemble_sizes(StackRule(5, 6, {1: 0.0, 3: 100.0}), rng)
        self.assertEqual(sizes, [3, 3])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `python3 -m unittest tests.test_assemble -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reelgen.generate'`

- [ ] **Step 3: Реализация**

`reelgen/generate.py` (начало файла, остальное допишется в Task 8):

```python
"""Генерация лент: сборка стеков, жадная укладка, локальный поиск."""

import random
import time
from dataclasses import dataclass, field

from .rules import (
    Block,
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
    """Размеры стеков для символа. Сумма всегда ровно stack.count."""
    if stack.count <= 0:
        return []
    options = [(size, weight) for size, weight in stack.sizes.items() if weight > 0]
    if not options:
        return [1] * stack.count

    sizes = [size for size, _ in options]
    weights = [weight for _, weight in options]

    result: list[int] = []
    left = stack.count
    while left > 0:
        size = rng.choices(sizes, weights=weights, k=1)[0]
        size = min(size, left)
        result.append(size)
        left -= size
    return result
```

- [ ] **Step 4: Тесты зелёные**

Run: `python3 -m unittest tests.test_assemble -v`
Expected: PASS, 7 тестов

- [ ] **Step 5: Checkpoint**

Run: `python3 -m unittest discover -s tests -t . -v`

---

### Task 8: Движок — жадная укладка и repair

**Files:**
- Modify: `reelgen/generate.py` (дописать после `assemble_sizes`)
- Test: `tests/test_generate.py`

**Interfaces:**
- Consumes: `assemble_sizes`, `ReelRules`, `DistanceRule`, `violations`, `penalty`, `blocks_of`, `matches`
- Produces:
  - `GenResult(strip: list[int], seed: int, stage: str, attempts: int, violations: list[Violation], stack_actual: dict[int, dict[int, int]])`, `stage` ∈ `{"greedy", "repair", "failed"}`
  - `generate_reel(rules: ReelRules, classes: dict[int, str], seed: int, greedy_attempts: int = 200, repair_seconds: float = 8.0) -> GenResult`
  - `generate_reelset(reel_rules: list[ReelRules], classes: dict[int, str], seed: int, **kwargs) -> list[GenResult]` — рил `i` получает сид `seed * 1000 + i`, чтобы один сид воспроизводил весь рилсет

Ключевое свойство жадной укладки: блок дописывается только в конец, поэтому промежуток между ним и предыдущим подходящим блоком уже окончателен — проверка задним числом ничего не ломает.

- [ ] **Step 1: Написать падающий тест**

`tests/test_generate.py`:

```python
import unittest
from collections import Counter

from reelgen.generate import GenResult, generate_reel, generate_reelset
from reelgen.rules import DistanceRule, ReelRules, StackRule, violations

CLASSES = {1: "low", 2: "low", 5: "middle", 7: "high", 10: "special", 11: "special"}


def easy_rules():
    return ReelRules(
        stacks=[
            StackRule(1, 40, {1: 60.0, 2: 40.0}),
            StackRule(5, 12, {1: 50.0, 3: 50.0}),
            StackRule(10, 5, {1: 100.0}),
        ],
        distances=[DistanceRule("class:special", "class:special", 6)],
    )


class TestGenerateReel(unittest.TestCase):
    def test_counts_match_exactly(self):
        result = generate_reel(easy_rules(), CLASSES, seed=1)
        counts = Counter(result.strip)
        self.assertEqual(counts[1], 40)
        self.assertEqual(counts[5], 12)
        self.assertEqual(counts[10], 5)

    def test_length_is_sum_of_counts(self):
        result = generate_reel(easy_rules(), CLASSES, seed=1)
        self.assertEqual(len(result.strip), 57)

    def test_no_violations_on_solvable_rules(self):
        result = generate_reel(easy_rules(), CLASSES, seed=1)
        self.assertEqual(result.violations, [])
        self.assertIn(result.stage, ("greedy", "repair"))

    def test_result_really_satisfies_the_rules(self):
        rules = easy_rules()
        result = generate_reel(rules, CLASSES, seed=2)
        self.assertEqual(violations(result.strip, rules.distances, CLASSES), [])

    def test_same_seed_gives_the_same_strip(self):
        a = generate_reel(easy_rules(), CLASSES, seed=42)
        b = generate_reel(easy_rules(), CLASSES, seed=42)
        self.assertEqual(a.strip, b.strip)

    def test_different_seeds_give_different_strips(self):
        a = generate_reel(easy_rules(), CLASSES, seed=1)
        b = generate_reel(easy_rules(), CLASSES, seed=2)
        self.assertNotEqual(a.strip, b.strip)

    def test_stack_actual_reports_what_was_built(self):
        result = generate_reel(easy_rules(), CLASSES, seed=1)
        by_size = result.stack_actual[10]
        self.assertEqual(sum(size * n for size, n in by_size.items()), 5)

    def test_filler_rule_is_honoured(self):
        rules = ReelRules(
            stacks=[
                StackRule(1, 40, {1: 100.0}),
                StackRule(5, 8, {1: 100.0}),
                StackRule(10, 4, {1: 100.0}),
            ],
            distances=[
                DistanceRule("class:special", "class:middle", 2, filler="low"),
                DistanceRule("class:special", "class:special", 5),
            ],
        )
        result = generate_reel(rules, CLASSES, seed=5)
        self.assertEqual(result.violations, [])

    def test_impossible_rules_report_failure_not_a_crash(self):
        rules = ReelRules(
            stacks=[StackRule(1, 6, {1: 100.0}), StackRule(10, 6, {1: 100.0})],
            distances=[DistanceRule("class:special", "class:special", 5)],
        )
        result = generate_reel(rules, CLASSES, seed=1, greedy_attempts=5, repair_seconds=0.5)
        self.assertEqual(result.stage, "failed")
        self.assertTrue(result.violations)
        self.assertEqual(len(result.strip), 12)
        self.assertEqual(Counter(result.strip)[10], 6)

    def test_empty_rules_give_empty_strip(self):
        result = generate_reel(ReelRules(), CLASSES, seed=1)
        self.assertEqual(result.strip, [])
        self.assertEqual(result.stage, "greedy")


class TestGenerateReelset(unittest.TestCase):
    def test_five_reels_are_generated(self):
        results = generate_reelset([easy_rules() for _ in range(5)], CLASSES, seed=9)
        self.assertEqual(len(results), 5)
        self.assertTrue(all(isinstance(r, GenResult) for r in results))

    def test_reels_differ_from_each_other(self):
        results = generate_reelset([easy_rules() for _ in range(5)], CLASSES, seed=9)
        strips = [tuple(r.strip) for r in results]
        self.assertEqual(len(set(strips)), 5)

    def test_reelset_is_reproducible(self):
        first = generate_reelset([easy_rules() for _ in range(5)], CLASSES, seed=9)
        second = generate_reelset([easy_rules() for _ in range(5)], CLASSES, seed=9)
        self.assertEqual([r.strip for r in first], [r.strip for r in second])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `python3 -m unittest tests.test_generate -v`
Expected: FAIL — `ImportError: cannot import name 'generate_reel'`

- [ ] **Step 3: Реализация**

Дописать в `reelgen/generate.py`:

```python
@dataclass
class GenResult:
    """Результат генерации одного рила."""

    strip: list[int] = field(default_factory=list)
    seed: int = 0
    stage: str = "greedy"
    attempts: int = 0
    violations: list[Violation] = field(default_factory=list)
    stack_actual: dict[int, dict[int, int]] = field(default_factory=dict)


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
        actual.setdefault(block.symbol_id, {})
        actual[block.symbol_id][block.size] = (
            actual[block.symbol_id].get(block.size, 0) + 1
        )
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
    # для каждого правила — последний уложенный блок, подходящий под a или b
    last_rel: dict[int, tuple[int, int, int]] = {}  # rule_index -> (sym, start, size)
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
            (item, remaining[item] * item[1])
            for item, count in remaining.items()
            if count > 0
        ]
        candidates = []
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
            start = len(strip)
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
                if not _pair_ok(rule, classes, strip + [symbol_id] * size, gap_start, gap):
                    ok = False
                    break
            if not ok:
                continue

            order.append(item)
            strip.extend([symbol_id] * size)
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

    # замыкаем кольцо
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


def _repair(
    blocks: list[tuple[int, int]],
    rules: ReelRules,
    classes: dict[int, str],
    rng: random.Random,
    seconds: float,
) -> tuple[list[int], int]:
    """Локальный поиск свопами. Возвращает (лента, штраф)."""
    order = list(blocks)
    rng.shuffle(order)
    strip = _expand(order)
    score = penalty(strip, rules.distances, classes)
    if score == 0 or len(order) < 2:
        return strip, score

    best_strip, best_score = strip, score
    deadline = time.monotonic() + seconds
    stall = 0

    while score > 0 and time.monotonic() < deadline:
        i, j = rng.randrange(len(order)), rng.randrange(len(order))
        if i == j:
            continue
        order[i], order[j] = order[j], order[i]
        candidate = _expand(order)
        candidate_score = penalty(candidate, rules.distances, classes)

        if candidate_score <= score:
            if candidate_score == score:
                stall += 1
            else:
                stall = 0
            score = candidate_score
            strip = candidate
            if score < best_score:
                best_strip, best_score = strip, score
        else:
            order[i], order[j] = order[j], order[i]
            stall += 1

        if stall > 300:
            # выбиваемся с плато случайной перетасовкой части блоков
            cut = rng.randrange(1, len(order))
            order = order[cut:] + order[:cut]
            rng.shuffle(order)
            strip = _expand(order)
            score = penalty(strip, rules.distances, classes)
            stall = 0

    if score < best_score:
        best_strip, best_score = strip, score
    return best_strip, best_score


def generate_reel(
    rules: ReelRules,
    classes: dict[int, str],
    seed: int,
    greedy_attempts: int = 200,
    repair_seconds: float = 8.0,
) -> GenResult:
    """Сгенерировать одну ленту. Стадии: жадная укладка → repair → failed."""
    rng = random.Random(seed)
    blocks = _build_blocks(rules, rng)
    if not blocks:
        return GenResult(strip=[], seed=seed, stage="greedy", attempts=0)

    for attempt in range(1, greedy_attempts + 1):
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
            )

    strip, score = _repair(blocks, rules, classes, rng, repair_seconds)
    left = violations(strip, rules.distances, classes)
    return GenResult(
        strip=strip,
        seed=seed,
        stage="repair" if score == 0 else "failed",
        attempts=greedy_attempts,
        violations=left,
        stack_actual=_stack_actual(strip),
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
```

- [ ] **Step 4: Тесты зелёные**

Run: `python3 -m unittest tests.test_generate -v`
Expected: PASS, 13 тестов

Если `test_no_violations_on_solvable_rules` падает — сначала проверить, что `_greedy_once` действительно замыкает кольцо, и только потом трогать параметры. Если тесты идут дольше 30 секунд — уменьшить `repair_seconds` в самих тестах, а не в дефолте.

- [ ] **Step 5: Checkpoint**

Run: `python3 -m unittest discover -s tests -t . -v`

---

### Task 9: Статистика состава

**Files:**
- Create: `reelgen/stats.py`
- Test: `tests/test_stats.py`

**Interfaces:**
- Consumes: `GameConfig`, `blocks_of`
- Produces:
  - `reel_composition(strip: list[int], classes: dict[int, str], game: GameConfig) -> list[dict]` — по одной записи на присутствующий символ, отсортировано по id. Ключи: `symbol_id`, `kind`, `asset`, `symbol_class`, `count`, `share`, `stacks` (`{размер: сколько}`)
  - `reelset_composition(strips: list[list[int]], classes, game) -> dict` — `{"reels": [список composition по рилам], "totals": [сводка по всему рилсету], "lengths": [длины лент]}`

- [ ] **Step 1: Написать падающий тест**

`tests/test_stats.py`:

```python
import unittest
from pathlib import Path

from reelgen.gameio import parse_file
from reelgen.rules import default_classes
from reelgen.stats import reel_composition, reelset_composition

FIXTURE = Path(__file__).parent / "fixtures" / "sample_game.py"


class TestStats(unittest.TestCase):
    def setUp(self):
        self.game = parse_file(FIXTURE)
        self.classes = default_classes(self.game)

    def test_counts_and_shares(self):
        strip = [1, 1, 1, 5, 10, 10, 10, 10]
        rows = reel_composition(strip, self.classes, self.game)
        by_id = {row["symbol_id"]: row for row in rows}
        self.assertEqual(by_id[1]["count"], 3)
        self.assertAlmostEqual(by_id[1]["share"], 3 / 8)
        self.assertEqual(by_id[10]["count"], 4)
        self.assertAlmostEqual(by_id[10]["share"], 0.5)

    def test_rows_are_sorted_by_id_and_carry_meta(self):
        rows = reel_composition([5, 1, 10], self.classes, self.game)
        self.assertEqual([row["symbol_id"] for row in rows], [1, 5, 10])
        self.assertEqual(rows[2]["kind"], "scat")
        self.assertEqual(rows[2]["asset"], "el_scatter")
        self.assertEqual(rows[0]["symbol_class"], "low")

    def test_stack_breakdown(self):
        strip = [1, 1, 5, 1, 1, 1, 5, 5]
        rows = reel_composition(strip, self.classes, self.game)
        by_id = {row["symbol_id"]: row for row in rows}
        self.assertEqual(by_id[1]["stacks"], {2: 1, 3: 1})
        self.assertEqual(by_id[5]["stacks"], {1: 1, 2: 1})

    def test_absent_symbols_are_not_listed(self):
        rows = reel_composition([1, 1, 1], self.classes, self.game)
        self.assertEqual([row["symbol_id"] for row in rows], [1])

    def test_reelset_totals_sum_across_reels(self):
        strips = [[1, 1, 5], [1, 5, 5], [10, 10, 1]]
        report = reelset_composition(strips, self.classes, self.game)
        self.assertEqual(report["lengths"], [3, 3, 3])
        self.assertEqual(len(report["reels"]), 3)
        totals = {row["symbol_id"]: row["count"] for row in report["totals"]}
        self.assertEqual(totals, {1: 4, 5: 3, 10: 2})

    def test_empty_strip(self):
        self.assertEqual(reel_composition([], self.classes, self.game), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `python3 -m unittest tests.test_stats -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reelgen.stats'`

- [ ] **Step 3: Реализация**

`reelgen/stats.py`:

```python
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
    """Состав по каждому рилу плюс сводка по всему рилсету."""
    reels = [reel_composition(strip, classes, game) for strip in strips]
    merged: list[int] = []
    for strip in strips:
        merged.extend(strip)
    return {
        "reels": reels,
        "totals": reel_composition(merged, classes, game),
        "lengths": [len(strip) for strip in strips],
    }
```

Замечание: `totals` считает стеки по склеенной ленте, поэтому на стыках рилов стеки могут слипнуться. Для сводки это неважно — важны `count` и `share`; в UI колонку стеков в сводной таблице не показываем.

- [ ] **Step 4: Тесты зелёные**

Run: `python3 -m unittest tests.test_stats -v`
Expected: PASS, 6 тестов

- [ ] **Step 5: Checkpoint**

Run: `python3 -m unittest discover -s tests -t . -v`

---

### Task 10: Точный RTP линий

**Files:**
- Create: `reelgen/mathexact.py`
- Test: `tests/test_math_lines.py`

**Interfaces:**
- Consumes: `GameConfig`, `Symbol`
- Produces:
  - `symbol_probs(strip: list[int]) -> dict[int, float]` — вероятность символа в одной видимой ячейке
  - `line_report(strips: list[list[int]], game: GameConfig, num_lines: int | None = None) -> dict` с ключами: `rtp` (доля от общей ставки), `per_symbol` (`{id: вклад в RTP}`), `per_length` (`{3|4|5: вклад}`), `line_hit_prob`, `line_hit_one_in`

Математика. Для конкретной линии видимый символ на барабане `r` — это `strip[(stop + row) % L]`, где `stop` равномерен, значит символ равномерно выбран из всей ленты, независимо от `row`. Барабаны независимы. Отсюда: распределение по линии одинаково для **всех** линий, и `RTP = ожидаемый выигрыш одной линии / ставка на линию`.

Выигрыш линии = максимум по всем платящим символам `s` от `pay(s, k_s)`, где `k_s` — длина ведущей серии из символов `{s, wild}` слева. Вайлд участвует наравне как обычный символ со своими выплатами, поэтому `max` разрешает случай «вся линия из вайлдов» правильно и без двойного счёта.

Перебор с отсечением: идём по барабанам слева направо, храним множество ещё «живых» символов (у которых серия не прервалась) и лучший выигрыш среди уже выбывших. Как только живых не осталось — остаток барабанов на результат не влияет, ветка закрывается.

- [ ] **Step 1: Написать падающий тест**

`tests/test_math_lines.py`:

```python
import unittest

from reelgen.mathexact import line_report, symbol_probs
from reelgen.model import GameConfig, Symbol


def toy_game():
    symbols = {
        1: Symbol(1, "line", {3: 2, 4: 5, 5: 10}, "el_01"),
        8: Symbol(8, "line", {3: 8, 4: 40, 5: 100}, "el_08"),
        9: Symbol(9, "wild", {3: 15, 4: 70, 5: 300}, "el_wild"),
        10: Symbol(10, "scat", {3: {"tb": 2, "fs": 8}}, "el_scatter"),
    }
    return GameConfig(symbols=symbols, paylines=[[0, 0, 0, 0, 0]], reelsets={})


class TestSymbolProbs(unittest.TestCase):
    def test_probs_sum_to_one(self):
        probs = symbol_probs([1, 1, 8, 9])
        self.assertAlmostEqual(sum(probs.values()), 1.0)
        self.assertAlmostEqual(probs[1], 0.5)


class TestLineReport(unittest.TestCase):
    def test_no_wins_when_no_symbol_can_line_up(self):
        # символ 1 только на первых двух барабанах — серия максимум 2
        strips = [[1], [1], [8], [8], [8]]
        report = line_report(strips, toy_game(), num_lines=1)
        # зато 8 стоит на барабанах 3-5, но серия слева обрывается на первом
        self.assertAlmostEqual(report["rtp"], 0.0)

    def test_guaranteed_five_of_a_kind(self):
        strips = [[1], [1], [1], [1], [1]]
        report = line_report(strips, toy_game(), num_lines=1)
        self.assertAlmostEqual(report["rtp"], 10.0)
        self.assertAlmostEqual(report["per_symbol"][1], 10.0)
        self.assertAlmostEqual(report["per_length"][5], 10.0)
        self.assertAlmostEqual(report["line_hit_prob"], 1.0)

    def test_exact_three_of_a_kind(self):
        strips = [[1], [1], [1], [8], [8]]
        report = line_report(strips, toy_game(), num_lines=1)
        self.assertAlmostEqual(report["rtp"], 2.0)
        self.assertAlmostEqual(report["per_length"][3], 2.0)

    def test_wild_completes_the_line(self):
        strips = [[1], [9], [1], [8], [8]]
        report = line_report(strips, toy_game(), num_lines=1)
        self.assertAlmostEqual(report["rtp"], 2.0)
        self.assertAlmostEqual(report["per_symbol"][1], 2.0)

    def test_wild_run_wins_when_it_beats_the_substituted_symbol(self):
        # 9 9 9 1 1: для символа 1 серия {1,9} длиной 5 -> 10, чистый вайлд 3 -> 15
        strips = [[9], [9], [9], [1], [1]]
        report = line_report(strips, toy_game(), num_lines=1)
        self.assertAlmostEqual(report["rtp"], 15.0)
        self.assertAlmostEqual(report["per_symbol"][9], 15.0)

    def test_line_of_only_wilds_pays_the_wild_five(self):
        strips = [[9], [9], [9], [9], [9]]
        report = line_report(strips, toy_game(), num_lines=1)
        self.assertAlmostEqual(report["rtp"], 300.0)
        self.assertAlmostEqual(report["per_symbol"][9], 300.0)

    def test_shorter_high_symbol_beats_longer_low_one(self):
        # 8 8 8 8 -> 40, а 1 не выстраивается вовсе; проверяем, что берётся max
        strips = [[8], [8], [8], [8], [1]]
        report = line_report(strips, toy_game(), num_lines=1)
        self.assertAlmostEqual(report["rtp"], 40.0)

    def test_max_is_taken_between_competing_symbols(self):
        # 9 9 9 8 8: для 8 серия {8,9} длиной 5 -> 100; для 9 чистая серия 3 -> 15
        strips = [[9], [9], [9], [8], [8]]
        report = line_report(strips, toy_game(), num_lines=1)
        self.assertAlmostEqual(report["rtp"], 100.0)
        self.assertAlmostEqual(report["per_symbol"][8], 100.0)

    def test_scatter_never_takes_part_in_line_wins(self):
        strips = [[10], [10], [10], [10], [10]]
        report = line_report(strips, toy_game(), num_lines=1)
        self.assertAlmostEqual(report["rtp"], 0.0)

    def test_half_and_half_reel_gives_expected_average(self):
        # барабан 1: 1 или 8 поровну; остальные всегда 1
        strips = [[1, 8], [1], [1], [1], [1]]
        report = line_report(strips, toy_game(), num_lines=1)
        # 50%: 1 1 1 1 1 -> 10; 50%: 8 1 1 1 1 -> ничего (серия 8 длиной 1)
        self.assertAlmostEqual(report["rtp"], 5.0)
        self.assertAlmostEqual(report["line_hit_prob"], 0.5)
        self.assertAlmostEqual(report["line_hit_one_in"], 2.0)

    def test_num_lines_does_not_change_rtp(self):
        strips = [[1, 8], [1], [1], [1], [1]]
        one = line_report(strips, toy_game(), num_lines=1)
        twenty = line_report(strips, toy_game(), num_lines=20)
        self.assertAlmostEqual(one["rtp"], twenty["rtp"])


if __name__ == "__main__":
    unittest.main()
```

Разбор `test_max_is_taken_between_competing_symbols`: линия `9 9 9 8 8`. Для символа 8 серия из `{8, 9}` покрывает все 5 барабанов → `pay(8, 5) = 100`. Для вайлда чистая серия — 3 → `pay(9, 3) = 15`. Максимум = 100.

- [ ] **Step 2: Убедиться, что тест падает**

Run: `python3 -m unittest tests.test_math_lines -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reelgen.mathexact'`

- [ ] **Step 3: Реализация**

`reelgen/mathexact.py`:

```python
"""Точная математика по лентам: RTP линий, распределения скаттера и бонуса.

Ключевой факт: для конкретной линии видимый символ на барабане — равномерный
выбор из всей ленты (позиция остановки равномерна, ряд фиксирован), а барабаны
независимы. Значит распределение по линии одинаково для всех линий, и RTP
считается один раз.
"""

from collections import Counter

from .model import GameConfig


def symbol_probs(strip: list[int]) -> dict[int, float]:
    """Вероятность каждого символа в одной видимой ячейке этого барабана."""
    if not strip:
        return {}
    total = len(strip)
    return {sid: count / total for sid, count in Counter(strip).items()}


def _pay(symbol, length: int) -> float:
    value = symbol.pays.get(length, 0)
    return float(value) if isinstance(value, (int, float)) else 0.0


def line_report(
    strips: list[list[int]], game: GameConfig, num_lines: int | None = None
) -> dict:
    """Точный RTP линий с разбивкой по символам и длинам."""
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

    def walk(reel: int, alive: frozenset, best: tuple[float, int, int], prob: float):
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
```

Пояснение к `walk`: `alive` — символы, у которых серия слева не прервалась, длина серии равна номеру текущего барабана `reel`. Когда символ выбывает на барабане `reel`, его серия имела длину ровно `reel`. `best` несёт лучший выигрыш среди выбывших. Ветка закрывается, как только живых не осталось.

Про `num_lines`: RTP в долях общей ставки не зависит от числа линий (каждая линия ставит 1 из общей ставки `num_lines`), поэтому поле информационное и в расчёт не входит.

- [ ] **Step 4: Тесты зелёные**

Run: `python3 -m unittest tests.test_math_lines -v`
Expected: PASS, 12 тестов

- [ ] **Step 5: Проверить скорость на реальной ленте**

Run:

```bash
python3 -c "
import time
from pathlib import Path
from reelgen.gameio import parse_file
from reelgen.mathexact import line_report
game = parse_file('tests/fixtures/sample_game.py')
strips = game.reelsets['spins_1']
t = time.monotonic()
r = line_report(strips, game)
print('rtp', round(r['rtp'], 4), 'за', round(time.monotonic() - t, 3), 'с')
"
```

Expected: время меньше 2 секунд. Если больше — проблема в отсутствии отсечения по пустым веткам, чинить `walk`, а не уменьшать точность.

- [ ] **Step 6: Checkpoint**

Run: `python3 -m unittest discover -s tests -t . -v`

---

### Task 11: Скаттер, бонус и общий hit rate

**Files:**
- Modify: `reelgen/mathexact.py` (дописать)
- Test: `tests/test_math_features.py`

**Interfaces:**
- Consumes: `symbol_probs`, `line_report`, `GameConfig`
- Produces:
  - `window_count_dist(strip: list[int], symbol_id: int, rows: int) -> dict[int, float]` — распределение числа символов в видимом окне одного барабана
  - `feature_dist(strips, symbol_id, rows) -> dict[int, float]` — свёртка по всем барабанам
  - `feature_report(strips, symbol_id, rows, threshold=3) -> dict` — `dist`, `prob`, `one_in`
  - `scatter_rtp(strips, game, rows, threshold=3) -> float` — вклад `tb`-выплаты в RTP
  - `simulate_hit_rate(strips, game, spins=50000, seed=0) -> dict` — `prob`, `one_in`, `spins`, `error` (стандартная ошибка), `estimated: True`
  - `full_report(strips, game, bonus_threshold=3, scatter_threshold=3, sim_spins=50000, seed=0, simulate=True) -> dict` — собирает всё вместе плюс `total_rtp`

- [ ] **Step 1: Написать падающий тест**

`tests/test_math_features.py`:

```python
import unittest

from reelgen.mathexact import (
    feature_dist,
    feature_report,
    full_report,
    scatter_rtp,
    simulate_hit_rate,
    window_count_dist,
)
from reelgen.model import GameConfig, Symbol


def toy_game():
    symbols = {
        1: Symbol(1, "line", {3: 2, 4: 5, 5: 10}, "el_01"),
        9: Symbol(9, "wild", {3: 15, 4: 70, 5: 300}, "el_wild"),
        10: Symbol(10, "scat", {3: {"tb": 2, "fs": 8}}, "el_scatter"),
        11: Symbol(11, "bonus", {}, "el_bonus"),
    }
    paylines = [[0, 0, 0, 0, 0], [1, 1, 1, 1, 1], [2, 2, 2, 2, 2], [3, 3, 3, 3, 3]]
    return GameConfig(symbols=symbols, paylines=paylines, reelsets={})


class TestWindowCounts(unittest.TestCase):
    def test_distribution_sums_to_one(self):
        dist = window_count_dist([1, 1, 10, 1, 1, 1, 10, 1], 10, rows=4)
        self.assertAlmostEqual(sum(dist.values()), 1.0)

    def test_single_scatter_on_a_long_reel(self):
        # окно 4 ряда, ровно один скаттер: он виден на 4 из 8 позиций остановки
        dist = window_count_dist([10, 1, 1, 1, 1, 1, 1, 1], 10, rows=4)
        self.assertAlmostEqual(dist[1], 0.5)
        self.assertAlmostEqual(dist[0], 0.5)

    def test_no_scatter_gives_all_zero(self):
        dist = window_count_dist([1, 1, 1, 1], 10, rows=4)
        self.assertEqual(dist, {0: 1.0})

    def test_window_wraps_around_the_seam(self):
        # скаттер на последней позиции виден и когда окно перескакивает стык
        dist = window_count_dist([1, 1, 1, 1, 1, 10], 10, rows=4)
        self.assertAlmostEqual(dist[1], 4 / 6)


class TestFeatureDist(unittest.TestCase):
    def test_convolution_across_reels(self):
        # три барабана, на каждом скаттер виден с вероятностью 1/2
        strip = [10, 1, 1, 1, 1, 1, 1, 1]
        dist = feature_dist([strip, strip, strip], 10, rows=4)
        self.assertAlmostEqual(dist[3], 0.125)
        self.assertAlmostEqual(dist[0], 0.125)
        self.assertAlmostEqual(sum(dist.values()), 1.0)

    def test_report_threshold(self):
        strip = [10, 1, 1, 1, 1, 1, 1, 1]
        report = feature_report([strip, strip, strip], 10, rows=4, threshold=3)
        self.assertAlmostEqual(report["prob"], 0.125)
        self.assertAlmostEqual(report["one_in"], 8.0)

    def test_zero_probability_gives_zero_one_in(self):
        report = feature_report([[1], [1], [1]], 10, rows=4, threshold=3)
        self.assertEqual(report["prob"], 0.0)
        self.assertEqual(report["one_in"], 0.0)


class TestScatterRtp(unittest.TestCase):
    def test_pays_total_bet_multiplier(self):
        strip = [10, 1, 1, 1, 1, 1, 1, 1]
        rtp = scatter_rtp([strip, strip, strip, strip, strip], toy_game(), rows=4)
        # P(>=3 из 5 по 1/2) = 16/32 = 0.5, выплата 2 общих ставки
        self.assertAlmostEqual(rtp, 1.0)

    def test_no_scatter_symbol_gives_zero(self):
        game = GameConfig(symbols={1: Symbol(1, "line", {3: 2}, "el_01")}, paylines=[[0] * 5])
        self.assertEqual(scatter_rtp([[1]] * 5, game, rows=4), 0.0)


class TestSimulation(unittest.TestCase):
    def test_certain_win_is_detected(self):
        strips = [[1]] * 5
        result = simulate_hit_rate(strips, toy_game(), spins=500, seed=1)
        self.assertAlmostEqual(result["prob"], 1.0)
        self.assertTrue(result["estimated"])

    def test_certain_loss_is_detected(self):
        strips = [[1], [10], [1], [1], [1]]
        result = simulate_hit_rate(strips, toy_game(), spins=500, seed=1)
        self.assertAlmostEqual(result["prob"], 0.0)

    def test_same_seed_reproduces(self):
        strips = [[1, 10, 9, 11], [1, 10, 9, 11], [1, 10, 9, 11], [1, 10, 9, 11], [1, 10, 9, 11]]
        a = simulate_hit_rate(strips, toy_game(), spins=2000, seed=5)
        b = simulate_hit_rate(strips, toy_game(), spins=2000, seed=5)
        self.assertEqual(a["prob"], b["prob"])


class TestFullReport(unittest.TestCase):
    def test_report_has_all_sections(self):
        strips = [[1, 10, 9, 11, 1, 1, 1, 1]] * 5
        report = full_report(strips, toy_game(), sim_spins=500, seed=1)
        for key in ("lines", "scatter", "bonus", "scatter_rtp", "total_rtp", "overall_hit"):
            self.assertIn(key, report)

    def test_total_is_lines_plus_scatter(self):
        strips = [[1, 10, 9, 11, 1, 1, 1, 1]] * 5
        report = full_report(strips, toy_game(), sim_spins=500, seed=1)
        self.assertAlmostEqual(
            report["total_rtp"], report["lines"]["rtp"] + report["scatter_rtp"]
        )

    def test_simulation_can_be_skipped(self):
        strips = [[1, 10, 9, 11, 1, 1, 1, 1]] * 5
        report = full_report(strips, toy_game(), simulate=False)
        self.assertIsNone(report["overall_hit"])


if __name__ == "__main__":
    unittest.main()
```

Разбор `test_pays_total_bet_multiplier`: пять барабанов, на каждом скаттер виден с вероятностью 1/2 независимо. `P(≥3 из 5)` = (10 + 5 + 1)/32 = 0.5. Выплата — 2 общие ставки, значит вклад в RTP = 0.5 × 2 = 1.0.

- [ ] **Step 2: Убедиться, что тест падает**

Run: `python3 -m unittest tests.test_math_features -v`
Expected: FAIL — `ImportError: cannot import name 'window_count_dist'`

- [ ] **Step 3: Реализация**

Дописать в `reelgen/mathexact.py`:

```python
import random


def window_count_dist(strip: list[int], symbol_id: int, rows: int) -> dict[int, float]:
    """Распределение числа символов symbol_id в видимом окне одного барабана."""
    length = len(strip)
    if length == 0:
        return {}
    counts: dict[int, int] = {}
    for stop in range(length):
        seen = sum(
            1 for row in range(rows) if strip[(stop + row) % length] == symbol_id
        )
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


def _line_wins(window: list[list[int]], line: list[int], paying, wild_id) -> bool:
    """Есть ли выигрыш на этой линии. Достаточно проверить серию из трёх."""
    visible = [window[reel][line[reel]] for reel in range(len(line))]
    for symbol_id in paying:
        run = 0
        for value in visible:
            if value == symbol_id or value == wild_id:
                run += 1
            else:
                break
        if run >= 3 and paying[symbol_id].pays.get(run):
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
        [[strip[(stop + row) % len(strip)] for row in range(rows)] for stop in range(len(strip))]
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
        feature_report(strips, scat_id, rows, scatter_threshold) if scat_id else None
    )
    bonus = feature_report(strips, bonus_id, rows, bonus_threshold) if bonus_id else None
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
```

Импорт `random` добавить к верхним импортам файла, а не оставлять посреди модуля.

- [ ] **Step 4: Тесты зелёные**

Run: `python3 -m unittest tests.test_math_features -v`
Expected: PASS, 14 тестов

- [ ] **Step 5: Checkpoint**

Run: `python3 -m unittest discover -s tests -t . -v`

---

### Task 12: Проект — сохранение и загрузка

**Files:**
- Create: `reelgen/project.py`
- Test: `tests/test_project.py`

**Interfaces:**
- Consumes: `RuleSet`, `ReelRules`, `StackRule`, `DistanceRule`
- Produces:
  - `Project(name: str, game_path: str, images_folder: str, image_map: dict[int, str], rules: RuleSet, seeds: dict[str, int], bonus_threshold: int = 3, scatter_threshold: int = 3)`
  - `to_dict(project: Project) -> dict` / `from_dict(data: dict) -> Project`
  - `save(project: Project, folder: str | Path) -> Path` — пишет `<folder>/<name>.json`
  - `load(path: str | Path) -> Project`
  - `list_projects(folder: str | Path) -> list[str]`

В JSON ключи словарей всегда строки — при загрузке `image_map`, `classes`, `sizes` и `seeds` нужно приводить ключи обратно к `int` там, где они целые.

- [ ] **Step 1: Написать падающий тест**

`tests/test_project.py`:

```python
import tempfile
import unittest
from pathlib import Path

from reelgen.project import Project, from_dict, list_projects, load, save, to_dict
from reelgen.rules import DistanceRule, ReelRules, RuleSet, StackRule


def sample_project():
    rules = RuleSet(
        classes={1: "low", 10: "special"},
        reels={
            "spins_1": [
                ReelRules(
                    stacks=[StackRule(1, 30, {1: 60.0, 2: 40.0}), StackRule(10, 4, {1: 100.0})],
                    distances=[DistanceRule("class:special", "class:special", 5, filler=None)],
                )
            ]
        },
    )
    return Project(
        name="test",
        game_path="/tmp/game.py",
        images_folder="/tmp/symbols",
        image_map={1: "sym1.png", 10: "sym10.png"},
        rules=rules,
        seeds={"spins_1": 7},
    )


class TestProjectRoundTrip(unittest.TestCase):
    def test_dict_round_trip_preserves_everything(self):
        original = sample_project()
        restored = from_dict(to_dict(original))
        self.assertEqual(restored, original)

    def test_int_keys_survive_json(self):
        restored = from_dict(to_dict(sample_project()))
        self.assertEqual(restored.image_map[1], "sym1.png")
        self.assertEqual(restored.rules.classes[10], "special")
        self.assertEqual(restored.rules.reels["spins_1"][0].stacks[0].sizes[2], 40.0)

    def test_save_and_load_from_disk(self):
        with tempfile.TemporaryDirectory() as folder:
            path = save(sample_project(), folder)
            self.assertTrue(path.exists())
            self.assertEqual(path.name, "test.json")
            self.assertEqual(load(path), sample_project())

    def test_list_projects(self):
        with tempfile.TemporaryDirectory() as folder:
            save(sample_project(), folder)
            other = sample_project()
            other.name = "second"
            save(other, folder)
            self.assertEqual(list_projects(folder), ["second", "test"])

    def test_list_projects_on_missing_folder(self):
        self.assertEqual(list_projects("/definitely/not/here"), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `python3 -m unittest tests.test_project -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reelgen.project'`

- [ ] **Step 3: Реализация**

`reelgen/project.py`:

```python
"""Сохранение и загрузка проекта: пути, картинки, классы, правила, сиды."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from .rules import DistanceRule, ReelRules, RuleSet, StackRule


@dataclass
class Project:
    name: str = "default"
    game_path: str = ""
    images_folder: str = ""
    image_map: dict[int, str] = field(default_factory=dict)
    rules: RuleSet = field(default_factory=RuleSet)
    seeds: dict[str, int] = field(default_factory=dict)
    bonus_threshold: int = 3
    scatter_threshold: int = 3


def _stack_to_dict(stack: StackRule) -> dict:
    return {
        "symbol_id": stack.symbol_id,
        "count": stack.count,
        "sizes": {str(size): weight for size, weight in stack.sizes.items()},
    }


def _stack_from_dict(data: dict) -> StackRule:
    return StackRule(
        symbol_id=int(data["symbol_id"]),
        count=int(data["count"]),
        sizes={int(size): float(weight) for size, weight in data["sizes"].items()},
    )


def _distance_to_dict(rule: DistanceRule) -> dict:
    return {"a": rule.a, "b": rule.b, "min_gap": rule.min_gap, "filler": rule.filler}


def _distance_from_dict(data: dict) -> DistanceRule:
    return DistanceRule(
        a=data["a"],
        b=data["b"],
        min_gap=int(data["min_gap"]),
        filler=data.get("filler") or None,
    )


def _reel_to_dict(rules: ReelRules) -> dict:
    return {
        "stacks": [_stack_to_dict(stack) for stack in rules.stacks],
        "distances": [_distance_to_dict(rule) for rule in rules.distances],
    }


def _reel_from_dict(data: dict) -> ReelRules:
    return ReelRules(
        stacks=[_stack_from_dict(item) for item in data.get("stacks", [])],
        distances=[_distance_from_dict(item) for item in data.get("distances", [])],
    )


def to_dict(project: Project) -> dict:
    return {
        "name": project.name,
        "game_path": project.game_path,
        "images_folder": project.images_folder,
        "image_map": {str(sid): name for sid, name in project.image_map.items()},
        "bonus_threshold": project.bonus_threshold,
        "scatter_threshold": project.scatter_threshold,
        "seeds": dict(project.seeds),
        "rules": {
            "classes": {str(sid): name for sid, name in project.rules.classes.items()},
            "reels": {
                name: [_reel_to_dict(reel) for reel in reels]
                for name, reels in project.rules.reels.items()
            },
        },
    }


def from_dict(data: dict) -> Project:
    rules_data = data.get("rules", {})
    rules = RuleSet(
        classes={int(sid): name for sid, name in rules_data.get("classes", {}).items()},
        reels={
            name: [_reel_from_dict(reel) for reel in reels]
            for name, reels in rules_data.get("reels", {}).items()
        },
    )
    return Project(
        name=data.get("name", "default"),
        game_path=data.get("game_path", ""),
        images_folder=data.get("images_folder", ""),
        image_map={int(sid): name for sid, name in data.get("image_map", {}).items()},
        rules=rules,
        seeds={name: int(seed) for name, seed in data.get("seeds", {}).items()},
        bonus_threshold=int(data.get("bonus_threshold", 3)),
        scatter_threshold=int(data.get("scatter_threshold", 3)),
    )


def save(project: Project, folder: str | Path) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{project.name}.json"
    path.write_text(
        json.dumps(to_dict(project), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def load(path: str | Path) -> Project:
    return from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def list_projects(folder: str | Path) -> list[str]:
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(path.stem for path in folder.glob("*.json"))
```

- [ ] **Step 4: Тесты зелёные**

Run: `python3 -m unittest tests.test_project -v`
Expected: PASS, 5 тестов

- [ ] **Step 5: Checkpoint**

Run: `python3 -m unittest discover -s tests -t . -v`

---

### Task 13: HTTP-сервер и API

**Files:**
- Create: `reelgen/service.py` — логика запросов, без HTTP
- Create: `reelgen/server.py` — тонкая обёртка на `http.server`
- Test: `tests/test_service.py`

**Interfaces:**
- Consumes: всё из `gameio`, `images`, `rules`, `feasibility`, `generate`, `stats`, `mathexact`, `project`
- Produces (в `service.py`, все функции принимают и возвращают простые dict, пригодные для JSON):
  - `import_game(payload: dict) -> dict` — вход `{"path": str}`; выход `{"symbols": [...], "paylines": [...], "reelsets": {...}, "default_classes": {...}, "rows": int}`
  - `list_images(payload: dict) -> dict` — вход `{"folder": str}`; выход `{"by_id": {...}, "auto_map": {...}}`
  - `default_rules(payload: dict) -> dict` — вход `{"path": str, "reelset": str}`; выход `{"reels": [...]}` — правила, восстановленные из текущих лент рилсета (количества и фактические стеки), чтобы было с чего стартовать
  - `generate(payload: dict) -> dict` — вход `{"path", "reelset", "seed", "classes", "reels": [правила по рилам]}`; выход `{"strips", "seeds", "stages", "problems", "violations", "composition", "math"}`
  - `evaluate(payload: dict) -> dict` — вход `{"path", "strips", "classes", "bonus_threshold", "scatter_threshold", "simulate", "sim_spins"}`; выход `{"composition", "math"}`
  - `export(payload: dict) -> dict` — вход `{"path", "out_path", "reelsets"}`; выход `{"written": str}`
  - `save_project(payload) -> dict`, `load_project(payload) -> dict`, `list_saved(payload) -> dict`
  - `ServiceError(Exception)` — сообщение уходит клиенту как `{"error": ...}` с кодом 400

- [ ] **Step 1: Написать падающий тест**

`tests/test_service.py`:

```python
import tempfile
import unittest
from pathlib import Path

from reelgen import service

FIXTURE = str(Path(__file__).parent / "fixtures" / "sample_game.py")


class TestImport(unittest.TestCase):
    def test_import_returns_symbols_and_reelsets(self):
        out = service.import_game({"path": FIXTURE})
        self.assertEqual(len(out["symbols"]), 12)
        self.assertEqual(out["rows"], 4)
        self.assertEqual(list(out["reelsets"]), ["spins_1", "freespins_0"])
        self.assertEqual(out["default_classes"]["1"], "low")

    def test_missing_file_raises_service_error(self):
        with self.assertRaises(service.ServiceError):
            service.import_game({"path": "/nope/nope.py"})


class TestDefaultRules(unittest.TestCase):
    def test_rules_are_derived_from_current_strips(self):
        out = service.default_rules({"path": FIXTURE, "reelset": "spins_1"})
        self.assertEqual(len(out["reels"]), 5)
        first = out["reels"][0]
        total = sum(stack["count"] for stack in first["stacks"])
        self.assertEqual(total, 40)

    def test_unknown_reelset_raises(self):
        with self.assertRaises(service.ServiceError):
            service.default_rules({"path": FIXTURE, "reelset": "nope"})


class TestGenerate(unittest.TestCase):
    def test_generate_from_default_rules_round_trips(self):
        rules = service.default_rules({"path": FIXTURE, "reelset": "spins_1"})
        game = service.import_game({"path": FIXTURE})
        out = service.generate(
            {
                "path": FIXTURE,
                "reelset": "spins_1",
                "seed": 1,
                "classes": game["default_classes"],
                "reels": rules["reels"],
                "simulate": False,
            }
        )
        self.assertEqual(len(out["strips"]), 5)
        self.assertTrue(all(len(strip) == 40 for strip in out["strips"]))
        self.assertIn("math", out)
        self.assertIn("total_rtp", out["math"])
        self.assertIn("composition", out)

    def test_infeasible_rules_are_reported_before_generating(self):
        game = service.import_game({"path": FIXTURE})
        reels = [
            {
                "stacks": [
                    {"symbol_id": 1, "count": 6, "sizes": {"1": 100.0}},
                    {"symbol_id": 10, "count": 6, "sizes": {"1": 100.0}},
                ],
                "distances": [
                    {"a": "class:special", "b": "class:special", "min_gap": 5, "filler": None}
                ],
            }
        ]
        out = service.generate(
            {
                "path": FIXTURE,
                "reelset": "spins_1",
                "seed": 1,
                "classes": game["default_classes"],
                "reels": reels,
                "simulate": False,
            }
        )
        self.assertTrue(out["problems"][0])
        self.assertEqual(out["strips"], [])


class TestEvaluate(unittest.TestCase):
    def test_evaluate_existing_strips(self):
        game = service.import_game({"path": FIXTURE})
        out = service.evaluate(
            {
                "path": FIXTURE,
                "strips": game["reelsets"]["spins_1"],
                "classes": game["default_classes"],
                "simulate": False,
            }
        )
        self.assertIn("total_rtp", out["math"])
        self.assertEqual(len(out["composition"]["reels"]), 5)


class TestExport(unittest.TestCase):
    def test_export_writes_a_new_file(self):
        game = service.import_game({"path": FIXTURE})
        with tempfile.TemporaryDirectory() as folder:
            out_path = str(Path(folder) / "out.py")
            result = service.export(
                {
                    "path": FIXTURE,
                    "out_path": out_path,
                    "reelsets": {"spins_1": [[1] * 4 for _ in range(5)]},
                }
            )
            self.assertEqual(result["written"], out_path)
            text = Path(out_path).read_text(encoding="utf-8")
            self.assertIn("1 1 1 1", text)
            self.assertIn("reels_freespins_0", text)


class TestProjects(unittest.TestCase):
    def test_save_list_load(self):
        with tempfile.TemporaryDirectory() as folder:
            payload = {
                "folder": folder,
                "project": {
                    "name": "p1",
                    "game_path": FIXTURE,
                    "images_folder": "",
                    "image_map": {},
                    "rules": {"classes": {}, "reels": {}},
                    "seeds": {},
                },
            }
            service.save_project(payload)
            self.assertEqual(service.list_saved({"folder": folder})["names"], ["p1"])
            loaded = service.load_project({"folder": folder, "name": "p1"})
            self.assertEqual(loaded["project"]["name"], "p1")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `python3 -m unittest tests.test_service -v`
Expected: FAIL — `ImportError: cannot import name 'service'`

- [ ] **Step 3: Реализация `service.py`**

`reelgen/service.py`:

```python
"""Логика запросов UI. Никакого HTTP — только dict на входе и dict на выходе."""

from pathlib import Path

from . import gameio, images, project as project_io
from .feasibility import check_reel
from .generate import generate_reelset
from .mathexact import full_report
from .model import GameConfig
from .rules import DistanceRule, ReelRules, StackRule, blocks_of, default_classes
from .stats import reelset_composition


class ServiceError(Exception):
    """Ошибка, которую надо показать пользователю, а не свалить в трейсбек."""


def _load_game(payload: dict) -> GameConfig:
    path = payload.get("path") or ""
    if not path or not Path(path).is_file():
        raise ServiceError(f"файл игры не найден: {path or '(пусто)'}")
    try:
        return gameio.parse_file(path)
    except gameio.ParseError as exc:
        raise ServiceError(str(exc)) from exc


def _classes(payload: dict, game: GameConfig) -> dict[int, str]:
    raw = payload.get("classes")
    if not raw:
        return default_classes(game)
    return {int(sid): name for sid, name in raw.items()}


def _reel_rules(data: dict) -> ReelRules:
    return ReelRules(
        stacks=[
            StackRule(
                symbol_id=int(stack["symbol_id"]),
                count=int(stack["count"]),
                sizes={int(size): float(weight) for size, weight in stack["sizes"].items()},
            )
            for stack in data.get("stacks", [])
        ],
        distances=[
            DistanceRule(
                a=rule["a"],
                b=rule["b"],
                min_gap=int(rule["min_gap"]),
                filler=rule.get("filler") or None,
            )
            for rule in data.get("distances", [])
        ],
    )


def import_game(payload: dict) -> dict:
    game = _load_game(payload)
    return {
        "path": game.source_path,
        "rows": game.rows,
        "reels_count": game.reels_count,
        "symbols": [
            {
                "id": symbol.id,
                "kind": symbol.kind,
                "pays": {str(k): v for k, v in symbol.pays.items()},
                "asset": symbol.asset,
            }
            for symbol in (game.symbols[sid] for sid in sorted(game.symbols))
        ],
        "paylines": game.paylines,
        "reelsets": game.reelsets,
        "default_classes": {str(sid): name for sid, name in default_classes(game).items()},
    }


def list_images(payload: dict) -> dict:
    folder = payload.get("folder") or ""
    by_id = images.scan_folder(folder)
    return {
        "folder": folder,
        "by_id": {str(sid): names for sid, names in by_id.items()},
        "auto_map": {str(sid): names[0] for sid, names in by_id.items()},
    }


def default_rules(payload: dict) -> dict:
    """Правила, восстановленные из текущих лент — стартовая точка для правки."""
    game = _load_game(payload)
    name = payload.get("reelset") or ""
    if name not in game.reelsets:
        raise ServiceError(f"рилсет '{name}' в файле не найден")

    reels = []
    for strip in game.reelsets[name]:
        sizes_by_symbol: dict[int, dict[int, int]] = {}
        counts: dict[int, int] = {}
        for block in blocks_of(strip):
            counts[block.symbol_id] = counts.get(block.symbol_id, 0) + block.size
            by_size = sizes_by_symbol.setdefault(block.symbol_id, {})
            by_size[block.size] = by_size.get(block.size, 0) + 1
        stacks = []
        for symbol_id in sorted(counts):
            by_size = sizes_by_symbol[symbol_id]
            total_blocks = sum(by_size.values())
            stacks.append(
                {
                    "symbol_id": symbol_id,
                    "count": counts[symbol_id],
                    "sizes": {
                        str(size): round(100.0 * n / total_blocks, 2)
                        for size, n in sorted(by_size.items())
                    },
                }
            )
        reels.append({"stacks": stacks, "distances": []})
    return {"reelset": name, "reels": reels}


def _math_and_stats(strips, game, classes, payload) -> dict:
    return {
        "composition": reelset_composition(strips, classes, game),
        "math": full_report(
            strips,
            game,
            bonus_threshold=int(payload.get("bonus_threshold", 3)),
            scatter_threshold=int(payload.get("scatter_threshold", 3)),
            sim_spins=int(payload.get("sim_spins", 50000)),
            seed=int(payload.get("seed", 0)),
            simulate=bool(payload.get("simulate", True)),
        ),
    }


def generate(payload: dict) -> dict:
    game = _load_game(payload)
    classes = _classes(payload, game)
    reels = [_reel_rules(item) for item in payload.get("reels", [])]
    if not reels:
        raise ServiceError("не заданы правила ни для одного рила")

    problems = [
        [{"kind": p.kind, "message": p.message} for p in check_reel(rules, classes)]
        for rules in reels
    ]
    if any(problems):
        return {
            "strips": [],
            "seeds": [],
            "stages": [],
            "problems": problems,
            "violations": [],
            "composition": None,
            "math": None,
        }

    results = generate_reelset(
        reels,
        classes,
        seed=int(payload.get("seed", 1)),
        greedy_attempts=int(payload.get("greedy_attempts", 200)),
        repair_seconds=float(payload.get("repair_seconds", 8.0)),
    )
    strips = [result.strip for result in results]

    out = {
        "strips": strips,
        "seeds": [result.seed for result in results],
        "stages": [result.stage for result in results],
        "attempts": [result.attempts for result in results],
        "problems": problems,
        "violations": [
            [
                {
                    "rule_index": v.rule_index,
                    "gap": v.gap,
                    "filler_count": v.filler_count,
                    "deficit": v.deficit,
                    "a": {"symbol_id": v.a.symbol_id, "start": v.a.start, "size": v.a.size},
                    "b": {"symbol_id": v.b.symbol_id, "start": v.b.start, "size": v.b.size},
                }
                for v in result.violations
            ]
            for result in results
        ],
    }
    out.update(_math_and_stats(strips, game, classes, payload))
    return out


def evaluate(payload: dict) -> dict:
    game = _load_game(payload)
    classes = _classes(payload, game)
    strips = payload.get("strips") or []
    if not strips:
        raise ServiceError("нечего считать: ленты не переданы")
    return _math_and_stats(strips, game, classes, payload)


def export(payload: dict) -> dict:
    game = _load_game(payload)
    out_path = payload.get("out_path") or game.source_path
    reelsets = payload.get("reelsets") or {}
    if not reelsets:
        raise ServiceError("нечего экспортировать: рилсеты не переданы")
    text = gameio.export_text(game.source_text, reelsets)
    Path(out_path).write_text(text, encoding="utf-8")
    return {"written": str(out_path)}


def save_project(payload: dict) -> dict:
    folder = payload.get("folder") or "projects"
    data = payload.get("project") or {}
    path = project_io.save(project_io.from_dict(data), folder)
    return {"saved": str(path)}


def load_project(payload: dict) -> dict:
    folder = Path(payload.get("folder") or "projects")
    name = payload.get("name") or ""
    path = folder / f"{name}.json"
    if not path.is_file():
        raise ServiceError(f"проект '{name}' не найден")
    return {"project": project_io.to_dict(project_io.load(path))}


def list_saved(payload: dict) -> dict:
    return {"names": project_io.list_projects(payload.get("folder") or "projects")}
```

- [ ] **Step 4: Тесты сервиса зелёные**

Run: `python3 -m unittest tests.test_service -v`
Expected: PASS, 9 тестов

- [ ] **Step 5: Реализация `server.py`**

`reelgen/server.py`:

```python
"""Локальный HTTP-сервер: JSON API поверх service.py плюс статика и картинки."""

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import service

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

ROUTES = {
    "/api/import": service.import_game,
    "/api/images": service.list_images,
    "/api/default-rules": service.default_rules,
    "/api/generate": service.generate,
    "/api/evaluate": service.evaluate,
    "/api/export": service.export,
    "/api/project/save": service.save_project,
    "/api/project/load": service.load_project,
    "/api/project/list": service.list_saved,
}


class Handler(BaseHTTPRequestHandler):
    images_folder = ""

    def log_message(self, fmt, *args):  # тише в консоли
        pass

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)
        if path == "/":
            path = "/index.html"

        if path.startswith("/img/"):
            folder = Path(Handler.images_folder or "")
            name = Path(path[len("/img/"):]).name
            target = folder / name
            if not folder.is_dir() or not target.is_file():
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
            kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self._send(200, target.read_bytes(), kind)
            return

        target = (WEB / path.lstrip("/")).resolve()
        if not str(target).startswith(str(WEB.resolve())) or not target.is_file():
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._send(200, target.read_bytes(), kind)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        handler = ROUTES.get(path)
        if handler is None:
            self._send_json(404, {"error": f"неизвестный маршрут {path}"})
            return

        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            self._send_json(400, {"error": f"битый JSON: {exc}"})
            return

        if path == "/api/images" and payload.get("folder"):
            Handler.images_folder = payload["folder"]

        try:
            self._send_json(200, handler(payload))
        except service.ServiceError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:  # чтобы UI показал причину, а не завис
            self._send_json(500, {"error": f"{type(exc).__name__}: {exc}"})


def serve(port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
```

- [ ] **Step 6: Checkpoint**

Run: `python3 -m unittest discover -s tests -t . -v`

---

### Task 14: Веб-интерфейс и точка входа

**Files:**
- Create: `web/index.html`
- Create: `web/style.css`
- Create: `web/app.js`
- Create: `run.py`
- Create: `README.md`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Consumes: `reelgen.server.serve`, весь JSON API
- Produces: `run.py` — CLI: `--port` (по умолчанию 8765), `--no-open`, `--images` (папка картинок по умолчанию)

Экраны UI, сверху вниз в одной колонке-панели слева и рабочей областью справа:

1. **Источник** — путь к `.py` игры, кнопка «Импорт»; путь к папке картинок, кнопка «Найти картинки». Список найденных символов с превью и выпадашкой для переназначения файла.
2. **Классы** — таблица id → картинка → селект класса.
3. **Рилсет** — выбор рилсета из импортированных, кнопка «Взять правила из текущих лент».
4. **Правила рила** — вкладки по рилам 1–5. Внутри: таблица состава (id, картинка, количество, чекбоксы размеров стека 1/2/3/4 с полями процентов) и список правил дистанции (селект A, селект B, поле N, селект наполнителя, кнопка удалить, кнопка добавить). Под таблицей — длина ленты, пересчитывается на лету. Кнопки «скопировать на все рилы» и «скопировать на все рилсеты».
5. **Генерация** — поле сида, кнопка «Generate», чекбокс «считать общий hit rate».
6. **Результат** — раскладка картинками (5 колонок, стеки в общей рамке, слайдер положения окна на 4 ряда), таблица состава, блок RTP.
7. **Экспорт** — путь выходного файла, кнопка «Экспортировать».
8. **Проект** — имя, кнопки «Сохранить» / «Загрузить», список сохранённых.

- [ ] **Step 1: Написать падающий smoke-тест**

`tests/test_smoke.py`:

```python
import json
import threading
import unittest
import urllib.request
from pathlib import Path

from reelgen.server import serve

FIXTURE = str(Path(__file__).parent / "fixtures" / "sample_game.py")


class TestServerSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = serve(port=0)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def post(self, path, payload):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_index_page_is_served(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/") as response:
            body = response.read().decode("utf-8")
        self.assertIn("Reel Generator", body)

    def test_app_js_is_served(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/app.js") as response:
            self.assertEqual(response.status, 200)

    def test_import_endpoint(self):
        out = self.post("/api/import", {"path": FIXTURE})
        self.assertEqual(len(out["symbols"]), 12)

    def test_full_generate_flow(self):
        game = self.post("/api/import", {"path": FIXTURE})
        rules = self.post("/api/default-rules", {"path": FIXTURE, "reelset": "spins_1"})
        out = self.post(
            "/api/generate",
            {
                "path": FIXTURE,
                "reelset": "spins_1",
                "seed": 3,
                "classes": game["default_classes"],
                "reels": rules["reels"],
                "simulate": False,
            },
        )
        self.assertEqual(len(out["strips"]), 5)
        self.assertIn("total_rtp", out["math"])

    def test_bad_path_returns_readable_error(self):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/import",
            data=json.dumps({"path": "/nope.py"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request)
        body = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertIn("не найден", body["error"])


if __name__ == "__main__":
    unittest.main()
```

Добавить `import urllib.error` в шапку теста.

- [ ] **Step 2: Убедиться, что тест падает**

Run: `python3 -m unittest tests.test_smoke -v`
Expected: FAIL — 404 на `/`, файла `web/index.html` ещё нет

- [ ] **Step 3: Написать `web/index.html`**

Разметка панелей 1–8 из списка выше. Обязательно: `<title>Reel Generator</title>` и `<h1>Reel Generator</h1>` (на них смотрит smoke-тест), подключение `style.css` и `app.js`. Никаких внешних CDN — только локальные файлы.

Каркас:

```html
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Reel Generator</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <h1>Reel Generator</h1>
  <div class="layout">
    <aside class="panel">
      <section id="source"><h2>Источник</h2></section>
      <section id="classes"><h2>Классы</h2></section>
      <section id="reelset"><h2>Рилсет</h2></section>
      <section id="rules"><h2>Правила рила</h2></section>
      <section id="run"><h2>Генерация</h2></section>
      <section id="io"><h2>Экспорт и проект</h2></section>
    </aside>
    <main class="work">
      <section id="strip-view"><h2>Ленты</h2><div id="strips"></div></section>
      <section id="composition"><h2>Состав</h2><div id="comp"></div></section>
      <section id="math"><h2>RTP</h2><div id="rtp"></div></section>
      <section id="log"><h2>Сообщения</h2><div id="messages"></div></section>
    </main>
  </div>
  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 4: Написать `web/style.css`**

Двухколоночный `grid` (панель 380px + рабочая область), тёмная тема, моноширинный шрифт для чисел. Ленты — горизонтальный `flex` из пяти колонок, каждая колонка — вертикальный `flex` ячеек 44×44 с картинкой `<img src="/img/<файл>">` и подписью id. Блок-стек обводится общей рамкой через класс `.stack-start` / `.stack-mid` / `.stack-end`. Окно 4 ряда подсвечивается классом `.in-window`. Длинные ленты скроллятся внутри своего контейнера — страница по горизонтали не едет.

- [ ] **Step 5: Написать `web/app.js`**

Ванильный JS без сборки. Структура:

```js
const state = {
  game: null,          // ответ /api/import
  imagesFolder: "",
  imageMap: {},        // id -> имя файла
  classes: {},         // id -> класс
  reelset: "",
  reels: [],           // правила по рилам
  activeReel: 0,
  result: null,        // ответ /api/generate
  windowOffset: 0,
};

async function post(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "ошибка запроса");
  return data;
}
```

Дальше — функции `renderSource`, `renderClasses`, `renderRules`, `renderStrips`, `renderComposition`, `renderMath`, `showMessage`. Обработчики кнопок дёргают `post()` и перерисовывают соответствующие блоки.

Обязательные детали поведения:

- длина ленты пересчитывается при каждом изменении количества и показывается рядом с номером рила
- если `/api/generate` вернул непустой `problems`, показываем красным сообщения и не рисуем ленты
- если `stages` содержит `failed`, рисуем ленты, но помечаем рил красным и печатаем оставшиеся нарушения
- «скопировать на все рилы» копирует `state.reels[state.activeReel]` через `structuredClone` во все пять
- у символа без картинки рисуется плашка с номером, а не битая картинка
- блок RTP печатает: `RTP линий`, разбивку по символам и длинам, `1 к X` для линии, скаттера и бонуса, итог, и отдельной строкой с пометкой «оценка» — общий hit rate

- [ ] **Step 6: Написать `run.py`**

```python
"""Точка входа: поднимает локальный сервер и открывает браузер."""

import argparse
import webbrowser

from reelgen.server import Handler, serve


def main() -> None:
    parser = argparse.ArgumentParser(description="Reel Generator")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true", help="не открывать браузер")
    parser.add_argument(
        "--images",
        default="/Users/mark/2_Claude/symbols",
        help="папка с картинками символов по умолчанию",
    )
    args = parser.parse_args()

    Handler.images_folder = args.images
    httpd = serve(args.port)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Reel Generator: {url}")
    print("Остановить — Ctrl+C")
    if not args.no_open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nостановлен")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Тесты зелёные**

Run: `python3 -m unittest tests.test_smoke -v`
Expected: PASS, 5 тестов

- [ ] **Step 8: Ручная проверка в браузере**

Run: `python3 run.py --no-open` в фоне, затем открыть `http://127.0.0.1:8765/`.

Пройти путь целиком: импорт `tests/fixtures/sample_game.py` → указать папку картинок `/Users/mark/2_Claude/symbols` → взять правила из текущих лент `spins_1` → добавить правило `special ↔ special ≥ 6` → Generate → убедиться, что ленты нарисованы картинками, состав сходится по количествам, RTP посчитан.

- [ ] **Step 9: Написать `README.md`**

Коротко: что это, как запустить (`python3 run.py`), как устроены правила, как прогнать тесты, ссылки на спеку и план.

- [ ] **Step 10: Финальный Checkpoint**

Run: `python3 -m unittest discover -s tests -t . -v`
Expected: все тесты зелёные, общее время меньше минуты

---

## Порядок исполнения

Задачи строго по номерам: 1 → 14. Каждая опирается на интерфейсы предыдущих.
Задачи 4 (картинки) и 12 (проект) независимы от математики и могут делаться в любой
момент после задачи 1, но проще идти подряд.
