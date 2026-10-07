"""Command line entry point.

    voxalyzer --token <t>            analyze for a DungeonTuber server (--server, --name; --fake returns mock values), see voxalyzer/agent.py
    voxalyzer <mp3|dir> [...]        analyze files / directories locally, writing the results into the ID3 tags (--force)
    voxalyzer --clean <mp3|dir> ...  remove the analysis results again
"""
import argparse
import asyncio
import logging
import os
import platform
import sys
import traceback
from pathlib import Path

from voxalyzer.agent import DEFAULT_SERVER, Analyzer, run
from voxalyzer.models import ensure_models
from voxalyzer.mp3 import clean_mp3, list_mp3s, update_mp3_results
from voxalyzer.utils import AnalyzeResult

logger = logging.getLogger(__name__)

APP_NAME = "DungeonTuber"


def log_dir() -> Path:
    """%APPDATA%/DungeonTuber/logs like the desktop app; ~/.local/state elsewhere (e.g. in Docker)."""
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / ".local" / "state"
    return base / APP_NAME / "logs"


def setup_logging():
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        directory = log_dir()
        directory.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(directory / "voxalyzer.log"))
    except OSError:
        pass  # read-only file system: console logging only
    logging.basicConfig(level=logging.INFO, handlers=handlers, force=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="voxalyzer", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", help="mp3 files or directories to analyze locally; without any the agent for a DungeonTuber server is started")
    parser.add_argument("--force", action="store_true", help="analyze files again even if they already have results")
    parser.add_argument("--clean", action="store_true", help="remove existing analysis results instead of analyzing")
    env = os.environ.get
    parser.add_argument("--server", default=env("DT_SERVER", DEFAULT_SERVER), help="agent: URL of the DungeonTuber server (default: %(default)s)")
    parser.add_argument("--token", default=env("DT_AGENT_TOKEN"), help="agent: agent token created in the DungeonTuber settings")
    parser.add_argument("--fake", action="store_true", default=env("DT_FAKE_ANALYSIS") == "1", help="agent: return mock values instead of analyzing")
    parser.add_argument("--name", default=env("DT_AGENT_NAME", platform.node() or "voxalyzer"), help="agent: name shown in the server log")
    return parser


def handle_analyze_result(file_path: str, analysis: AnalyzeResult):
    logger.info(f"Analyzed {file_path}:")
    clean_mp3(file_path)
    update_mp3_results(file_path, analysis)

    for key, item in analysis.items():
        logger.debug(f"  {key}: {item}")


def process_paths(paths: list[str], force: bool = False, clean: bool = False):
    from voxalyzer.analyzer import analyze_files

    if not clean:
        ensure_models()
    for path in paths:
        if os.path.isfile(path) and path.lower().endswith(".mp3"):
            files = [path]
        elif os.path.isdir(path):
            files = list_mp3s(path)
        else:
            logger.warning("Unrecognized argument: %s" % path)
            continue

        try:
            if clean:
                clean_mp3(files)
            else:
                analyze_files(files, directory_name=path, force=force, handle_result_callback=handle_analyze_result)
        except KeyboardInterrupt:
            sys.exit(0)
        except Exception as e:
            logger.error(e, exc_info=True)
            traceback.print_exc()


def run_agent(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if not args.token:
        parser.error("--token is required (or DT_AGENT_TOKEN)")
    if not args.fake:
        ensure_models()
    analyzer = Analyzer(args.server, args.token, fake=args.fake)
    try:
        return asyncio.run(run(args.server, args.token, args.name, analyzer))
    except KeyboardInterrupt:
        return 0
    finally:
        analyzer.close()


def main(argv: list[str] | None = None):
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging()

    if args.paths:
        process_paths(args.paths, force=args.force, clean=args.clean)
    else:
        sys.exit(run_agent(args, parser))


if __name__ == "__main__":
    main()
