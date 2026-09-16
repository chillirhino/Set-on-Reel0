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
