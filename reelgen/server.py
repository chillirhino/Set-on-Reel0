"""Локальный HTTP-сервер: JSON API поверх service.py плюс статика и картинки."""

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import service
from . import sets as symbols

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

# Публичный режим. Включается переменной окружения на хостинге.
PUBLIC = os.environ.get("REELGEN_PUBLIC", "").strip().lower() in ("1", "true", "yes")

# Эти маршруты остались от контура импорта `.py`-игры, и у интерфейса на них нет
# ни одной кнопки. Для инструмента на 127.0.0.1 они безобидны, но на публичном
# адресе это чтение и запись любого файла на сервере:
#   /api/import  — отдаёт содержимое произвольного пути;
#   /api/export  — пишет по произвольному пути, то есть перезаписывает сам код;
#   /api/images  — сканирует и раздаёт произвольную папку.
# В публичном режиме они снимаются с регистрации.
LOCAL_ONLY = (
    "/api/import",
    "/api/export",
    "/api/images",
    "/api/default-rules",
    "/api/generate",
    "/api/evaluate",
    "/api/project/save",
    "/api/project/load",
    "/api/project/list",
)

def env(_payload: dict) -> dict:
    """Что интерфейсу нужно знать о том, где он запущен."""
    return {"public": PUBLIC}


ROUTES = {
    "/api/env": env,
    "/api/import": service.import_game,
    "/api/images": service.list_images,
    "/api/default-rules": service.default_rules,
    "/api/generate": service.generate,
    "/api/evaluate": service.evaluate,
    "/api/export": service.export,
    "/api/project/save": service.save_project,
    "/api/project/load": service.load_project,
    "/api/project/list": service.list_saved,
    "/api/symbols/list": service.symbols_list,
    "/api/symbols/add": service.symbols_add,
    "/api/symbols/update": service.symbols_update,
    "/api/symbols/delete": service.symbols_delete,
    "/api/symbols/image": service.symbols_image,
    "/api/sets/select": service.sets_select,
    "/api/sets/create": service.sets_create,
    "/api/sets/save-as": service.sets_save_as,
    "/api/sets/rename": service.sets_rename,
    "/api/sets/delete": service.sets_delete,
    "/api/symbols/pay": service.symbols_pay,
    "/api/symbols/weight": service.symbols_weight,
    "/api/symbols/id": service.symbols_id,
    "/api/set/bet": service.set_bet,
    "/api/field/size": service.field_size,
    "/api/field/lines": service.field_lines,
    "/api/field/lines/reset": service.field_lines_reset,
    "/api/field/lines/paste": service.field_lines_paste,
    "/api/sets/save": service.sets_save,
    "/api/sets/restore": service.sets_restore,
    "/api/sets/export": service.sets_export,
    "/api/sets/import": service.sets_import,
    "/api/gaps/set": service.gaps_set,
    "/api/reels/symbol": service.reels_symbol,
    "/api/reels/copy": service.reels_copy,
    "/api/reels/clear": service.reels_clear,
    "/api/reels/generate": service.reels_generate,
    "/api/set/triggers": service.set_triggers,
    "/api/set/filler-low": service.set_filler_low,
    "/api/groups/create": service.groups_create,
    "/api/groups/rename": service.groups_rename,
    "/api/groups/delete": service.groups_delete,
    "/api/groups/member": service.groups_member,
    "/api/reels/group": service.reels_group,
    "/api/master/mode": service.master_mode,
    "/api/master/symbol": service.master_symbol,
    "/api/master/group": service.master_group,
    "/api/master/clear": service.master_clear,
    "/api/pattern/set": service.pattern_set,
    "/api/pattern/count": service.pattern_count,
    "/api/play/spin": service.play_spin,
    "/api/play/simulate": service.play_simulate,
}


class Handler(BaseHTTPRequestHandler):
    """Папка картинок общая для всех запросов — её задаёт UI или run.py."""

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

        if path.startswith("/symimg/"):
            # /symimg/<сет>/<файл>
            parts = path[len("/symimg/") :].split("/", 1)
            target = symbols.image_path(*parts) if len(parts) == 2 else None
            if target is None:
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
            kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self._send(200, target.read_bytes(), kind)
            return

        if path.startswith("/img/"):
            # раздача из произвольной папки — только для локального запуска
            if PUBLIC:
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
            folder = Path(Handler.images_folder or "")
            name = Path(path[len("/img/") :]).name
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


def serve(port: int = 8765, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    """Локально слушаем только себя. Публичный хост передаёт host='0.0.0.0'."""
    if PUBLIC:
        for route in LOCAL_ONLY:
            ROUTES.pop(route, None)
        # раздача картинок из произвольной папки — оттуда же
        Handler.images_folder = ""
    return ThreadingHTTPServer((host, port), Handler)
