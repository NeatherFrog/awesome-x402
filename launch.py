#!/usr/bin/env python3
"""Start the local app and reload its child process after a requested update.

This launcher deliberately imports no application modules. Replacing application
files can therefore be followed by a fresh interpreter without stale imports.
"""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser


MIN_PYTHON = (3, 11)
RESTART_EXIT_CODE = 42
STARTUP_TIMEOUT = 15.0
MAX_RAPID_RESTARTS = 3
RESTART_WINDOW = 60.0
REPOSITORY = "NeatherFrog/awesome-x402"
BRANCH = "main"
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_VERSION = re.compile(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?\Z")


class LaunchError(Exception):
    """An actionable startup problem, safe to show without a traceback."""


def _read_metadata(path):
    try:
        path = Path(path)
        if path.is_symlink() or path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("Invalid metadata file")
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LaunchError("Не удалось прочитать манифест приложения. Распакуйте полный архив; проверьте локальное состояние обновлений.") from exc


def read_release(root, data_dir=None):
    """Read the same effective installation commit as the child updater.

    RELEASE.json describes source version; installed/update-state manifests
    bind that version to a GitHub commit. Development Git checkouts do not use
    a package baseline. Relative data paths follow the child's root cwd.
    """
    root = Path(root).resolve()
    release = _read_metadata(root / "RELEASE.json")
    if (not isinstance(release, dict) or type(release.get("schema")) is not int or release["schema"] != 1
            or release.get("repository") != REPOSITORY or release.get("branch") != BRANCH
            or not isinstance(release.get("version"), str) or not _VERSION.fullmatch(release["version"])):
        raise LaunchError("Неверный RELEASE.json: версия, репозиторий или ветка приложения не совпадают.")
    commit = None
    if not (root / ".git").exists():
        directory = Path(data_dir or os.environ.get("TRADING_DATA_DIR") or root / ".local")
        if not directory.is_absolute():
            directory = root / directory
        state = directory / "updater" / "state.json"
        baseline_path = state if state.exists() else root / ".installed.json"
        if baseline_path.exists():
            baseline = _read_metadata(baseline_path)
            if (not isinstance(baseline, dict)
                    or any(baseline.get(key) != release[key] for key in ("schema", "version", "repository", "branch"))
                    or type(baseline.get("schema")) is not int
                    or not isinstance(baseline.get("commit"), str) or not _COMMIT.fullmatch(baseline["commit"])):
                raise LaunchError("Манифест установки и файлы программы не совпадают. Проверьте каталог данных и полный архив приложения.")
            commit = baseline["commit"]
    return {"version": release["version"], "commit": commit}


def probe_health(port, release, timeout=0.6):
    """Only a bounded, direct loopback request; never use a configured proxy."""
    request = urllib.request.Request(
        "http://127.0.0.1:{}/api/health".format(port),
        headers={"Accept": "application/json", "Cache-Control": "no-cache"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200:
                return False
            if response.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                return False
            raw = response.read(8193)
            if len(raw) > 8192:
                return False
        payload = json.loads(raw)
    except (OSError, ValueError, urllib.error.URLError):
        return False
    if not isinstance(payload, dict):
        return False
    return (
        payload.get("ok") is True
        and payload.get("status") == "ok"
        and payload.get("app") == "PROP LAB"
        and payload.get("version") == release["version"]
        and (not release.get("commit") or payload.get("commit") == release["commit"])
    )


def select_port(preferred, release):
    """Reuse a matching app, or find a free port; never stop other processes."""
    for port in range(preferred, min(preferred + 10, 65535) + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.bind(("127.0.0.1", port))
            return port, False
        except OSError:
            if probe_health(port, release):
                return port, True
    raise LaunchError(
        "Порты {}–{} заняты. Запустите с другим портом: python launch.py --port 8100".format(
            preferred, min(preferred + 10, 65535)
        )
    )


def wait_ready(child, port, release, timeout=STARTUP_TIMEOUT):
    deadline = time.monotonic() + timeout
    while True:
        code = child.poll()
        if code is not None:
            raise LaunchError("Приложение завершилось при запуске (код {}). Проверьте сообщение выше.".format(code))
        if probe_health(port, release):
            return
        if time.monotonic() >= deadline:
            raise LaunchError("Приложение не ответило за 15 секунд. Проверьте сообщение выше и повторите запуск.")
        time.sleep(0.15)


def stop_child(child):
    """Terminate only the process started by this launcher."""
    if child is None or child.poll() is not None:
        return
    try:
        child.terminate()
    except ProcessLookupError:
        return
    try:
        child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            child.kill()
        except ProcessLookupError:
            return
        child.wait(timeout=3)


def open_browser(url):
    try:
        opened = webbrowser.open(url, new=2)
    except (OSError, webbrowser.Error):
        opened = False
    if not opened:
        print("Откройте адрес в браузере: " + url, flush=True)


def supervise(root, port=8000, no_browser=False, data_dir=None):
    child = None
    try:
        release = read_release(root, data_dir)
        port, existing = select_port(port, release)
        url = "http://127.0.0.1:{}/".format(port)
        if existing:
            print("PROP LAB уже работает: " + url, flush=True)
            if not no_browser:
                open_browser(url)
            return 0

        environment = os.environ.copy()
        environment["TRADING_SUPERVISED"] = "1"
        command = [sys.executable, "-m", "propdesk", "serve", "--host", "127.0.0.1", "--port", str(port)]
        if data_dir is not None:
            command.extend(["--data-dir", str(data_dir)])
        recent_restarts = []
        opened = False
        while True:
            release = read_release(root, data_dir)
            child = subprocess.Popen(command, cwd=str(root), env=environment)
            wait_ready(child, port, release)
            if not opened:
                print("PROP LAB готов: " + url, flush=True)
                print("Оставьте это окно открытым. Для остановки нажмите Ctrl+C.", flush=True)
                if not no_browser:
                    open_browser(url)
                opened = True
            code = child.wait()
            child = None
            if code != RESTART_EXIT_CODE:
                if code:
                    print("Ошибка: приложение завершилось с кодом {}. Проверьте сообщение выше.".format(code), file=sys.stderr)
                return code

            now = time.monotonic()
            recent_restarts = [stamp for stamp in recent_restarts if now - stamp < RESTART_WINDOW]
            if len(recent_restarts) >= MAX_RAPID_RESTARTS:
                raise LaunchError("Остановлен повторяющийся перезапуск. Запустите приложение заново и проверьте обновление.")
            recent_restarts.append(now)
            print("Обновление установлено. Перезапускаю PROP LAB…", flush=True)
    except KeyboardInterrupt:
        print("\nPROP LAB остановлен.", flush=True)
        return 0
    except (LaunchError, OSError) as exc:
        print("Ошибка: " + str(exc), file=sys.stderr, flush=True)
        return 1
    finally:
        stop_child(child)


def main(argv=None):
    if sys.version_info < MIN_PYTHON:
        print("Нужен Python 3.11 или новее. Установите Python с python.org и запустите снова.", file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description="Запустить PROP LAB с автоматическим перезапуском после обновлений")
    parser.add_argument("--port", type=int, default=8000, help="Первый порт поиска (по умолчанию 8000)")
    parser.add_argument("--no-browser", action="store_true", help="Не открывать браузер автоматически")
    parser.add_argument("--data-dir", help="Каталог дневника и локальных настроек")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port должен быть числом от 1 до 65535")
    root = Path(__file__).resolve().parent

    def request_stop(_signum, _frame):
        raise KeyboardInterrupt

    previous_handler = signal.signal(signal.SIGTERM, request_stop)
    try:
        return supervise(root, args.port, args.no_browser, args.data_dir)
    finally:
        signal.signal(signal.SIGTERM, previous_handler)


if __name__ == "__main__":
    raise SystemExit(main())
