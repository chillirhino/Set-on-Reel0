"""Игра на готовых лентах: спин, подсчёт выигрыша по линиям, симуляция и её статистика.

Линия платит, если одинаковые символы идут подряд слева направо с первого
барабана. Символ типа wild подставляется вместо любого обычного символа, но не
вместо special (скаттер и бонус вайлдом не собираются). Из всех трактовок линии
берём самую дорогую, выплата — за самую длинную оплачиваемую длину.

Комбинация записывается в статистику на тот символ, по чьей таблице заплатили:
«ID 5, wild, wild, ID 5, ID 5» — это пятёрка ID 5, а не выигрыш вайлда. Отдельно
помечаем, участвовал ли вайлд в оплаченной части линии.

Символ типа hidden до подсчёта линий не доживает. Порядок спина — бросок,
замена, стоп, игра: на каждый hidden-id делается один бросок по его весам, и
все экземпляры этого id на экране становятся выбранным символом. Два разных
hidden-а бросают независимо. Линии, триггеры и разнообразие считаются уже по
превращённому полю, поэтому hidden, ставший бонусом, честно добирает порог.

Бросок делается, только если hidden-символы в сете действительно есть: лишнее
обращение к генератору сдвинуло бы всю последовательность, и сет без hidden-ов
при том же сиде играл бы иначе, чем раньше.
"""

import bisect
import random


def columns(strip: list[int], rows: int) -> list[tuple[int, ...]]:
    """Все возможные окна барабана: для каждой позиции — что видно на экране."""
    size = len(strip)
    if size == 0:
        return []
    return [tuple(strip[(offset + row) % size] for row in range(rows)) for offset in range(size)]


def spin(all_columns: list[list[tuple[int, ...]]], rng: random.Random) -> list[tuple[int, ...]]:
    """Случайная позиция каждого барабана → видимое окно."""
    return [rng.choice(reel) if reel else tuple() for reel in all_columns]


def _pay_ladder(pays: dict, reels: int) -> dict[int, list[int]]:
    """Для каждого символа: длина совпадения → какая длина реально платит (0 — никакая).

    Выпало четыре подряд, а таблица знает только 3 и 5 — платим за 3.
    """
    ladder: dict[int, list[int]] = {}
    for symbol_id, table in pays.items():
        best = [0] * (reels + 1)
        for length in range(1, reels + 1):
            paying = [size for size in table if size <= length]
            best[length] = max(paying) if paying else 0
        ladder[symbol_id] = best
    return ladder


def wild_ids(types: dict[int, str] | None) -> frozenset[int]:
    return frozenset(sid for sid, kind in (types or {}).items() if kind == "wild")


def no_sub_ids(types: dict[int, str] | None) -> frozenset[int]:
    """Символы, которые вайлд не собирает: скаттер и бонус."""
    return frozenset(sid for sid, kind in (types or {}).items() if kind == "special")


def hidden_ids(types: dict[int, str] | None) -> frozenset[int]:
    """Символы, которые перед стопом превращаются в другие."""
    return frozenset(sid for sid, kind in (types or {}).items() if kind == "hidden")


def weight_tables(weights, hidden: frozenset[int]) -> dict[int, dict[int, float]]:
    """Веса превращения в виде «hidden-id → {цель: вес}», только с живыми весами."""
    tables: dict[int, dict[int, float]] = {}
    for symbol_id, table in (weights or {}).items():
        symbol_id = int(symbol_id)
        if symbol_id not in hidden:
            continue
        usable = {
            int(target): float(weight)
            for target, weight in (table or {}).items()
            if float(weight) > 0
        }
        if usable:
            tables[symbol_id] = usable
    return tables


def check_hidden(all_strips, hidden: frozenset[int], tables: dict[int, dict]) -> frozenset[int]:
    """Какие hidden-ы реально лежат в лентах. Без весов играть нельзя — это ошибка."""
    present = frozenset(
        symbol_id for strip in all_strips for symbol_id in strip
    ) & hidden
    missing = sorted(symbol_id for symbol_id in present if not tables.get(symbol_id))
    if missing:
        names = ", ".join(str(symbol_id) for symbol_id in missing)
        raise ValueError(
            f"у символа {names} не задано ни одного веса превращения — "
            "заполни веса на вкладке «Скрытые» или убери символ с лент"
        )
    return present


def roll_hidden(tables: dict[int, dict[int, float]], rng: random.Random) -> dict[int, int]:
    """Один бросок на каждый hidden-id: во что он превращается в этом спине.

    Порядок бросков фиксирован по возрастанию id, иначе один и тот же сид давал
    бы разные результаты.
    """
    plan: dict[int, int] = {}
    for hidden_id in sorted(tables):
        table = tables[hidden_id]
        targets = sorted(table)
        plan[hidden_id] = rng.choices(targets, weights=[table[t] for t in targets])[0]
    return plan


def apply_hidden(window, plan: dict[int, int]):
    """Заменяем hidden-ы по броску. Вторым значением — где они стояли.

    Маска рила это None, если hidden-ов на нём не было: в горячем цикле это
    избавляет от лишнего прохода по клеткам.
    """
    cells_by_reel, marks = [], []
    for reel in window:
        if not any(symbol_id in plan for symbol_id in reel):
            cells_by_reel.append(tuple(reel))
            marks.append(None)
            continue
        cells_by_reel.append(tuple(plan.get(symbol_id, symbol_id) for symbol_id in reel))
        marks.append(tuple(symbol_id if symbol_id in plan else 0 for symbol_id in reel))
    return cells_by_reel, marks


def _line_has_hidden(marks, line, length: int) -> bool:
    """Попал ли превращённый символ в оплаченную часть линии."""
    for index in range(length):
        reel_marks = marks[index]
        if reel_marks is not None and reel_marks[line[index]]:
            return True
    return False


def line_win(cells: list[int], pays, wilds=frozenset(), no_sub=frozenset()) -> dict | None:
    """Лучшая трактовка одной линии. cells — символы линии слева направо."""
    reels = len(cells)
    if not reels:
        return None

    best = None

    def offer(symbol_id, run, first_wild):
        """Записываем вариант, если он платит больше уже найденного."""
        nonlocal best
        table = pays.get(symbol_id) or {}
        paying = [size for size in table if size <= run]
        if not paying:
            return
        length = max(paying)
        amount = table[length]
        if best is None or amount > best["amount"]:
            best = {
                "symbol": symbol_id,
                "length": length,
                "amount": amount,
                # вайлд засчитан, только если попал в оплаченную часть линии
                "with_wild": 0 <= first_wild < length,
            }

    leading = 0
    while leading < reels and cells[leading] in wilds:
        leading += 1

    if leading:  # вариант «платит сам вайлд»
        offer(cells[0], leading, -1)

    base = cells[leading] if leading < reels else None
    if base is not None and base not in wilds:
        run, first_wild = 0, -1
        substitutes = base not in no_sub
        for index in range(reels):
            symbol_id = cells[index]
            if symbol_id == base:
                run += 1
                continue
            if substitutes and symbol_id in wilds:
                if first_wild < 0:
                    first_wild = index
                run += 1
                continue
            break
        offer(base, run, first_wild)

    return best


def evaluate(window, paylines: list[list[int]], pays, types=None, marks=None) -> dict:
    """Все выигрыши окна и их сумма.

    marks — маска превращённых клеток, если в сете есть hidden-ы. Когда её нет,
    признак with_hidden в выигрыш не кладётся вовсе: сет без hidden-ов должен
    отдавать ровно тот же ответ, что и раньше.
    """
    if not window or any(not reel for reel in window):
        return {"wins": [], "total": 0.0}
    wilds, no_sub = wild_ids(types), no_sub_ids(types)
    wins = []
    for index, line in enumerate(paylines):
        cells = [window[reel][line[reel]] for reel in range(len(window))]
        win = line_win(cells, pays, wilds, no_sub)
        if not win:
            continue
        if marks is not None:
            win["with_hidden"] = _line_has_hidden(marks, line, win["length"])
        wins.append({"line": index, **win})
    return {"wins": wins, "total": sum(win["amount"] for win in wins)}


def prepare(all_strips: list[list[int]], rows: int) -> list[list[tuple[int, ...]]]:
    return [columns(strip, rows) for strip in all_strips]


def one_spin(all_strips, rows, paylines, pays, types=None, seed=None, weights=None) -> dict:
    """Один спин для показа в интерфейсе.

    При hidden-ах отдаём и превращённое поле, и «что во что» — интерфейсу нужно
    нарисовать выпавший символ с пометкой, из какого hidden-а он пришёл.
    """
    rng = random.Random(seed)
    prepared = prepare(all_strips, rows)
    window = spin(prepared, rng)

    hidden = hidden_ids(types)
    if not hidden:
        result = evaluate(window, paylines, pays, types)
        return {"window": [list(reel) for reel in window], **result}

    tables = weight_tables(weights, hidden)
    check_hidden(all_strips, hidden, tables)
    plan = roll_hidden(tables, rng)
    window, marks = apply_hidden(window, plan)
    result = evaluate(window, paylines, pays, types, marks)
    return {
        "window": [list(reel) for reel in window],
        # клетка → id hidden-а, из которого она пришла; 0 — обычный символ
        "hidden_cells": [list(reel) if reel else [0] * rows for reel in marks],
        "hidden_map": {str(hidden_id): target for hidden_id, target in plan.items()},
        **result,
    }


def simulate(all_strips, rows, paylines, pays, bet: float, rounds: int, types=None,
             seed=None, triggers: dict | None = None, weights=None) -> dict:
    """Крутим rounds спинов и собираем статистику по выигрышам и триггерам."""
    if bet <= 0:
        raise ValueError("ставка должна быть больше нуля")

    prepared = prepare(all_strips, rows)
    if any(not reel for reel in prepared):
        raise ValueError("не все ленты сгенерированы")
    if not paylines:
        raise ValueError("не задано ни одной линии")

    reels = len(prepared)
    ladder = _pay_ladder(pays, reels)
    wilds, no_sub = wild_ids(types), no_sub_ids(types)
    hidden = hidden_ids(types)
    # крутим только те hidden-ы, что реально лежат в лентах: бросок за символ,
    # которого на барабанах нет, ничего не решает и только путал бы статистику
    tables = weight_tables(weights, hidden) if hidden else {}
    if hidden:
        present = check_hidden(all_strips, hidden, tables)
        tables = {symbol_id: tables[symbol_id] for symbol_id in sorted(present)}
    triggers = triggers or {}
    bonus = triggers.get("bonus") or {}
    freespins = triggers.get("fs") or {}
    bonus_id, fs_id = int(bonus.get("symbol") or 0), int(freespins.get("symbol") or 0)
    bonus_min, fs_min = int(bonus.get("min") or 0), int(freespins.get("min") or 0)

    # антисипейшн: на каких рилах и сколько символов означают «намечается»
    bonus_ant = _ant_rule(bonus, reels)
    fs_ant = _ant_rule(freespins, reels)

    # «Роялсы» — это символы типа low, «картинки» — все остальные. Считаем по
    # экрану, каким игрок его видит: hidden к этому моменту уже превратился,
    # поэтому клетка из него идёт в ту группу, в какую попал её символ.
    lows = frozenset(sid for sid, kind in (types or {}).items() if kind == "low")

    # для каждой позиции барабана заранее знаем: что видно, какие символы,
    # сколько на этом барабане триггерных символов, есть ли hidden и сколько
    # тут роялсов и вайлдов — в цикле останется сложить, а окно без hidden-ов
    # пройдёт прежним путём нетронутым
    def _view(cells):
        return (
            cells,
            frozenset(cells),
            cells.count(bonus_id),
            cells.count(fs_id),
            any(symbol_id in tables for symbol_id in cells),
            sum(1 for symbol_id in cells if symbol_id in lows),
            sum(1 for symbol_id in cells if symbol_id in wilds),
        )

    views = [[_view(cells) for cells in reel] for reel in prepared]
    lines = [tuple(line) for line in paylines]
    screen = sum(len(reel[0]) for reel in prepared) if prepared and prepared[0] else 0

    total_win = 0.0
    paying_spins = 0
    bonus_hits = 0
    fs_hits = 0
    bonus_ant_hits = 0
    fs_ant_hits = 0
    lines_hist: dict[int, int] = {}
    value_count = [0] * len(WIN_BANDS)
    value_win = [0.0] * len(WIN_BANDS)
    length_hist: dict[int, int] = {}
    diversity_hist: dict[int, int] = {}
    # сколько роялсов на экране, сколько вайлдов и на скольких рилах они лежат
    royal_hist: dict[int, int] = {}
    wild_hist: dict[int, int] = {}
    wild_reels_hist: dict[int, int] = {}
    hits: dict[tuple[int, int], list] = {}
    hidden_win = 0.0
    # hidden-id → {цель: сколько раз выпала} и сколько спинов символ был на экране
    hidden_rolls = {symbol_id: dict.fromkeys(tables[symbol_id], 0) for symbol_id in tables}
    hidden_seen = dict.fromkeys(tables, 0)

    rng = random.Random(seed)
    choice = rng.choice

    for _ in range(rounds):
        picked = [choice(reel) for reel in views]

        marks = None
        if tables:
            plan = roll_hidden(tables, rng)
            for hidden_id, target in plan.items():
                hidden_rolls[hidden_id][target] += 1
            marks = [None] * reels
            appeared = set()
            for index in range(reels):
                view = picked[index]
                if not view[4]:
                    continue
                source = view[0]
                cells = tuple(plan.get(symbol_id, symbol_id) for symbol_id in source)
                marks[index] = tuple(
                    symbol_id if symbol_id in plan else 0 for symbol_id in source
                )
                appeared.update(symbol_id for symbol_id in source if symbol_id in plan)
                # все счётчики пересчитываем заново: hidden мог стать бонусом,
                # вайлдом или роялсом, и каждая из групп от этого меняется
                picked[index] = _view(cells)
            for hidden_id in appeared:
                hidden_seen[hidden_id] += 1

        spin_win = 0.0
        win_lines = 0
        for line in lines:
            cells = [picked[index][0][line[index]] for index in range(reels)]

            leading = 0
            while leading < reels and cells[leading] in wilds:
                leading += 1

            top_amount, top_symbol, top_length, top_wild = 0.0, 0, 0, False

            if leading:  # платит сам вайлд
                rung = ladder.get(cells[0])
                if rung:
                    paying = rung[leading]
                    if paying:
                        top_amount = pays[cells[0]][paying]
                        top_symbol, top_length = cells[0], paying

            base = cells[leading] if leading < reels else None
            if base is not None and base not in wilds:
                rung = ladder.get(base)
                if rung:
                    run, first_wild = 0, -1
                    substitutes = base not in no_sub
                    for index in range(reels):
                        symbol_id = cells[index]
                        if symbol_id == base:
                            run += 1
                        elif substitutes and symbol_id in wilds:
                            if first_wild < 0:
                                first_wild = index
                            run += 1
                        else:
                            break
                    paying = rung[run]
                    if paying:
                        amount = pays[base][paying]
                        if amount > top_amount:
                            top_amount = amount
                            top_symbol, top_length = base, paying
                            top_wild = 0 <= first_wild < paying

            if not top_amount:
                continue

            top_hidden = marks is not None and _line_has_hidden(marks, line, top_length)
            if top_hidden:
                hidden_win += top_amount

            spin_win += top_amount
            win_lines += 1
            length_hist[top_length] = length_hist.get(top_length, 0) + 1
            slot = hits.get((top_symbol, top_length))
            if slot is None:
                hits[(top_symbol, top_length)] = [
                    1, top_amount,
                    int(top_wild), top_amount if top_wild else 0.0,
                    int(top_hidden), top_amount if top_hidden else 0.0,
                ]
            else:
                slot[0] += 1
                slot[1] += top_amount
                if top_wild:
                    slot[2] += 1
                    slot[3] += top_amount
                if top_hidden:
                    slot[4] += 1
                    slot[5] += top_amount

        if win_lines:
            paying_spins += 1
            total_win += spin_win
            lines_hist[win_lines] = lines_hist.get(win_lines, 0) + 1
            band = bisect.bisect_right(WIN_BANDS, spin_win / bet) - 1
            value_count[band] += 1
            value_win[band] += spin_win

        seen = picked[0][1]
        for index in range(1, reels):
            seen = seen | picked[index][1]
        kinds = len(seen)
        diversity_hist[kinds] = diversity_hist.get(kinds, 0) + 1

        royals = 0
        wild_count = 0
        wild_reels = 0
        for view in picked:
            royals += view[5]
            if view[6]:
                wild_count += view[6]
                wild_reels += 1
        royal_hist[royals] = royal_hist.get(royals, 0) + 1
        wild_hist[wild_count] = wild_hist.get(wild_count, 0) + 1
        wild_reels_hist[wild_reels] = wild_reels_hist.get(wild_reels, 0) + 1

        if bonus_id:
            if bonus_min and sum(view[2] for view in picked) >= bonus_min:
                bonus_hits += 1
            if _ant_hit(picked, 2, bonus_ant):
                bonus_ant_hits += 1
        if fs_id:
            if fs_min and sum(view[3] for view in picked) >= fs_min:
                fs_hits += 1
            if _ant_hit(picked, 3, fs_ant):
                fs_ant_hits += 1

    staked = bet * rounds
    return {
        "rounds": rounds,
        "bet": bet,
        "total_win": total_win,
        "rtp": (total_win / staked * 100) if staked else 0.0,
        "hit_rate": paying_spins / rounds * 100 if rounds else 0.0,
        "paying_spins": paying_spins,
        "lines_hist": _as_rows(lines_hist),
        "lines_avg": _mean(lines_hist),
        "length_hist": _as_rows(length_hist),
        "length_avg": _mean(length_hist),
        "diversity_hist": _as_rows(diversity_hist),
        "diversity_avg": _mean(diversity_hist),
        # роялсы и картинки дополняют друг друга до полного экрана, поэтому
        # хватает одного распределения: картинки это остаток
        "screen": screen,
        "royal_hist": _as_rows(royal_hist),
        "royal_avg": _mean(royal_hist),
        "picture_avg": screen - _mean(royal_hist),
        "wild_hist": _as_rows(wild_hist),
        "wild_avg": _mean(wild_hist),
        "wild_reels_hist": _as_rows(wild_reels_hist),
        "wild_reels_avg": _mean(wild_reels_hist),
        "symbol_hits": _hit_rows(hits, pays, reels),
        "win_values": _band_rows(value_count, value_win),
        "win_avg": (total_win / paying_spins) if paying_spins else 0.0,
        "wild_win": sum(slot[3] for slot in hits.values()),
        "hidden_win": hidden_win,
        "hidden": _hidden_rows(tables, hidden_rolls, hidden_seen, rounds),
        "triggers": {
            "bonus": _trigger_row(bonus_id, bonus_min, bonus_hits, rounds, bonus_ant, bonus_ant_hits),
            "fs": _trigger_row(fs_id, fs_min, fs_hits, rounds, fs_ant, fs_ant_hits),
        },
    }


def _ant_rule(trigger: dict, reels: int) -> tuple[tuple[int, ...], int, bool]:
    """Правило антисипейшна: индексы рилов, порог и режим «на каждом»."""
    numbers = trigger.get("ant_reels") or []
    indexes = tuple(int(number) - 1 for number in numbers if 1 <= int(number) <= reels)
    return indexes, int(trigger.get("ant_min") or 0), bool(trigger.get("ant_each"))


def _ant_hit(picked, slot: int, rule) -> bool:
    """Намечается ли триггер: символы на нужных рилах уже лежат."""
    indexes, need, each = rule
    if not indexes or not need:
        return False
    if each:
        return all(picked[index][slot] >= need for index in indexes)
    return sum(picked[index][slot] for index in indexes) >= need


# Границы корзин выплат в ставках: до 1 ставки, 1–2, 2–3, 3–5 и так далее.
WIN_BANDS = [0, 1, 2, 3, 5, 10, 20, 50, 100, 200, 500, 1000]


def _band_rows(counts: list[int], wins: list[float]) -> list[list]:
    """Корзины выплат: [от, до (None — без потолка), спинов, выплачено]."""
    last = max((index for index, count in enumerate(counts) if count), default=-1)
    rows = []
    for index in range(last + 1):
        top = WIN_BANDS[index + 1] if index + 1 < len(WIN_BANDS) else None
        rows.append([WIN_BANDS[index], top, counts[index], wins[index]])
    return rows


def _as_rows(hist: dict[int, int]) -> list[list[int]]:
    return [[key, hist[key]] for key in sorted(hist)]


def _mean(hist: dict[int, int]) -> float:
    total = sum(hist.values())
    if not total:
        return 0.0
    return sum(key * count for key, count in hist.items()) / total


def _hit_rows(hits, pays, reels: int) -> list[list]:
    """Строки вида [id, длина, раз, выплата, раз с wild, выплата с wild, то же по hidden].

    Показываем и нулевые строки: важно видеть, что комбинация не выпала ни разу.
    Колонки hidden дописаны справа, чтобы не сдвинуть уже разбираемые индексы.
    """
    rows = []
    for symbol_id in sorted(pays):
        for length in sorted(pays[symbol_id]):
            if length > reels:
                continue
            slot = hits.get((symbol_id, length), (0, 0.0, 0, 0.0, 0, 0.0))
            rows.append([symbol_id, length, *slot])
    return rows


def _hidden_rows(tables, rolls, seen, rounds: int) -> list[dict]:
    """Во что превращался каждый hidden: заданный вес против фактической доли.

    Расхождение факта с весом на большом числе раундов — первый признак, что в
    механике что-то не так.
    """
    result = []
    for hidden_id in sorted(tables):
        table = tables[hidden_id]
        total_weight = sum(table.values())
        spun = sum(rolls[hidden_id].values())
        result.append(
            {
                "symbol": hidden_id,
                "rolls": spun,
                "on_screen": seen[hidden_id],
                "on_screen_rate": seen[hidden_id] / rounds * 100 if rounds else 0.0,
                "targets": [
                    {
                        "symbol": target,
                        "weight": table[target],
                        "want": table[target] / total_weight * 100 if total_weight else 0.0,
                        "hits": rolls[hidden_id][target],
                        "got": rolls[hidden_id][target] / spun * 100 if spun else 0.0,
                    }
                    for target in sorted(table)
                ],
            }
        )
    return result


def _trigger_row(symbol_id: int, minimum: int, hits: int, rounds: int, rule, ant_hits: int) -> dict:
    indexes, need, each = rule
    return {
        "symbol": symbol_id,
        "min": minimum,
        "hits": hits,
        "rate": hits / rounds * 100 if rounds else 0.0,
        "one_in": (rounds / hits) if hits else 0.0,
        "ant": {
            "reels": [index + 1 for index in indexes],
            "min": need,
            "each": each,
            "hits": ant_hits,
            "rate": ant_hits / rounds * 100 if rounds else 0.0,
            "one_in": (rounds / ant_hits) if ant_hits else 0.0,
        },
    }
