"""Логика запросов UI. Никакого HTTP — только dict на входе и dict на выходе."""

from pathlib import Path

from . import gameio, images
from . import project as project_io
from . import sets as symbols
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
                sizes={
                    int(size): float(weight) for size, weight in stack["sizes"].items()
                },
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
        "default_classes": {
            str(sid): name for sid, name in default_classes(game).items()
        },
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
            "attempts": [],
            "problems": problems,
            "violations": [],
            "merges": [],
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
        "merges": [result.merges for result in results],
        "problems": problems,
        "violations": [
            [
                {
                    "rule_index": v.rule_index,
                    "gap": v.gap,
                    "filler_count": v.filler_count,
                    "deficit": v.deficit,
                    "a": {
                        "symbol_id": v.a.symbol_id,
                        "start": v.a.start,
                        "size": v.a.size,
                    },
                    "b": {
                        "symbol_id": v.b.symbol_id,
                        "start": v.b.start,
                        "size": v.b.size,
                    },
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


# --- символы и сеты -----------------------------------------------------------
#
# Каждый ответ — целиком состояние вкладки: список сетов, активный, его символы.


def _symbols(_payload: dict | None = None) -> dict:
    return symbols.state()


def _do(action) -> dict:
    """Гоняет операцию над сетами/символами и всегда отдаёт свежее состояние.

    TypeError здесь тоже ошибка запроса, а не поломка: кривой payload не должен
    доезжать до пользователя пятисоткой без объяснения.
    """
    try:
        action()
    except (KeyError, TypeError, ValueError, symbols.SymbolError) as exc:
        raise ServiceError(str(exc)) from exc
    return symbols.state()


def symbols_list(payload: dict) -> dict:
    return _symbols(payload)


def sets_select(payload: dict) -> dict:
    return _do(lambda: symbols.select_set(payload.get("name") or ""))


def sets_create(payload: dict) -> dict:
    return _do(lambda: symbols.create_set(payload.get("name") or ""))


def sets_save(_payload: dict) -> dict:
    return _do(symbols.save_set)


def sets_save_as(payload: dict) -> dict:
    return _do(
        lambda: symbols.copy_set(payload.get("name") or "", bool(payload.get("overwrite")))
    )


def sets_rename(payload: dict) -> dict:
    return _do(
        lambda: symbols.rename_set(
            payload.get("old") or symbols.active_set(), payload.get("name") or ""
        )
    )


def sets_export(payload: dict) -> dict:
    """Отдаёт файл сета целиком — UI сохранит его через браузер."""
    try:
        return symbols.export_set(payload.get("name") or "")
    except symbols.SymbolError as exc:
        raise ServiceError(str(exc)) from exc


def sets_import(payload: dict) -> dict:
    return _do(lambda: symbols.import_set(payload.get("bundle"), payload.get("name") or ""))


def sets_restore(payload: dict) -> dict:
    return _do(lambda: symbols.restore_set(payload.get("name") or ""))


def sets_delete(payload: dict) -> dict:
    return _do(lambda: symbols.delete_set(payload.get("name") or ""))


def set_bet(payload: dict) -> dict:
    return _do(lambda: symbols.set_bet(payload.get("bet")))


def field_size(payload: dict) -> dict:
    return _do(lambda: symbols.set_size(payload.get("rows"), payload.get("reels")))


def field_lines(payload: dict) -> dict:
    return _do(lambda: symbols.set_lines(payload.get("lines")))


def field_lines_reset(_payload: dict) -> dict:
    return _do(symbols.reset_lines)


def field_lines_paste(payload: dict) -> dict:
    return _do(lambda: symbols.paste_lines(payload.get("text") or ""))


def gaps_set(payload: dict) -> dict:
    return _do(lambda: symbols.set_gaps(payload.get("rules")))


def reels_symbol(payload: dict) -> dict:
    return _do(
        lambda: symbols.set_reel_symbol(
            payload.get("reel"),
            payload.get("symbol"),
            payload.get("stacks"),
            payload.get("infinity"),
        )
    )


def set_filler_low(payload: dict) -> dict:
    return _do(lambda: symbols.set_filler_low(payload.get("value")))


# --- мастер-рил и паттерн -----------------------------------------------------


def master_mode(payload: dict) -> dict:
    return _do(
        lambda: symbols.set_master_mode(payload.get("value"), payload.get("from_reel"))
    )


def master_symbol(payload: dict) -> dict:
    return _do(
        lambda: symbols.set_master_symbol(
            payload.get("symbol"),
            payload.get("stacks"),
            payload.get("infinity"),
        )
    )


def master_group(payload: dict) -> dict:
    return _do(
        lambda: symbols.set_master_group(
            payload.get("group") or "",
            payload.get("stacks"),
            payload.get("infinity"),
        )
    )


def master_clear(_payload: dict) -> dict:
    return _do(symbols.clear_master)


def pattern_set(payload: dict) -> dict:
    """reel не передан — правим только потолок множителя."""
    return _do(
        lambda: symbols.set_pattern(
            payload.get("target") or "",
            payload.get("reel"),
            payload.get("mult"),
            payload.get("max"),
        )
    )


def pattern_count(payload: dict) -> dict:
    """Сколько стеков этой длины на этом риле. Пусто — как в мастере."""
    return _do(
        lambda: symbols.set_pattern_count(
            payload.get("target") or "",
            payload.get("length"),
            payload.get("reel"),
            payload.get("value"),
        )
    )


# --- группы символов ----------------------------------------------------------


def groups_create(payload: dict) -> dict:
    return _do(lambda: symbols.create_group(payload.get("name") or ""))


def groups_rename(payload: dict) -> dict:
    return _do(
        lambda: symbols.rename_group(payload.get("name") or "", payload.get("new_name") or "")
    )


def groups_delete(payload: dict) -> dict:
    return _do(lambda: symbols.delete_group(payload.get("name") or ""))


def groups_member(payload: dict) -> dict:
    """join не передан — считаем, что символ вводят в группу."""
    return _do(
        lambda: symbols.set_group_member(
            payload.get("name") or "",
            payload.get("symbol"),
            bool(payload.get("join", True)),
        )
    )


def reels_group(payload: dict) -> dict:
    """Одно значение сразу во все символы группы на этом риле."""
    return _do(
        lambda: symbols.set_reel_group(
            payload.get("reel"),
            payload.get("group") or "",
            payload.get("stacks"),
            payload.get("infinity"),
        )
    )


def reels_copy(payload: dict) -> dict:
    return _do(lambda: symbols.copy_reel_to_all(payload.get("reel")))


def reels_clear(payload: dict) -> dict:
    return _do(lambda: symbols.clear_reel(payload.get("reel")))


def reels_generate(payload: dict) -> dict:
    """reel не передан — генерим все ленты, иначе только указанную."""
    extra: dict = {}

    def run() -> None:
        extra.update(
            symbols.generate(
                reel=payload.get("reel"),
                seed=payload.get("seed"),
                reseed=bool(payload.get("reseed")),
            )
        )

    result = _do(run)
    result["stats"] = extra.get("stats", [])
    return result


def play_spin(payload: dict) -> dict:
    """Один спин: окно символов и выигравшие линии. Состояние не меняем."""
    try:
        return symbols.spin(payload.get("seed"))
    except symbols.SymbolError as exc:
        raise ServiceError(str(exc)) from exc


def set_triggers(payload: dict) -> dict:
    return _do(lambda: symbols.set_triggers(payload.get("bonus"), payload.get("fs")))


def play_simulate(payload: dict) -> dict:
    try:
        return symbols.simulate(payload.get("rounds"), payload.get("seed"))
    except symbols.SymbolError as exc:
        raise ServiceError(str(exc)) from exc


def symbols_pay(payload: dict) -> dict:
    return _do(
        lambda: symbols.set_pay(
            int(payload["id"]), payload.get("length"), payload.get("amount")
        )
    )


def symbols_add(payload: dict) -> dict:
    return _do(lambda: symbols.add(payload.get("type") or "low", payload.get("name") or ""))


def symbols_update(payload: dict) -> dict:
    return _do(
        lambda: symbols.update(
            int(payload["id"]), kind=payload.get("type"), name=payload.get("name")
        )
    )


def symbols_weight(payload: dict) -> dict:
    """Вес превращения hidden-а в конкретный символ."""
    return _do(
        lambda: symbols.set_weight(
            int(payload["id"]), payload.get("target"), payload.get("weight")
        )
    )


def symbols_id(payload: dict) -> dict:
    """Ручная смена id символа: номера свободные, дыры разрешены."""
    return _do(lambda: symbols.set_id(int(payload["id"]), payload.get("new_id")))


def symbols_delete(payload: dict) -> dict:
    return _do(lambda: symbols.delete(int(payload["id"])))


def symbols_image(payload: dict) -> dict:
    """Картинка приходит из drag-n-drop как data-url; id может быть новым символом."""

    def put() -> None:
        symbol_id = payload.get("id")
        if symbol_id in (None, "", "new"):
            symbol_id = symbols.add(payload.get("type") or "low")["id"]
        symbols.set_image(
            int(symbol_id), payload.get("filename") or "", payload.get("data") or ""
        )

    return _do(put)
