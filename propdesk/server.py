"""Same-origin local HTTP API for research and a manual paper journal."""
from __future__ import annotations

import hmac
import json
import os
import threading
import tempfile
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from .store import Store, finite
from .version import ROOT, VERSION

STATIC = Path(__file__).resolve().parents[1] / "static"
RESEARCH_LOCK = threading.Lock()
MAX_BODY = 5 * 1024 * 1024
SCAN_SYMBOLS = ("EURUSD", "XAUUSD", "NAS100", "BTCUSD", "MES=F", "MNQ=F", "AAPL", "MSFT")


def execution_assumptions(symbol, provenance):
    """Explicit research priors, never an assertion about a broker's tariff."""
    provider = provenance.get("provider_symbol", symbol)
    futures = {"ES=F": 50, "MES=F": 5, "NQ=F": 20, "MNQ=F": 2, "GC=F": 100, "MGC=F": 10}
    common = {"contract_multiplier": 1, "quantity_step": 1, "fee_per_unit": 0, "max_leverage": 2}
    if provider in futures:
        return {**common, "contract_multiplier": futures[provider], "fee_bps": 0,
                "fee_per_unit": 1.25 if provider in ("MES=F", "MNQ=F", "MGC=F") else 2.5,
                "spread_bps": 0.5, "slippage_bps": 0.5}
    if symbol in ("BTCUSD", "BTC-USD") or provenance.get("instrument_type") == "CRYPTOCURRENCY":
        return {**common, "fee_bps": 10, "spread_bps": 2, "slippage_bps": 2, "quantity_step": 0.00001}
    if symbol in ("EURUSD", "EURUSD=X") or provenance.get("instrument_type") == "CURRENCY":
        return {**common, "fee_bps": 0.3, "spread_bps": 1, "slippage_bps": 0.5, "quantity_step": 1000}
    if provider.startswith("^") or symbol == "NAS100":
        return {**common, "fee_bps": 0.2, "spread_bps": 1, "slippage_bps": 0.5}
    return {**common, "fee_bps": 2, "spread_bps": 1, "slippage_bps": 1}


def payout_cadence(research, trades):
    """Include quiet edges of the full holdout in the completed-trade rate."""
    from .market import utc_datetime
    from .payout import _business_day_count
    data = research.get("data", {})
    if not trades or not data.get("holdout_start") or not data.get("end"):
        return {}
    days = _business_day_count(utc_datetime(data["holdout_start"]).date(),
                               utc_datetime(data["end"]).date())
    if days < 1:
        return {}
    return {"trades_per_day": max(0.001, len(trades) / days),
            "trade_rate_basis": "oos_closed_trades_per_full_holdout_business_day"}


@lru_cache(maxsize=1)
def known_demo_fingerprints():
    from .market import data_fingerprint, demo_bars
    return frozenset(data_fingerprint(demo_bars(symbol=symbol, count=1200, seed=42))
                     for symbol in ("EURUSD", "XAUUSD", "NAS100", "BTCUSD"))


def default_account(profile):
    size = profile["account_size"]
    return {"balance": size, "equity": size, "day_start_balance": size, "day_start_equity": size,
            "high_water_equity": size, "realized_today": 0, "open_risk": 0, "trading_days": 0,
            "confirmed_rules": False}


class Application:
    def __init__(self, directory=None, root=None):
        from .updater import Updater
        self.store = Store(directory)
        self.updater = Updater(root or ROOT, self.store.path.parent / "updater")
        self.running_commit = self.updater.status().get("current_commit")
        self.restart_requested = False
        self._warm_diary_quotes = False
        from .trader import Trader
        self.trader = Trader(self.store.path.parent, root or ROOT)
        from .jobs import ScannerJobs
        self.scanner = ScannerJobs(self.store.path.parent / "scanner", self.trader_scan)
        self.trader.recover(self.scanner)
        from .news import CalendarFeed
        self.news = CalendarFeed(self.store.path.parent)
        from .autopilot import Autopilot
        package = self.updater.status().get("mode") == "package"
        enabled = package and os.environ.get("TRADING_SUPERVISED") == "1"
        default = os.environ.get("TRADING_AUTOPILOT_DEFAULT", "").strip()
        if default in ("0", "1"):
            enabled = default == "1"
        self.autopilot = Autopilot(
            self.store.path.parent / "autopilot.json", self.start_auto_scan,
            self.auto_scan_result, latest_scan=self.scanner.latest,
            can_start=self.auto_scan_available, enabled=enabled)
        self._warm_diary_quotes = self.autopilot.status()["enabled"]

    def auto_scan_available(self):
        if self.restart_requested or self.updater.status().get("busy"):
            return {"allowed": False, "reason": "maintenance"}
        if self.scanner.busy or RESEARCH_LOCK.locked():
            return {"allowed": False, "reason": "research_busy"}
        return {"allowed": True}

    def start_auto_scan(self, payload):
        from .autopilot import ResearchDeferred
        request = self.scan_payload(payload)
        if not RESEARCH_LOCK.acquire(blocking=False):
            raise ResearchDeferred("Дождитесь завершения текущего исследования")
        try:
            if self.restart_requested or self.updater.status().get("busy") or self.scanner.busy:
                raise ResearchDeferred("Исследование или обновление уже выполняется")
            return self.scanner.start(request)
        finally:
            RESEARCH_LOCK.release()

    def auto_scan_result(self, job_id):
        job = self.scanner.get(job_id)
        if job.get("state") == "completed" and isinstance(job.get("result"), dict):
            primary = job["result"].get("primary_symbol")
            market = next((item for item in job["result"].get("markets", [])
                           if item.get("symbol") == primary and item.get("report")), None)
            if market:
                latest = self.store.latest_research()
                if not latest or latest.get("autopilot_job_id") != job_id:
                    report = copy.deepcopy(market["report"])
                    report["autopilot_job_id"] = job_id
                    report["automation"] = "research_only"
                    self.store.save_research(report)
        return job

    def trader_scan(self, payload, progress):
        """Record one bounded attempt around the existing locked scanner worker."""
        job = self.scanner.latest()
        identifier = job["id"]
        self.trader.begin(identifier, payload)

        def tracked(stage, details=None):
            if isinstance(details, dict) and details.get("training_lock"):
                self.trader.training_locked(identifier, details)
            progress(stage, details)

        try:
            # Diary quotes are warmed by this background worker, never by a GET.
            # Their availability does not change qualification or entry rules.
            if self._warm_diary_quotes:
                try:
                    from .diary import warm_diary_quotes
                    progress("diary", {"state": "loading"})
                    diary = warm_diary_quotes(self.trader.root, directory=self.store.path.parent / "diary-quotes")
                    progress("diary", {"state": diary.get("state", "unknown")})
                except Exception:
                    progress("diary", {"state": "unavailable"})
            result = self.scan_markets(payload, tracked)
            self.trader.finish(identifier, result)
            return result
        except BaseException as exc:
            # Error messages may contain vendor URLs or credentials; the compact
            # strategy ledger only records the exception type.
            record = self.trader.attempt(identifier)
            if record and record.get("state") == "running":
                self.trader.finish(identifier, error_type=type(exc).__name__)
            raise

    def trader_board(self):
        context_path = self.store.path.parent / "context.json"
        context = None
        if context_path.exists():
            if context_path.is_symlink() or context_path.stat().st_size > MAX_BODY:
                raise ValueError("Сохранённый контекст имеет недопустимый размер или путь")
            context = json.loads(context_path.read_text(encoding="utf-8"))
        return self.trader.board(self.scanner.latest(), self.autopilot.status(),
                                 self.news.context(), context=context)

    def find_setups(self, payload):
        if payload:
            raise ValueError("Поиск сетапов принимает пустой JSON объект; настройки стратегии выбираются автоматически")
        self._warm_diary_quotes = True
        active = self.scanner.latest()
        if isinstance(active, dict) and active.get("state") in ("queued", "running"):
            from .trader import compact_job
            return {"queued": True, "reused": True, "job": compact_job(active),
                    "automation": self.autopilot.status(), "live_orders": False}
        state = self.autopilot.run_now()
        from .trader import compact_job
        return {"queued": bool(state.get("running") or state.get("manual_requested")),
                "reused": False, "job": compact_job(self.scanner.latest()),
                "automation": state, "live_orders": False}

    def reference_reports(self):
        file = ROOT / "docs" / "research-results.json"
        result = {"reports": [], "archived": True,
                  "notice": "Архивные рыночные данные: результаты не являются актуальными торговыми сигналами."}
        if file.is_file():
            data = json.loads(file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                result.update(data)
            elif isinstance(data, list):
                result["reports"] = data
        edge_file = ROOT / "docs" / "edge-search.json"
        if edge_file.is_file():
            edge = json.loads(edge_file.read_text(encoding="utf-8"))
            locked = edge.get("locked_training", {})
            result["reports"].extend(edge.get("reports", []))
            # The 485-asset training audit stays in the downloadable report;
            # ordinary page loads only need the frozen five-candidate result.
            result["edge_search"] = {key: edge.get(key) for key in (
                "phase", "decision", "accepted_historical_candidates", "live_candidates", "training_lock_sha256")}
            result["edge_search"].update({
                "training_assets_tested": locked.get("training_assets_tested"),
                "parameter_combinations_tested": locked.get("parameter_combinations_tested"),
                "holdout_count": len(edge.get("holdout_results", [])),
            })
        for name in ("independent-results.json", "crypto-results.json"):
            extra_file = ROOT / "docs" / name
            if extra_file.is_file():
                extra = json.loads(extra_file.read_text(encoding="utf-8"))
                result["reports"].extend(extra.get("reports", []))
        result["notice"] = "Архивные исследования, не текущие сигналы. ETH/BTC рассчитан в BTC quote units с гипотетическими short; результаты нельзя переносить в долларовый проп-счёт."
        return result

    def reference_csv(self, symbol):
        if symbol not in ("AAPL", "MSFT", "JPM", "XOM"):
            raise ValueError("Доступные архивы: AAPL, MSFT, JPM, XOM")
        file = ROOT / "data" / "market-history" / f"{symbol}-1d.csv"
        if not file.is_file():
            raise ValueError("Архив ещё не подготовлен; загрузите свои котировки в лаборатории")
        return file.read_text(encoding="utf-8")

    def setup(self, payload):
        from .setups import build_setup
        research = self.store.latest_research()
        if research is None:
            raise ValueError("Сначала выполните исследование в лаборатории")
        context_file = self.store.path.parent / "context.json"
        context = payload.get("context")
        if context is None and context_file.exists():
            context = json.loads(context_file.read_text(encoding="utf-8"))
        effective = copy.deepcopy(context) if isinstance(context, dict) else context
        if effective is None:
            effective = {}
        if isinstance(effective, dict):
            news = effective.get("news")
            empty_manual = (isinstance(news, dict) and news.get("confirmed", False) is False
                            and news.get("source", "") == "" and news.get("events", []) == []
                            and news.get("observed_at") is None)
            if news is None or empty_manual or isinstance(news, dict) and news.get("generation") == "provider":
                effective["news"] = self.news.context()
        result = build_setup(research, effective)
        # Persist explicit manual context, while the provider cache refreshes independently.
        if payload.get("context") is not None:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=context_file.parent,
                                             prefix=".context-", delete=False) as file:
                temporary = Path(file.name)
                json.dump(context, file, ensure_ascii=False, allow_nan=False)
            try:
                os.replace(temporary, context_file)
            finally:
                temporary.unlink(missing_ok=True)
        return result

    def profiles(self):
        from .risk import default_profiles
        return self.store.profiles(default_profiles())

    def profile(self, profile_id=None):
        profiles = self.profiles()
        if profile_id is None:
            return profiles[0]
        for profile in profiles:
            if profile["id"] == profile_id:
                return profile
        raise ValueError("Профиль правил не найден")

    def research(self, payload, *, reference=False):
        from .backtest import run_research
        from .market import demo_bars, parse_csv
        profile = self.profile(payload.get("profile_id"))
        source = payload.get("source", "demo")
        input_source = source
        provenance = None
        symbol = str(payload.get("symbol", "EURUSD")).strip().upper()
        if not symbol or len(symbol) > 32:
            raise ValueError("Укажите symbol длиной до 32 символов")
        config = payload.get("config", {})
        if not isinstance(config, dict):
            raise ValueError("config должен быть объектом")
        config = dict(config)
        # Input bound at API boundary, independent of indicator implementations.
        for key, default, lower, upper in (
            ("account_size", profile["account_size"], 100, 1e9),
            ("risk_pct", 0.25, 0.001, 5), ("fee_bps", 0.2, 0, 100),
            ("spread_bps", 1, 0, 200), ("slippage_bps", 0.5, 0, 100),
            ("train_fraction", 0.6, 0.5, 0.8), ("contract_multiplier", 1, 1e-6, 1e9),
            ("max_leverage", 5, 0.1, 50),
            ("quantity_step", profile.get("quantity_step", 0.01), 0, 1e9),
            ("fee_per_unit", 0, 0, 1e6),
        ):
            config[key] = finite(config.get(key, default), key, lower, upper)
        strategy_ids = config.get("strategy_ids")
        if strategy_ids is not None and (not isinstance(strategy_ids, list) or len(strategy_ids) > 12 or
                                         any(not isinstance(x, str) for x in strategy_ids)):
            raise ValueError("strategy_ids: список максимум из 12 идентификаторов")
        config.update(source=source, symbol=symbol)
        config["max_drawdown_pct"] = finite(config.get("max_drawdown_pct", profile["max_loss_pct"] * 0.8),
                                           "max_drawdown_pct", 0.1, 50)
        # Keep modeled rule floors and research amounts in the same units.
        config["prop_profile"] = {**profile, "account_size": config["account_size"]}
        if source == "demo":
            if symbol not in ("EURUSD", "XAUUSD", "NAS100", "BTCUSD"):
                raise ValueError("Демо доступно для EURUSD, XAUUSD, NAS100, BTCUSD; другие активы загрузите CSV")
            bars = demo_bars(symbol=symbol, count=1200, seed=42)
        elif source == "csv":
            csv_text = payload.get("csv_text")
            if not isinstance(csv_text, str) or not csv_text.strip():
                raise ValueError("Загрузите CSV с time,open,high,low,close,volume")
            bars = parse_csv(csv_text)
        elif source == "yahoo":
            from .feeds import get_history
            history = get_history(symbol, interval=payload.get("interval", "1h"),
                                  range_=payload.get("range", "3mo"))
            bars, provenance = history["bars"], history["provenance"]
            # Validated historical OHLC enter the same evidence engine as CSV.
            source = "csv"
            config["source"] = source
        else:
            raise ValueError("source: demo, csv или yahoo")
        if source == "csv":
            from .market import data_fingerprint
            if data_fingerprint(bars) in known_demo_fingerprints():
                source = "demo"
                config["source"] = "demo"
        result = run_research(bars, config)
        return self.prepare_research(result, bars, profile, input_source=input_source,
                                     provenance=provenance, reference=reference)

    def prepare_research(self, result, bars, profile, *, input_source, provenance=None,
                         reference=False, save=True):
        from .payout import simulate
        from .strategies import atr, ema
        config = result["config"]
        source = result["data"]["source"]
        closes = [bar["close"] for bar in bars]
        current_atr = atr(bars, 14)[-1]
        result["market_context"] = {
            **result.get("market_context", {}),
            "last_bar": bars[-1], "atr14": current_atr, "ema20": ema(closes, 20)[-1],
            "ema50": ema(closes, 50)[-1], "recent_high20": max(b["high"] for b in bars[-20:]),
            "recent_low20": min(b["low"] for b in bars[-20:]),
            "volatility_pct": current_atr / closes[-1] * 100 if current_atr is not None else None,
            "timeframe_minutes": result["data"]["timeframe_minutes"],
        }
        result["profile_rules"] = {key: profile.get(key) for key in (
            "id", "name", "status", "news_allowed", "overnight_allowed", "weekend_allowed", "ea_allowed")}
        result["data"]["input_source"] = input_source
        if reference:
            result["archived"] = True
            result["data"]["input_source"] = "reference"
        if provenance is not None:
            result["data"]["provenance"] = provenance
            result["summary"]["warnings"][:0] = provenance.get("warnings", [])
        if input_source == "csv" and source == "demo":
            result["summary"]["warnings"].insert(0, "Загруженный CSV совпадает со встроенной синтетической историей; сохранён учебный режим.")
        result["mode"] = "research_paper_only"
        result["profile_id"] = profile["id"]
        result["profile_status"] = profile.get("status", "illustrative")
        selected = next((s for s in result["strategies"] if s["id"] == result.get("selected_strategy")), None)
        trades = selected["trades"] if selected else []
        sim_config = {"risk_pct": min(config["risk_pct"], profile.get("max_risk_pct", 1)),
                      "paths": 300, "seed": 42, "returns_are_oos": source == "csv", "data_source": source,
                      **payout_cadence(result, trades)}
        result["payout"] = simulate(trades, profile, sim_config)
        result["firm_comparison"] = []
        if selected:
            for candidate in self.profiles()[:12]:
                sim = simulate(trades, candidate, sim_config)
                result["firm_comparison"].append({"profile_id": candidate["id"], "name": candidate["name"],
                                                   "status": candidate.get("status", "illustrative"), **sim})
        if save:
            result["research_id"] = self.store.save_research(result)
        return result

    def scan_payload(self, payload):
        from .feeds import _arguments
        source = payload.get("source", "yahoo")
        if source not in ("yahoo", "reference"):
            raise ValueError("source автопоиска: yahoo или reference")
        profile = self.profile(payload.get("profile_id"))
        symbols = payload.get("symbols")
        if symbols is None:
            symbols = list(SCAN_SYMBOLS if source == "yahoo" else ("AAPL", "MSFT", "JPM", "XOM"))
        if not isinstance(symbols, list) or not 1 <= len(symbols) <= 12:
            raise ValueError("symbols: список от 1 до 12 тикеров")
        interval, range_ = payload.get("interval", "1h"), payload.get("range", "3mo")
        normalized = []
        for symbol in symbols:
            ticker, _, _ = _arguments(symbol, interval, range_)
            if source == "reference" and ticker not in ("AAPL", "MSFT", "JPM", "XOM", "GOOG"):
                raise ValueError("Архивный сканер: AAPL, MSFT, JPM, XOM, GOOG")
            if ticker not in normalized:
                normalized.append(ticker)
        supplied = payload.get("config", {})
        if not isinstance(supplied, dict):
            raise ValueError("config должен быть объектом")
        config = {key: finite(supplied.get(key, default), key, lower, upper)
                  for key, default, lower, upper in (
                      ("risk_pct", 0.25, 0.001, min(5, profile["max_risk_pct"])),
                      ("fee_bps", 10, 0, 100), ("slippage_bps", 2, 0, 100), ("spread_bps", 2, 0, 200))}
        use_market_costs = supplied.get("use_market_costs", True)
        if not isinstance(use_market_costs, bool):
            raise ValueError("use_market_costs: требуется boolean")
        config["use_market_costs"] = use_market_costs
        return {"source": source, "symbols": normalized, "interval": interval, "range": range_,
                "profile_id": profile["id"], "config": config}

    def scan_markets(self, payload, progress):
        from .feeds import get_history
        from .market import parse_csv
        from .backtest import MIN_RESEARCH_BARS
        from .scanner import scan
        with RESEARCH_LOCK:
            profile = self.profile(payload["profile_id"])
            datasets, errors = {}, []
            symbols = payload["symbols"]
            if payload["source"] == "yahoo":
                progress("calendar", {"source": "economic_calendar"})
                self.news.refresh()
            progress("loading", {"finished": 0, "total": len(symbols)})

            def load(symbol):
                if payload["source"] == "reference":
                    path = ROOT / "data" / ("independent-history/GOOG-1d.csv" if symbol == "GOOG" else
                                              f"market-history/{symbol}-1d.csv")
                    return {"bars": parse_csv(path.read_text(encoding="utf-8")),
                            "provenance": {"provider": "Bundled immutable historical OHLCV",
                                           "source": "csv", "quote_currency": "USD", "archived": True,
                                           "warnings": ["Архив 2004–2018: повторный расчёт, не новый независимый тест или текущие цены."]}}
                return get_history(symbol, interval=payload["interval"], range_=payload["range"])

            with ThreadPoolExecutor(max_workers=3) as pool:
                pending = {pool.submit(load, symbol): symbol for symbol in symbols}
                for finished, future in enumerate(as_completed(pending), 1):
                    symbol = pending[future]
                    try:
                        dataset = future.result()
                        if len(dataset["bars"]) < MIN_RESEARCH_BARS:
                            raise ValueError(f"Для исследования нужно минимум {MIN_RESEARCH_BARS} закрытых баров; увеличьте период")
                        if payload["config"].get("use_market_costs"):
                            dataset["execution_model"] = execution_assumptions(symbol, dataset["provenance"])
                            dataset["provenance"].setdefault("warnings", []).append("Издержки и спецификация — явные исследовательские допущения, не подтверждённые тарифы или разрешение брокера.")
                        datasets[symbol] = dataset
                    except ValueError as exc:
                        errors.append({"symbol": symbol, "error": str(exc)})
                    except Exception:
                        errors.append({"symbol": symbol, "error": "Котировки не получены; используйте проверенный CSV"})
                    progress("loading", {"finished": finished, "total": len(symbols), "symbol": symbol})
            if not datasets:
                # Preserve per-market errors in the completed report, not just one generic failure.
                return {"primary_symbol": None, "selected_symbol": None, "selected_profile_id": None,
                        "markets": [], "fetch_errors": errors, "market_count": 0, "source": payload["source"],
                        "decision": "Котировки недоступны. Загрузите CSV в лабораторию или проверьте доступ к Yahoo.",
                        "warnings": [], "planning_only": True, "live_orders": False}
            if payload["source"] == "reference" and "GOOG" in datasets and len(datasets) > 1:
                # The independent GOOG archive ends in 2013; the four comparison
                # archives share 2015–2018. Different cycles are not a fair ranking.
                del datasets["GOOG"]
                errors.append({"symbol": "GOOG", "error": "Архив GOOG 2004–2013 не пересекается с окном сравнения 2015–2018; исследуйте его отдельно"})
            settings = {**payload["config"], "account_size": profile["account_size"], "account_currency": "USD",
                        "train_fraction": 0.6, "max_leverage": 2, "contract_multiplier": 1,
                        "quantity_step": profile["quantity_step"],
                        "max_drawdown_pct": profile["max_loss_pct"] * 0.8, "prop_profile": profile}
            frozen_lock = {}

            def report_progress(stage, details=None):
                if isinstance(stage, dict):
                    details = stage
                    stage = str(stage.get("phase", "research"))
                detail = dict(details or {})
                if frozen_lock:
                    detail["training_lock"] = frozen_lock
                progress(stage, detail)

            def locked(lock):
                frozen_lock.update(copy.deepcopy(lock))
                report_progress("training_locked")

            result = scan(datasets, settings=settings, profiles=self.profiles(), on_lock=locked,
                          progress=report_progress)
            for market in result.get("markets", []):
                symbol = market["symbol"]
                report = market.get("report")
                if not report:
                    continue
                if symbol != result.get("selected_symbol"):
                    report["selected_strategy"] = None
                    report["summary"]["status"] = "no_qualified_strategy"
                    report["summary"]["warnings"].insert(0, "Глобальный выбор сделан на обучении; этот рынок не допущен как замена основному по результату теста.")
                self.prepare_research(report, datasets[symbol]["bars"], profile,
                                      input_source=payload["source"], provenance=datasets[symbol]["provenance"],
                                      reference=payload["source"] == "reference", save=False)
            result.update(fetch_errors=sorted(errors, key=lambda item: item["symbol"]), market_count=len(datasets),
                          source=payload["source"], interval=payload["interval"], range=payload["range"])
            return result

    def use_scan(self, payload):
        job = self.scanner.get(payload.get("job_id"))
        if job["state"] != "completed":
            raise ValueError("Дождитесь завершения автопоиска")
        symbol = payload.get("symbol")
        market = next((item for item in job["result"].get("markets", []) if item["symbol"] == symbol), None)
        if market is None or not market.get("report"):
            raise ValueError("Укажите рынок из завершённого исследования")
        report = copy.deepcopy(market["report"])
        report["research_id"] = self.store.save_research(report)
        return report


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "PropLab/" + VERSION

        def log_message(self, fmt, *args):
            # No query strings, body contents, or credentials in access logs.
            print(f"HTTP {self.command} {urlparse(self.path).path} {args[1] if len(args) > 1 else ''}", flush=True)

        def respond(self, status, payload, content_type="application/json; charset=utf-8", attachment=None):
            if isinstance(payload, (dict, list)):
                data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
            elif isinstance(payload, str):
                data = payload.encode()
            else:
                data = payload
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            if attachment:
                self.send_header("Content-Disposition", f'attachment; filename="{attachment}"')
            self.end_headers()
            self.wfile.write(data)

        def body(self):
            if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                raise ValueError("Content-Type должен быть application/json")
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise ValueError("Неверный Content-Length") from None
            if not 0 < length <= MAX_BODY:
                raise ValueError("Размер запроса: от 1 байта до 5 МБ")
            def invalid_constant(value):
                raise ValueError(f"Недопустимое число {value}")
            try:
                payload = json.loads(self.rfile.read(length), parse_constant=invalid_constant)
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise ValueError("Неверный JSON") from None
            if not isinstance(payload, dict):
                raise ValueError("JSON должен быть объектом")
            return payload

        def mutation_origin_ok(self):
            origin = self.headers.get("Origin")
            if origin:
                parsed = urlparse(origin)
                if parsed.scheme not in ("http", "https") or parsed.netloc != self.headers.get("Host"):
                    self.respond(403, {"error": "Запросы изменения разрешены только с этого сайта"})
                    return False
            return True

        def host_ok(self):
            # A foreign hostname resolving to loopback must not read a local journal.
            raw = self.headers.get("Host", "")
            try:
                parsed = urlparse("http://" + raw)
                parsed.port
                allowed = {"localhost", "127.0.0.1", "::1", self.server.server_address[0]}
                allowed.update(x.strip().lower() for x in os.environ.get("TRADING_ALLOWED_HOSTS", "").split(",") if x.strip())
                valid = parsed.hostname in allowed and not parsed.username and not parsed.password and not parsed.path
            except ValueError:
                valid = False
            if not valid:
                self.respond(403, {"error": "Hostname не разрешён; настройте TRADING_ALLOWED_HOSTS для своего reverse proxy"})
            return valid

        def do_GET(self):
            if not self.host_ok():
                return
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                if path == "/api/health":
                    self.respond(200, {"ok": True, "status": "ok", "app": "PROP LAB", "mode": "paper",
                                       "version": VERSION, "commit": app.running_commit})
                elif path == "/api/updates/status":
                    status = app.updater.status()
                    if app.scanner.busy:
                        status.update(can_apply=False, reason="Дождитесь завершения автоматического исследования")
                    self.respond(200, {**status, "running_version": VERSION,
                                       "running_commit": app.running_commit,
                                       "supervised": os.environ.get("TRADING_SUPERVISED") == "1"})
                elif path == "/api/scanner/jobs/latest":
                    self.respond(200, {"job": app.scanner.latest()})
                elif path == "/api/trader/board":
                    self.respond(200, app.trader_board())
                elif path == "/api/trader/research-progress":
                    from . import research_campaign
                    query = parse_qs(parsed.query, keep_blank_values=True)
                    if set(query) - {"study"} or any(len(values) != 1 for values in query.values()):
                        raise ValueError("Допустим только один параметр study")
                    result = (research_campaign.report(app.trader.root, query["study"][0])
                              if "study" in query else research_campaign.board(app.trader.root))
                    if result is None:
                        self.respond(404, {"error": "Отчёт ещё не опубликован"})
                    else:
                        self.respond(200, result)
                elif path == "/api/trader/evidence":
                    from . import evidence
                    query = parse_qs(parsed.query, keep_blank_values=True)
                    if set(query) - {"study"} or any(len(v) != 1 for v in query.values()):
                        raise ValueError("Допустим только один параметр study")
                    if "study" in query:
                        result = evidence.report(app.trader.root, query["study"][0])
                        if result is None:
                            self.respond(404, {"error": "Исследование ещё не завершено"})
                        else:
                            self.respond(200, result)
                    else:
                        self.respond(200, evidence.board(app.trader.root))
                elif path == "/api/trader/attempts":
                    query = parse_qs(parsed.query, keep_blank_values=True)
                    if set(query) - {"limit"} or any(len(values) != 1 for values in query.values()):
                        raise ValueError("Журнал поиска принимает только один параметр limit")
                    try:
                        limit = int(query.get("limit", ["20"])[0])
                    except ValueError:
                        raise ValueError("limit: целое число от 1 до 100") from None
                    self.respond(200, app.trader.listing(limit))
                elif path.startswith("/api/trader/attempts/"):
                    query = parse_qs(parsed.query, keep_blank_values=True)
                    if query not in ({}, {"download": ["1"]}):
                        raise ValueError("Экспорт попытки поиска принимает только download=1")
                    record = app.trader.export_attempt(path.removeprefix("/api/trader/attempts/"))
                    attachment = f"strategy-audit-{record['id']}.json" if query else None
                    self.respond(200, record, attachment=attachment)
                elif path == "/api/trader/diary":
                    from .diary import build_diary
                    query = parse_qs(parsed.query, keep_blank_values=True)
                    if set(query) - {"month", "study"} or any(len(values) != 1 for values in query.values()):
                        raise ValueError("Дневник принимает по одному параметру month и study")
                    self.respond(200, build_diary(app.trader.root, month=query.get("month", [None])[0],
                                                 directory=app.store.path.parent / "diary-quotes",
                                                 study=query.get("study", ["sourced_daily"])[0]))
                elif path == "/api/autopilot":
                    self.respond(200, app.autopilot.status())
                elif path == "/api/news/status":
                    self.respond(200, app.news.status())
                elif path.startswith("/api/scanner/jobs/"):
                    self.respond(200, app.scanner.get(path.removeprefix("/api/scanner/jobs/")))
                elif path == "/api/bootstrap":
                    from .strategies import catalog
                    profiles = app.profiles()
                    self.respond(200, {"profiles": profiles, "strategies": catalog(),
                                       "symbols": ["EURUSD", "XAUUSD", "NAS100", "BTCUSD"],
                                       "journal": app.store.journal(), "account": default_account(profiles[0]),
                                       "mode": "paper", "version": VERSION,
                                       "webhook_configured": bool(os.environ.get("TRADING_WEBHOOK_TOKEN")),
                                       "latest_research": app.store.latest_research()})
                elif path == "/api/profiles":
                    self.respond(200, {"profiles": app.profiles()})
                elif path == "/api/firms/review":
                    review = ROOT / "docs" / "prop-firm-review.json"
                    self.respond(200, json.loads(review.read_text(encoding="utf-8")) if review.is_file() else
                                 {"review_status": "unavailable", "products": [], "user_verified": False})
                elif path == "/api/research/current":
                    current = ROOT / "docs" / "current-research.json"
                    if current.is_file():
                        record = json.loads(current.read_text(encoding="utf-8"))
                        self.respond(200, {key: record.get(key) for key in (
                            "schema", "phase", "completed_at", "decision", "primary_symbol",
                            "selected_symbol", "selected_profile_id", "protocol_sha256", "training_lock_sha256",
                            "snapshots", "fetch_errors", "reports", "warnings")})
                    else:
                        self.respond(200, {"phase": "unavailable", "reports": []})
                elif path == "/api/journal":
                    self.respond(200, app.store.journal())
                elif path == "/api/journal/export":
                    self.respond(200, app.store.export_journal(), "text/csv; charset=utf-8", "trading-journal.csv")
                elif path == "/api/research/latest":
                    self.respond(200, {"research": app.store.latest_research()})
                elif path == "/api/research/reference":
                    self.respond(200, app.reference_reports())
                elif path == "/api/data/reference":
                    symbol = parse_qs(parsed.query).get("symbol", ["AAPL"])[0].upper()
                    self.respond(200, app.reference_csv(symbol), "text/csv; charset=utf-8", f"ARCHIVE-{symbol}-1d.csv")
                elif path == "/api/research/export":
                    result = app.store.latest_research()
                    if result is None:
                        raise ValueError("Сначала выполните исследование")
                    self.respond(200, json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2),
                                 "application/json; charset=utf-8", "prop-lab-research.json")
                elif path == "/api/data/example":
                    import csv
                    import io
                    from .market import demo_bars
                    output = io.StringIO(newline="")
                    writer = csv.DictWriter(output, fieldnames=["time", "open", "high", "low", "close", "volume"])
                    writer.writeheader()
                    writer.writerows(demo_bars(symbol="EURUSD", count=1200, seed=42))
                    self.respond(200, output.getvalue(), "text/csv; charset=utf-8", "SYNTHETIC-DEMO-EURUSD.csv")
                elif path == "/api/signals":
                    self.respond(200, {"signals": app.store.signals(), "execution_enabled": False})
                elif path == "/api/export/pine":
                    from .pine import generate
                    sid = parse_qs(parsed.query).get("strategy_id", ["ema_pullback"])[0]
                    self.respond(200, generate(sid), "text/plain; charset=utf-8", "prop-lab.pine")
                elif path.startswith("/api/"):
                    self.respond(404, {"error": "Маршрут не найден"})
                else:
                    files = {"/": ("index.html", "text/html; charset=utf-8"),
                             "/index.html": ("index.html", "text/html; charset=utf-8"),
                             "/style.css": ("style.css", "text/css; charset=utf-8"),
                             "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                             "/static/style.css": ("style.css", "text/css; charset=utf-8"),
                             "/static/app.js": ("app.js", "text/javascript; charset=utf-8")}
                    if path not in files:
                        self.respond(404, {"error": "Файл не найден"})
                    else:
                        name, mime = files[path]
                        self.respond(200, (STATIC / name).read_bytes(), mime)
            except ValueError as exc:
                self.respond(400, {"error": str(exc)})
            except (OSError, RuntimeError) as exc:
                print(f"GET failure: {type(exc).__name__}", flush=True)
                self.respond(500, {"error": "Ошибка локального хранилища или сервера"})

        def do_POST(self):
            if not self.host_ok() or not self.mutation_origin_ok():
                return
            path = urlparse(self.path).path
            try:
                payload = self.body()
                if app.restart_requested:
                    self.respond(503, {"error": "Приложение перезапускается после обновления. Подождите."})
                    return
                if path not in ("/api/updates/check", "/api/updates/apply") and app.updater.status().get("busy"):
                    self.respond(503, {"error": "Выполняется обновление программы. Дождитесь его завершения."})
                    return
                if path == "/api/updates/check":
                    self.respond(200, app.updater.check())
                elif path == "/api/updates/apply":
                    if not RESEARCH_LOCK.acquire(blocking=False):
                        self.respond(409, {"error": "Дождитесь завершения исследования перед обновлением"})
                        return
                    try:
                        if app.scanner.busy:
                            raise ValueError("Дождитесь завершения автоматического исследования перед обновлением")
                        result = app.updater.apply()
                        supervised = os.environ.get("TRADING_SUPERVISED") == "1"
                        restarting = result.get("updated") is True and supervised
                        app.restart_requested = restarting
                    finally:
                        RESEARCH_LOCK.release()
                    self.respond(200, {**result, "restarting": restarting})
                    if restarting:
                        timer = threading.Timer(1.0, self.server.shutdown)
                        timer.daemon = True
                        timer.start()
                elif path == "/api/research":
                    if not RESEARCH_LOCK.acquire(blocking=False):
                        self.respond(429, {"error": "Исследование уже выполняется. Дождитесь результата."})
                        return
                    try:
                        result = app.research(payload)
                    finally:
                        RESEARCH_LOCK.release()
                    self.respond(200, result)
                elif path == "/api/scanner/jobs":
                    request = app.scan_payload(payload)
                    if not RESEARCH_LOCK.acquire(blocking=False):
                        self.respond(429, {"error": "Другое исследование уже выполняется"})
                        return
                    try:
                        result = app.scanner.start(request)
                    finally:
                        RESEARCH_LOCK.release()
                    self.respond(202, result)
                elif path == "/api/autopilot":
                    if payload.get("action") == "run" and set(payload) == {"action"}:
                        self.respond(202, app.autopilot.run_now())
                    else:
                        self.respond(200, app.autopilot.configure(payload))
                elif path == "/api/trader/find-setups":
                    self.respond(202, app.find_setups(payload))
                elif path == "/api/news/refresh":
                    if payload:
                        raise ValueError("Обновление календаря принимает пустой JSON объект")
                    self.respond(200, app.news.refresh())
                elif path == "/api/scanner/use":
                    if app.scanner.busy:
                        raise ValueError("Дождитесь завершения автоматического исследования")
                    self.respond(200, app.use_scan(payload))
                elif path == "/api/research/reference":
                    if not RESEARCH_LOCK.acquire(blocking=False):
                        self.respond(429, {"error": "Исследование уже выполняется"})
                        return
                    try:
                        symbol = str(payload.get("symbol", "AAPL")).upper()
                        result = app.research({"source": "csv", "symbol": symbol,
                                               "csv_text": app.reference_csv(symbol),
                                               "config": {"account_size": 100000, "risk_pct": 0.25,
                                                          "fee_bps": 2, "slippage_bps": 1, "spread_bps": 1,
                                                          "max_leverage": 2, "quantity_step": 1}}, reference=True)
                    finally:
                        RESEARCH_LOCK.release()
                    self.respond(200, result)
                elif path == "/api/setups":
                    self.respond(200, app.setup(payload))
                elif path == "/api/profiles":
                    from .risk import normalize_profile
                    if not payload.get("id"):
                        payload["id"] = "custom-" + str(uuid4())[:8]
                    profile = normalize_profile(payload)
                    app.store.save_profile(profile)
                    self.respond(200, {"profile": profile, "profiles": app.profiles()})
                elif path == "/api/check":
                    from .risk import check_trade
                    account = payload.get("account", {})
                    trade = payload.get("trade", {})
                    if not isinstance(account, dict) or not isinstance(trade, dict):
                        raise ValueError("account и trade должны быть объектами")
                    self.respond(200, check_trade(app.profile(payload.get("profile_id")), account, trade))
                elif path == "/api/payout":
                    from .payout import simulate
                    latest = app.store.latest_research()
                    if latest is None:
                        raise ValueError("Сначала выполните исследование")
                    chosen = next((s for s in latest["strategies"] if s["id"] == payload.get("strategy_id")), None)
                    if chosen is None:
                        raise ValueError("Укажите стратегию из последнего исследования")
                    config = payload.get("config", {})
                    if not isinstance(config, dict):
                        raise ValueError("config должен быть объектом")
                    config = dict(config)
                    if "trades_per_day" not in config:
                        config.update(payout_cadence(latest, chosen["trades"]))
                    config["returns_are_oos"] = latest["data"].get("source") == "csv"
                    config["data_source"] = latest["data"].get("source")
                    if not chosen.get("eligible"):
                        if config.get("allow_illustrative") is not True:
                            raise ValueError("Стратегия не прошла фильтр. Можно запустить только явно учебную симуляцию.")
                    result = simulate(chosen["trades"], app.profile(payload.get("profile_id")), config)
                    self.respond(200, result)
                elif path == "/api/journal":
                    trade = app.store.add_trade(payload)
                    self.respond(201, {"trade": trade, **app.store.journal()})
                elif path == "/api/webhook/tradingview":
                    token = os.environ.get("TRADING_WEBHOOK_TOKEN", "")
                    if not token:
                        self.respond(503, {"error": "Webhook выключен: задайте TRADING_WEBHOOK_TOKEN в окружении"})
                        return
                    auth = self.headers.get("Authorization", "")
                    supplied = auth[7:] if auth.startswith("Bearer ") else payload.pop("token", "")
                    if not isinstance(supplied, str) or not hmac.compare_digest(supplied.encode(), token.encode()):
                        self.respond(401, {"error": "Неверная авторизация webhook"})
                        return
                    if "strategy_id" in payload and "strategy" not in payload:
                        payload["strategy"] = payload["strategy_id"]
                    self.respond(202, {"signal": app.store.add_signal(payload), "executed": False})
                else:
                    self.respond(404, {"error": "Маршрут не найден"})
            except (ValueError, TypeError, KeyError) as exc:
                self.respond(400, {"error": str(exc)})
            except Exception as exc:
                print(f"POST failure: {type(exc).__name__}", flush=True)
                self.respond(500, {"error": "Внутренняя ошибка расчёта; проверьте журнал сервера"})

        def do_DELETE(self):
            if not self.host_ok() or not self.mutation_origin_ok():
                return
            path = urlparse(self.path).path
            if path.startswith("/api/journal/"):
                deleted = app.store.delete_trade(path.rsplit("/", 1)[1])
                self.respond(200 if deleted else 404, {"ok": deleted, **app.store.journal()})
            else:
                self.respond(404, {"error": "Маршрут не найден"})

    return Handler


def serve(host="127.0.0.1", port=8000, directory=None):
    app = Application(directory)
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    httpd.daemon_threads = True
    print(f"PROP LAB {VERSION}: {host}:{httpd.server_port}, paper/research only", flush=True)
    try:
        app.news.start(enabled=lambda: app.autopilot.status()["enabled"])
        app.autopilot.start()
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.autopilot.stop()
        app.news.stop()
        httpd.server_close()
    return 42 if app.restart_requested else 0
