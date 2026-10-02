"""Primary navigation leads to setups; manual calculations stay disclosed."""
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
BROWSER = shutil.which("chromium") or shutil.which("google-chrome")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.nodes, self.stack = [], []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "parents": list(self.stack)}
        self.nodes.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                break

    def by_id(self, name):
        return next(node for node in self.nodes if node["attrs"].get("id") == name)


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT / "static/index.html").read_text()
        self.document = Document(self.html)

    def test_primary_navigation_has_six_workflow_destinations(self):
        buttons = [node for node in self.document.nodes if "data-tab" in node["attrs"]]
        primary = [node["attrs"]["data-tab"] for node in buttons
                   if not any(parent["tag"] == "details" for parent in node["parents"])]
        self.assertEqual(primary, ["overview", "strategy", "firms", "journal", "settings", "updates"])
        self.assertNotIn("open", self.document.by_id("advanced-tools")["attrs"])
        for node in buttons:
            self.document.by_id("tab-" + node["attrs"]["data-tab"])

    def test_manual_forms_and_historical_journal_require_explicit_disclosure(self):
        for form, disclosure in (("research-form", "manual-backtest-tools"),
                                 ("scanner-form", "manual-market-tools"),
                                 ("replay-diary-study", "journal-history")):
            with self.subTest(form=form):
                node = self.document.by_id(form)
                self.assertIn(disclosure, [parent["attrs"].get("id") for parent in node["parents"]])
                self.assertNotIn("open", self.document.by_id(disclosure)["attrs"])
        self.assertNotIn("Запустить исследование", self.html)
        self.assertNotIn("Сначала запустите исследование", self.html)
        self.assertNotIn("Автопилот исследований", self.html)

    def test_evidence_and_settings_keep_existing_runtime_controls(self):
        for ident, tab in (("strategy-evidence-card", "tab-strategy"),
                           ("research-progress-summary", "tab-strategy"),
                           ("autopilot-toggle", "tab-settings")):
            node = self.document.by_id(ident)
            self.assertIn(tab, [parent["attrs"].get("id") for parent in node["parents"]])
        ids = [node["attrs"]["id"] for node in self.document.nodes if "id" in node["attrs"]]
        self.assertEqual(len(ids), len(set(ids)))
        for ident in ("find-setups", "today-board", "today-levels", "active-profile-select", "check-form",
                      "journal-form", "apply-update", "research-submit", "scanner-start", "autopilot-run"):
            self.document.by_id(ident)
        self.assertNotIn("hidden", self.document.by_id("tab-overview")["attrs"])
        self.assertIn("hidden", self.document.by_id("tab-strategy")["attrs"])

    @unittest.skipUnless(shutil.which("node"), "Optional Node runtime is unavailable")
    def test_actual_navigation_code_routes_primary_and_advanced_views(self):
        program = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(process.argv[1],'utf8'),html=fs.readFileSync(process.argv[2],'utf8');
const block=source.slice(source.indexOf('const tabMeta ='),source.indexOf('function notice'));
const panelIds=[...html.matchAll(/<section id="(tab-[^"]+)" class="tab-panel"/g)].map(match=>match[1]);
const buttons=[...html.matchAll(/<button class="nav-item[^"]*" data-tab="([^"]+)"/g)].map(match=>({dataset:{tab:match[1]},classList:{toggle(){}},setAttribute(){},removeAttribute(){}}));
const panels=panelIds.map(id=>({id,hidden:true})),elements={};
elements['#advanced-tools']={open:false,querySelector(selector){return ['checker','scanner','lab','setups','integrations'].some(tab=>selector.includes('"'+tab+'"'));}};
const context={document:{title:''},location:{hash:''},history:{replaceState(){}},window:{scrollTo(){}},
$:selector=>elements[selector]||(elements[selector]={textContent:'',innerHTML:''}),
$$:selector=>selector==='.tab-panel'?panels:buttons};
vm.createContext(context);vm.runInContext(block,context);
for(const tab of ['overview','strategy','firms','journal','settings','updates']){
 vm.runInContext('navigate('+JSON.stringify(tab)+',false)',context);
 assert.deepStrictEqual(panels.filter(item=>!item.hidden).map(item=>item.id),['tab-'+tab]);
 assert.strictEqual(elements['#advanced-tools'].open,false);
}
vm.runInContext("navigate('lab',false)",context);assert.strictEqual(elements['#advanced-tools'].open,true);
vm.runInContext("navigate('unknown',false)",context);assert.strictEqual(panels.find(item=>item.id==='tab-overview').hidden,false);
"""
        subprocess.run([shutil.which("node"), "-e", program, str(ROOT / "static/app.js"),
                        str(ROOT / "static/index.html")], check=True, capture_output=True, text=True, timeout=10)

    @unittest.skipUnless(BROWSER and importlib.util.find_spec("playwright"), "Optional local browser is unavailable")
    def test_browser_visible_workflow_and_find_setups_do_not_start_manual_research(self):
        from playwright.sync_api import sync_playwright
        from propdesk.risk import default_profiles
        from propdesk.strategies import catalog

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(ROOT), **kwargs)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        worker.start()
        board = {"mode": "paper", "live_orders": False, "status": "no_trade", "setups": [], "markets": [],
                 "decision": "Допущенных входов нет.", "coverage": {}, "evidence": {"studies": []}}
        requests, errors = [], []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=BROWSER, headless=True, args=["--no-sandbox"])
                page = browser.new_page(viewport={"width": 1365, "height": 900})
                page.on("pageerror", lambda error: errors.append(str(error)))

                def api(route):
                    request = route.request
                    path = request.url.split("/api/", 1)[1]
                    requests.append((request.method, path, request.post_data))
                    if path == "bootstrap":
                        value = {"profiles": default_profiles(), "strategies": catalog(), "version": "test",
                                 "journal": {"trades": [], "stats": {}}, "latest_research": None}
                    elif path == "trader/board":
                        value = {"board": board}
                    elif path == "trader/qualified-setups":
                        value = {"queued": True, "live_orders": False}
                    elif path == "trader/research-progress":
                        value = {"target_monthly_return_pct": 8, "reported_evaluated_configurations": 1100,
                                 "previous_evaluated_configurations": 292, "new_reported_evaluated_configurations": 808,
                                 "new_replay_artifacts_verified_configurations": 808, "studies": [],
                                 "eligible_for_paper": False, "live_orders": False, "telegram_enabled": False}
                    elif path == "trader/evidence":
                        value = {"phase": "no_qualified_strategy", "variant_count": 292, "primary": None,
                                 "studies": [], "forward_test_required": True, "live_orders": False, "telegram_enabled": False}
                    elif path == "autopilot":
                        value = {"enabled": False, "running": False, "result_ready": False}
                    elif path == "scanner/jobs/latest":
                        value = {"job": None}
                    elif path == "signals":
                        value = {"signals": []}
                    else:
                        route.fulfill(status=404, content_type="application/json", body=json.dumps({"error": "Fixture unavailable"}))
                        return
                    route.fulfill(content_type="application/json", body=json.dumps(value))

                page.route("**/api/**", api)
                page.goto(f"http://127.0.0.1:{server.server_port}/static/index.html")
                page.wait_for_function("document.querySelector('#connection-status').textContent==='Локальный сервер'")
                self.assertTrue(page.locator("#find-setups").is_visible())
                self.assertFalse(page.locator("#research-submit").is_visible())
                self.assertFalse(page.locator("#scanner-start").is_visible())
                self.assertFalse(page.locator("#today-levels").is_visible())
                page.locator('[data-tab="strategy"]').click()
                self.assertTrue(page.locator("#strategy-evidence-card").is_visible())
                page.locator('[data-tab="settings"]').click()
                self.assertFalse(page.locator("#autopilot-toggle").is_visible())
                page.locator("#autopilot-settings>summary").click()
                self.assertTrue(page.locator("#autopilot-toggle").is_visible())
                page.locator("#advanced-tools>summary").click()
                page.locator('[data-tab="lab"]').click()
                self.assertFalse(page.locator("#research-submit").is_visible())
                page.locator("#manual-backtest-tools>summary").click()
                self.assertTrue(page.locator("#research-submit").is_visible())
                page.locator('[data-tab="overview"]').click()
                page.locator("#find-setups").click()
                page.wait_for_function("document.querySelector('#find-setups').disabled===false")
                posts = [item for item in requests if item[0] == "POST"]
                self.assertEqual([(item[1], json.loads(item[2])) for item in posts], [("trader/qualified-setups", {})])
                self.assertFalse(page.locator("#today-levels").is_visible())
                self.assertEqual(errors, [])
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
