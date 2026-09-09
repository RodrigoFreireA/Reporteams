"""Desktop launcher for the ReportChart Flask app."""

import multiprocessing
import os
import socket
import sqlite3
import sys
import threading
import time
import webbrowser


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

os.environ.setdefault("APP_ENV", "desktop")
os.environ.setdefault("HOST", "127.0.0.1")

from werkzeug.serving import make_server  # noqa: E402

from app import app  # noqa: E402


def _assert_bundled_runtime() -> None:
    connection = sqlite3.connect(":memory:")
    connection.close()


def _port_is_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _pick_port(host: str) -> int:
    requested = os.environ.get("PORT")
    candidates: list[int] = []
    if requested:
        try:
            candidates.append(int(requested))
        except ValueError:
            pass
    candidates.extend(range(5001, 5101))

    seen: set[int] = set()
    for port in candidates:
        if port in seen:
            continue
        seen.add(port)
        if _port_is_available(host, port):
            return port
    raise RuntimeError("Nenhuma porta local disponivel entre 5001 e 5100.")


def _open_browser(url: str) -> None:
    time.sleep(0.8)
    webbrowser.open(url)


def main() -> None:
    multiprocessing.freeze_support()
    _assert_bundled_runtime()

    host = os.environ.get("HOST", "127.0.0.1")
    port = _pick_port(host)
    os.environ["PORT"] = str(port)
    url = f"http://{host}:{port}/"

    server = make_server(host, port, app, threaded=True)
    no_browser = os.environ.get("REPORTCHART_NO_BROWSER", "").strip().lower()
    if no_browser not in {"1", "true", "yes", "on"}:
        threading.Thread(target=_open_browser, args=(url,), daemon=True).start()

    print("")
    print(f"  ReportChart Desktop -> {url}")
    print("  Feche esta janela para encerrar o aplicativo.")
    print("")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
