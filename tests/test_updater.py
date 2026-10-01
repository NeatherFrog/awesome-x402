"""Update real temporary installations with controlled GitHub responses."""
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from propdesk.updater import (BRANCH, REPOSITORY, MAX_ARCHIVE_BYTES, Updater,
                              UpdaterError, _SafeRedirect, is_managed_path)

OLD = "1" * 40
NEW = "2" * 40


def release(version="0.2.0", **overrides):
    return {"schema": 1, "repository": REPOSITORY, "branch": BRANCH,
            "version": version, **overrides}


def code(version="0.2.0"):
    return {"RELEASE.json": json.dumps(release(version)).encode(),
            "propdesk/server.py": b"VERSION = '" + version.encode() + b"'\n",
            "static/index.html": b"<html>" + version.encode() + b"</html>",
            "scripts/start.sh": b"#!/bin/sh\necho start\n"}


def archive(files=None, *, commit=NEW, extra=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as output:
        for name, content in (files or code("0.3.0")).items():
            output.writestr(f"awesome-x402-{commit}/{name}", content)
        for info, content in extra or []:
            output.writestr(info, content)
    return stream.getvalue()


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "trading"
        self.root.mkdir()
        self.initial = code()
        for relative, content in self.initial.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.baseline = {**release(), "commit": OLD,
                         "files": {name: hashlib.sha256(value).hexdigest()
                                   for name, value in self.initial.items()}}
        (self.root / ".installed.json").write_text(json.dumps(self.baseline), encoding="utf-8")
        local = self.root / ".local"
        local.mkdir()
        (local / "journal.sqlite").write_bytes(b"precious user journal")
        (self.root / ".env").write_text("SECRET=nevercopy", encoding="utf-8")
        self.updater = Updater(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def fetcher(self, package=None, commit=NEW):
        package = archive() if package is None else package

        def fetch(url, limit, *, authenticated=False):
            if "/commits/" in url:
                self.assertEqual(url, f"https://api.github.com/repos/{REPOSITORY}/commits/{BRANCH}")
                self.assertTrue(authenticated)
                return json.dumps({"sha": commit}).encode()
            self.assertEqual(url, f"https://api.github.com/repos/{REPOSITORY}/zipball/{commit}")
            self.assertTrue(authenticated)
            self.assertEqual(limit, MAX_ARCHIVE_BYTES)
            return package
        return fetch

    def apply(self, package=None, commit=NEW):
        with patch.object(self.updater, "_fetch", side_effect=self.fetcher(package, commit)):
            return self.updater.apply()

    def test_updates_source_preserves_user_data_and_backup(self):
        updated = code("0.3.0")
        updated["propdesk/new.py"] = b"# a new module\n"
        del updated["scripts/start.sh"]
        result = self.apply(archive(updated, extra=[
            (f"awesome-x402-{NEW}/.env", "SECRET=attacker"),
            (f"awesome-x402-{NEW}/.local/journal.sqlite", "bad"),
            (f"awesome-x402-{NEW}/data/user.csv", "bad"),
        ]))
        self.assertTrue(result["updated"])
        self.assertTrue(result["restart_required"])
        self.assertEqual(result["version"], "0.3.0")
        for relative, content in updated.items():
            self.assertEqual((self.root / relative).read_bytes(), content)
        self.assertFalse((self.root / "scripts/start.sh").exists())
        self.assertEqual((self.root / ".local/journal.sqlite").read_bytes(), b"precious user journal")
        self.assertEqual((self.root / ".env").read_text(), "SECRET=nevercopy")
        backup = self.root / ".local/updater/updates/backups" / result["backup"]
        self.assertEqual((backup / "source/propdesk/server.py").read_bytes(), self.initial["propdesk/server.py"])
        self.assertFalse((backup / "source/.env").exists())
        state = json.loads((self.root / ".local/updater/state.json").read_text())
        self.assertEqual(state["commit"], NEW)
        self.assertEqual(state["files"], {path: hashlib.sha256(value).hexdigest()
                                          for path, value in updated.items()})
        self.assertTrue(self.updater.status()["restart_required"])
        fresh = Updater(self.root)
        self.assertFalse(fresh.status()["restart_required"])
        self.assertEqual(fresh.status()["current_commit"], NEW)
        with patch.object(fresh, "_fetch", side_effect=self.fetcher(commit=NEW)):
            self.assertFalse(fresh.apply()["updated"])

    def test_check_exact_fixed_repository_and_no_file_changes(self):
        with patch.object(self.updater, "_fetch", side_effect=self.fetcher()):
            result = self.updater.check()
        self.assertTrue(result["available"])
        self.assertFalse(result["busy"])
        self.assertEqual(result["current_commit"], OLD)
        self.assertEqual(result["latest_commit"], NEW)
        self.assertEqual((self.root / "propdesk/server.py").read_bytes(), self.initial["propdesk/server.py"])
        self.assertFalse((self.root / ".local/updater/state.json").exists())

    def test_no_update_skips_archive_download(self):
        with patch.object(self.updater, "_fetch", return_value=json.dumps({"sha": OLD}).encode()) as fetch:
            self.assertFalse(self.updater.apply()["updated"])
        self.assertEqual(fetch.call_count, 1)

    def test_dirty_source_is_never_overwritten(self):
        changed = self.root / "propdesk/server.py"
        changed.write_bytes(b"my own work")
        with self.assertRaisesRegex(UpdaterError, "Локальный исходный файл изменён"):
            self.apply()
        self.assertEqual(changed.read_bytes(), b"my own work")
        self.assertFalse((self.root / ".local/updater/state.json").exists())

    def test_new_file_collision_is_never_overwritten(self):
        existing = self.root / "propdesk/new.py"
        existing.write_bytes(b"my new file")
        incoming = code("0.3.0")
        incoming["propdesk/new.py"] = b"release new file"
        with self.assertRaisesRegex(UpdaterError, "ваш локальный файл"):
            self.apply(archive(incoming))
        self.assertEqual(existing.read_bytes(), b"my new file")

    def test_git_checkout_apply_disabled_even_with_baseline(self):
        (self.root / ".git").mkdir()
        development = Updater(self.root)
        self.assertEqual(development.status()["mode"], "development")
        with self.assertRaisesRegex(UpdaterError, "Git checkout"):
            development.apply()
        with patch.object(development, "_fetch", side_effect=self.fetcher()):
            self.assertEqual(development.check()["latest_commit"], NEW)

    def test_missing_baseline_disables_apply(self):
        (self.root / ".installed.json").unlink()
        development = Updater(self.root)
        self.assertEqual(development.status()["mode"], "development")
        with self.assertRaisesRegex(UpdaterError, "готовый пакет"):
            development.apply()

    def test_invalid_baseline_hash_disables_apply(self):
        self.baseline["files"]["propdesk/server.py"] = "not a hash"
        (self.root / ".installed.json").write_text(json.dumps(self.baseline))
        self.assertEqual(Updater(self.root).status()["mode"], "development")

    def test_operation_lock_prevents_concurrent_mutations(self):
        self.updater._lock.acquire()
        try:
            self.assertTrue(self.updater.status()["busy"])
            with self.assertRaisesRegex(UpdaterError, "уже выполняется"):
                self.updater.apply()
            with self.assertRaisesRegex(UpdaterError, "уже выполняется"):
                Updater(self.root).check()
        finally:
            self.updater._lock.release()

    def test_second_apply_requires_restart(self):
        self.apply()
        with self.assertRaisesRegex(UpdaterError, "сначала перезапустите"):
            self.apply()

    def test_malformed_commit_rejected_before_download(self):
        for bad in ("../outside", "3" * 39, "g" * 40, None, [NEW]):
            with self.subTest(bad=bad), patch.object(self.updater, "_fetch", return_value=json.dumps({"sha": bad}).encode()):
                with self.assertRaisesRegex(UpdaterError, "некорректный commit"):
                    self.updater.apply()

    def test_wrong_archive_commit_rejected(self):
        with self.assertRaisesRegex(UpdaterError, "недопустимый путь"):
            self.apply(archive(commit=OLD))

    def test_zip_traversal_absolute_backslash_and_drive_rejected(self):
        for name in (f"awesome-x402-{NEW}/../outside", "/absolute",
                     f"awesome-x402-{NEW}/propdesk/../../outside", "C:/absolute",
                     f"awesome-x402-{NEW}/propdesk\\evil.py"):
            with self.subTest(name=name), self.assertRaisesRegex(UpdaterError, "недопустимый путь"):
                # ZipInfo normalizes the native separator while writing on
                # Windows. Inject raw invalid bytes into both ZIP headers so
                # the fixture exercises the archive reader on every platform.
                written_name = name.replace("\\", "/")
                package = archive(extra=[(written_name, b"evil")])
                if "\\" in name:
                    self.assertEqual(package.count(written_name.encode()), 2)
                    package = package.replace(written_name.encode(), name.encode())
                self.apply(package)
        self.assertEqual((self.root / "propdesk/server.py").read_bytes(), self.initial["propdesk/server.py"])

    def test_zip_symlinks_rejected_even_in_ignored_user_directory(self):
        info = zipfile.ZipInfo(f"awesome-x402-{NEW}/data/link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaisesRegex(UpdaterError, "ссылку"):
            self.apply(archive(extra=[(info, "../../outside")]))

    def test_bad_release_metadata_rejected(self):
        for overrides in ({"repository": "other/repo"}, {"branch": "other"}, {"schema": 2}, {"version": "<script>"}):
            package = code("0.3.0")
            package["RELEASE.json"] = json.dumps({**release("0.3.0"), **overrides}).encode()
            with self.subTest(overrides=overrides), self.assertRaises(UpdaterError):
                self.apply(archive(package))

    def test_incomplete_repository_rejected(self):
        with self.assertRaisesRegex(UpdaterError, "обязательные файлы"):
            self.apply(archive({"README.md": b"old awesome list"}))

    def test_symlinked_source_directory_rejected(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        for name in (self.root / "propdesk").iterdir():
            name.unlink()
        (self.root / "propdesk").rmdir()
        try:
            (self.root / "propdesk").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable")
        with self.assertRaisesRegex(UpdaterError, "символические ссылки"):
            self.apply()
        self.assertEqual(list(outside.iterdir()), [])

    def test_failed_write_rolls_back_added_updated_and_removed_files(self):
        incoming = code("0.3.0")
        incoming["propdesk/added.py"] = b"new"
        writer = self.updater._atomic_write
        count = 0

        def interrupted(path, content, mode=0o644):
            nonlocal count
            # Backup manifest is allowed; fail after replacing two source files.
            # Updater resolves paths; Windows may expand RUNNER~1 into its long
            # name, so compare against the same canonical application root.
            if path.is_relative_to(self.updater.root) and ".local" not in path.relative_to(self.updater.root).parts:
                count += 1
                if count == 3:
                    raise OSError("simulated disk failure")
            return writer(path, content, mode)

        with patch.object(self.updater, "_atomic_write", side_effect=interrupted):
            with self.assertRaisesRegex(UpdaterError, "автоматически восстановлены"):
                self.apply(archive(incoming))
        self.assertEqual(count, 3)
        for relative, content in self.initial.items():
            self.assertEqual((self.root / relative).read_bytes(), content)
        self.assertFalse((self.root / "propdesk/added.py").exists())
        self.assertFalse((self.root / ".local/updater/state.json").exists())
        self.assertEqual(self.updater.status()["current_commit"], OLD)

    def test_failed_state_commit_rolls_back_deleted_file(self):
        incoming = code("0.3.0")
        del incoming["scripts/start.sh"]
        writer = self.updater._atomic_write

        def interrupted(path, content, mode=0o644):
            if path.name == "state.json":
                raise OSError("simulated disk failure")
            return writer(path, content, mode)

        with patch.object(self.updater, "_atomic_write", side_effect=interrupted):
            with self.assertRaisesRegex(UpdaterError, "автоматически восстановлены"):
                self.apply(archive(incoming))
        for relative, content in self.initial.items():
            self.assertEqual((self.root / relative).read_bytes(), content)

    def test_github_private_zipball_owner_short_commit_root(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as output:
            for relative, value in code("0.3.0").items():
                output.writestr(f"NeatherFrog-awesome-x402-{NEW[:7]}/{relative}", value)
        self.assertTrue(self.apply(stream.getvalue())["updated"])

    def test_case_colliding_archive_paths_rejected(self):
        package = code("0.3.0")
        package["propdesk/SERVER.py"] = b"case collision"
        with self.assertRaisesRegex(UpdaterError, "повторяющиеся"):
            self.apply(archive(package))

    def test_portable_device_and_trailing_dot_paths_rejected(self):
        for relative in ("propdesk/NUL", "propdesk/COM1.py", "propdesk/file.", "propdesk/file "):
            with self.subTest(relative=relative), self.assertRaisesRegex(UpdaterError, "недопустимый путь"):
                self.apply(archive(extra=[(f"awesome-x402-{NEW}/{relative}", "bad")]))

    def test_extracted_size_and_file_count_enforced(self):
        with patch("propdesk.updater.MAX_EXTRACTED_BYTES", 64):
            with self.assertRaisesRegex(UpdaterError, "допустимый размер"):
                self.apply()
        with patch("propdesk.updater.MAX_FILES", 3):
            with self.assertRaisesRegex(UpdaterError, "Слишком много"):
                self.apply()

    def test_corrupt_zip_rejected_without_source_changes(self):
        with self.assertRaisesRegex(UpdaterError, "повреждённый ZIP"):
            self.apply(b"not a ZIP")
        self.assertEqual((self.root / "propdesk/server.py").read_bytes(), self.initial["propdesk/server.py"])

    def test_cross_process_lock_is_nonblocking(self):
        self.updater._state_directory()
        with self.updater._process_lock():
            with self.assertRaisesRegex(UpdaterError, "другом окне"):
                self.apply()
        self.assertFalse(self.updater.status()["busy"])

    def test_old_process_detects_update_from_other_process(self):
        stale = Updater(self.root)
        self.apply()
        with self.assertRaisesRegex(UpdaterError, "другом окне"):
            stale.apply()
        self.assertTrue(stale.status()["restart_required"])
        self.assertEqual(stale.status()["current_commit"], NEW)

    def test_permission_error_keeps_sanitized_message(self):
        import urllib.error
        sensitive = "https://api.github.com/x?token=do-not-leak"
        with patch("propdesk.updater.urllib.request.build_opener") as builder:
            builder.return_value.open.side_effect = urllib.error.HTTPError(sensitive, 403, sensitive, {}, None)
            with self.assertRaises(UpdaterError) as failure:
                self.updater.check()
        self.assertNotIn("do-not-leak", str(failure.exception))
        self.assertFalse(self.updater.status()["busy"])

    def test_unsafe_file_names_are_unmanaged(self):
        for path in (".local/db", ".git/config", ".env", "data/journal.csv", "dist/app.zip",
                     "propdesk/__pycache__/x.pyc", "propdesk/../../outside", "C:/path", "propdesk\\file"):
            self.assertFalse(is_managed_path(path), path)
        self.assertTrue(is_managed_path("propdesk/updater.py"))
        self.assertTrue(is_managed_path(".env.example"))

    def test_tokens_only_used_for_api_not_archive(self):
        observed = []

        class Response:
            headers = {}
            data = b"abc"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self, limit):
                result, self.data = self.data[:limit], self.data[limit:]
                return result

        class Opener:
            def open(inner_self, request, timeout):
                observed.append(request)
                return Response()

        with patch.dict(os.environ, {"TRADING_GITHUB_TOKEN": "private-test-token"}), \
                patch("propdesk.updater.urllib.request.build_opener", return_value=Opener()):
            self.updater._fetch("https://api.github.com/repos/a/b", 10, authenticated=True)
            self.updater._fetch("https://codeload.github.com/a/b/zip/commit", 10)
        self.assertEqual(observed[0].get_header("Authorization"), "Bearer private-test-token")
        self.assertIsNone(observed[1].get_header("Authorization"))

    def test_download_size_enforced_with_or_without_content_length(self):
        class Response:
            headers = {}
            data = b"123456"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self, limit):
                result, self.data = self.data[:limit], self.data[limit:]
                return result

        class Opener:
            def open(inner_self, request, timeout):
                return Response()

        with patch("propdesk.updater.urllib.request.build_opener", return_value=Opener()):
            with self.assertRaisesRegex(UpdaterError, "превышает"):
                self.updater._fetch("https://api.github.com/repos/a/b", 4)

    def test_redirect_does_not_leak_authentication(self):
        import urllib.request
        request = urllib.request.Request("https://api.github.com/repos/a/b", headers={"Authorization": "Bearer secret"})
        handler = _SafeRedirect()
        for address in ("http://api.github.com/x", "https://evil.example/x", "https://api.github.com:444/x"):
            with self.subTest(address=address), self.assertRaises(UpdaterError):
                handler.redirect_request(request, None, 302, "", {}, address)
        result = handler.redirect_request(request, None, 302, "", {}, "https://api.github.com/repos/renamed/b")
        self.assertEqual(result.get_header("Authorization"), "Bearer secret")
        redirected = handler.redirect_request(request, None, 302, "", {},
                                              "https://codeload.github.com/NeatherFrog/awesome-x402/legacy.zip/" + NEW + "?token=signed")
        self.assertIsNone(redirected.get_header("Authorization"))


if __name__ == "__main__":
    unittest.main()
