"""Functional local readiness probe; safe to repeat without modifying state."""
import argparse
import json
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from propdesk.version import VERSION


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    try:
        base = f"http://127.0.0.1:{args.port}"
        with urlopen(base + "/api/health", timeout=2) as response:
            health = json.load(response)
        with urlopen(base + "/api/bootstrap", timeout=2) as response:
            bootstrap = json.load(response)
        with urlopen(base + "/static/app.js", timeout=2) as response:
            script = response.read()
        with urlopen(base + "/api/scanner/jobs/latest", timeout=2) as response:
            scanner = json.load(response)
        with urlopen(base + "/api/updates/status", timeout=2) as response:
            updater = json.load(response)
        with urlopen(base + "/api/autopilot", timeout=2) as response:
            autopilot = json.load(response)
        with urlopen(base + "/api/news/status", timeout=2) as response:
            news = json.load(response)
        if health.get("ok") is not True or health.get("mode") != "paper" or bootstrap.get("version") != VERSION:
            raise ValueError("На порту работает другой сервер")
        if len(bootstrap.get("strategies", [])) < 8 or not bootstrap.get("profiles") or len(script) < 100:
            raise ValueError("Каталог, профили или интерфейс не готовы")
        if "job" not in scanner or updater.get("running_version") != VERSION or updater.get("configured") is not True:
            raise ValueError("Автопоиск или обновления не готовы")
        if not isinstance(autopilot.get("enabled"), bool) or news.get("state") not in ("ready", "stale", "unknown"):
            raise ValueError("Автопилот или состояние календаря не готовы")
        if not args.quiet:
            print("READY: API, стратегии, профили, автопилот, календарь, обновления и JavaScript доступны; режим paper")
    except (URLError, OSError, ValueError) as exc:
        if not args.quiet:
            print(f"NOT READY: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
