"""Optional browser check for automatic research; uses an isolated temporary database.

Requires Playwright and Chromium. The archive scan runs the real engine. The
Yahoo-denial scenario mocks the feed adapter, so this check never needs external
market access and never writes to the user's journal or configuration.
"""
import argparse
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from propdesk.server import Application, SCAN_SYMBOLS, make_handler


def main():
    from playwright.sync_api import expect, sync_playwright

    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "artifacts"))
    parser.add_argument("--browser-executable", default="/usr/bin/chromium")
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    scan_requests = []

    with tempfile.TemporaryDirectory(prefix="prop-lab-scanner-browser-") as directory:
        app = Application(directory)
        handler = make_handler(app)
        handler.log_message = lambda *args: None
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever,
                                  kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=args.browser_executable,
                                           headless=True, args=["--no-sandbox"])
                page = browser.new_page(viewport={"width": 1440, "height": 1100}, locale="ru-RU")
                page.on("pageerror", lambda error: errors.append(str(error)))

                def record_request(request):
                    if request.method == "POST" and request.url.endswith("/api/scanner/jobs"):
                        scan_requests.append(request.post_data_json)

                page.on("request", record_request)
                page.goto(f"http://127.0.0.1:{server.server_port}", wait_until="networkidle")
                expect(page.locator("#global-error")).to_be_hidden()
                assert scan_requests == [], "A page load must not create a scanner job"
                assert app.scanner.latest() is None

                page.locator('[data-tab="scanner"]').click()
                form = page.locator("#scanner-form")
                auto_costs = form.locator('[name="use_market_costs"]')
                expect(auto_costs).to_be_checked()
                expect(form.locator('[name="risk_pct"]')).to_be_enabled()
                for name in ("fee_bps", "spread_bps", "slippage_bps"):
                    expect(form.locator(f'[name="{name}"]')).to_be_disabled()

                form.locator(".settings-details > summary").click()
                auto_costs.uncheck()
                for name in ("fee_bps", "spread_bps", "slippage_bps"):
                    expect(form.locator(f'[name="{name}"]')).to_be_enabled()
                auto_costs.check()
                form.locator(".settings-details > summary").click()
                form.locator(".segmented label").filter(
                    has=page.locator('[value="reference"]')).click()
                expect(page.locator("#scanner-online-controls")).to_be_hidden()
                expect(page.locator("#scanner-source-note")).to_contain_text("2015–2018")
                page.locator("#scanner-start").click()
                expect(page.locator("#scanner-start")).to_be_disabled(timeout=5000)
                expect(page.locator("#scanner-output")).to_be_visible(timeout=120000)
                expect(page.locator("#scanner-error")).to_be_hidden()

                job = app.scanner.latest()
                assert job["state"] == "completed", job.get("error")
                report = job["result"]
                assert report["market_count"] == 4
                assert report["selected_symbol"] is None
                assert report.get("selected_profile_id") is None
                assert set(report["training_lock"]["training_results"][index]["symbol"]
                           for index in range(4)) == {"AAPL", "MSFT", "JPM", "XOM"}
                assert 1 <= len(report["markets"]) <= 3
                expect(page.locator(".scanner-market")).to_have_count(len(report["markets"]))
                expect(page.locator("#scanner-output")).to_contain_text(report["primary_symbol"])
                expect(page.locator("#scanner-output")).to_contain_text("Устойчивый кандидат не найден")
                expect(page.locator("#scanner-output")).to_contain_text("Архивные котировки")
                expect(page.locator("#scanner-output")).to_contain_text("Проверка профилей фирм")
                assert len(scan_requests) == 1
                assert scan_requests[0]["config"]["use_market_costs"] is True
                assert "symbols" not in scan_requests[0]
                for market in report["markets"]:
                    config = market["report"]["config"]
                    assert config["fee_bps"] == 2, "Stocks must use the stock execution model"
                    assert config["quantity_step"] == 1
                page.screenshot(path=str(output / "scanner.png"), full_page=True)

                page.locator("[data-use-scan]").first.click()
                expect(page.locator("#research-output")).to_be_visible(timeout=30000)
                expect(page.locator("#research-data-banner")).to_contain_text("АРХИВ")
                page.locator('[data-tab="setups"]').click()
                page.locator("#setup-submit").click()
                expect(page.locator("#setup-output")).to_contain_text("План заблокирован", timeout=10000)
                expect(page.locator("#setup-error")).to_be_hidden()
                expect(page.locator(".price-zone")).to_have_count(4)
                assert page.locator(".price-zone strong").all_text_contents() == ["—"] * 4
                assert page.locator("[data-check-setup]").count() == 0
                page.screenshot(path=str(output / "setups.png"), full_page=True)

                page.locator('[data-tab="scanner"]').click()
                page.reload(wait_until="networkidle")
                expect(page.locator("#scanner-output")).to_be_visible(timeout=10000)
                assert app.scanner.latest()["id"] == job["id"]
                assert len(scan_requests) == 1, "Reloading must restore, not rerun, the job"

                page.locator('[data-tab="lab"]').click()
                page.locator("#load-reference").click()
                expect(page.locator(".reference-report")).to_have_count(11, timeout=10000)
                crypto = page.locator(".reference-report").filter(has_text="ETHBTC")
                crypto.locator("summary").click()
                expect(crypto).to_contain_text("BTC")
                expect(crypto).to_contain_text("не долларовый")
                expect(crypto).to_contain_text("Short моделируется гипотетически")
                assert crypto.locator("[data-research-reference]").count() == 0
                assert page.locator("[data-research-reference]").count() == 4
                page.screenshot(path=str(output / "crypto-archive.png"), full_page=True)

                page.set_viewport_size({"width": 390, "height": 844})
                for tab in ("overview", "scanner", "lab", "setups", "firms", "checker",
                            "journal", "integrations", "updates"):
                    page.locator(f'[data-tab="{tab}"]').click()
                    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth + 2"), \
                        f"Mobile horizontal overflow in {tab}"
                page.locator('[data-tab="scanner"]').click()
                page.screenshot(path=str(output / "scanner-mobile.png"), full_page=True)

                # A controlled provider denial verifies the fallback UI without
                # querying a third party or treating a failed download as DEMO.
                with patch("propdesk.feeds.get_history",
                           side_effect=ValueError("Yahoo Finance HTTP 403: controlled browser-test denial")) as feed:
                    form = page.locator("#scanner-form")
                    form.locator(".segmented label").filter(
                        has=page.locator('[value="yahoo"]')).click()
                    with page.expect_response(lambda response: response.url.endswith("/api/scanner/jobs")
                                              and response.request.method == "POST"):
                        page.locator("#scanner-start").click()
                    expect(page.locator("#scanner-output")).to_contain_text("История не получена", timeout=30000)
                    expect(page.locator("#scanner-error")).to_be_hidden()
                    expect(page.locator(".scanner-diagnostics li")).to_have_count(len(SCAN_SYMBOLS))
                    assert {call.args[0] for call in feed.call_args_list} == set(SCAN_SYMBOLS)
                    failed_download = app.scanner.latest()
                    assert failed_download["state"] == "completed"
                    assert failed_download["result"]["market_count"] == 0
                    assert failed_download["result"]["markets"] == []
                    assert "DEMO" not in page.locator("#scanner-output").inner_text()
                assert len(scan_requests) == 2
                assert not errors, "JavaScript errors: " + "; ".join(errors)
                page.screenshot(path=str(output / "scanner-unavailable.png"), full_page=True)
                browser.close()
                print("PASS: scanner defaults/cost controls, real archive job and polling, "
                      "train-only market choice, unverified firms, research handoff, job persistence, "
                      "stale setup blocks, crypto BTC units, nine mobile tabs, provider-denial diagnostics")
                print(f"Screenshots: {output}")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    main()
