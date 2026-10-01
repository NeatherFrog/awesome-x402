#!/usr/bin/env python3
"""Frozen seven-family evaluation on an independent pinned GOOG OHLC archive.

This study does not retune or reuse the earlier Plotly holdouts. EURUSD's source
fixture is preserved but excluded: the upstream timestamps do not state their
zone. Normal execution uses included files, hashes them, and needs no network.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from propdesk.backtest import run_research
from propdesk.market import data_fingerprint, parse_csv, to_csv, validate_bars
from propdesk.risk import normalize_profile
from propdesk.strategies import parameter_candidates

SOURCE_REPOSITORY = "https://github.com/kernc/backtesting.py"
SOURCE_COMMIT = "ca2e2611621e472542ba90f7243a1fa06a7d7108"
SOURCE_BLOBS = {
    "backtesting/test/GOOG.csv": "60e961a567490b157f71888df9e6afb36190a34a40a6286aa38988e2343f1b1a",
    "backtesting/test/EURUSD.csv": "81e977905a006cc8fbc034ebdb83c999a8ed6ba00191dc7ea5ef5b386fb74a82",
    "LICENSE.md": "ad858d53cae05eed9531ecd4c467440803acffe34c69de7b88e03affc5b6a1bd",
    "backtesting/test/__init__.py": "823c9e294b8a70a394350f4089f102a5bd3ddfecb4ac3e8fe41085f6970906e4",
}
CANONICAL_SHA256 = "eebd06257a66a7dac2a4eaa51420ef5eb9533b1463479e693af07e2311f288c0"
CANONICAL_FINGERPRINT = "6d89304e707cf807c5ac1026b576ee03c512e5a4ce348ed31e796928cfd962de"
STRATEGY_IDS = ["ema_pullback", "donchian_breakout", "rsi_reversion", "bollinger_reversion",
                "trend_momentum", "inside_bar_breakout", "volatility_expansion", "buy_hold"]
FIXED_CONFIG = {
    "source": "csv", "symbol": "GOOG", "account_size": 100000,
    "risk_pct": 0.25, "train_fraction": 0.6, "max_leverage": 2,
    "fee_bps": 2, "slippage_bps": 1, "spread_bps": 1, "fee_per_unit": 0,
    "contract_multiplier": 1, "quantity_step": 1, "max_drawdown_pct": 8,
    "strategy_ids": STRATEGY_IDS,
    "prop_profile": normalize_profile({
        "id": "independent-static-illustrative", "name": "Независимый архив: учебные static limits",
        "account_size": 100000, "daily_loss_pct": 5, "max_loss_pct": 10,
        "drawdown_type": "static", "daily_reset_timezone": "UTC",
        "max_calendar_days": None, "status": "illustrative", "verified_at": None,
        "source_url": "", "news_allowed": None, "ea_allowed": None,
        "overnight_allowed": None, "weekend_allowed": None,
    }),
}
EXCLUDED_FX = [{"symbol": "EURUSD", "source_file": "original/EURUSD.csv", "bars": 5000,
                "source_first_time": "2017-04-19 09:00:00", "source_last_time": "2018-02-07 15:00:00",
                "status": "unsupported", "reason": "Hourly timestamps are timezone-naive; upstream loader and source descriptions do not establish their timezone. No UTC assumption or intraday research."}]
LIMITATIONS = [
    "GOOG — подлинный публичный OHLCV fixture 2004–2013 годов; это не актуальные цены, исполнимые котировки или сегодняшние сетапы.",
    "Source commit и байты файлов закреплены и проверяются; первоначальный market vendor и adjustment policy независимо не подтверждены.",
    "Дата GOOG — дневная биржевая сессия. Метка dateT00:00:00Z сохраняет дату, но не обозначает фактическое время открытия NASDAQ.",
    "Весь доступный GOOG fixture выбран до результатов: нет вырезания неудачных режимов или корректировки OHLC. Аудит gap >25% помечает данные unsupported, а не исправляет цену.",
    "Ни один split/дивиденд/rollover не корректируется дополнительно. Отсутствие крупного gap не доказывает полноту корпоративных действий.",
    "EURUSD имеет 5000 timezone-naive hourly bars без подтверждённой зоны: он исключён, UTC не придуман. Никаких intraday FX выводов по нему не сделано.",
    "Фиксированы семь семейств и их существующий grid, риск 0.25%, плечо 2, 60% train/40% untouched holdout. Holdout не выбирает замену победителю train.",
    "Условные издержки: fee 2 bps/сторона, slippage 1 bps/сторона, полный spread 1 bps; примерно 7 bps за оборот. Borrow, финансирование, дивиденды и ликвидность не моделируются.",
    "Дневной OHLC не восстанавливает порядок ticks, реальное исполнение и переносы. Учебный 5% daily/10% static replay проверяет только описанные loss floors.",
    "Положительный исторический P&L и описательный bootstrap не доказывают будущее преимущество, действующие правила или выплаты проп-фирмы. Multiple testing и survivorship bias сохраняются.",
    "Upstream AGPL-3.0 license сохранён рядом с неизменёнными fixtures; код backtesting.py не импортирован и не скопирован в наш движок.",
]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git(source_root, *args):
    try:
        return subprocess.run(["git", *args], cwd=source_root, check=True,
                              capture_output=True).stdout
    except (subprocess.CalledProcessError, OSError):
        raise ValueError("Unable to read the pinned public Git snapshot") from None


def convert_goog(raw):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
    if reader.fieldnames != ["", "Open", "High", "Low", "Close", "Volume"]:
        raise ValueError("Unexpected GOOG source schema")
    bars = []
    for row in reader:
        parsed = date.fromisoformat(row[""])
        if parsed.isoformat() != row[""]:
            raise ValueError("GOOG source requires explicit daily dates, not intraday timezone guesses")
        bars.append({"time": parsed.isoformat() + "T00:00:00Z",
                     **{key: row[key.title()] for key in ("open", "high", "low", "close", "volume")}})
    bars = validate_bars(bars)
    if len(bars) != 2148 or bars[0]["time"] != "2004-08-19T00:00:00Z" or bars[-1]["time"] != "2013-03-01T00:00:00Z":
        raise ValueError("GOOG full pinned sample size or dates differ")
    return bars


def quality_audit(bars):
    gaps = [(abs(current["open"] / previous["close"] - 1) * 100, current["time"])
            for previous, current in zip(bars, bars[1:])]
    suspect = [{"time": stamp, "absolute_open_gap_pct": round(gap, 6)} for gap, stamp in gaps if gap > 25]
    maximum, day = max(gaps, default=(0, None))
    return {"status": "unsupported" if suspect else "validated_with_source_limitations",
            "gap_flag_threshold_pct": 25, "maximum_absolute_open_gap_pct": round(maximum, 6),
            "maximum_gap_date": day, "flagged_gaps": suspect,
            "prices_adjusted_or_cleaned": False,
            "reason": "Large discontinuity requires independent corporate-action evidence" if suspect else None}


def protocol():
    return {"study_id": "independent-goog-2004-2013-fixed-v1", "source_commit": SOURCE_COMMIT,
            "predeclared_analyzed_symbols": ["GOOG"], "examined_source_symbols": ["GOOG", "EURUSD"],
            "full_source_window": "all 2148 GOOG daily source rows; no cuts", "minimum_bars": 300,
            "fixed_config": FIXED_CONFIG,
            "parameter_grid": {key: parameter_candidates(key) for key in STRATEGY_IDS},
            "selection": "Train alone chooses params and strategy; untouched holdout gates winner; no substitution.",
            "registered_before_holdout_evaluation": True, "post_result_grid_changes": False}


def prepare(source_root, data_dir):
    source_root, data_dir = Path(source_root), Path(data_dir)
    head = _git(source_root, "rev-parse", "HEAD").decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", head) or head != SOURCE_COMMIT:
        raise ValueError("Source checkout must match the exact pinned immutable 40-character commit")
    blobs = {path: _git(source_root, "show", SOURCE_COMMIT + ":" + path) for path in SOURCE_BLOBS}
    for path, digest in SOURCE_BLOBS.items():
        if hashlib.sha256(blobs[path]).hexdigest() != digest:
            raise ValueError("Source snapshot blob checksum mismatch: " + path)
    bars = convert_goog(blobs["backtesting/test/GOOG.csv"])
    canonical = to_csv(bars).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != CANONICAL_SHA256 or data_fingerprint(bars) != CANONICAL_FINGERPRINT:
        raise ValueError("Canonical GOOG conversion does not match preregistered content")
    excluded_fx = list(csv.DictReader(io.StringIO(blobs["backtesting/test/EURUSD.csv"].decode())))
    if (len(excluded_fx) != 5000 or excluded_fx[0][""] != EXCLUDED_FX[0]["source_first_time"]
            or excluded_fx[-1][""] != EXCLUDED_FX[0]["source_last_time"]):
        raise ValueError("Excluded EURUSD fixture size differs from the pinned source")
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "original").mkdir(exist_ok=True)
    # The fixed protocol is saved before the first run of the strategy engine.
    (data_dir / "protocol.json").write_text(json.dumps(protocol(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (data_dir / "original" / "GOOG.csv").write_bytes(blobs["backtesting/test/GOOG.csv"])
    (data_dir / "original" / "EURUSD.csv").write_bytes(blobs["backtesting/test/EURUSD.csv"])
    (data_dir / "BACKTESTING-PY-LICENSE.md").write_bytes(blobs["LICENSE.md"])
    (data_dir / "GOOG-1d.csv").write_bytes(canonical)
    manifest = {
        "schema": 1, "source_repository": SOURCE_REPOSITORY, "source_commit": SOURCE_COMMIT,
        "source_blob_sha256": SOURCE_BLOBS, "acquisition": "Read-only HTTPS Git proxy; pinned Git blobs, no external executable dependency",
        "source_url": SOURCE_REPOSITORY + "/blob/" + SOURCE_COMMIT + "/backtesting/test/GOOG.csv",
        "license": "GNU Affero General Public License version 3, upstream LICENSE.md retained verbatim",
        "conversion": "Daily session date -> dateT00:00:00Z. Copy source OHLCV unchanged; no sorting/resampling/imputation/adjustments.",
        "datasets": [{"symbol": "GOOG", "file": "GOOG-1d.csv", "bars": len(bars),
                      "start": bars[0]["time"], "end": bars[-1]["time"], "timeframe": "1d",
                      "sha256": CANONICAL_SHA256, "data_fingerprint": CANONICAL_FINGERPRINT,
                      "quality": quality_audit(bars)}],
        "excluded": EXCLUDED_FX,
        "limitations": LIMITATIONS,
    }
    (data_dir / "provenance.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def load_data(data_dir):
    data_dir = Path(data_dir)
    manifest = json.loads((data_dir / "provenance.json").read_text(encoding="utf-8"))
    if (manifest.get("source_commit") != SOURCE_COMMIT or manifest.get("source_blob_sha256") != SOURCE_BLOBS
            or manifest.get("source_repository") != SOURCE_REPOSITORY
            or manifest.get("source_url") != SOURCE_REPOSITORY + "/blob/" + SOURCE_COMMIT + "/backtesting/test/GOOG.csv"
            or manifest.get("excluded") != EXCLUDED_FX):
        raise ValueError("Study provenance differs from the immutable source snapshot")
    if json.loads((data_dir / "protocol.json").read_text(encoding="utf-8")) != protocol():
        raise ValueError("Research protocol or engine parameter grid changed; do not reuse this holdout for tuning")
    for local, upstream in (("original/GOOG.csv", "backtesting/test/GOOG.csv"),
                            ("original/EURUSD.csv", "backtesting/test/EURUSD.csv"),
                            ("BACKTESTING-PY-LICENSE.md", "LICENSE.md")):
        if sha256(data_dir / local) != SOURCE_BLOBS[upstream]:
            raise ValueError("Included source archive or license changed: " + local)
    datasets = manifest.get("datasets")
    if not isinstance(datasets, list) or len(datasets) != 1 or datasets[0].get("symbol") != "GOOG" or datasets[0].get("file") != "GOOG-1d.csv":
        raise ValueError("Only the predeclared GOOG dataset may be analyzed")
    for key, value in {"bars": 2148, "start": "2004-08-19T00:00:00Z", "end": "2013-03-01T00:00:00Z", "timeframe": "1d"}.items():
        if datasets[0].get(key) != value:
            raise ValueError("Pinned sample metadata differs from the source dates or full row count")
    path = data_dir / "GOOG-1d.csv"
    if datasets[0].get("sha256") != CANONICAL_SHA256 or sha256(path) != CANONICAL_SHA256:
        raise ValueError("Canonical CSV changed; do not silently reuse or tune the holdout")
    bars = parse_csv(path.read_text(encoding="utf-8"))
    if data_fingerprint(bars) != CANONICAL_FINGERPRINT or datasets[0].get("data_fingerprint") != CANONICAL_FINGERPRINT:
        raise ValueError("GOOG canonical bar fingerprint mismatch")
    if quality_audit(bars) != datasets[0].get("quality"):
        raise ValueError("Quality-audit metadata differs from the full unchanged price history")
    return bars, manifest


def research(data_dir, as_of):
    bars, manifest = load_data(data_dir)
    engine_files = ("backtest.py", "strategies.py", "market.py", "risk.py", "compliance.py", "timezones.py")
    before = {"propdesk/" + filename: sha256(ROOT / "propdesk" / filename) for filename in engine_files}
    last_day = date.fromisoformat(bars[-1]["time"][:10])
    if as_of < last_day:
        raise ValueError("as_of precedes archive end")
    audit = quality_audit(bars)
    reports = []
    if audit["status"] != "unsupported":
        result = run_research(bars, FIXED_CONFIG)
        strategy_keys = ("id", "name", "params", "train_metrics", "test_metrics", "walk_forward", "eligible",
                         "confidence", "reasons", "training_score", "training_winner", "baseline", "regime_metrics", "rule_replay")
        reports.append({"symbol": "GOOG", "data": result["data"], "summary": result["summary"],
                        "training_candidate": result["training_candidate"], "selected_strategy": result["selected_strategy"],
                        "methodology": result["methodology"], "config": result["config"],
                        "strategies": [{key: item[key] for key in strategy_keys} for item in result["strategies"]]})
    if before != {"propdesk/" + filename: sha256(ROOT / "propdesk" / filename) for filename in engine_files}:
        raise ValueError("Engine changed during independent study; rerun with stable sources")
    all_active = [item for report in reports for item in report["strategies"] if not item["baseline"]]
    return {"schema": 1, "study_id": protocol()["study_id"], "as_of": as_of.isoformat(), "historical_only": True,
            "latest_bar_date": last_day.isoformat(), "staleness_days": (as_of - last_day).days,
            "status": "unsupported_data" if audit["status"] == "unsupported" else "historical_research_completed",
            "profit_is_guaranteed": False, "live_orders_enabled": False, "actual_payouts_verified": False,
            "protocol": protocol(), "provenance": manifest, "engine_sha256": before, "limitations": LIMITATIONS,
            "reports": reports, "excluded": manifest["excluded"],
            "counts": {"analyzed_assets": len(reports), "excluded_assets": len(manifest["excluded"]),
                       "active_strategy_tests": len(all_active),
                       "positive_active_holdouts": sum(item["test_metrics"]["net_profit"] > 0 for item in all_active),
                       "qualified_active_holdouts": sum(item["eligible"] for item in all_active),
                       "selected_training_winners": sum(report["selected_strategy"] is not None for report in reports)}}


def render_markdown(report):
    counts = report["counts"]
    lines = ["# Независимая проверка архивной истории", "",
             f"Новый источник: [GOOG fixture]({report['provenance']['source_url']}), immutable commit `{SOURCE_COMMIT}`. "
             "Ранее изученные Plotly holdouts здесь не использованы и не перенастроены.", "",
             f"Весь GOOG: 2148 дневных баров 2004-08-19–2013-03-01. На {report['as_of']} последний бар устарел "
             f"на {report['staleness_days']} дней; текущих торговых сетапов и реальных выплат этот отчёт не подтверждает.", "",
             f"Семь активных проверок: положительных holdout {counts['positive_active_holdouts']}, "
             f"прошедших внутренние фильтры {counts['qualified_active_holdouts']}, выбранных победителей train "
             f"{counts['selected_training_winners']}. Buy-and-hold показан отдельно как ориентир.", "",
             "## Зафиксированный протокол", "",
             "Первые 60% (1288 баров) выбирают параметры и победителя стратегии; последние 40% (860) только "
             "проверяют его. Walk-forward выполняется внутри train. Замена победителя на лучший результат holdout не допускается.", "",
             "Счёт 100 000 USD, риск 0.25%, leverage 2, целые акции. Fee 2 bps и slippage 1 bps на сторону, "
             "полный spread 1 bps: около 7 bps полного оборота. Действительные broker fees, borrow и financing не проверены. "
             "Статический replay 5% daily / 10% total — учебный; исследовательский max drawdown 8%.", "",
             "Дата дневной сессии хранится как 00:00:00Z, а не как фактическое открытие NASDAQ. OHLC не изменены. "
             "Максимальный close→next-open gap " + str(report["provenance"]["datasets"][0]["quality"]["maximum_absolute_open_gap_pct"]) +
             "% не превышает зафиксированный аудит-порог 25%; это не подтверждение corporate-action policy.", "",
             "## Все стратегии после издержек", "",
             "| Стратегия | Train % | Holdout % | DD % | Сделок OOS | PF | Mean R 95% | WF + / folds | Итог |",
             "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |"]
    for dataset in report["reports"]:
        for item in dataset["strategies"]:
            metrics, wf = item["test_metrics"], item["walk_forward"]
            interval = item["confidence"]["mean_r_ci95"]
            interval_text = "—" if interval is None else f"[{interval[0]:.3f}; {interval[1]:.3f}]"
            pf = "—" if metrics["profit_factor"] is None else f"{metrics['profit_factor']:.3f}"
            label = item["id"] + (" ★ train" if item["training_winner"] else "")
            decision = "Ориентир" if item["baseline"] else "paper-review gate passed" if item["eligible"] else "Не квалифицирована"
            lines.append(f"| {label} | {item['train_metrics']['net_return_pct']:.4f} | {metrics['net_return_pct']:.4f} | "
                         f"{metrics['max_drawdown_pct']:.4f} | {metrics['total_trades']} | {pf} | {interval_text} | "
                         f"{wf['positive_folds']}/{wf['fold_count']} | {decision} |")
        winner = next(item for item in dataset["strategies"] if item["training_winner"])
        lines.extend(["", "Победитель, выбранный на train: `" + winner["id"] + "`. " +
                      ("Фильтры пройдены; требуется отдельный последующий paper-test." if dataset["selected_strategy"] else
                       "Отказ: " + " ".join(winner["reasons"])), ""])
    lines.extend(["## Исключённые источники", "",
                  "EURUSD: 5000 hourly bars 2017-04-19 09:00–2018-02-07 15:00. Тimestamps не содержат зоны, "
                  "а source loader и описания её не устанавливают. UTC не придуман; hourly FX не тестировался. "
                  "Оригинал сохранён отдельно для аудита.", "", "## Ограничения и лицензия", ""])
    lines.extend("- " + limitation for limitation in report["limitations"])
    lines.extend(["", "## Воспроизведение", "", "```bash", "python scripts/research_independent.py --as-of 2026-10-01", "```", "",
                  "Пересборка canonical файла требует checkout ровно указанного commit:", "", "```bash",
                  "python scripts/research_independent.py --prepare-from /path/to/pinned/backtesting.py --as-of 2026-10-01", "```", "",
                  "Команда проверяет source SHA-256, canonical SHA-256, bar fingerprint и protocol. "
                  "При изменении данных или grid повторное использование holdout отклоняется.", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-from", type=Path)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "independent-history")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date(2026, 10, 1))
    args = parser.parse_args()
    if args.prepare_from is not None:
        prepare(args.prepare_from, args.data_dir)
    report = research(args.data_dir, args.as_of)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "independent-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (args.output_dir / "INDEPENDENT_RESULTS.md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"counts": report["counts"], "latest_bar_date": report["latest_bar_date"],
                      "staleness_days": report["staleness_days"],
                      "training_candidate": report["reports"][0]["training_candidate"] if report["reports"] else None,
                      "selected_strategy": report["reports"][0]["selected_strategy"] if report["reports"] else None}, ensure_ascii=False))


if __name__ == "__main__":
    main()
