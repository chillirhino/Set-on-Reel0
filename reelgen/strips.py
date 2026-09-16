"""Сборка ленты из стеков: раскладываем блоки, мешаем и разводим по правилам.

Символ на риле описан прямо: **сколько стеков каждой длины**. Разброс 6/2/2 по
длинам 2/3/4 значит шесть двоек, две тройки и две четвёрки — десять стеков и
6×2 + 2×3 + 2×4 = 26 символов. Количество символов считается из этого, а не
задаётся отдельно.

Так сделано ради одной конкретной вещи: **стек неделим, поэтому остатка не
возникает и длина 1 появляется только если её заказали.** Прежняя модель
«количество символов плюс шансы на длину» подрезала последний стек по остатку и
при разрешённых длинах 2 и 3 выдавала одиночный символ в 43% сборок.

Блок — это стек: N подряд идущих одинаковых символов. Два стека одного символа
встык не ставим — заказывали стеки определённой длины, склейка делает их длиннее.
Исключение — флаг ∞: для такого символа склейка разрешена, два стека по 4 могут
встать рядом и дать восьмёрку.

Правило пересечения: между A и B должно лежать минимум N символов-прокладок
(по умолчанию low). A и B — либо конкретный id ("id:13"), либо весь класс
("type:special"). Лента кольцевая, стык конца с началом тоже считается.

Прослойка (filler_low) — предпочтение, а не правило: после low-стека укладчик
пробует поставить не-low и наоборот, чтобы дешёвое разделяло ценное. Жёсткие
дистанции по-прежнему решает укладка по правилам, поэтому спорить им не о чем.
"""

import random

ATTEMPTS = 200  # столько раскладок пробуем, прежде чем взять лучшую из неудачных


def assemble_sizes(count: int, sizes: dict, rng: random.Random) -> list[int]:
    """Длины стеков по количеству символов и шансам на длину.

    Это модель контура с импортом `.py`-игры (`rules.StackRule`): там количество
    символов — закон, а шансы ориентир, поэтому последний стек подрезается по
    остатку. Сеты работают иначе, по явному числу стеков (`stack_lengths`), и
    смешивать эти две модели нельзя: у них разный смысл заказа.
    """
    if count <= 0:
        return []
    options = [(int(size), float(chance)) for size, chance in sizes.items() if float(chance) > 0]
    if not options:
        return [1] * count

    lengths = [size for size, _ in options]
    chances = [chance for _, chance in options]

    result: list[int] = []
    left = count
    while left > 0:
        size = min(rng.choices(lengths, weights=chances, k=1)[0], left)
        result.append(size)
        left -= size
    return result


def stack_lengths(stacks: dict) -> list[int]:
    """Длины стеков по заказу: столько штук каждой длины, сколько указано.

    Ни случайности, ни остатка. Стек неделим, поэтому длина 1 попадает в ленту
    только если её заказали явно.
    """
    lengths: list[int] = []
    for length in sorted(stacks, key=int):
        lengths.extend([int(length)] * int(stacks[length]))
    return lengths


def symbols_of(stacks: dict) -> int:
    """Сколько символов дают эти стеки: 6×2 + 2×3 + 2×4 = 26."""
    return sum(int(length) * int(count) for length, count in (stacks or {}).items())


def blocks_of(reel_cfg: dict) -> list[tuple[int, int]]:
    """Конфиг рила → список блоков (id символа, длина стека)."""
    blocks: list[tuple[int, int]] = []
    for key, cfg in sorted(reel_cfg.items(), key=lambda item: int(item[0])):
        symbol_id = int(key)
        for size in stack_lengths(cfg.get("stacks") or {}):
            blocks.append((symbol_id, size))
    return blocks


def infinite_of(reel_cfg: dict) -> frozenset[int]:
    """Символы с флагом ∞: их стеки можно ставить встык, склейка разрешена."""
    return frozenset(
        int(key)
        for key, cfg in reel_cfg.items()
        if cfg.get("infinity") and symbols_of(cfg.get("stacks"))
    )


def total_of(reel_cfg: dict) -> int:
    """Сколько всего символов встанет в ленту по этому конфигу."""
    return sum(symbols_of(cfg.get("stacks")) for cfg in reel_cfg.values())


def build(reel_cfg: dict, seed: int, rules: list[dict] | None = None,
          types: dict[int, str] | None = None, filler_low: bool = False) -> dict:
    """Лента из перемешанных блоков с оглядкой на правила пересечения."""
    if not total_of(reel_cfg):
        return {"strip": [], "glued": 0, "broken": 0, "longest": {}}

    rules = [rule for rule in (rules or []) if int(rule.get("min", 0)) > 0]
    types = types or {}
    infinite = infinite_of(reel_cfg)
    lows = frozenset(sid for sid, kind in types.items() if kind == "low") if filler_low else frozenset()
    rng = random.Random(seed)

    # набор стеков задан точно, поэтому ищем только порядок — пересобирать
    # блоки на каждой попытке больше нечего
    blocks = blocks_of(reel_cfg)

    best_blocks, best_score = None, None
    for _ in range(ATTEMPTS):
        laid = _lay_out(blocks, rng, rules, types, infinite, lows)
        # сначала важны нарушения правил, потом склейки одинаковых стеков
        score = (count_broken(laid, rules, types, infinite), _glued(laid, infinite))
        if best_score is None or score < best_score:
            best_blocks, best_score = laid, score
        if score == (0, 0):
            break

    strip = _flatten(best_blocks)
    return {
        "strip": strip,
        "glued": best_score[1],
        "broken": best_score[0],
        "longest": _longest_runs(strip),
    }


def _flatten(blocks: list[tuple[int, int]]) -> list[int]:
    strip: list[int] = []
    for symbol_id, length in blocks:
        strip.extend([symbol_id] * length)
    return strip


def _lay_out(blocks, rng, rules, types, infinite=frozenset(), lows=frozenset()) -> list[tuple[int, int]]:
    """Сначала раскладываем свободные символы, потом врезаем связанные правилами.

    Жадная укладка слева направо копила «трудные» символы в хвосте и там их
    сваливала встык. Врезка ищет место в уже готовой ленте, поэтому промежутки
    из прокладок к этому моменту уже есть.
    """
    pool = list(blocks)
    rng.shuffle(pool)

    free = [block for block in pool if not _tied(block[0], rules, types)]
    tied = [block for block in pool if _tied(block[0], rules, types)]
    laid = _interleave(free, rng, infinite, lows) if lows else _spread(free, rng, infinite)
    if not tied:
        return laid
    # самые «связанные» символы врезаем первыми — им труднее всего найти место
    tied.sort(key=lambda block: -_rule_weight(block[0], rules, types))

    for block in tied:
        if not laid:
            laid.append(block)
            continue
        spots = list(range(len(laid)))
        rng.shuffle(spots)
        spot, damage = spots[0], None
        for place in spots:
            misfits = _misfits_at(laid, place, block[0], rules, types, infinite)
            if not misfits:
                spot, damage = place, 0
                break
            if damage is None or misfits < damage:  # места нет — выбираем наименьшее зло
                spot, damage = place, misfits
        laid.insert(spot, block)
    return laid


def _interleave(blocks, rng, infinite, lows) -> list[tuple[int, int]]:
    """Прослойка: не-low становятся каркасом, low ровно расходятся по промежуткам.

    Локальное предпочтение «после low ставь не-low» тут не работает: как только
    ценные кандидаты кончаются, весь остаток low валится в хвост одной кучей —
    ровно то, от чего прослойка должна избавлять. Поэтому сначала раскладываем
    ценные, а потом делим low по промежуткам между ними поровну: остаток от
    деления достаётся случайным промежуткам, чтобы лента не выглядела линованной.

    Обещание честное настолько, насколько позволяет арифметика: если low-стеков
    меньше, чем промежутков, часть ценных всё равно встанет рядом.
    """
    low_blocks = [block for block in blocks if block[0] in lows]
    rest = [block for block in blocks if block[0] not in lows]
    if not low_blocks or not rest:
        return _spread(blocks, rng, infinite)

    spine = _spread(rest, rng, infinite)
    bag = _spread(low_blocks, rng, infinite)

    pockets = len(spine)
    share = [len(bag) // pockets] * pockets
    for index in rng.sample(range(pockets), len(bag) % pockets):
        share[index] += 1

    laid: list[tuple[int, int]] = []
    cursor = 0
    for index, block in enumerate(spine):
        laid.append(block)
        laid.extend(bag[cursor : cursor + share[index]])
        cursor += share[index]
    return _unwrap(laid)


def _spread(blocks, rng, infinite=frozenset()) -> list[tuple[int, int]]:
    """Раскладываем блоки так, чтобы одинаковые символы не вставали встык.

    На каждом шаге берём символ, которого осталось больше всего (кроме только
    что положенного) — так самый частый символ не копится к концу.
    """
    left: dict[int, list[tuple[int, int]]] = {}
    for block in blocks:
        left.setdefault(block[0], []).append(block)

    laid: list[tuple[int, int]] = []
    last = None
    for _ in range(len(blocks)):
        options = [
            symbol
            for symbol, items in left.items()
            if items and (symbol != last or symbol in infinite)
        ]
        if not options:  # остались только «свои» — деваться некуда, слипнется
            options = [symbol for symbol, items in left.items() if items]
        if not options:
            break
        most = max(len(left[symbol]) for symbol in options)
        pick = rng.choice([symbol for symbol in options if len(left[symbol]) == most])
        laid.append(left[pick].pop())
        last = pick

    return _unwrap(laid)


def _unwrap(laid: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Лента кольцевая: хвост не должен совпадать с головой."""
    if len(laid) < 3 or laid[0][0] != laid[-1][0]:
        return laid
    tail = laid[-1]
    for spot in range(1, len(laid) - 1):
        if laid[spot - 1][0] != tail[0] and laid[spot][0] != tail[0]:
            return laid[: len(laid) - 1][:spot] + [tail] + laid[: len(laid) - 1][spot:]
    return laid


def _tied(symbol_id: int, rules, types) -> bool:
    return _rule_weight(symbol_id, rules, types) > 0


def _rule_weight(symbol_id: int, rules, types) -> int:
    """В скольких правилах участвует символ."""
    return sum(
        1
        for rule in rules
        if _matches(symbol_id, rule.get("a"), types)
        or _matches(symbol_id, rule.get("b"), types)
    )


def _misfits_at(laid, spot: int, symbol_id: int, rules, types, infinite=frozenset()) -> int:
    """Сколько правил ломается, если врезать символ перед позицией spot.

    Прилипание к своему же символу считаем нарушением всегда: заказывали стеки
    определённой длины, а склейка делает их длиннее.
    """
    broken = 0
    size = len(laid)
    if size and symbol_id not in infinite:  # ∞ — склейка со своим же стеком разрешена
        broken += laid[(spot - 1) % size][0] == symbol_id
        broken += laid[spot % size][0] == symbol_id

    for rule in rules:
        for side, other in (("a", "b"), ("b", "a")):
            if not _matches(symbol_id, rule.get(side), types):
                continue
            if not _walk(laid, spot - 1, -1, rule, other, types, symbol_id, infinite):
                broken += 1
            if not _walk(laid, spot, 1, rule, other, types, symbol_id, infinite):
                broken += 1
    return broken


def _walk(laid, start: int, step: int, rule, other, types, self_symbol, infinite) -> bool:
    """Идём от места врезки в одну сторону: успеем ли набрать прокладок до пары.

    Два стека одного символа встык — это тоже пара: слипшись, они дают стек
    длиннее заказанного, чего никто не просил.
    """
    need, seen = int(rule.get("min", 0)), 0
    size = len(laid)
    for offset in range(size):
        symbol_id, length = laid[(start + step * offset) % size]
        if symbol_id == self_symbol and symbol_id in infinite:
            continue  # ∞: свои стеки сливаются в один, дистанцию мерим от его края
        if _matches(symbol_id, rule.get(other), types):
            return seen >= need
        if _is_filler(symbol_id, rule.get("filler"), types):
            seen += length
            if seen >= need:
                return True
    return True


def count_broken(blocks: list[tuple[int, int]], rules, types, infinite=frozenset()) -> int:
    """Сколько пар стеков нарушают дистанцию.

    Считаем по стекам, а не по позициям: внутри одного стека пары нет, зато два
    отдельных стека одного символа встык — самая настоящая пара.
    """
    if not blocks or not rules:
        return 0

    broken = 0
    size = len(blocks)
    for rule in rules:
        need = int(rule.get("min", 0))
        for side, other in (("a", "b"), ("b", "a")):
            for start in range(size):
                if not _matches(blocks[start][0], rule.get(side), types):
                    continue
                seen = 0
                source = blocks[start][0]
                for step in range(1, size):
                    symbol_id, length = blocks[(start + step) % size]
                    if symbol_id == source and symbol_id in infinite:
                        continue  # ∞: продолжение своего же стека, а не пара
                    if _matches(symbol_id, rule.get(other), types):
                        if seen < need:
                            broken += 1
                        break
                    if _is_filler(symbol_id, rule.get("filler"), types):
                        seen += length
                        if seen >= need:
                            break
    return broken


def _matches(symbol_id: int, target, types) -> bool:
    """target — 'id:13' или 'type:special'."""
    if not target:
        return False
    kind, _, value = str(target).partition(":")
    if kind == "id":
        return str(symbol_id) == value
    if kind == "type":
        return types.get(symbol_id) == value
    return False


def _is_filler(symbol_id: int, filler, types) -> bool:
    """Прокладка: символ нужного класса. 'any' — засчитываем любой символ."""
    if not filler or filler == "any":
        return True
    return types.get(symbol_id) == filler


def _glued(blocks: list[tuple[int, int]], infinite=frozenset()) -> int:
    """Незапланированные склейки: соседние блоки одного символа без флага ∞."""
    if len(blocks) < 2:
        return 0
    return sum(
        1
        for index in range(len(blocks))
        if blocks[index][0] == blocks[(index + 1) % len(blocks)][0]
        and blocks[index][0] not in infinite
    )


def _longest_runs(strip: list[int]) -> dict[int, int]:
    """id символа → самый длинный стек в готовой ленте (с учётом кольца)."""
    longest: dict[int, int] = {}
    if not strip:
        return longest

    run_symbol, run_length = strip[0], 0
    for symbol_id in strip + strip:
        if symbol_id == run_symbol:
            run_length += 1
        else:
            longest[run_symbol] = min(max(longest.get(run_symbol, 0), run_length), len(strip))
            run_symbol, run_length = symbol_id, 1
    longest[run_symbol] = min(max(longest.get(run_symbol, 0), run_length), len(strip))
    return longest
