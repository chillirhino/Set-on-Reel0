"""Сеты. Каждый сет — папка sets/<имя>/ с set.json и картинками в images/.

В set.json лежит всё про сет: ставка, символы с выплатами, поле с линиями.
Правки пишутся сразу, поэтому потерять работу нельзя. «Сохранить как» — копия.
"""

import base64
import json
import os
import random
import re
import shutil
from pathlib import Path

from . import play, strips

ROOT = Path(__file__).resolve().parent.parent
# Хранилище можно увести в сторону (REELGEN_SETS) — тесты не должны трогать рабочие сеты.
SETS = Path(os.environ.get("REELGEN_SETS") or ROOT / "sets")
ACTIVE_FILE = SETS / ".active"
TRASH = SETS / ".trash"
EXPORTS = SETS.parent / "exports"
DEFAULT_SET = "default"

TYPES = ("low", "middle", "high", "special", "wild", "hidden")
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}

# id символов задаются вручную и могут идти с дырами. Потолок тот же, что у
# ссылки на символ в триггерах, — иначе настроенный бонус стало бы не записать.
MAX_ID = 999

DEFAULT_BET = 20
DEFAULT_ROWS = 4
DEFAULT_REELS = 5
MAX_ROWS = 12
MAX_REELS = 10
MAX_STACK = 200
MAX_COUNT = 500
MAX_ON_REEL = 5000  # сколько символов одного вида влезает на один рил
MAX_PATTERN = 100  # потолок множителя паттерна: «хоть ×100»
MAX_ROUNDS = 5_000_000

# 20 стандартных линий для поля 4x5 — с них начинается новый сет.
DEFAULT_PAYLINES = [
    [0, 0, 0, 0, 0],
    [1, 1, 1, 1, 1],
    [2, 2, 2, 2, 2],
    [3, 3, 3, 3, 3],
    [0, 1, 2, 1, 0],
    [1, 2, 3, 2, 1],
    [2, 1, 0, 1, 2],
    [3, 2, 1, 2, 3],
    [0, 1, 0, 1, 0],
    [1, 2, 1, 2, 1],
    [2, 3, 2, 3, 2],
    [1, 0, 1, 0, 1],
    [2, 1, 2, 1, 2],
    [3, 2, 3, 2, 3],
    [0, 1, 1, 1, 0],
    [1, 2, 2, 2, 1],
    [2, 3, 3, 3, 2],
    [1, 0, 0, 0, 1],
    [2, 1, 1, 1, 2],
    [3, 2, 2, 2, 3],
]

_NAME_RE = re.compile(r"^[\w \-]{1,40}$", re.UNICODE)
_LIST_RE = re.compile(r"\[([\d\s,]+)\]")
_INLINE_RE = re.compile(r"\[\s*\d+(?:\s*,\s*\d+)*\s*\]")


class SymbolError(Exception):
    """Понятная UI ошибка."""


# --- папки сетов --------------------------------------------------------------


def clean_name(name: str) -> str:
    name = (name or "").strip()
    if not _NAME_RE.match(name):
        raise SymbolError(
            f"имя сета {name!r} не годится: буквы, цифры, пробел, дефис, до 40 знаков"
        )
    return name


def set_dir(name: str) -> Path:
    return SETS / clean_name(name)


def list_sets() -> list[str]:
    if not SETS.is_dir():
        return []
    return sorted(
        entry.name
        for entry in SETS.iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
    )


def active_set() -> str:
    """Активный сет; если его нет — берём первый попавшийся или заводим default."""
    name = ""
    if ACTIVE_FILE.is_file():
        name = ACTIVE_FILE.read_text(encoding="utf-8").strip()
    names = list_sets()
    if name in names:
        return name
    if names:
        select_set(names[0])
        return names[0]
    create_set(DEFAULT_SET)
    return DEFAULT_SET


def select_set(name: str) -> str:
    name = clean_name(name)
    if not set_dir(name).is_dir():
        raise SymbolError(f"сета {name!r} нет")
    SETS.mkdir(parents=True, exist_ok=True)
    ACTIVE_FILE.write_text(name, encoding="utf-8")
    return name


def create_set(name: str) -> str:
    """Новый сет: без символов, поле 4x5 с 20 стандартными линиями."""
    name = clean_name(name)
    folder = set_dir(name)
    if folder.is_dir():
        raise SymbolError(f"сет {name!r} уже есть")
    (folder / "images").mkdir(parents=True)
    _write(name, _blank(name))
    return select_set(name)


def save_set() -> str:
    """Явно перезаписать активный сет тем, что сейчас в нём. Возвращает имя."""
    name = active_set()
    _write(name, _read(name))
    return name


def copy_set(name: str, overwrite: bool = False) -> str:
    """Копия активного сета вместе с картинками. Становится активной."""
    name = clean_name(name)
    target = set_dir(name)
    source = set_dir(active_set())
    if target.is_dir():
        if not overwrite:
            raise SymbolError(f"сет {name!r} уже есть — выбери другое имя")
        if target.resolve() == source.resolve():
            return save_set()
        _to_trash(target)  # перезаписанный сет остаётся в корзине
    shutil.copytree(source, target)
    doc = _read(name)
    doc["name"] = name
    _write(name, doc)
    return select_set(name)


def rename_set(old: str, new: str) -> str:
    old, new = clean_name(old), clean_name(new)
    if old == new:
        return old
    if not set_dir(old).is_dir():
        raise SymbolError(f"сета {old!r} нет")
    if set_dir(new).is_dir():
        raise SymbolError(f"сет {new!r} уже есть")
    was_active = active_set() == old
    set_dir(old).rename(set_dir(new))
    doc = _read(new)
    doc["name"] = new
    _write(new, doc)
    return select_set(new) if was_active else new


def delete_set(name: str) -> str:
    name = clean_name(name)
    folder = set_dir(name)
    if not folder.is_dir():
        raise SymbolError(f"сета {name!r} нет")
    _to_trash(folder)
    ACTIVE_FILE.unlink(missing_ok=True)
    return active_set()


def _to_trash(folder: Path) -> Path:
    """Сеты не удаляем совсем: уносим в sets/.trash, откуда их видно и можно вернуть."""
    TRASH.mkdir(parents=True, exist_ok=True)
    target = TRASH / folder.name
    suffix = 2
    while target.exists():
        target = TRASH / f"{folder.name} ({suffix})"
        suffix += 1
    shutil.move(str(folder), str(target))
    return target


def list_trash() -> list[str]:
    if not TRASH.is_dir():
        return []
    return sorted(entry.name for entry in TRASH.iterdir() if entry.is_dir())


def restore_set(name: str) -> str:
    """Вернуть сет из корзины. Имя занято — добавим пометку «возврат»."""
    source = TRASH / Path(name).name
    if not source.is_dir():
        raise SymbolError(f"в корзине нет {name!r}")
    base = re.sub(r" \(\d+\)$", "", source.name)
    target = SETS / base
    suffix = 2
    while target.exists():
        target = SETS / f"{base} возврат {suffix}"
        suffix += 1
    shutil.move(str(source), str(target))
    doc = _read(target.name)
    doc["name"] = target.name
    _write(target.name, doc)
    return select_set(target.name)


def export_set(name: str = "") -> dict:
    """Сет одним файлом: настройки плюс картинки в base64. Копию кладём в exports/."""
    name = clean_name(name or active_set())
    if not set_dir(name).is_dir():
        raise SymbolError(f"сета {name!r} нет")

    images: dict[str, str] = {}
    folder = _images(name)
    if folder.is_dir():
        for entry in sorted(folder.iterdir()):
            if entry.is_file() and entry.suffix.lower() in IMAGE_EXTS:
                images[entry.name] = base64.b64encode(entry.read_bytes()).decode("ascii")

    bundle = {
        "format": "reelgen-set",
        "version": 1,
        "name": name,
        "set": _read(name),
        "images": images,
    }
    EXPORTS.mkdir(parents=True, exist_ok=True)
    path = EXPORTS / f"{name}.rgset.json"
    path.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    return {"bundle": bundle, "file": f"{path.parent.name}/{path.name}", "name": name}


def import_set(bundle, wanted: str = "") -> str:
    """Разворачиваем файл в новый сет. Имя занято — добавим номер."""
    if not isinstance(bundle, dict) or bundle.get("format") != "reelgen-set":
        raise SymbolError("это не файл сета: нет метки reelgen-set")

    base = (wanted or bundle.get("name") or "импорт").strip()
    try:
        base = clean_name(base)
    except SymbolError:
        base = "импорт"
    name, suffix = base, 2
    while set_dir(name).is_dir():
        name = f"{base} {suffix}"
        suffix += 1

    (_images(name)).mkdir(parents=True, exist_ok=True)
    for filename, payload in (bundle.get("images") or {}).items():
        safe = Path(str(filename)).name
        if Path(safe).suffix.lower() not in IMAGE_EXTS:
            continue
        (_images(name) / safe).write_bytes(_decode(payload))

    doc = bundle.get("set") or {}
    doc["name"] = name
    _write(name, doc)
    return select_set(name)


def state() -> dict:
    """Всё, что нужно интерфейсу за один запрос.

    `derived` — что реально пойдёт в генерацию: в режиме мастера это вывод по
    множителям, иначе те же пять рилов. Считает сервер, а не интерфейс: иначе
    график состава показывал бы вторую реализацию тех же правил, и она рано или
    поздно разошлась бы с настоящей.
    """
    name = active_set()
    doc = _read(name)
    return {
        "sets": list_sets(),
        "active": name,
        "trash": list_trash(),
        **doc,
        "derived": effective_reels(doc),
    }


# --- чтение и запись set.json -------------------------------------------------


def _doc_path(name: str) -> Path:
    return set_dir(name) / "set.json"


def _images(name: str) -> Path:
    return set_dir(name) / "images"


def _blank(name: str) -> dict:
    return {
        "name": name,
        "bet": DEFAULT_BET,
        "field": {
            "rows": DEFAULT_ROWS,
            "reels": DEFAULT_REELS,
            "paylines": [list(line) for line in DEFAULT_PAYLINES],
        },
        "symbols": [],
        # Группы задают членство, но не значения: группа пишет одно и то же во всех
        # своих символов, поэтому reels остаётся обычным и генерация о группах не знает.
        # Членство общее на сет, значения у каждого рила свои.
        "groups": [],
        "gaps": [],
        # low как прослойка: укладчик стремится чередовать дешёвое и ценное.
        # Один тумблер на сет — это стиль всей игры, а не отдельного барабана.
        "filler_low": False,
        "triggers": {
            "bonus": {"symbol": 0, "min": 6, "ant_min": 4, "ant_each": False, "ant_reels": [1, 2, 3, 4]},
            "fs": {"symbol": 0, "min": 3, "ant_min": 1, "ant_each": True, "ant_reels": [1, 3]},
        },
        # Мастер-рил: один конфиг, из которого множителями паттерна выводятся все
        # пять. Сами пять при этом лежат нетронутыми — выключение режима возвращает
        # ручную настройку как была.
        "master": {},
        "master_on": False,
        # цель → {max: потолок множителя, mult: множитель на каждый рил}
        "pattern": {},
        "reels": [{} for _ in range(DEFAULT_REELS)],
        "seeds": [index + 1 for index in range(DEFAULT_REELS)],
        "strips": [[] for _ in range(DEFAULT_REELS)],
        "stats": [{"glued": 0, "broken": 0} for _ in range(DEFAULT_REELS)],
    }


def _read(name: str) -> dict:
    path = _doc_path(name)
    legacy = set_dir(name) / "symbols.json"
    raw: dict = {}
    if path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8"))
    elif legacy.is_file():  # сеты, сделанные до появления поля и выплат
        raw = json.loads(legacy.read_text(encoding="utf-8"))
    return _normalize(name, raw if isinstance(raw, dict) else {})


def _write(name: str, doc: dict) -> None:
    set_dir(name).mkdir(parents=True, exist_ok=True)
    text = json.dumps(_normalize(name, doc), ensure_ascii=False, indent=2)
    # линии читаются глазами, поэтому держим их в одну строку: [0, 1, 2, 1, 0]
    text = _INLINE_RE.sub(lambda m: "[" + ", ".join(re.findall(r"\d+", m.group(0))) + "]", text)
    _doc_path(name).write_text(text, encoding="utf-8")
    _flush_images()


def _normalize(name: str, raw: dict) -> dict:
    """Чиним что угодно до валидного документа: размеры поля, линии, выплаты."""
    doc = _blank(name)
    doc["bet"] = _positive(raw.get("bet"), DEFAULT_BET)

    field = raw.get("field") or {}
    rows = _clamp(field.get("rows"), 1, MAX_ROWS, DEFAULT_ROWS)
    reels = _clamp(field.get("reels"), 1, MAX_REELS, DEFAULT_REELS)
    lines = field.get("paylines")
    if lines is None:  # старый сет без поля — даём стандартные линии
        lines = [list(line) for line in DEFAULT_PAYLINES]
    doc["field"] = {
        "rows": rows,
        "reels": reels,
        "paylines": [_fit_line(line, rows, reels) for line in lines],
    }

    doc["symbols"] = sorted(
        (_fit_symbol(item) for item in raw.get("symbols", []) if isinstance(item, dict)),
        key=lambda item: item["id"],
    )
    _fit_weights(doc["symbols"])
    doc["groups"] = _fit_groups(raw.get("groups"), doc["symbols"])

    doc["gaps"] = [
        rule
        for rule in (_fit_gap(item) for item in raw.get("gaps", []) if isinstance(item, dict))
        if rule
    ]

    doc["filler_low"] = bool(raw.get("filler_low"))

    stored_triggers = raw.get("triggers") or {}
    blank = _blank(name)["triggers"]
    doc["triggers"] = {
        "bonus": _fit_trigger(stored_triggers.get("bonus"), blank["bonus"], reels),
        "fs": _fit_trigger(stored_triggers.get("fs"), blank["fs"], reels),
    }

    stored = raw.get("reels") or []
    doc["reels"] = [
        _fit_reel(stored[index] if index < len(stored) else None) for index in range(reels)
    ]
    doc["master"] = _fit_reel(raw.get("master"))
    doc["master_on"] = bool(raw.get("master_on"))
    doc["pattern"] = _fit_pattern(raw.get("pattern"), reels)
    # у каждого рила свой сид; старые сеты знали один общий — разворачиваем его
    stored_seeds = raw.get("seeds")
    if not isinstance(stored_seeds, list):
        base = _clamp(raw.get("seed"), 0, 10**9, 1)
        stored_seeds = [base * 1000 + index for index in range(reels)]
    doc["seeds"] = [
        _clamp(stored_seeds[index] if index < len(stored_seeds) else None, 0, 10**9, index + 1)
        for index in range(reels)
    ]

    stored_strips = [
        [int(value) for value in strip if isinstance(value, (int, float))]
        for strip in (raw.get("strips") or [])
        if isinstance(strip, list)
    ]
    doc["strips"] = [
        stored_strips[index] if index < len(stored_strips) else [] for index in range(reels)
    ]

    stored_stats = raw.get("stats") or []
    doc["stats"] = [
        {
            "glued": _clamp((stored_stats[index] or {}).get("glued"), 0, 10**6, 0),
            "broken": _clamp((stored_stats[index] or {}).get("broken"), 0, 10**6, 0),
        }
        if index < len(stored_stats) and isinstance(stored_stats[index], dict)
        else {"glued": 0, "broken": 0}
        for index in range(reels)
    ]
    return doc


def _fit_pattern(raw, reels: int) -> dict:
    """Паттерн: цель → потолок множителя и множитель на каждый рил.

    Цель это 'id:N' или 'group:имя' — та же запись, что уже используют правила
    пересечения. Отсутствие записи означает ×1 на всех рилах, то есть «ровно как
    в мастере»: паттерн по умолчанию ничего не меняет.

    Храним множитель, а не положение ползунка: тогда правка потолка ×3 → ×5 не
    двигает количества, а только растягивает шкалу под ползунком.
    """
    fixed: dict[str, dict] = {}
    for key, item in (raw or {}).items():
        if not isinstance(item, dict):
            continue
        kind, _, value = str(key).partition(":")
        if kind not in ("id", "group") or not value:
            continue
        top = min(max(_positive(item.get("max"), 2), 1), MAX_PATTERN)
        stored = item.get("mult") if isinstance(item.get("mult"), list) else []
        row = []
        for index in range(reels):
            try:
                number = float(stored[index])
            except (TypeError, ValueError, IndexError):
                number = 1.0
            row.append(min(max(number, 0.0), top))

        # Приоритет стеков заданный руками: сколько стеков этой длины стоит на
        # этом риле. None значит «не трогал» — берётся из мастера и правится
        # общим множителем. Явное число бьёт и мастер, и множитель.
        counts: dict[str, list] = {}
        for key, stored_row in (item.get("counts") or {}).items():
            try:
                length = int(key)
            except (TypeError, ValueError):
                continue
            if not 1 <= length <= MAX_STACK or not isinstance(stored_row, list):
                continue
            hand = []
            for index in range(reels):
                try:
                    hand.append(min(max(int(stored_row[index]), 0), MAX_COUNT))
                except (TypeError, ValueError, IndexError):
                    hand.append(None)
            if any(value is not None for value in hand):  # ничего не задано — не храним
                counts[str(length)] = hand

        fixed[f"{kind}:{value}"] = {"max": top, "mult": row, "counts": counts}
    return fixed


def _fit_groups(raw, symbols: list[dict]) -> list[dict]:
    """Группы символов: имя и члены.

    Символ состоит максимум в одной группе — иначе «применить ко всем» перестаёт
    иметь однозначный смысл. Мёртвые id выбрасываем: символ могли удалить.
    """
    alive = {symbol["id"] for symbol in symbols}
    taken: set[int] = set()
    names: set[str] = set()
    groups: list[dict] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or name in names:
            continue
        members: list[int] = []
        for value in item.get("members") or []:
            try:
                symbol_id = int(value)
            except (TypeError, ValueError):
                continue
            if symbol_id in alive and symbol_id not in taken:
                members.append(symbol_id)
                taken.add(symbol_id)
        names.add(name)
        groups.append({"name": name, "members": sorted(members)})
    return groups


def _fit_gap(raw: dict) -> dict | None:
    """Правило дистанции: между a и b минимум min символов класса filler."""
    a, b = _fit_target(raw.get("a")), _fit_target(raw.get("b"))
    if not a or not b:
        return None
    filler = raw.get("filler")
    if filler not in TYPES and filler != "any":
        filler = "low"
    return {"a": a, "b": b, "min": _clamp(raw.get("min"), 0, MAX_STACK, 1), "filler": filler}


def _fit_target(raw) -> str:
    """'id:13' или 'type:special'; всё остальное отбрасываем."""
    kind, _, value = str(raw or "").partition(":")
    if kind == "type" and value in TYPES:
        return f"type:{value}"
    if kind == "id":
        try:
            return f"id:{int(value)}"
        except ValueError:
            return ""
    return ""


def _fit_trigger(raw, blank: dict, reels: int) -> dict:
    """Триггер: сколько символов на поле собирает бонус/фриспины.

    Плюс антисипейшн — условие «намечается»: сколько символов должно лежать
    на указанных рилах, суммарно или на каждом.
    """
    raw = raw if isinstance(raw, dict) else {}
    ant_reels = raw.get("ant_reels")
    if not isinstance(ant_reels, list):
        ant_reels = blank["ant_reels"]
    ant_reels = sorted({number for number in (_clamp(item, 1, reels, 0) for item in ant_reels) if number})
    return {
        "symbol": _clamp(raw.get("symbol"), 0, 999, 0),  # 0 — триггер не настроен
        "min": _clamp(raw.get("min"), 1, 60, blank["min"]),
        "ant_min": _clamp(raw.get("ant_min"), 1, 60, blank["ant_min"]),
        "ant_each": bool(raw.get("ant_each", blank["ant_each"])),
        "ant_reels": ant_reels or blank["ant_reels"][:reels],
    }


def set_triggers(bonus, fs) -> dict:
    name = active_set()
    doc = _read(name)
    doc["triggers"] = {"bonus": bonus, "fs": fs}
    _write(name, doc)
    return _read(name)["triggers"]


def _fit_reel(raw) -> dict:
    """Конфиг одного рила: id символа → сколько его всего, шансы длин, флаг ∞."""
    if not isinstance(raw, dict):
        return {}
    fixed: dict[str, dict] = {}
    for key, value in raw.items():
        try:
            symbol_id = int(key)
        except (TypeError, ValueError):
            continue
        if not isinstance(value, dict):
            continue
        entry = _fit_reel_symbol(value)
        if entry:
            fixed[str(symbol_id)] = entry
    return fixed


def _fit_reel_symbol(raw: dict) -> dict | None:
    """Символ на риле: сколько стеков каждой длины.

    `count` и `stacks_total` — производные: считаются из `stacks` при каждом
    чтении, поэтому разойтись с ними не могут. Лежат в документе для удобства
    интерфейса и читаемости файла.

    Две прежние формы переводятся на месте, чтобы сеты открывались без потерь:
    список `[[длина, стеков], …]` и пара «количество символов + шансы».
    """
    stacks: dict[str, int] = {}
    stored = raw.get("stacks")
    if isinstance(stored, dict):
        for key, value in stored.items():
            try:
                length, times = int(key), int(value)
            except (TypeError, ValueError):
                continue
            if 1 <= length <= MAX_STACK and times >= 1:
                stacks[str(length)] = min(times, MAX_COUNT)
    elif isinstance(stored, list):
        stacks = _from_pairs(stored)
    elif raw.get("count"):
        stacks = _from_count(raw)

    infinity = bool(raw.get("infinity"))
    total = strips.symbols_of(stacks)
    if not total and not infinity:
        return None
    return {
        "stacks": {key: stacks[key] for key in sorted(stacks, key=int)},
        "infinity": infinity,
        "count": min(total, MAX_ON_REEL),
        "stacks_total": sum(stacks.values()),
    }


def _from_pairs(pairs) -> dict[str, int]:
    """Самый старый вид: список пар [длина, сколько стеков]."""
    stacks: dict[str, int] = {}
    for pair in pairs or []:
        try:
            length, times = int(pair[0]), int(pair[1])
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        if length >= 1 and times >= 1:
            key = str(min(length, MAX_STACK))
            stacks[key] = min(stacks.get(key, 0) + times, MAX_COUNT)
    return stacks


def _from_count(raw: dict) -> dict[str, int]:
    """Вид «количество символов + шансы на длину» → число стеков по каждой длине.

    Держимся состава: подбираем целые числа стеков так, чтобы сумма символов
    была как можно ближе к заказанной, а форма разброса — к прежним шансам.
    RTP линий зависит только от количеств, поэтому так он сдвинется минимально.
    """
    count = _clamp(raw.get("count"), 0, MAX_ON_REEL, 0)
    chances: dict[int, float] = {}
    for key, value in (raw.get("sizes") or {}).items():
        try:
            length, chance = int(key), float(value)
        except (TypeError, ValueError):
            continue
        if 1 <= length <= MAX_STACK and chance > 0:
            chances[length] = chance
    if not count:
        return {}
    if not chances:  # длины не задавались — символ ложился по одному
        return {"1": count}

    weight = sum(chances.values())
    average = sum(length * chance for length, chance in chances.items()) / weight
    lengths = sorted(chances)

    # стартовая раскладка: делим ожидаемое число стеков по долям шансов
    stacks = {
        length: max(1, round(count / average * chances[length] / weight)) for length in lengths
    }
    # и подтягиваем к заказанному количеству, двигая по одному стеку за шаг
    for _ in range(MAX_ON_REEL):
        total = sum(length * times for length, times in stacks.items())
        if total == count:
            break
        step = 1 if total < count else -1
        # шагаем самой длинной подходящей длиной — так подгонка короче
        moved = False
        for length in sorted(lengths, key=lambda item: -abs(item - abs(count - total))):
            if step < 0 and stacks[length] <= 0:
                continue
            after = total + step * length
            if abs(after - count) < abs(total - count):
                stacks[length] += step
                moved = True
                break
        if not moved:
            break
    return {str(length): times for length, times in stacks.items() if times > 0}


def _fit_symbol(raw: dict) -> dict:
    """Выплаты длиннее поля не выбрасываем: вдруг барабаны ужали по ошибке."""
    pays: dict[str, float] = {}
    for key, value in (raw.get("pays") or {}).items():
        try:
            length, amount = int(key), float(value)
        except (TypeError, ValueError):
            continue
        if 1 <= length <= MAX_REELS and amount > 0:
            pays[str(length)] = int(amount) if amount == int(amount) else amount

    weights: dict[str, float] = {}
    for key, value in (raw.get("weights") or {}).items():
        try:
            target, weight = int(key), float(value)
        except (TypeError, ValueError):
            continue
        if 1 <= target <= MAX_ID and weight > 0:
            weights[str(target)] = int(weight) if weight == int(weight) else weight

    kind = raw.get("type")
    return {
        "id": int(raw.get("id", 0)),
        "type": kind if kind in TYPES else "low",
        "name": str(raw.get("name") or ""),
        "image": str(raw.get("image") or ""),
        "pays": pays,
        "weights": weights,
    }


def _fit_weights(symbols: list[dict]) -> None:
    """Целью превращения может быть любой живой символ, кроме hidden-ов.

    Проверка отдельным проходом, а не внутри _fit_symbol: та видит один символ и
    про типы соседей ничего не знает. У символа, которому тип hidden сняли, веса
    не стираем — иначе случайная смена типа туда-обратно уносила бы таблицу.
    """
    allowed = {symbol["id"] for symbol in symbols if symbol["type"] != "hidden"}
    for symbol in symbols:
        symbol["weights"] = {
            target: weight
            for target, weight in symbol["weights"].items()
            if int(target) in allowed
        }


def _fit_line(raw, rows: int, reels: int) -> list[int]:
    """Линия всегда длиной в число барабанов и в пределах числа рядов."""
    line = [int(value) for value in (raw or []) if isinstance(value, (int, float))]
    while len(line) < reels:
        line.append(line[-1] if line else 0)
    return [min(max(value, 0), rows - 1) for value in line[:reels]]


def _clamp(value, low: int, high: int, fallback: int) -> int:
    try:
        return min(max(int(value), low), high)
    except (TypeError, ValueError):
        return fallback


def _positive(value, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number <= 0:
        return fallback
    return int(number) if number == int(number) else number


# --- ставка и поле ------------------------------------------------------------


def set_bet(bet) -> float:
    name = active_set()
    doc = _read(name)
    doc["bet"] = _positive(bet, doc["bet"])
    _write(name, doc)
    return doc["bet"]


def set_size(rows, reels) -> dict:
    """Меняет размер поля; линии подрезаются/дотягиваются под новый размер."""
    name = active_set()
    doc = _read(name)
    doc["field"]["rows"] = _clamp(rows, 1, MAX_ROWS, doc["field"]["rows"])
    doc["field"]["reels"] = _clamp(reels, 1, MAX_REELS, doc["field"]["reels"])
    _write(name, doc)  # _normalize подгонит линии и выплаты под новый размер
    return _read(name)["field"]


def set_lines(lines) -> list[list[int]]:
    name = active_set()
    doc = _read(name)
    doc["field"]["paylines"] = list(lines or [])
    _write(name, doc)
    return _read(name)["field"]["paylines"]


def reset_lines() -> list[list[int]]:
    """Вернуть 20 стандартных линий (подгонятся под текущий размер поля)."""
    return set_lines([list(line) for line in DEFAULT_PAYLINES])


def parse_lines(text: str) -> list[list[int]]:
    """Разбирает текст вида payline_01 = [0, 0, 0, 0, 0] — по строке на линию."""
    found = [
        [int(part) for part in chunk.replace(",", " ").split()]
        for chunk in _LIST_RE.findall(text or "")
    ]
    found = [line for line in found if line]
    if not found:
        raise SymbolError("не нашёл ни одной линии — жду строки вида [0, 1, 2, 1, 0]")
    return found


def paste_lines(text: str) -> dict:
    """Вставка линий текстом. Поле подстраивается под длину и высоту линий."""
    lines = parse_lines(text)
    name = active_set()
    doc = _read(name)
    widths = {len(line) for line in lines}
    if len(widths) == 1:
        doc["field"]["reels"] = _clamp(widths.pop(), 1, MAX_REELS, doc["field"]["reels"])
    highest = max(max(line) for line in lines) + 1
    doc["field"]["rows"] = _clamp(
        max(highest, doc["field"]["rows"]), 1, MAX_ROWS, doc["field"]["rows"]
    )
    doc["field"]["paylines"] = lines
    _write(name, doc)
    return _read(name)["field"]


# --- правила пересечения ------------------------------------------------------


def set_gaps(rules) -> list[dict]:
    name = active_set()
    doc = _read(name)
    doc["gaps"] = list(rules or [])
    _write(name, doc)
    return _read(name)["gaps"]


# --- нумерация символов -------------------------------------------------------


def set_id(old_id: int, new_id: int) -> dict:
    """Сменить id символа. Номера свободные — дыры в нумерации это нормально.

    Если номер занят, символы меняются номерами. Отказ здесь был бы отказом от
    самой возможности переставлять: в сете, пронумерованном подряд, занято всё,
    и «сделай этот символ пятым» не сработало бы никогда. Обмен ничего не теряет
    — оба символа увозят с собой картинки, стеки, правила и ленты, — и его видно
    в ответе, так что второй символ не меняется молча.
    """
    current = active_set()
    doc = _read(current)
    _find(doc["symbols"], old_id)

    try:
        new_id = int(new_id)
    except (TypeError, ValueError) as exc:
        raise SymbolError(f"непонятный id {new_id!r}") from exc
    if not 1 <= new_id <= MAX_ID:
        raise SymbolError(f"id {new_id} вне диапазона 1..{MAX_ID}")
    if new_id == old_id:
        return _find(doc["symbols"], old_id)

    taken = next((item for item in doc["symbols"] if item["id"] == new_id), None)
    mapping = {old_id: new_id}
    if taken is not None:
        mapping[new_id] = old_id

    _apply_ids(current, doc, mapping)
    _write(current, doc)
    return _find(_read(current)["symbols"], new_id)


def _apply_ids(set_name: str, doc: dict, mapping: dict[int, int]) -> None:
    """Переносит по отображению всё, что на символы ссылается, за один проход.

    Ссылок больше, чем кажется: картинка названа по id, стеки на рилах лежат под
    ключом-id, правила пересечения целятся в 'id:N', уже сгенерированные ленты
    хранят id прямо в значениях, и на символ смотрят триггеры и веса hidden-ов.

    Один проход, а не два вызова подряд: при обмене номерами 3 и 7 после первой
    половины оба символа оказались бы на одном номере.
    """
    for symbol in doc["symbols"]:
        if symbol["id"] in mapping:
            symbol["image"] = _move_image(set_name, symbol["image"], mapping[symbol["id"]])
            symbol["id"] = mapping[symbol["id"]]
    doc["symbols"].sort(key=lambda item: item["id"])

    doc["reels"] = [
        {str(mapping.get(int(key), int(key))): value for key, value in reel.items()}
        for reel in doc["reels"]
    ]
    doc["master"] = {
        str(mapping.get(int(key), int(key))): value for key, value in doc["master"].items()
    }
    doc["pattern"] = {
        (
            f"id:{mapping.get(int(key.partition(':')[2]), int(key.partition(':')[2]))}"
            if key.startswith("id:")
            else key
        ): entry
        for key, entry in doc["pattern"].items()
    }

    doc["gaps"] = [
        {
            **rule,
            "a": _remap_target(rule["a"], mapping),
            "b": _remap_target(rule["b"], mapping),
        }
        for rule in doc["gaps"]
    ]

    doc["strips"] = [
        [mapping.get(value, value) for value in strip] for strip in doc["strips"]
    ]

    for trigger in doc["triggers"].values():
        if trigger.get("symbol") in mapping:
            trigger["symbol"] = mapping[trigger["symbol"]]

    for item in doc["symbols"]:
        item["weights"] = {
            str(mapping.get(int(target), int(target))): weight
            for target, weight in (item.get("weights") or {}).items()
        }

    for group in doc["groups"]:
        group["members"] = sorted(
            mapping.get(member, member) for member in group["members"]
        )


def _move_image(set_name: str, image_name: str, new_id: int) -> str:
    """Картинка называется по id, поэтому при перенумерации переезжает."""
    if not image_name:
        return ""
    source = image_path(set_name, image_name)
    if source is None:
        return ""
    target = source.with_name(f"sym_{new_id:02d}{source.suffix}")
    if target == source:
        return source.name
    staging = source.with_name(f"~{source.name}")  # чтобы не затереть чужой файл на полпути
    source.rename(staging)
    _PENDING.append((staging, target))
    return target.name


_PENDING: list[tuple[Path, Path]] = []


def _flush_images() -> None:
    """Вторая фаза переименования: временные имена → окончательные."""
    while _PENDING:
        staging, target = _PENDING.pop(0)
        target.unlink(missing_ok=True)
        staging.rename(target)


def _remap_target(target: str, mapping: dict[int, int]) -> str:
    """Правило, целящееся в чужой символ, трогать нельзя — оно остаётся как есть."""
    kind, _, value = target.partition(":")
    if kind != "id":
        return target
    old = int(value)
    return f"id:{mapping.get(old, old)}"


# --- ленты --------------------------------------------------------------------


def _symbol_key(doc: dict, symbol_id) -> str:
    """Проверяем, что символ вообще существует: иначе в конфиг попал бы мёртвый id."""
    try:
        number = int(symbol_id)
    except (TypeError, ValueError) as exc:
        raise SymbolError(f"непонятный id символа {symbol_id!r}") from exc
    return str(_find(doc["symbols"], number)["id"])


def _reel_entry(stacks, infinity) -> dict:
    return {"stacks": dict(stacks or {}), "infinity": bool(infinity)}


def set_reel_symbol(reel: int, symbol_id, stacks, infinity) -> dict:
    """Символ на одном риле: сколько стеков каждой длины. Пусто — символа нет."""
    name = active_set()
    doc = _read(name)
    reel = _reel_index(doc, reel)
    key = _symbol_key(doc, symbol_id)
    entry = _reel_entry(stacks, infinity)
    if _fit_reel_symbol(entry):
        doc["reels"][reel][key] = entry
    else:
        doc["reels"][reel].pop(key, None)
    _write(name, doc)
    return _read(name)["reels"][reel]


# --- группы символов ----------------------------------------------------------
#
# Группа — пульт «поставь всем одинаково», а не хранилище. Она пишет одно и то же
# количество, шансы и флаг ∞ во все свои символы, поэтому в файле у неё только
# членство. Удалили группу — значения остались на месте, просто перестали быть
# связанными.


def _clean_group(name: str) -> str:
    name = (name or "").strip()
    if not _NAME_RE.match(name):
        raise SymbolError(
            f"имя группы {name!r} не годится: буквы, цифры, пробел, дефис, до 40 знаков"
        )
    return name


def _find_group(groups: list[dict], name: str) -> dict:
    for group in groups:
        if group["name"] == name:
            return group
    raise SymbolError(f"группы {name!r} нет")


def group_of(doc: dict, symbol_id: int) -> dict | None:
    for group in doc["groups"]:
        if symbol_id in group["members"]:
            return group
    return None


def create_group(name: str) -> dict:
    current = active_set()
    doc = _read(current)
    name = _clean_group(name)
    if any(group["name"] == name for group in doc["groups"]):
        raise SymbolError(f"группа {name!r} уже есть")
    doc["groups"].append({"name": name, "members": []})
    _write(current, doc)
    return _find_group(_read(current)["groups"], name)


def rename_group(old: str, new: str) -> dict:
    current = active_set()
    doc = _read(current)
    old, new = _clean_group(old), _clean_group(new)
    group = _find_group(doc["groups"], old)
    if new != old and any(item["name"] == new for item in doc["groups"]):
        raise SymbolError(f"группа {new!r} уже есть")
    group["name"] = new
    # паттерн целится в группу по имени, поэтому переименование тянет и его
    entry = doc["pattern"].pop(f"group:{old}", None)
    if entry is not None:
        doc["pattern"][f"group:{new}"] = entry
    _write(current, doc)
    return _find_group(_read(current)["groups"], new)


def delete_group(name: str) -> None:
    """Разбираем группу. Значения символов не трогаем — терять их не за что."""
    current = active_set()
    doc = _read(current)
    name = _clean_group(name)
    _find_group(doc["groups"], name)
    doc["groups"] = [item for item in doc["groups"] if item["name"] != name]
    doc["pattern"].pop(f"group:{name}", None)
    _write(current, doc)


def set_group_member(name: str, symbol_id, join: bool = True) -> list[dict]:
    """Ввести символ в группу или вывести. Из прежней группы он выбывает сам."""
    current = active_set()
    doc = _read(current)
    group = _find_group(doc["groups"], _clean_group(name))
    symbol = _find(doc["symbols"], int(symbol_id))

    for item in doc["groups"]:
        item["members"] = [member for member in item["members"] if member != symbol["id"]]
    if join:
        group["members"] = sorted(group["members"] + [symbol["id"]])

    _write(current, doc)
    return _read(current)["groups"]


def set_reel_group(reel: int, name: str, stacks, infinity) -> dict:
    """Одно значение во все символы группы. Пустое — символы уходят с рила."""
    current = active_set()
    doc = _read(current)
    index = _reel_index(doc, reel)
    group = _find_group(doc["groups"], _clean_group(name))
    if not group["members"]:
        raise SymbolError(f"в группе {group['name']!r} нет символов")

    entry = _reel_entry(stacks, infinity)
    keep = _fit_reel_symbol(entry) is not None
    for symbol_id in group["members"]:
        key = str(symbol_id)
        if keep:
            doc["reels"][index][key] = json.loads(json.dumps(entry))
        else:
            doc["reels"][index].pop(key, None)
    _write(current, doc)
    return _read(current)["reels"][index]


# --- мастер-рил и паттерн -----------------------------------------------------
#
# Мастер-рил — единственный конфиг, который правят руками. Пять рилов выводятся
# из него множителями паттерна: ползунок в середине даёт ×1, в нуле убирает
# символ с рила совсем, в максимуме даёт ×N, где N задаётся на каждую цель своим.
#
# Выводятся на ходу, а не записываются: ручная настройка пяти рилов лежит рядом
# нетронутой, поэтому выключение режима возвращает её целиком.


def target_of(doc: dict, symbol_id: int) -> str:
    """Цель паттерна для символа: своя группа, если есть, иначе он сам.

    Члены группы не имеют отдельной цели — иначе один символ тянули бы две
    настройки, групповая и своя, и было бы непонятно, какая сильнее.
    """
    group = group_of(doc, symbol_id)
    return f"group:{group['name']}" if group else f"id:{symbol_id}"


def multiplier(doc: dict, symbol_id: int, reel: int) -> float:
    entry = doc["pattern"].get(target_of(doc, symbol_id))
    if not entry:
        return 1.0
    try:
        return float(entry["mult"][reel])
    except (IndexError, TypeError, ValueError):
        return 1.0


def stack_override(doc: dict, symbol_id: int, reel: int, length) -> int | None:
    """Сколько стеков этой длины задано руками на этом риле, или None.

    Явное число сильнее и мастера, и общего множителя: руками — значит руками.
    Где не задано, работает мастер с множителем.
    """
    entry = doc["pattern"].get(target_of(doc, symbol_id))
    if not entry:
        return None
    try:
        value = entry["counts"][str(int(length))][reel]
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return None if value is None else int(value)


def effective_reels(doc: dict) -> list[dict]:
    """Что реально пойдёт в генерацию: либо ручные пять рилов, либо вывод мастера.

    Множитель масштабирует **число стеков**, а не число символов: иначе он снова
    порождал бы остаток и одиночные символы, от которых мы и ушли. Количество
    символов пересчитывается из стеков само.
    """
    if not doc["master_on"]:
        return doc["reels"]
    derived = []
    for index in range(len(doc["reels"])):
        reel: dict[str, dict] = {}
        for key, entry in doc["master"].items():
            factor = multiplier(doc, int(key), index)
            # round() в Python округляет 4.5 к чётному, то есть к 4. Для
            # множителя это сюрприз: половина должна идти вверх.
            scaled = {}
            for length, times in entry["stacks"].items():
                hand = stack_override(doc, int(key), index, length)
                scaled[length] = times * factor + 0.5 if hand is None else hand
                scaled[length] = int(scaled[length])
            scaled = {length: times for length, times in scaled.items() if times > 0}
            if not scaled:  # ползунок в нуле — символа на этом риле нет
                continue
            fixed = _fit_reel_symbol({"stacks": scaled, "infinity": entry["infinity"]})
            if fixed:
                reel[key] = fixed
        derived.append(reel)
    return derived


def set_master_mode(value, from_reel=None) -> bool:
    """Включение режима сеет мастер из указанного рила, если мастер ещё пуст."""
    name = active_set()
    doc = _read(name)
    doc["master_on"] = bool(value)
    if doc["master_on"] and not doc["master"] and from_reel is not None:
        doc["master"] = json.loads(json.dumps(doc["reels"][_reel_index(doc, from_reel)]))
    _write(name, doc)
    return _read(name)["master_on"]


def set_master_symbol(symbol_id, stacks, infinity) -> dict:
    name = active_set()
    doc = _read(name)
    key = _symbol_key(doc, symbol_id)
    entry = _reel_entry(stacks, infinity)
    if _fit_reel_symbol(entry):
        doc["master"][key] = entry
    else:
        doc["master"].pop(key, None)
    _write(name, doc)
    return _read(name)["master"]


def set_master_group(group_name: str, stacks, infinity) -> dict:
    """То же, что и для рила: одно значение во все символы группы."""
    name = active_set()
    doc = _read(name)
    group = _find_group(doc["groups"], _clean_group(group_name))
    if not group["members"]:
        raise SymbolError(f"в группе {group['name']!r} нет символов")
    entry = _reel_entry(stacks, infinity)
    keep = _fit_reel_symbol(entry) is not None
    for symbol_id in group["members"]:
        key = str(symbol_id)
        if keep:
            doc["master"][key] = json.loads(json.dumps(entry))
        else:
            doc["master"].pop(key, None)
    _write(name, doc)
    return _read(name)["master"]


def clear_master() -> dict:
    name = active_set()
    doc = _read(name)
    doc["master"] = {}
    _write(name, doc)
    return {}


def set_pattern(target: str, reel=None, mult=None, top=None) -> dict:
    """Правка паттерна: множитель на одном риле и/или потолок для цели."""
    name = active_set()
    doc = _read(name)
    kind, _, value = str(target or "").partition(":")
    if kind == "id":
        _find(doc["symbols"], int(value))
    elif kind == "group":
        _find_group(doc["groups"], _clean_group(value))
    else:
        raise SymbolError(f"непонятная цель паттерна {target!r}")

    key = f"{kind}:{value}"
    entry = doc["pattern"].get(key) or {"max": 2, "mult": [1.0] * len(doc["reels"])}
    if top is not None:
        entry["max"] = top
    if reel is not None:
        index = _reel_index(doc, reel)
        row = list(entry.get("mult") or [])
        while len(row) < len(doc["reels"]):
            row.append(1.0)
        try:
            row[index] = float(str(mult).replace(",", "."))
        except (TypeError, ValueError) as exc:
            raise SymbolError(f"множитель {mult!r} — не число") from exc
        entry["mult"] = row
    doc["pattern"][key] = entry
    _write(name, doc)
    return _read(name)["pattern"]


def set_pattern_count(target: str, length, reel, value) -> dict:
    """Сколько стеков этой длины стоит на этом риле. Пусто — вернуть как в мастере."""
    name = active_set()
    doc = _read(name)
    # имя не `value`: параметр с этим именем уже занят количеством стеков
    kind, _, value_key = str(target or "").partition(":")
    if kind == "id":
        _find(doc["symbols"], int(value_key))
    elif kind == "group":
        _find_group(doc["groups"], _clean_group(value_key))
    else:
        raise SymbolError(f"непонятная цель паттерна {target!r}")

    try:
        length = int(length)
    except (TypeError, ValueError) as exc:
        raise SymbolError(f"непонятная длина стека {length!r}") from exc
    if not 1 <= length <= MAX_STACK:
        raise SymbolError(f"длина {length} вне диапазона 1..{MAX_STACK}")
    text = str(value).strip() if value is not None else ""
    if text in ("", "-"):
        hand = None  # пусто — снова как в мастере
    else:
        try:
            hand = max(0, int(float(text.replace(",", "."))))
        except (TypeError, ValueError) as exc:
            raise SymbolError(f"количество стеков {value!r} — не число") from exc

    key = f"{kind}:{value_key}"
    entry = doc["pattern"].get(key) or {
        "max": 2,
        "mult": [1.0] * len(doc["reels"]),
        "counts": {},
    }
    index = _reel_index(doc, reel)
    rows = dict(entry.get("counts") or {})
    row = list(rows.get(str(length)) or [])
    while len(row) < len(doc["reels"]):
        row.append(None)
    row[index] = hand
    rows[str(length)] = row
    entry["counts"] = rows
    doc["pattern"][key] = entry
    _write(name, doc)
    return _read(name)["pattern"]


def set_filler_low(value) -> bool:
    """Тумблер «low как прослойка» — один на весь сет."""
    name = active_set()
    doc = _read(name)
    doc["filler_low"] = bool(value)
    _write(name, doc)
    return _read(name)["filler_low"]


def copy_reel_to_all(reel: int) -> list[dict]:
    """Разложить конфиг одного рила на все остальные."""
    name = active_set()
    doc = _read(name)
    reel = _reel_index(doc, reel)
    source = json.loads(json.dumps(doc["reels"][reel]))
    doc["reels"] = [json.loads(json.dumps(source)) for _ in doc["reels"]]
    _write(name, doc)
    return _read(name)["reels"]


def clear_reel(reel: int) -> dict:
    name = active_set()
    doc = _read(name)
    reel = _reel_index(doc, reel)
    doc["reels"][reel] = {}
    _write(name, doc)
    return {}


def generate(reel=None, seed=None, reseed: bool = False) -> dict:
    """Собирает ленты. reel=None — все рилы, иначе только один: остальные не трогаем."""
    name = active_set()
    doc = _read(name)
    indices = (
        list(range(len(doc["reels"]))) if reel is None else [_reel_index(doc, reel)]
    )

    types = {symbol["id"]: symbol["type"] for symbol in doc["symbols"]}
    # в режиме мастера конфиги выводятся, а не берутся из doc["reels"]
    configs = effective_reels(doc)
    for index in indices:
        if seed is not None and len(indices) == 1:
            doc["seeds"][index] = _clamp(seed, 0, 10**9, doc["seeds"][index])
        elif reseed:
            doc["seeds"][index] = random.randrange(1, 1000000)

        built = strips.build(
            configs[index], doc["seeds"][index], doc["gaps"], types, doc["filler_low"]
        )
        doc["strips"][index] = built["strip"]
        doc["stats"][index] = {"glued": built["glued"], "broken": built["broken"]}

    _write(name, doc)
    _write_strips_text(name, doc["strips"])
    return {"stats": doc["stats"], "seeds": doc["seeds"]}


# --- игра и статистика --------------------------------------------------------


def _pay_table(doc: dict) -> dict[int, dict[int, float]]:
    """id символа → {длина: выплата} в удобном для расчёта виде.

    Hidden-ы вычёркиваем: они превращаются до подсчёта линий, поэтому заплатить
    за себя не могут — пусть это будет свойством таблицы, а не договорённостью.
    """
    return {
        symbol["id"]: {int(length): float(amount) for length, amount in symbol["pays"].items()}
        for symbol in doc["symbols"]
        if symbol["type"] != "hidden"
    }


def _types(doc: dict) -> dict[int, str]:
    return {symbol["id"]: symbol["type"] for symbol in doc["symbols"]}


def _weights(doc: dict) -> dict[int, dict[int, float]]:
    """id hidden-символа → {цель: вес}."""
    return {
        symbol["id"]: {int(target): float(weight) for target, weight in symbol["weights"].items()}
        for symbol in doc["symbols"]
        if symbol["type"] == "hidden"
    }


def spin(seed=None) -> dict:
    doc = _read(active_set())
    try:
        return play.one_spin(
            doc["strips"],
            doc["field"]["rows"],
            doc["field"]["paylines"],
            _pay_table(doc),
            _types(doc),
            seed,
            _weights(doc),
        )
    except ValueError as exc:
        raise SymbolError(str(exc)) from exc


def simulate(rounds, seed=None) -> dict:
    doc = _read(active_set())
    rounds = _clamp(rounds, 1, MAX_ROUNDS, 10000)
    try:
        return play.simulate(
            doc["strips"],
            doc["field"]["rows"],
            doc["field"]["paylines"],
            _pay_table(doc),
            doc["bet"],
            rounds,
            _types(doc),
            seed,
            doc["triggers"],
            _weights(doc),
        )
    except ValueError as exc:
        raise SymbolError(str(exc)) from exc


def _write_strips_text(name: str, all_strips: list[list[int]]) -> Path:
    """Ленты в плоском виде: id через пробел, по строке на рил."""
    path = set_dir(name) / "strips.txt"
    path.write_text(
        "\n".join(" ".join(str(value) for value in strip) for strip in all_strips) + "\n",
        encoding="utf-8",
    )
    return path


def _reel_index(doc: dict, reel) -> int:
    try:
        index = int(reel)
    except (TypeError, ValueError) as exc:
        raise SymbolError(f"непонятный номер рила {reel!r}") from exc
    if not 0 <= index < len(doc["reels"]):
        raise SymbolError(f"рила {index + 1} нет (всего {len(doc['reels'])})")
    return index


# --- символы ------------------------------------------------------------------


def list_symbols(name: str | None = None) -> list[dict]:
    return _read(name or active_set())["symbols"]


def next_id(symbols: list[dict]) -> int:
    return max((item["id"] for item in symbols), default=0) + 1


def add(kind: str = "low", name: str = "") -> dict:
    """Новый символ с очередным id в активном сете."""
    if kind not in TYPES:
        raise SymbolError(f"неизвестный тип {kind!r}")
    current = active_set()
    doc = _read(current)
    symbol = {
        "id": next_id(doc["symbols"]),
        "type": kind,
        "name": name,
        "image": "",
        "pays": {},
        "weights": {},
    }
    doc["symbols"].append(symbol)
    _write(current, doc)
    return symbol


def update(symbol_id: int, kind: str | None = None, name: str | None = None) -> dict:
    current = active_set()
    doc = _read(current)
    symbol = _find(doc["symbols"], symbol_id)
    if kind is not None:
        if kind not in TYPES:
            raise SymbolError(f"неизвестный тип {kind!r}")
        symbol["type"] = kind
    if name is not None:
        symbol["name"] = name
    _write(current, doc)
    return symbol


def set_pay(symbol_id: int, length, amount) -> dict:
    """Выплата за length одинаковых символов в линии. Пусто/0 — выплаты нет."""
    current = active_set()
    doc = _read(current)
    symbol = _find(doc["symbols"], symbol_id)
    reels = doc["field"]["reels"]
    try:
        length = int(length)
    except (TypeError, ValueError) as exc:
        raise SymbolError(f"непонятная длина линии {length!r}") from exc
    if not 1 <= length <= reels:
        raise SymbolError(f"длина {length} вне поля (1..{reels})")

    text = str(amount).strip().replace(",", ".") if amount is not None else ""
    if text in ("", "0", "-"):
        symbol["pays"].pop(str(length), None)
    else:
        try:
            value = float(text)
        except ValueError as exc:
            raise SymbolError(f"выплата {amount!r} — не число") from exc
        if value <= 0:
            symbol["pays"].pop(str(length), None)
        else:
            symbol["pays"][str(length)] = int(value) if value == int(value) else value
    _write(current, doc)
    return symbol


def set_weight(hidden_id: int, target_id, weight) -> dict:
    """Вес превращения hidden-а в конкретный символ. Пусто/0 — превращения нет.

    Веса относительные: 10 и 30 означают ровно то же, что 1 и 3. Проценты
    считает интерфейс, здесь хранится то, что ввели.
    """
    current = active_set()
    doc = _read(current)
    symbol = _find(doc["symbols"], hidden_id)
    if symbol["type"] != "hidden":
        raise SymbolError(f"символ {hidden_id} не типа hidden — веса ему не нужны")

    target = _find(doc["symbols"], int(target_id))
    if target["type"] == "hidden":
        raise SymbolError("hidden не может превращаться в другой hidden")

    key = str(target["id"])
    text = str(weight).strip().replace(",", ".") if weight is not None else ""
    if text in ("", "0", "-"):
        symbol["weights"].pop(key, None)
    else:
        try:
            value = float(text)
        except ValueError as exc:
            raise SymbolError(f"вес {weight!r} — не число") from exc
        if value <= 0:
            symbol["weights"].pop(key, None)
        else:
            symbol["weights"][key] = int(value) if value == int(value) else value
    _write(current, doc)
    return _find(_read(current)["symbols"], symbol["id"])


def delete(symbol_id: int) -> None:
    current = active_set()
    doc = _read(current)
    symbol = _find(doc["symbols"], symbol_id)
    _drop_image(current, symbol.get("image", ""))
    doc["symbols"] = [item for item in doc["symbols"] if item["id"] != symbol_id]
    # иначе группа осталась бы с мёртвым id — _fit_groups его и так выбросит,
    # но лучше не писать в файл то, чего уже нет
    for group in doc["groups"]:
        group["members"] = [member for member in group["members"] if member != symbol_id]
    doc["master"].pop(str(symbol_id), None)
    doc["pattern"].pop(f"id:{symbol_id}", None)
    _write(current, doc)


def set_image(symbol_id: int, filename: str, data_url: str) -> dict:
    """Картинка ложится в sets/<сет>/images/ под именем sym_<id>.<ext>."""
    current = active_set()
    doc = _read(current)
    symbol = _find(doc["symbols"], symbol_id)
    ext = Path(filename or "").suffix.lower()
    if ext not in IMAGE_EXTS:
        raise SymbolError(f"это не картинка: {filename!r}")

    raw = _decode(data_url)
    _images(current).mkdir(parents=True, exist_ok=True)
    _drop_image(current, symbol.get("image", ""))
    stored = f"sym_{symbol_id:02d}{ext}"
    (_images(current) / stored).write_bytes(raw)
    symbol["image"] = stored
    _write(current, doc)
    return symbol


def image_path(set_name: str, image_name: str) -> Path | None:
    """Путь к картинке — только внутри images своего сета."""
    try:
        folder = _images(set_name).resolve()
    except SymbolError:
        return None
    target = (folder / Path(image_name).name).resolve()
    if not str(target).startswith(str(folder)) or not target.is_file():
        return None
    return target


def _find(symbols: list[dict], symbol_id: int) -> dict:
    for item in symbols:
        if item["id"] == symbol_id:
            return item
    raise SymbolError(f"символа {symbol_id} нет")


def _drop_image(set_name: str, image_name: str) -> None:
    if not image_name:
        return
    path = image_path(set_name, image_name)
    if path is not None:
        path.unlink(missing_ok=True)


def _decode(data_url: str) -> bytes:
    payload = data_url.split(",", 1)[-1] if data_url.startswith("data:") else data_url
    try:
        return base64.b64decode(payload, validate=True)
    except Exception as exc:  # noqa: BLE001 — UI покажет причину
        raise SymbolError(f"не удалось прочитать файл: {exc}") from exc
