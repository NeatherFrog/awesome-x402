"""Optional browser check of the persistent research autopilot.

Uses a temporary database, the real local HTTP API/controller/scanner, and a
controlled Yahoo denial. No external quotes, live orders, or user data are used.
The final renderer-only fixture checks that diagnostic qualification never
becomes a recommendation when the locked primary market was rejected.
"""
import argparse
import json
import os
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from propdesk.market import parse_csv
from propdesk.server import Application, SCAN_SYMBOLS, make_handler


def main():
    from playwright.sync_api import expect, sync_playwright

    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "artifacts"))
    parser.add_argument("--browser-executable", default="/usr/bin/chromium")
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    errors, posts = [], []

    with tempfile.TemporaryDirectory(prefix="prop-lab-autopilot-browser-") as directory:
        with patch.dict(os.environ, {"TRADING_AUTOPILOT_DEFAULT": "0"}):
            app = Application(directory)
        app.autopilot.poll_interval = 0.05
        handler = make_handler(app)
        handler.log_message = lambda *args: None
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever,
                                  kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()
        try:
            with patch("propdesk.news._fetch",
                       side_effect=ValueError("Контрольная недоступность публичного календаря")) as calendar_fetch, \
                    patch("propdesk.feeds.get_history",
                       side_effect=ValueError("Yahoo Finance HTTP 403: controlled autopilot-test denial")) as feed:
                app.autopilot.start()
                with sync_playwright() as p:
                    browser = p.chromium.launch(executable_path=args.browser_executable,
                                               headless=True, args=["--no-sandbox"])
                    page = browser.new_page(viewport={"width": 1440, "height": 1100}, locale="ru-RU")
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on("request", lambda request: posts.append(request.url)
                            if request.method == "POST" else None)
                    page.goto(f"http://127.0.0.1:{server.server_port}", wait_until="networkidle")
                    page.locator("#advanced-tools").evaluate("element => element.open = true")
                    expect(page.locator("#global-error")).to_be_hidden()
                    expect(page.locator("#autopilot-badge")).to_have_text("Выключен")
                    page.locator("#autopilot-settings").evaluate("element => element.open = true")
                    expect(page.locator("#autopilot-run")).to_be_enabled(timeout=15000)
                    expect(page.locator("#autopilot-results")).to_be_disabled()
                    assert posts == [], "Opening the interface must not send automatic POST requests"
                    assert app.scanner.latest() is None
                    assert feed.call_count == 0, "The disabled development controller must not fetch quotes"
                    assert calendar_fetch.call_count == 0, "Page loads must read only the cached calendar"

                    # Enabling the actual scheduler launches one bounded search.
                    page.locator("#autopilot-settings").evaluate("element => element.open = true")
                    page.locator("#autopilot-toggle").click()
                    expect(page.locator("#autopilot-toggle")).to_contain_text("Выключить")
                    expect(page.locator("#autopilot-error")).to_contain_text("Котировки не получены", timeout=30000)
                    expect(page.locator("#autopilot-result")).to_have_text("Нужна повторная проверка")
                    status = app.autopilot.status()
                    assert status["enabled"] is True and status["running"] is False
                    assert status["result_ready"] is False and status["selected_symbol"] is None
                    assert status["last_attempt_at"] and status["next_attempt_at"]
                    job = app.scanner.latest()
                    assert job["state"] == "completed"
                    assert job["result"]["market_count"] == 0
                    assert job["result"]["markets"] == []
                    assert {call.args[0] for call in feed.call_args_list} == set(SCAN_SYMBOLS)
                    assert feed.call_count == len(SCAN_SYMBOLS)
                    assert calendar_fetch.call_count == 1
                    page.screenshot(path=str(output / "autopilot.png"), full_page=True)

                    page.locator("#autopilot-settings").evaluate("element => element.open = true")
                    page.locator("#autopilot-results").click()
                    expect(page.locator("#scanner-output")).to_contain_text("История не получена")
                    expect(page.locator(".scanner-diagnostics li")).to_have_count(len(SCAN_SYMBOLS))
                    assert "DEMO" not in page.locator("#scanner-output").inner_text()
                    page.locator('[data-tab="overview"]').click()
                    prior_posts = len(posts)
                    page.reload(wait_until="networkidle")
                    expect(page.locator("#autopilot-toggle")).to_contain_text("Выключить")
                    expect(page.locator("#autopilot-error")).to_contain_text("Котировки не получены")
                    assert len(posts) == prior_posts, "Reloading must restore settings without posting"
                    assert app.scanner.latest()["id"] == job["id"]
                    assert feed.call_count == len(SCAN_SYMBOLS), "An enabled reload must not repeat today's search"

                    # An HTTP failure remains visible after the button exits its
                    # busy state. Refreshing clears only the request error.
                    def denied_change(route):
                        if route.request.method == "POST":
                            route.fulfill(status=503, content_type="application/json",
                                          body=json.dumps({"error": "Контрольная ошибка сохранения"}))
                        else:
                            route.continue_()

                    page.route("**/api/autopilot", denied_change)
                    page.locator("#autopilot-settings").evaluate("element => element.open = true")
                    page.locator("#autopilot-toggle").click()
                    expect(page.locator("#autopilot-toggle")).to_be_enabled()
                    expect(page.locator("#autopilot-error")).to_contain_text("Изменение автопилота не выполнено")
                    expect(page.locator("#autopilot-error")).to_contain_text("Контрольная ошибка сохранения")
                    assert app.autopilot.status()["enabled"] is True
                    page.unroute("**/api/autopilot", denied_change)
                    page.locator("#autopilot-settings").evaluate("element => element.open = true")
                    page.locator("#autopilot-refresh").click()
                    expect(page.locator("#autopilot-error")).to_contain_text("Котировки не получены")
                    expect(page.locator("#autopilot-error")).not_to_contain_text("Изменение автопилота")

                    page.locator("#autopilot-settings").evaluate("element => element.open = true")
                    page.locator("#autopilot-toggle").click()
                    expect(page.locator("#autopilot-badge")).to_have_text("Выключен")
                    expect(page.locator("#autopilot-next-attempt")).to_have_text("Остановлен")
                    assert app.autopilot.status()["enabled"] is False
                    assert app.scanner.latest()["id"] == job["id"]

                    # A deliberate one-off retry works while the schedule is
                    # disabled and does not turn automatic execution back on.
                    with page.expect_response(lambda response: response.url.endswith("/api/autopilot")
                                              and response.request.method == "POST"):
                        page.locator("#autopilot-settings").evaluate("element => element.open = true")
                        page.locator("#autopilot-run").click()
                    expect(page.locator("#autopilot-result")).to_have_text("Нужна повторная проверка", timeout=30000)
                    page.locator("#autopilot-settings").evaluate("element => element.open = true")
                    expect(page.locator("#autopilot-run")).to_be_enabled(timeout=15000)
                    retry = app.scanner.latest()
                    assert retry["id"] != job["id"] and retry["state"] == "completed"
                    assert app.autopilot.status()["enabled"] is False
                    assert app.autopilot.status()["job_id"] == retry["id"]
                    assert feed.call_count == 2 * len(SCAN_SYMBOLS)

                    # Replay real archived AAPL bars through the feed adapter
                    # and the actual engine. This is explicitly old fixture
                    # history, not a successful Yahoo download or fresh edge.
                    history = parse_csv((ROOT / "data" / "market-history" / "AAPL-1d.csv")
                                        .read_text(encoding="utf-8"))
                    feed.side_effect = None
                    feed.return_value = {"bars": history, "provenance": {
                        "provider": "Browser check: bundled AAPL archive", "quote_currency": "USD",
                        "historical_only": True, "archived": True,
                        "warnings": ["Архив 2015–2018: контролируемое воспроизведение для проверки интерфейса."]}}
                    app.autopilot.configure({"settings": {"symbols": ["AAPL"],
                                                         "interval": "1d", "range": "2y"}})
                    with page.expect_response(lambda response: response.url.endswith("/api/autopilot")
                                              and response.request.method == "POST"):
                        page.locator("#autopilot-settings").evaluate("element => element.open = true")
                        page.locator("#autopilot-run").click()
                    expect(page.locator("#autopilot-result")).to_have_text("Устойчивый кандидат не найден", timeout=30000)
                    page.locator("#autopilot-settings").evaluate("element => element.open = true")
                    expect(page.locator("#autopilot-run")).to_be_enabled(timeout=15000)
                    completed = app.scanner.latest()
                    assert completed["id"] != retry["id"] and completed["state"] == "completed"
                    assert completed["result"]["primary_symbol"] == "AAPL"
                    assert completed["result"]["selected_symbol"] is None
                    stored = app.store.latest_research()
                    assert stored["autopilot_job_id"] == completed["id"]
                    assert stored["selected_strategy"] is None
                    page.locator("#advanced-tools").evaluate("element => element.open = true")
                    page.locator('[data-tab="lab"]').click()
                    expect(page.locator("#research-output")).to_be_visible(timeout=10000)
                    expect(page.locator("#research-data-banner")).to_contain_text("AAPL")
                    expect(page.locator("#research-data-banner")).to_contain_text("АРХИВ")
                    expect(page.locator("#research-qualified-badge")).to_have_text("ВНЕ РЫНКА")
                    page.locator('[data-tab="overview"]').click()
                    page.screenshot(path=str(output / "autopilot-research.png"), full_page=True)

                    page.locator("#advanced-tools").evaluate("element => element.open = true")
                    page.locator('[data-tab="setups"]').click()
                    expect(page.locator("#calendar-feed-badge")).to_have_text("Нет данных")
                    expect(page.locator("#calendar-feed-message")).to_contain_text("Контрольная недоступность")
                    expect(page.locator('#setup-form [name="news_confirmed"]')).not_to_be_checked()
                    page.locator("#refresh-calendar").click()
                    expect(page.locator("#refresh-calendar")).to_be_enabled(timeout=15000)
                    expect(page.locator("#calendar-feed-badge")).to_have_text("Нет данных")
                    assert calendar_fetch.call_count == 1, "Repeated refresh respects the calendar rate limit"
                    page.locator("#setup-submit").click()
                    expect(page.locator("#setup-output")).to_contain_text("План заблокирован", timeout=10000)
                    expect(page.locator("#setup-output")).to_contain_text("публичный снимок")
                    assert page.locator(".price-zone strong").all_text_contents() == ["—"] * 4
                    page.locator('[data-tab="overview"]').click()

                    # This fixture exercises presentation only; it is not an
                    # invented market study or a fake profitable engine result.
                    fixture = {**app.autopilot.status(), "result_ready": True,
                               "qualified_count": 1, "selected_symbol": None, "last_error": None}

                    def diagnostic_status(route):
                        route.fulfill(status=200, content_type="application/json",
                                      body=json.dumps(fixture))

                    page.route("**/api/autopilot", diagnostic_status)
                    page.locator("#autopilot-settings").evaluate("element => element.open = true")
                    page.locator("#autopilot-refresh").click()
                    expect(page.locator("#autopilot-result")).to_have_text("Устойчивый кандидат не найден")
                    expect(page.locator("#autopilot-error")).to_be_hidden()
                    page.unroute("**/api/autopilot", diagnostic_status)
                    page.locator("#autopilot-settings").evaluate("element => element.open = true")
                    page.locator("#autopilot-refresh").click()
                    expect(page.locator("#autopilot-result")).to_have_text("Устойчивый кандидат не найден")

                    page.locator("#advanced-tools").evaluate("element => element.open = true")
                    page.locator('[data-tab="firms"]').click()
                    expect(page.locator(".firm-review-product")).to_have_count(3, timeout=10000)
                    expect(page.locator("#firm-review-error")).to_be_hidden()
                    expect(page.locator(".firm-review-priority")).to_contain_text("FTMO")
                    expect(page.locator(".firm-review-priority")).to_contain_text("Swing")
                    expect(page.locator(".firm-review-priority")).to_contain_text("Не выбран")
                    expect(page.locator(".firm-review-priority")).to_contain_text("Не установлена")
                    expect(page.locator('[data-review-product="review-ftmo-1step-standard"]')).to_contain_text("10,00%")
                    expect(page.locator("#firm-review-output")).to_contain_text("личного устройства")
                    expect(page.locator("#firm-review-output")).to_contain_text("удалённого сервера")
                    expect(page.locator('#profile-form [name="verified"]')).not_to_be_checked()
                    assert all(profile["status"] != "user_verified" for profile in app.profiles()), \
                        "Reading official drafts must not certify an account profile"
                    page.screenshot(path=str(output / "firm-review.png"), full_page=True)

                    page.set_viewport_size({"width": 390, "height": 844})
                    page.locator(".firm-review-evidence").first.locator("summary").click()
                    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth + 2"), \
                        "Official review overflows the mobile viewport"
                    page.screenshot(path=str(output / "firm-review-mobile.png"), full_page=True)
                    page.locator('[data-tab="overview"]').click()
                    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth + 2"), \
                        "Autopilot overview overflows the mobile viewport"
                    page.screenshot(path=str(output / "autopilot-mobile.png"), full_page=True)
                    assert not errors, "JavaScript errors: " + "; ".join(errors)
                    browser.close()
                    print("PASS: no startup POSTs, real scheduled scan, provider-denial visibility, "
                          "daily reuse/persistence, results handoff, HTTP error persistence, disable/retry controls, "
                          "automatic tagged research display, diagnostic-only rejection, "
                          "official drafts without user verification, unavailable cached calendar, mobile layout")
                    print(f"Screenshots: {output}")
        finally:
            app.autopilot.stop()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    main()
