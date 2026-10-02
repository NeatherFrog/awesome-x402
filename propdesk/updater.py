"""Transactional updates for the downloadable PROP LAB package, without Git.

Only the fixed GitHub repository is trusted. TLS remains enabled; this is transport
and commit identity verification, not a cryptographically signed release system.
User data and credentials never enter the update archive or source backup.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import stat
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

REPOSITORY = "NeatherFrog/awesome-x402"
BRANCH = "main"
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_EXTRACTED_BYTES = 128 * 1024 * 1024
MAX_FILES = 1000
MAX_METADATA_BYTES = 1024 * 1024
DEFAULT_VERSION = "0.2.0"
_REQUIRED = {"propdesk/server.py", "static/index.html", "RELEASE.json"}
_SOURCE_DIRS = {"propdesk", "static", "docs", "scripts", "tests"}
_SOURCE_FILES = {"README.md", ".gitignore", ".env.example", "Makefile", "RELEASE.json",
                 "launch.py", "launch.bat", "launch.cmd", "launch.sh", "launch.command",
                 "Launch.bat", "Launch.command", "START.bat", "START.command", "start.bat",
                 "START-WINDOWS.bat", "START-MAC.command", "START-LINUX.sh"}
_PROTECTED_PARTS = {".git", ".local", ".venv", "venv", "__pycache__", "node_modules",
                    "artifacts", "dist", ".aws", ".codex", ".agents"}
_WINDOWS_DEVICE = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?\Z", re.IGNORECASE)
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_VERSION = re.compile(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?\Z")
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


class UpdaterError(ValueError):
    """A user-readable error; network messages never contain credential values."""


def is_managed_path(path: str) -> bool:
    """Whether a package source path may be replaced by an update."""
    if not isinstance(path, str) or not path or "\\" in path or ":" in path or "\x00" in path:
        return False
    parts = path.split("/")
    if any(part in ("", ".", "..") or part.casefold() in _PROTECTED_PARTS or
           part.endswith((".", " ")) or _WINDOWS_DEVICE.fullmatch(part) for part in parts):
        return False
    if any(part.casefold().startswith(".env") for part in parts) and path != ".env.example":
        return False
    return path in _SOURCE_FILES or len(parts) > 1 and parts[0] in _SOURCE_DIRS


def _digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _read_json(path: Path):
    if path.is_symlink() or not path.is_file():
        raise UpdaterError("Некорректный файл состояния обновлений")
    if path.stat().st_size > MAX_METADATA_BYTES:
        raise UpdaterError("Слишком большой файл состояния обновлений")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise UpdaterError("Файл состояния обновлений повреждён") from exc


def _release(value):
    if not isinstance(value, dict) or value.get("schema") != 1 or isinstance(value.get("schema"), bool):
        raise UpdaterError("Неподдерживаемый формат RELEASE.json")
    if value.get("repository") != REPOSITORY or value.get("branch") != BRANCH:
        raise UpdaterError("Пакет относится к другому репозиторию или ветке")
    version = value.get("version")
    if not isinstance(version, str) or len(version) > 64 or not _VERSION.fullmatch(version):
        raise UpdaterError("Некорректная версия пакета")
    return value


def _baseline(value):
    _release(value)
    if not isinstance(value.get("commit"), str) or not _SHA.fullmatch(value["commit"]):
        raise UpdaterError("В пакете отсутствует проверяемый commit GitHub")
    files = value.get("files")
    if not isinstance(files, dict) or not _REQUIRED.issubset(files) or len(files) > MAX_FILES:
        raise UpdaterError("В пакете отсутствует манифест исходных файлов")
    for name, digest in files.items():
        if not is_managed_path(name) or not isinstance(digest, str) or not _HASH.fullmatch(digest):
            raise UpdaterError("Некорректный манифест исходных файлов")
    return value


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    """Limit every redirect, and never forward a token to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if (parsed.scheme != "https" or parsed.hostname not in {"api.github.com", "codeload.github.com"}
                or parsed.username or parsed.password or parsed.port not in (None, 443)):
            raise UpdaterError("GitHub перенаправил запрос на недопустимый адрес")
        if parsed.hostname != urlparse(req.full_url).hostname and not (
                urlparse(req.full_url).hostname == "api.github.com" and parsed.hostname == "codeload.github.com"):
            raise UpdaterError("GitHub перенаправил запрос на другой сервер")
        result = super().redirect_request(req, fp, code, msg, headers, newurl)
        if result is not None and parsed.hostname != "api.github.com":
            result.remove_header("Authorization")
        return result


class Updater:
    def __init__(self, root: Path, state_dir: Path | None = None):
        self.root = Path(root).resolve()
        self.state_dir = Path(state_dir) if state_dir is not None else self.root / ".local" / "updater"
        self.state_dir = self.state_dir.absolute()
        self.state_path = self.state_dir / "state.json"
        with _LOCKS_GUARD:
            self._lock = _LOCKS.setdefault(str(self.root), threading.Lock())
        self._release = {"schema": 1, "repository": REPOSITORY, "branch": BRANCH,
                         "version": DEFAULT_VERSION}
        release_path = self.root / "RELEASE.json"
        if release_path.exists():
            self._release = _release(_read_json(release_path))
        self._baseline = None
        self._reason = None
        if (self.root / ".git").exists():
            self._reason = "Git checkout: обновляйте исходники через Git; кнопка доступна в скачанном пакете"
        else:
            baseline_path = self.state_path if self.state_path.exists() else self.root / ".installed.json"
            if baseline_path.exists():
                try:
                    self._baseline = _baseline(_read_json(baseline_path))
                except UpdaterError as exc:
                    self._reason = str(exc)
            else:
                self._reason = "Скачайте готовый пакет: отсутствует исходный манифест установки"
        self._loaded_commit = self._baseline["commit"] if self._baseline else None

    def status(self) -> dict:
        baseline = self._baseline
        result = {"repository": REPOSITORY, "branch": BRANCH,
                  "current_version": baseline["version"] if baseline else self._release["version"],
                  "current_commit": baseline["commit"] if baseline else None,
                  "restart_required": bool(baseline and baseline["commit"] != self._loaded_commit),
                  "busy": self._lock.locked(), "configured": True,
                  "mode": "package" if baseline else "development",
                  "can_apply": bool(baseline and baseline["commit"] == self._loaded_commit
                                    and not self._lock.locked())}
        if self._reason:
            result["reason"] = self._reason
        return result

    def _fetch(self, url: str, limit: int, *, authenticated: bool = False) -> bytes:
        parsed = urlparse(url)
        if (parsed.scheme != "https" or parsed.hostname not in {"api.github.com", "codeload.github.com"}
                or parsed.username or parsed.password or parsed.port not in (None, 443)):
            raise UpdaterError("Недопустимый адрес обновления")
        headers = {"User-Agent": "PROP-LAB-Updater/1", "Accept": "application/vnd.github+json"}
        token = os.environ.get("TRADING_GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if authenticated and parsed.hostname == "api.github.com" and token:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(url, headers=headers)
        try:
            opener = urllib.request.build_opener(_SafeRedirect())
            with opener.open(request, timeout=30) as response:
                declared = response.headers.get("Content-Length")
                if declared is not None:
                    try:
                        declared_size = int(declared)
                    except ValueError:
                        raise UpdaterError("Некорректный размер ответа GitHub") from None
                    if declared_size < 0:
                        raise UpdaterError("Некорректный размер ответа GitHub")
                    if declared_size > limit:
                        raise UpdaterError("Архив обновления превышает допустимый размер")
                chunks = []
                count = 0
                while True:
                    block = response.read(min(1024 * 1024, limit + 1 - count))
                    if not block:
                        break
                    count += len(block)
                    if count > limit:
                        raise UpdaterError("Ответ GitHub превышает допустимый размер")
                    chunks.append(block)
                return b"".join(chunks)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                message = "GitHub отклонил доступ или исчерпан лимит API; повторите позже"
            elif exc.code == 404:
                message = "На GitHub ещё нет доступной версии PROP LAB в ветке main"
            else:
                message = f"GitHub вернул HTTP {exc.code}"
            raise UpdaterError(message) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise UpdaterError("Не удалось связаться с GitHub; проверьте интернет и повторите") from None

    def _latest_commit(self) -> str:
        body = self._fetch(f"https://api.github.com/repos/{REPOSITORY}/commits/{BRANCH}",
                           MAX_METADATA_BYTES, authenticated=True)
        try:
            value = json.loads(body)
        except (ValueError, UnicodeError):
            raise UpdaterError("GitHub вернул некорректные сведения о версии") from None
        commit = value.get("sha") if isinstance(value, dict) else None
        if not isinstance(commit, str) or not _SHA.fullmatch(commit):
            raise UpdaterError("GitHub вернул некорректный commit")
        return commit

    def check(self) -> dict:
        if not self._lock.acquire(blocking=False):
            raise UpdaterError("Обновление уже выполняется")
        try:
            latest = self._latest_commit()
        finally:
            self._lock.release()
        return {**self.status(), "latest_commit": latest, "latest_version": None,
                "available": latest != self.status()["current_commit"]}

    def _safe_path(self, relative: str, *, create_parents: bool = False) -> Path:
        if not is_managed_path(relative):
            raise UpdaterError("Попытка заменить защищённый файл")
        target = self.root.joinpath(*relative.split("/"))
        current = self.root
        for part in relative.split("/"):
            current = current / part
            if current.is_symlink():
                raise UpdaterError("Исходные файлы не должны содержать символические ссылки")
        if create_parents:
            target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def _state_directory(self):
        current = self.state_dir
        while current != current.parent:
            if current.is_symlink():
                raise UpdaterError("Каталог обновлений не должен быть символической ссылкой")
            current = current.parent
        if self.state_path.is_symlink():
            raise UpdaterError("Файл состояния не должен быть символической ссылкой")
        self.state_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _process_lock(self):
        """OS locks release even if the application exits during a download."""
        lock_path = self.state_dir / "operation.lock"
        if lock_path.is_symlink():
            raise UpdaterError("Файл блокировки не должен быть символической ссылкой")
        handle = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        locked = False
        try:
            if os.name == "nt":
                import msvcrt
                if os.fstat(handle).st_size == 0:
                    os.write(handle, b"0")
                os.lseek(handle, 0, os.SEEK_SET)
                try:
                    msvcrt.locking(handle, msvcrt.LK_NBLCK, 1)
                    locked = True
                except OSError:
                    raise UpdaterError("Обновление уже выполняется в другом окне") from None
            else:
                import fcntl
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                except OSError:
                    raise UpdaterError("Обновление уже выполняется в другом окне") from None
            yield
        finally:
            if locked:
                if os.name == "nt":
                    os.lseek(handle, 0, os.SEEK_SET)
                    msvcrt.locking(handle, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)
            os.close(handle)

    def _unpack(self, archive: bytes, commit: str, stage: Path) -> tuple[dict, dict[str, int]]:
        try:
            source = zipfile.ZipFile(io.BytesIO(archive))
        except (zipfile.BadZipFile, OSError):
            raise UpdaterError("GitHub вернул повреждённый ZIP") from None
        owner, repository_name = REPOSITORY.split("/")
        root_name = None
        files = {}
        total_size = 0
        file_count = 0
        seen = set()
        with source:
            entries = source.infolist()
            if len(entries) > MAX_FILES * 2:
                raise UpdaterError("Слишком много записей в архиве обновления")
            for info in entries:
                name = info.filename
                if info.orig_filename != name:
                    raise UpdaterError("Архив содержит недопустимый путь")
                parts = name.rstrip("/").split("/")
                if (not name or "\\" in name or ":" in name or "\x00" in name or
                        any(part in ("", ".", "..") or part.endswith((".", " ")) or
                            _WINDOWS_DEVICE.fullmatch(part) for part in parts)):
                    raise UpdaterError("Архив содержит недопустимый путь")
                if root_name is None:
                    root_name = parts[0]
                    prefix = next((prefix for prefix in (repository_name + "-", owner + "-" + repository_name + "-")
                                   if root_name.startswith(prefix)), None)
                    suffix = root_name[len(prefix):] if prefix else ""
                    if not (7 <= len(suffix) <= 40 and commit.startswith(suffix)):
                        raise UpdaterError("Архив содержит недопустимый путь: commit не совпадает")
                if parts[0] != root_name:
                    raise UpdaterError("Архив содержит недопустимый путь")
                normalized = name.rstrip("/").casefold()
                if normalized in seen:
                    raise UpdaterError("Архив содержит повторяющиеся пути")
                seen.add(normalized)
                mode = info.external_attr >> 16
                kind = stat.S_IFMT(mode)
                if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise UpdaterError("Архив содержит ссылку или специальный файл")
                if info.flag_bits & 1:
                    raise UpdaterError("Зашифрованные ZIP не поддерживаются")
                if info.is_dir():
                    continue
                file_count += 1
                if file_count > MAX_FILES:
                    raise UpdaterError("Слишком много файлов в архиве обновления")
                if len(parts) < 2:
                    raise UpdaterError("Некорректная структура архива")
                total_size += info.file_size
                if total_size > MAX_EXTRACTED_BYTES or info.file_size < 0:
                    raise UpdaterError("Распакованный архив превышает допустимый размер")
                relative = "/".join(parts[1:])
                if not is_managed_path(relative):
                    continue
                if len(files) >= MAX_FILES:
                    raise UpdaterError("Слишком много исходных файлов в архиве")
                destination = stage.joinpath(*parts[1:])
                try:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with source.open(info) as content, destination.open("wb") as output:
                        copied = 0
                        while True:
                            block = content.read(1024 * 1024)
                            if not block:
                                break
                            copied += len(block)
                            if copied > info.file_size or copied > MAX_EXTRACTED_BYTES:
                                raise UpdaterError("Распакованный файл превышает заявленный размер")
                            output.write(block)
                    if copied != info.file_size:
                        raise UpdaterError("Архив содержит повреждённый файл")
                except (zipfile.BadZipFile, RuntimeError, OSError):
                    raise UpdaterError("Архив содержит повреждённый файл или конфликтующие пути") from None
                files[relative] = 0o755 if mode & 0o111 else 0o644
        if not _REQUIRED.issubset(files):
            raise UpdaterError("На GitHub нет полного пакета PROP LAB: не найдены обязательные файлы")
        release = _release(_read_json(stage / "RELEASE.json"))
        return release, files

    def _assert_pristine(self, incoming: dict):
        for relative, expected in self._baseline["files"].items():
            path = self._safe_path(relative)
            if not path.is_file() or _digest(path) != expected:
                raise UpdaterError(f"Локальный исходный файл изменён: {relative}. Сохраните изменения перед обновлением")
        for relative in incoming:
            path = self._safe_path(relative)
            if relative not in self._baseline["files"] and path.exists():
                raise UpdaterError(f"Обновление затронет ваш локальный файл: {relative}. Переместите его перед обновлением")

    @staticmethod
    def _atomic_write(path: Path, data: bytes, mode: int = 0o644):
        handle, temporary = tempfile.mkstemp(prefix=".prop-update-", dir=str(path.parent))
        temporary_path = Path(temporary)
        try:
            with os.fdopen(handle, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.chmod(temporary_path, mode)
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)

    def _install(self, stage: Path, release: dict, files: dict, commit: str) -> dict:
        self._assert_pristine(files)
        before = self._baseline
        backup_id = commit[:12] + "-" + uuid4().hex[:12]
        backup = self.state_dir / "updates" / "backups" / backup_id
        backup.mkdir(parents=True)
        for relative in before["files"]:
            destination = backup.joinpath("source", *relative.split("/"))
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self._safe_path(relative), destination)
        old_state = self.state_path.read_bytes() if self.state_path.exists() else None
        self._atomic_write(backup / "manifest.json", _json_bytes(before), 0o600)
        hashes = {relative: _digest(stage.joinpath(*relative.split("/"))) for relative in files}
        installed = {**release, "commit": commit, "files": hashes, "backup": backup_id}
        changed = []
        new_dirs = set()
        try:
            # Recheck after making the backup, before the first source replacement.
            self._assert_pristine(files)
            for relative in sorted(files):
                destination = self._safe_path(relative)
                parent = destination.parent
                while parent != self.root and not parent.exists():
                    new_dirs.add(parent)
                    parent = parent.parent
                destination = self._safe_path(relative, create_parents=True)
                changed.append(relative)
                self._atomic_write(destination, stage.joinpath(*relative.split("/")).read_bytes(), files[relative])
            for relative in sorted(set(before["files"]) - set(files)):
                changed.append(relative)
                self._safe_path(relative).unlink()
            self._atomic_write(self.state_path, _json_bytes(installed), 0o600)
        except BaseException as exc:
            errors = []
            for relative in reversed(changed):
                try:
                    destination = self._safe_path(relative, create_parents=True)
                    if relative in before["files"]:
                        saved = backup.joinpath("source", *relative.split("/"))
                        # Do not use the installation writer: a transient writer
                        # failure must not prevent the independent rollback path.
                        temporary = destination.with_name(".prop-rollback-" + uuid4().hex)
                        try:
                            shutil.copy2(saved, temporary)
                            os.replace(temporary, destination)
                        finally:
                            temporary.unlink(missing_ok=True)
                    else:
                        destination.unlink(missing_ok=True)
                except OSError:
                    errors.append(relative)
            try:
                if old_state is None:
                    self.state_path.unlink(missing_ok=True)
                else:
                    temporary = self.state_path.with_name(".state-rollback-" + uuid4().hex)
                    temporary.write_bytes(old_state)
                    os.chmod(temporary, 0o600)
                    os.replace(temporary, self.state_path)
            except OSError:
                errors.append("state.json")
            for directory in sorted(new_dirs, key=lambda value: len(value.parts), reverse=True):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            if errors:
                raise UpdaterError(f"Обновление прервано; требуется восстановление из резервной копии {backup_id}") from exc
            raise UpdaterError("Обновление прервано; исходные файлы автоматически восстановлены") from exc
        self._baseline = installed
        self._release = release
        return {"updated": True, "commit": commit, "version": release["version"],
                "restart_required": True, "backup": backup_id,
                "message": "Обновление установлено; перезапустите приложение для загрузки новой версии"}

    def apply(self) -> dict:
        if not self._baseline:
            raise UpdaterError(self._reason or "Кнопка обновления доступна только в готовом пакете")
        if not self._lock.acquire(blocking=False):
            raise UpdaterError("Обновление уже выполняется")
        try:
            if self.status()["restart_required"]:
                raise UpdaterError("Предыдущее обновление установлено; сначала перезапустите приложение")
            self._state_directory()
            with self._process_lock():
                if self.state_path.exists():
                    disk_baseline = _baseline(_read_json(self.state_path))
                    if disk_baseline["commit"] != self._baseline["commit"]:
                        self._baseline = disk_baseline
                        raise UpdaterError("Приложение обновлено в другом окне; сначала перезапустите его")
                latest = self._latest_commit()
                if latest == self._baseline["commit"]:
                    return {"updated": False, "commit": latest, "version": self._baseline["version"],
                            "restart_required": False, "message": "Установлена последняя версия"}
                archive = self._fetch(f"https://api.github.com/repos/{REPOSITORY}/zipball/{latest}",
                                      MAX_ARCHIVE_BYTES, authenticated=True)
                with tempfile.TemporaryDirectory(prefix="stage-", dir=str(self.state_dir)) as temporary:
                    stage = Path(temporary)
                    release, files = self._unpack(archive, latest, stage)
                    return self._install(stage, release, files, latest)
        except OSError:
            raise UpdaterError("Не удалось записать обновление; проверьте права и свободное место") from None
        finally:
            self._lock.release()
