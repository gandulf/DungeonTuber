"""Run the DungeonTuber server.

    python -m server [--host 0.0.0.0] [--port 8765] [--data-dir DIR] [--library DIR ...] [--set-password]

Every option can also be given as environment variable (used by the Docker image):
DT_HOST, DT_PORT, DT_DATA_DIR, DT_LIBRARY (paths separated by the OS path separator),
DT_S3_BUCKET (+ DT_S3_PREFIX, DT_S3_ENDPOINT, DT_S3_PUBLIC_ENDPOINT, DT_S3_REGION, DT_S3_ACCESS_KEY, DT_S3_SECRET_KEY, DT_S3_NAME, DT_S3_ID, DT_S3_DIRECT=1) adds an
S3 compatible library (needs the boto3 extra), DT_PASSWORD (sets/updates the login password on start), DT_FAKE_LIGHTS=1,
DT_AGENT_TOKEN (token for agents such as the WiZ light agent, see agents/wiz),
DT_FORWARDED_ALLOW_IPS (proxies whose X-Forwarded-* headers are trusted, default 127.0.0.1).
"""
import argparse
import getpass
import os
import sys
from pathlib import Path

import uvicorn

from core.lights import fake_lights_mode
from core.log import setup_logging
from core.settings import AppSettings, SettingKeys, settings
from server.app import create_app
from server.agents import set_agent_token, valid_agent_token
from server.auth import password_set, set_password, verify_password
from server.config import ServerConfig
from server.roots import slugify


def _env_paths(name: str) -> list[Path] | None:
    value = os.environ.get(name)
    return [Path(p) for p in value.split(os.pathsep) if p.strip()] if value else None


def _env_storage() -> list[dict] | None:
    """An S3 compatible library described by DT_S3_* environment variables."""
    bucket = os.environ.get("DT_S3_BUCKET")
    if not bucket:
        return None
    env = os.environ.get
    name = env("DT_S3_NAME", bucket)
    config = {"type": "s3", "id": env("DT_S3_ID") or slugify(name), "bucket": bucket, "prefix": env("DT_S3_PREFIX", ""), "endpoint_url": env("DT_S3_ENDPOINT", ""),
              "public_endpoint_url": env("DT_S3_PUBLIC_ENDPOINT", ""),
              "region": env("DT_S3_REGION", ""), "access_key": env("DT_S3_ACCESS_KEY", ""), "secret_key": env("DT_S3_SECRET_KEY", ""),
              "name": name, "direct": env("DT_S3_DIRECT") == "1"}
    return [{key: value for key, value in config.items() if value not in ("", None)}]


def main(argv: list[str] | None = None):
    env = os.environ.get
    parser = argparse.ArgumentParser(prog="python -m server", description="DungeonTuber web server")
    parser.add_argument("--host", default=env("DT_HOST", "127.0.0.1"), help="Interface to bind (0.0.0.0 for LAN access)")
    parser.add_argument("--port", type=int, default=int(env("DT_PORT", "8765")))
    parser.add_argument("--local", action="store_true", help="Desktop mode: this computer never needs to log in")
    parser.add_argument("--set-password", action="store_true", help="Set the login password and exit")
    parser.add_argument("--fake-lights", action="store_true", default=env("DT_FAKE_LIGHTS") == "1", help="Use simulated WiZ bulbs")
    parser.add_argument("--data-dir", type=Path, default=Path(env("DT_DATA_DIR")) if env("DT_DATA_DIR") else None,
                        help="Directory for settings.json and library.db (default: user app data)")
    parser.add_argument("--library", type=Path, action="append", default=None, help="Library folder to expose (repeatable; saved to settings)")
    parser.add_argument("--forwarded-allow-ips", default=env("DT_FORWARDED_ALLOW_IPS", "127.0.0.1"),
                        help="Reverse proxies whose X-Forwarded-* headers are trusted ('*' inside docker compose)")
    args = parser.parse_args(argv)
    libraries = args.library or _env_paths("DT_LIBRARY")

    if args.data_dir:
        args.data_dir.mkdir(parents=True, exist_ok=True)
        AppSettings.set_path(args.data_dir / "settings.json")
        settings.reload()
    if libraries:
        AppSettings.setValue(SettingKeys.LIBRARY_ROOTS, [str(path.resolve()) for path in libraries])

    storages = _env_storage()
    if storages:
        # the environment manages its own storage; storages added in the settings dialog are kept
        current = [c for c in (AppSettings.value(SettingKeys.STORAGE_ROOTS, type=list) or []) if isinstance(c, dict)]
        AppSettings.setValue(SettingKeys.STORAGE_ROOTS, [c for c in current if c.get("id") != storages[0]["id"]] + storages)

    setup_logging()

    if args.set_password:
        password = getpass.getpass("New password (empty to remove): ")
        if password and password != getpass.getpass("Repeat password: "):
            print("Passwords do not match.", file=sys.stderr)
            return 1
        set_password(password or None)
        print("Password set." if password else "Password removed.")
        return 0

    env_password = env("DT_PASSWORD")
    if env_password and not verify_password(env_password, AppSettings.value(SettingKeys.SERVER_PASSWORD_HASH, type=str)):
        set_password(env_password)

    env_agent_token = env("DT_AGENT_TOKEN")
    if env_agent_token and not valid_agent_token(env_agent_token):
        set_agent_token(env_agent_token)

    if args.fake_lights:
        fake_lights_mode()

    if args.host not in ("127.0.0.1", "localhost", "::1") and not password_set():
        print("Warning: no password set - only this machine can use the server. Use --set-password or DT_PASSWORD.", file=sys.stderr)

    uvicorn.run(create_app(ServerConfig(local_mode=args.local, data_dir=args.data_dir)), host=args.host, port=args.port, log_level="warning",
                proxy_headers=True, forwarded_allow_ips=args.forwarded_allow_ips)
    return 0


if __name__ == "__main__":
    sys.exit(main())
