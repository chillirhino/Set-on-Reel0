"""Точка входа: поднимает сервер и открывает браузер.

Локально слушает 127.0.0.1 и открывает вкладку. На хостинге всё берётся из
окружения: PORT и HOST задаёт платформа, REELGEN_PUBLIC=1 снимает маршруты,
которые дают доступ к файловой системе сервера.
"""

import argparse
import os
import webbrowser

from reelgen.server import PUBLIC, Handler, serve


def main() -> None:
    parser = argparse.ArgumentParser(description="Reel Generator")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8765)))
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--no-open", action="store_true", help="не открывать браузер")
    parser.add_argument(
        "--images",
        default=os.environ.get("REELGEN_IMAGES", "/Users/mark/2_Claude/symbols"),
        help="папка с картинками символов по умолчанию",
    )
    args = parser.parse_args()

    Handler.images_folder = "" if PUBLIC else args.images
    httpd = serve(args.port, args.host)

    where = f"http://{args.host}:{args.port}/"
    print(f"Reel Generator: {where}")
    if PUBLIC:
        print("публичный режим: доступ к файловой системе сервера закрыт")
    print("Остановить — Ctrl+C")

    # браузер открываем только когда сервер и правда локальный
    if not args.no_open and not PUBLIC and args.host in ("127.0.0.1", "localhost"):
        webbrowser.open(where)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nостановлен")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
