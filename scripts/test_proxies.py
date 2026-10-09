"""Checks a list of proxies against a YouTube link: every proxy fetches the metadata of the video (nothing is downloaded).
Prints whether it worked and how long it took.

    python scripts/test_proxies.py proxies.txt https://www.youtube.com/watch?v=dQw4w9WgXcQ

proxies.txt has one proxy per line (empty lines and lines starting with # are ignored):
    socks5://user:password@host:1080
    http://host:8080
    host:8080            (the scheme of --scheme is added, default http)
"""
import argparse
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SCHEMES = ("http", "https", "socks4", "socks4a", "socks5", "socks5h")


def read_proxies(path: Path, scheme: str) -> list[str]:
    proxies = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        proxies.append(line if "://" in line else f"{scheme}://{line}")
    return list(dict.fromkeys(proxies))


def masked(proxy: str) -> str:
    """The proxy without its password."""
    parts = urlsplit(proxy)
    if parts.password:
        host = parts.netloc.rsplit("@", 1)[-1]
        return urlunsplit((parts.scheme, f"{parts.username}:***@{host}", parts.path, "", ""))
    return proxy


def short(error: Exception) -> str:
    message = re.sub(r"\x1b\[[0-9;]*m", "", str(error))
    message = re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*[\w-]+:\s*)?", "", message).strip()
    return (message[:117] + "...") if len(message) > 120 else message


class Silent:
    """yt-dlp prints its errors itself; here they are only reported in the result line."""

    def debug(self, message): pass

    def info(self, message): pass

    def warning(self, message): pass

    def error(self, message): pass


def check(proxy: str, url: str, timeout: float, runtimes: dict, cookies: str | None) -> dict:
    from yt_dlp import YoutubeDL

    options = {"quiet": True, "no_warnings": True, "noprogress": True, "skip_download": True, "noplaylist": True,
               "proxy": proxy, "socket_timeout": timeout, "retries": 0, "extractor_retries": 0, "logger": Silent(), "js_runtimes": runtimes}
    if cookies:
        options["cookiefile"] = cookies
    started = time.perf_counter()
    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
        return {"proxy": proxy, "ok": True, "seconds": time.perf_counter() - started, "detail": (info or {}).get("title") or ""}
    except Exception as e:  # any failure of the proxy or of YouTube
        return {"proxy": proxy, "ok": False, "seconds": time.perf_counter() - started, "detail": short(e)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Checks proxies against a YouTube link (metadata only).")
    parser.add_argument("proxies", type=Path, help="text file with one proxy per line")
    parser.add_argument("url", help="YouTube link of a video")
    parser.add_argument("--scheme", default="http", choices=SCHEMES, help="scheme for lines without one (default: %(default)s)")
    parser.add_argument("--timeout", type=float, default=5, help="seconds per network operation (default: %(default)s)")
    parser.add_argument("--workers", type=int, default=5, help="proxies checked at the same time (default: %(default)s)")
    parser.add_argument("--cookies", help="cookies.txt of a signed-in YouTube session")
    parser.add_argument("--no-js", action="store_true", help="do not look for deno/node (yt-dlp then works with fewer YouTube clients)")
    args = parser.parse_args()

    proxies = read_proxies(args.proxies, args.scheme)
    if not proxies:
        print(f"No proxies in {args.proxies}")
        return 2
    runtimes: dict = {}
    if not args.no_js:
        try:
            from core.ytimport import _runtime  # the JavaScript runtime the app uses (deno or node, deno is downloaded when missing)
            runtimes = _runtime(lambda message: print(message, file=sys.stderr))
        except Exception as e:
            print(f"No JavaScript runtime ({e}), continuing without", file=sys.stderr)

    print(f"{len(proxies)} proxies, {args.url}\n")
    width = max(len(masked(proxy)) for proxy in proxies)
    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for result in pool.map(lambda proxy: check(proxy, args.url, args.timeout, runtimes, args.cookies), proxies):
            results.append(result)
            status = "OK  " if result["ok"] else "FAIL"
            print(f"{status} {masked(result['proxy']):<{width}}  {result['seconds']:6.2f} s  {result['detail']}", flush=True)

    working = sorted((r for r in results if r["ok"]), key=lambda r: r["seconds"])
    print(f"\n{len(working)} of {len(results)} proxies work")
    for result in working:
        print(f"  {result['seconds']:6.2f} s  {masked(result['proxy'])}")
    return 0 if working else 1


if __name__ == "__main__":
    sys.exit(main())
