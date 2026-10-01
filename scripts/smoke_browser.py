"""Optional browser integration test. Needs Playwright and Chromium, not app runtime dependencies.

Uses an isolated temporary database, never the user's journal.
"""
import argparse
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from propdesk.server import Application, make_handler


def main():
    from playwright.sync_api import sync_playwright, expect
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "artifacts"))
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with tempfile.TemporaryDirectory(prefix="prop-lab-browser-") as directory:
        handler = make_handler(Application(directory))
        handler.log_message = lambda *args: None
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path="/usr/bin/chromium", headless=True,
                                             args=["--no-sandbox"])
                page = browser.new_page(viewport={"width": 1440, "height": 1100}, locale="ru-RU")
                page.on("pageerror", lambda err: errors.append(str(err)))
                page.goto(f"http://127.0.0.1:{server.server_port}", wait_until="networkidle")
                expect(page.locator("#global-error")).to_be_hidden()
                expect(page.locator("#active-profile-select option")).to_have_count(3)
                page.screenshot(path=str(output / "overview-empty.png"), full_page=True)
                page.locator('[data-tab="lab"]').click()
                page.locator("#research-submit").click()
                expect(page.locator("#research-output")).to_be_visible(timeout=30000)
                expect(page.locator("#research-error")).to_be_hidden()
                expect(page.locator("#strategies-table tr")).to_have_count(8)
                page.screenshot(path=str(output / "laboratory.png"), full_page=True)
                page.locator("#payout-illustrative").check()
                page.locator("#payout-submit").click()
                expect(page.locator("#payout-submit")).to_be_enabled(timeout=30000)
                expect(page.locator("#payout-error")).to_be_hidden()
                assert "—" not in page.locator("#payout-metrics").inner_text()

                page.locator('[data-tab="checker"]').click()
                form = page.locator("#check-form")
                for name, value in (("entry", "1.1"), ("stop", "1.09"), ("target", "1.12"), ("quantity", "1000")):
                    form.locator(f'[name="{name}"]').fill(value)
                page.locator("#check-submit").click()
                expect(page.locator("#check-result")).to_contain_text("Подтвердите", timeout=5000)
                form.locator('[name="confirmed_rules"]').check()
                page.locator("#check-submit").click()
                expect(page.locator("#check-result")).to_contain_text("бумаж", timeout=5000)
                page.screenshot(path=str(output / "checker.png"), full_page=True)

                page.locator('[data-tab="journal"]').click()
                journal = page.locator("#journal-form")
                for name, value in (("entry", "1.1"), ("exit", "1.11"), ("stop", "1.09"),
                                    ("quantity", "10000"), ("fees", "5"), ("strategy", "UI regression")):
                    journal.locator(f'[name="{name}"]').fill(value)
                journal.locator('[name="notes"]').fill('<img src=x onerror="alert(1)">')
                page.locator("#journal-submit").click()
                expect(page.locator("#journal-table tr")).to_have_count(1, timeout=5000)
                expect(page.locator("#journal-table")).to_contain_text("95")
                page.locator('[data-tab="overview"]').click()
                page.screenshot(path=str(output / "overview.png"), full_page=True)
                page.reload(wait_until="networkidle")
                expect(page.locator("#metric-journal")).to_contain_text("1")
                expect(page.locator("#equity-chart svg")).to_be_visible()

                page.locator('[data-tab="integrations"]').click()
                page.locator("#pine-strategy").select_option("ema_pullback")
                with page.expect_download() as download:
                    page.locator("#pine-download").click()
                destination = output / "example.pine"
                download.value.save_as(destination)
                assert destination.read_text().startswith("//@version=6")
                page.locator('[data-tab="firms"]').click()
                page.locator("#new-profile").click()
                profile = page.locator("#profile-form")
                profile.locator('[name="name"]').fill("Мой тестовый профиль")
                page.locator("#profile-submit").click()
                expect(page.locator("#profiles-list")).to_contain_text("Мой тестовый профиль", timeout=5000)
                page.screenshot(path=str(output / "firms.png"), full_page=True)
                page.locator('[data-tab="journal"]').click()
                page.on("dialog", lambda dialog: dialog.accept())
                page.locator("[data-delete-trade]").first.click()
                expect(page.locator("#journal-table tr")).to_have_count(0)

                page.set_viewport_size({"width": 390, "height": 844})
                page.locator('[data-tab="overview"]').click()
                page.screenshot(path=str(output / "mobile.png"), full_page=True)
                overflow = page.evaluate("document.documentElement.scrollWidth > innerWidth + 2")
                assert not overflow, "Mobile page has horizontal overflow"
                assert not errors, "JavaScript errors: " + "; ".join(errors)
                browser.close()
                print("PASS: browser research/payout, checker block/allow, journal lifecycle, persistence, Pine, profiles, mobile")
                print(f"Screenshots: {output}")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    main()
