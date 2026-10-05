"""DungeonTuber desktop app: the web frontend in a native window (pywebview / WebView2)
backed by an embedded server that only accepts connections from this computer.

Usage: python DungeonTuber.py [--fake] [--debug] [--port N]
"""
import argparse
import os
import socket
import sys
import threading
import time
import urllib.request

import uvicorn

from core.legacy import migrate_legacy_settings
from core.lights import fake_lights_mode
from core.log import setup_logging
from core.utils import get_current_version, get_path
from server.app import create_app
from server.config import ServerConfig

APP_TITLE = "Dungeon Tuber"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port: int) -> uvicorn.Server:
    config = uvicorn.Config(create_app(ServerConfig(local_mode=True)), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="server", daemon=True)
    thread.start()
    return server


def wait_until_ready(url: str, timeout: float = 15) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/api/auth/me", timeout=1):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--fake", action="store_true", help="Use simulated WiZ bulbs")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging and the web inspector")
    parser.add_argument("--port", type=int, default=0, help="Port of the embedded server (default: random free port)")
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.debug:
        os.environ["DEBUG"] = "1"
    setup_logging()
    migrate_legacy_settings()
    if args.fake:
        fake_lights_mode()

    port = args.port or free_port()
    url = f"http://127.0.0.1:{port}"
    server = start_server(port)
    if not wait_until_ready(url):
        print("Embedded server did not start.", file=sys.stderr)
        return 1

    import webview

    window = webview.create_window(f"{APP_TITLE} {get_current_version()}", url, width=1400, height=900, min_size=(900, 600),
                                   background_color="#16181d")

    def on_started():
        if args.smoke_test:
            time.sleep(4)
            print("smoke-test:", window.evaluate_js("document.title + ' | shell=' + !!document.querySelector('.app')"), flush=True)
            window.destroy()

    icon = get_path("docs/icon.ico")
    webview.start(on_started, debug=args.debug, private_mode=False, icon=icon if os.path.exists(icon) else None)
    server.should_exit = True
    return 0


if __name__ == "__main__":
    sys.exit(main())
