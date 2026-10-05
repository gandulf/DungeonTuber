"""Run the DungeonTuber server: python -m server [--host 0.0.0.0] [--port 8765] [--set-password]"""
import argparse
import getpass
import sys
from pathlib import Path

import uvicorn

from core.legacy import migrate_legacy_settings
from core.lights import fake_lights_mode
from core.log import setup_logging
from core.settings import AppSettings, SettingKeys, settings
from server.app import create_app
from server.auth import password_set, set_password
from server.config import ServerConfig


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(prog="python -m server", description="DungeonTuber web server")
    parser.add_argument("--host", default="127.0.0.1", help="Interface to bind (0.0.0.0 for LAN access)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--local", action="store_true", help="Desktop mode: only loopback clients, no login")
    parser.add_argument("--set-password", action="store_true", help="Set the login password and exit")
    parser.add_argument("--fake-lights", action="store_true", help="Use simulated WiZ bulbs")
    parser.add_argument("--data-dir", type=Path, help="Directory for settings.json and library.db (default: user app data)")
    parser.add_argument("--library", type=Path, action="append", help="Library folder to expose (can be repeated; saved to settings)")
    args = parser.parse_args(argv)

    if args.data_dir:
        args.data_dir.mkdir(parents=True, exist_ok=True)
        AppSettings.set_path(args.data_dir / "settings.json")
        settings.reload()
    if args.library:
        AppSettings.setValue(SettingKeys.LIBRARY_ROOTS, [str(path.resolve()) for path in args.library])

    setup_logging()
    migrate_legacy_settings()

    if args.set_password:
        password = getpass.getpass("New password (empty to remove): ")
        if password and password != getpass.getpass("Repeat password: "):
            print("Passwords do not match.", file=sys.stderr)
            return 1
        set_password(password or None)
        print("Password set." if password else "Password removed.")
        return 0

    if args.fake_lights:
        fake_lights_mode()

    if args.host not in ("127.0.0.1", "localhost", "::1") and not password_set() and not args.local:
        print("Warning: no password set - only this machine can use the server. Run with --set-password first.", file=sys.stderr)

    uvicorn.run(create_app(ServerConfig(local_mode=args.local, data_dir=args.data_dir)), host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
