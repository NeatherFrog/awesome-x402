#!/usr/bin/env python3
"""Reproduce the preregistered daily equity archive study, without tuning OOS.

Normal use reads included canonical CSVs without network/Git. To reconstruct
those CSVs, pass --prepare-from with the pinned Plotly checkout. That operation
requires Git and validates the source commit and whole-file SHA-256 first.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from propdesk.backtest import run_research
from propdesk.market import data_fingerprint, parse_csv, to_csv, validate_bars
from propdesk.risk import normalize_profile


SOURCE_REPOSITORY = "https://github.com/plotly/datasets"
SOURCE_COMMIT = "0c447c47b757ad74edecab31f0d72f849d2e67c2"
SOURCE_PATH = "all_stocks_5yr.csv"
SOURCE_SHA256 = "6aea253cd19de60b568143991aaf1fa482456565c389205658d236e595e716cf"
SYMBOLS = ("AAPL", "MSFT", "JPM", "XOM")
START = "2015-01-01"
END = "2018-02-07"
STRATEGY_IDS = [
    "ema_pullback", "donchian_breakout", "rsi_reversion", "bollinger_reversion",
    "trend_momentum", "inside_bar_breakout", "volatility_expansion", "buy_hold",
]
FIXED_CONFIG = {
    "source": "csv", "account_size": 100_000, "train_fraction": 0.6,
    "risk_pct": 0.25, "max_leverage": 2, "fee_bps": 2,
    "spread_bps": 1, "slippage_bps": 1, "max_drawdown_pct": 8,
    "quantity_step": 1, "contract_multiplier": 1, "fee_per_unit": 0,
    "strategy_ids": STRATEGY_IDS,
    "prop_profile": normalize_profile({
        "id": "archive-static-illustrative", "name": "Архивное исследование: учебный static",
        "status": "illustrative", "verified_at": None, "source_url": "",
        "account_size": 100_000, "profit_target_pct": 8, "daily_loss_pct": 5,
        "max_loss_pct": 10, "drawdown_type": "static", "daily_reset_timezone": "UTC",
        "quantity_step": 1, "min_trading_days": 5, "max_calendar_days": None,
        "ea_allowed": None, "news_allowed": None, "overnight_allowed": None, "weekend_allowed": None,
    }),
}
LIMITATIONS = [
    "Это архив дневных акций США 2015–2018 годов: текущих котировок и сегодняшних сетапов здесь нет.",
    "Plotly — публичное зеркало набора данных. Исходный поставщик и полный порядок обработки корпоративных событий независимо не подтверждены.",
    "Общее окно зафиксировано до просмотра результатов и исключает split AAPL 2014 года. Новые корректировки цены и дивидендов не применялись.",
    "Выборка содержит сохранившиеся компании: survivorship bias не устранён. Четыре тикера не означают охват всех активов.",
    "Дата источника обозначает биржевую сессию. 00:00:00Z — каноническая метка дневной даты, а не фактическое открытие биржи США.",
    "Дневные OHLC не устанавливают внутридневную последовательность, реальные исполнения, соблюдение всех правил проп-фирмы, разрешение переносов и выплату.",
    "Издержки предполагаются: комиссия 2 bps, проскальзывание 1 bps и половина спреда 1 bps на сторону, около 7 bps за оборот. Заём акций, дивиденды и финансирование не учитываются.",
    "Выбирается только победитель train каждого актива. Положительные альтернативы на holdout показаны полностью, но не подменяют исходный выбор.",
    "Описательный bootstrap не скорректирован за множественный поиск стратегий и активов. Пройденный фильтр означает кандидата для paper-review, а не доказательство будущей прибыли.",
    "Включён только учебный replay лимитов 5% daily и 10% static; действующие официальные правила фирм не проверены. Реальные ордера и challenge/funded выплаты не подтверждены.",
]


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare(source_root, data_dir):
    source_root, data_dir = Path(source_root), Path(data_dir)
    completed = subprocess.run(["git", "rev-parse", "HEAD"], cwd=source_root,
                               check=True, capture_output=True, text=True)
    if completed.stdout.strip() != SOURCE_COMMIT:
        raise ValueError("Source checkout does not match the pinned Plotly commit")
    source = source_root / SOURCE_PATH
    if sha256(source) != SOURCE_SHA256:
        raise ValueError("Source CSV SHA-256 differs from the recorded snapshot")
    selected = {symbol: [] for symbol in SYMBOLS}
    with source.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["date", "open", "high", "low", "close", "volume", "Name"]:
            raise ValueError("Unexpected source columns")
        for row in reader:
            symbol = row["Name"]
            if symbol in selected and START <= row["date"] <= END:
                parsed = date.fromisoformat(row["date"])
                selected[symbol].append({
                    "time": parsed.isoformat() + "T00:00:00Z",
                    **{field: row[field] for field in ("open", "high", "low", "close", "volume")},
                })
    # Validate the entire predeclared sample before writing any output.
    canonical = {symbol: validate_bars(bars) for symbol, bars in selected.items()}
    for symbol, bars in canonical.items():
        if len(bars) != 781 or bars[0]["time"] != "2015-01-02T00:00:00Z" or bars[-1]["time"] != END + "T00:00:00Z":
            raise ValueError(f"{symbol}: incomplete pinned daily window")
        gaps = [abs(b["open"] / a["close"] - 1) for a, b in zip(bars, bars[1:])]
        if max(gaps, default=0) > 0.25:
            raise ValueError(f"{symbol}: large discontinuity needs corporate-action investigation")
    data_dir.mkdir(parents=True, exist_ok=True)
    datasets = []
    for symbol, bars in canonical.items():
        filename = symbol + "-1d.csv"
        path = data_dir / filename
        path.write_text(to_csv(bars), encoding="utf-8")
        datasets.append({
            "symbol": symbol, "file": filename, "asset_class": "equity", "timeframe": "1d",
            "currency": "USD", "bars": len(bars), "start": bars[0]["time"], "end": bars[-1]["time"],
            "sha256": sha256(path), "data_fingerprint": data_fingerprint(bars),
            "maximum_absolute_open_gap_pct": round(max(abs(b["open"] / a["close"] - 1) for a, b in zip(bars, bars[1:])) * 100, 6),
        })
    license_result = subprocess.run(["git", "show", SOURCE_COMMIT + ":LICENSE"], cwd=source_root,
                                    check=True, capture_output=True, text=True)
    (data_dir / "PLOTLY-LICENSE.txt").write_text(license_result.stdout, encoding="utf-8")
    provenance = {
        "schema": 1, "source_repository": SOURCE_REPOSITORY, "source_commit": SOURCE_COMMIT,
        "source_path": SOURCE_PATH, "source_sha256": SOURCE_SHA256,
        "source_url": SOURCE_REPOSITORY + "/blob/" + SOURCE_COMMIT + "/" + SOURCE_PATH,
        "timeframe": "daily exchange sessions", "predeclared_symbols": list(SYMBOLS),
        "requested_window": {"start": START, "end": END},
        "conversion": "Name filters fixed symbols; date -> dateT00:00:00Z; copy source open/high/low/close/volume. No sorting, resampling, invented OHLC or extra adjustments.",
        "corporate_actions": "Post-2014 fixed window; original vendor adjustment policy is unknown. A >25% close-to-next-open gap is rejected pending investigation; absence of a gap does not certify split handling.",
        "license": "Included MIT license from the pinned Plotly repository; original market-vendor provenance remains incomplete.",
        "unavailable": [
            {"symbol": "SPY", "reason": "No SPY rows in the pinned all_stocks_5yr snapshot."},
            {"symbol": "BTCUSD", "reason": "Mining-BTC-180.csv lacks genuine OHLCV; Market-price alone cannot reconstruct bars."},
            {"symbol": "EURUSD", "reason": "Web-trader sample is timezone-naive bid/ask ticks, not a validated historical OHLCV feed."},
        ],
        "datasets": datasets, "limitations": LIMITATIONS,
    }
    (data_dir / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return provenance


def compact_strategy(item):
    return {key: item[key] for key in (
        "id", "name", "params", "train_metrics", "test_metrics", "walk_forward", "eligible",
        "confidence", "reasons", "training_score", "training_winner", "baseline", "regime_metrics", "rule_replay",
    )}


def research(data_dir, as_of):
    data_dir = Path(data_dir)
    engine_paths = (
        ROOT / "propdesk" / "backtest.py", ROOT / "propdesk" / "strategies.py",
        ROOT / "propdesk" / "market.py", ROOT / "propdesk" / "risk.py", ROOT / "propdesk" / "compliance.py",
    )
    engine_hashes = {str(path.relative_to(ROOT)): sha256(path) for path in engine_paths}
    provenance = json.loads((data_dir / "provenance.json").read_text(encoding="utf-8"))
    if provenance.get("source_commit") != SOURCE_COMMIT or provenance.get("predeclared_symbols") != list(SYMBOLS):
        raise ValueError("The sample provenance differs from this preregistered study")
    outcomes = []
    for dataset in provenance["datasets"]:
        if dataset["symbol"] not in SYMBOLS or dataset["file"] != dataset["symbol"] + "-1d.csv":
            raise ValueError("Unexpected sample path or symbol")
        path = data_dir / dataset["file"]
        if sha256(path) != dataset["sha256"]:
            raise ValueError(f"{dataset['symbol']}: canonical data changed; do not silently reuse the holdout")
        bars = parse_csv(path.read_text(encoding="utf-8"))
        if data_fingerprint(bars) != dataset["data_fingerprint"]:
            raise ValueError("Canonical bar fingerprint mismatch")
        result = run_research(bars, {**FIXED_CONFIG, "symbol": dataset["symbol"]})
        outcomes.append({
            "symbol": dataset["symbol"], "data": result["data"], "summary": result["summary"],
            "training_candidate": result["training_candidate"], "selected_strategy": result["selected_strategy"],
            "config": result["config"], "methodology": result["methodology"],
            "provenance": {**dataset, "source_commit": SOURCE_COMMIT,
                           "source_url": provenance["source_url"], "historical_only": True,
                           "staleness_days": (as_of - date.fromisoformat(END)).days},
            "strategies": [compact_strategy(item) for item in result["strategies"]],
        })
    if {item["symbol"] for item in outcomes} != set(SYMBOLS) or len(outcomes) != len(SYMBOLS):
        raise ValueError("Study must include every predeclared symbol exactly once")
    if engine_hashes != {str(path.relative_to(ROOT)): sha256(path) for path in engine_paths}:
        raise ValueError("Engine source changed during the study; rerun with a stable checkout")
    last_day = date.fromisoformat(END)
    return {
        "schema": 1, "study_id": "equities-daily-2015-2018-fixed-v1", "as_of": as_of.isoformat(),
        "historical_only": True, "latest_bar_date": END, "staleness_days": (as_of - last_day).days,
        "profit_is_guaranteed": False, "live_orders_enabled": False,
        "protocol": "Four predeclared assets; 7 fixed strategy families + reference; chronological 60% train/40% holdout; train-only parameter/strategy selection; report all results.",
        "provenance": provenance, "fixed_config": FIXED_CONFIG, "limitations": LIMITATIONS,
        "reports": outcomes,
        "engine_sha256": engine_hashes,
        "counts": {
            "assets": len(outcomes), "active_strategy_tests": 7 * len(outcomes),
            "positive_active_holdouts": sum(item["test_metrics"]["net_profit"] > 0 for outcome in outcomes for item in outcome["strategies"] if not item["baseline"]),
            "qualified_active_holdouts": sum(item["eligible"] for outcome in outcomes for item in outcome["strategies"] if not item["baseline"]),
            "selected_training_winners": sum(outcome["selected_strategy"] is not None for outcome in outcomes),
        },
    }


def render_markdown(report):
    counts = report["counts"]
    lines = [
        "# Проверка на реальной архивной истории", "",
        "Исследование использует опубликованные исторические OHLCV, а не синтетическое демо. "
        "Положительный исторический P&L сам по себе не доказывает будущий edge и выплаты проп-фирмы.", "",
        f"На {report['as_of']} последний бар датирован {END}: давность {report['staleness_days']} дней. "
        "Сигналы на этих данных не являются сегодняшними торговыми сетапами.", "",
        f"Из {counts['active_strategy_tests']} активных проверок {counts['positive_active_holdouts']} дали положительный "
        f"holdout после заданных издержек; {counts['qualified_active_holdouts']} прошли внутренние фильтры. "
        f"Выбрано заранее определённых победителей train: {counts['selected_training_winners']}. "
        "Остальные положительные результаты остаются исследовательскими наблюдениями.", "",
        "## Данные и заранее установленный протокол", "",
        f"Источник: [{SOURCE_PATH}]({report['provenance']['source_url']}), commit `{SOURCE_COMMIT}`. "
        f"SHA-256 исходного файла: `{SOURCE_SHA256}`.", "",
        "Активы AAPL, MSFT, JPM и XOM выбраны до просмотра результатов, чтобы представить технологический, "
        "банковский и энергетический сектора. Общий период зафиксирован с 2015-01-01 по 2018-02-07: "
        "по 781 дневному бару, 468 train и 313 holdout. Окно начинается после split AAPL 2014 года. "
        "Дата сессии преобразована в UTC-метку 00:00:00Z; это метка дневного бара, а не фактическое время открытия биржи.", "",
        "Параметры и победитель стратегии выбираются на первых 60% истории. Walk-forward окна полностью "
        "предшествуют holdout. Последние 40% только проверяют выбранного победителя: замена на другую "
        "стратегию, которая выглядит лучше на holdout, запрещена протоколом.", "",
        "Счёт 100 000 USD; риск 0,25% на сделку; плечо максимум 2; целое число акций. "
        "Комиссия 2 bps и проскальзывание 1 bps на каждую сторону плюс половина спреда 1 bps: "
        "примерно 7 bps полного оборота. Borrow fees, дивиденды и финансирование не моделируются. "
        "Это предположения исследования, не тариф конкретного брокера. "
        "Replay использует учебный профиль 5% daily / 10% static; он проверяет моделируемые loss floors, "
        "а не подтверждает все действующие условия какой-либо фирмы. Исследовательский предел drawdown — 8%.", "",
        "## Победители, выбранные только на train", "",
        "| Актив | Победитель train | Holdout, % | Макс. DD, % | Сделок | Итог |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for outcome in report["reports"]:
        winner = next(item for item in outcome["strategies"] if item["training_winner"])
        metrics = winner["test_metrics"]
        decision = "Кандидат для paper-review" if outcome["selected_strategy"] else "Не квалифицирован"
        lines.append(f"| {outcome['symbol']} | {winner['id']} | {metrics['net_return_pct']:.4f} | {metrics['max_drawdown_pct']:.4f} | {metrics['total_trades']} | {decision} |")
    lines.extend(["", "## Все результаты: положительные и отрицательные", "",
                  "PF — отношение суммы положительного P&L к модулю отрицательного; «—» означает отсутствие "
                  "убыточных сделок или сделок вообще. Интервал R — описательный moving-block bootstrap "
                  "с 300 повторениями. Он не исправляет множественный поиск по стратегиям и активам.", ""])
    for outcome in report["reports"]:
        lines.extend([f"### {outcome['symbol']}", "",
                      "| Стратегия | Train, % | Holdout, % | DD, % | Сделок | PF | 95% интервал mean R | WF + / окон | Квалифицирована |",
                      "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |"])
        for item in outcome["strategies"]:
            m, wf = item["test_metrics"], item["walk_forward"]
            interval = item["confidence"]["mean_r_ci95"]
            interval_text = "—" if interval is None else f"[{interval[0]:.3f}; {interval[1]:.3f}]"
            pf = "—" if m["profit_factor"] is None else f"{m['profit_factor']:.3f}"
            name = item["id"] + (" ★ train" if item["training_winner"] else "")
            decision = "ориентир" if item["baseline"] else "да" if item["eligible"] else "нет"
            lines.append(f"| {name} | {item['train_metrics']['net_return_pct']:.4f} | {m['net_return_pct']:.4f} | {m['max_drawdown_pct']:.4f} | {m['total_trades']} | {pf} | {interval_text} | {wf['positive_folds']}/{wf['fold_count']} | {decision} |")
        winner = next(item for item in outcome["strategies"] if item["training_winner"])
        lines.extend(["", "Причины отказа победителя train: " + (" ".join(winner["reasons"]) if winner["reasons"] else "внутренние фильтры пройдены; нужен независимый последующий paper-test."), ""])
    lines.extend(["## Ограничения и отсутствующие активы", ""])
    lines.extend("- " + limitation for limitation in LIMITATIONS)
    lines.extend(["", "SPY отсутствует в выбранном снимке. BTC-файл содержит только цену/сетевые показатели, "
                  "из которых нельзя восстановить OHLC. EURUSD-файл содержит bid/ask ticks без явного timezone. "
                  "Эти источники отклонены; значения high/low не выдумывались.", "",
                  "## Воспроизведение", "", "Из корня проекта, без сети и внешних Python-пакетов:", "", "```bash",
                  "python3 scripts/research_markets.py --as-of 2026-10-01", "```", "",
                  "Команда проверяет SHA-256 CSV и отпечатки баров, затем пересоздаёт JSON и этот отчёт. "
                  "Чтобы реконструировать CSV из исходного Plotly checkout, используйте "
                  "`--prepare-from /tmp/prop-lab-market-source`; commit и SHA-256 исходного файла также проверяются.", "",
                  "Машиночитаемые результаты: `docs/research-results.json`. Канонические CSV, метаданные источника "
                  "и его лицензия: `data/market-history/`. В отчёт включены все комбинации; повторная подгонка "
                  "по этому holdout превратит его в обучающие данные и потребует нового независимого периода.", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-from", type=Path, help="Pinned Plotly Git checkout; reconstruct bundled CSVs")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "market-history")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs")
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    args = parser.parse_args()
    try:
        if args.prepare_from:
            prepare(args.prepare_from, args.data_dir)
        report = research(args.data_dir, args.as_of)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "research-results.json").write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")
        (args.output_dir / "RESEARCH_RESULTS.md").write_text(render_markdown(report), encoding="utf-8")
        print(json.dumps({"study_id": report["study_id"], "counts": report["counts"],
                          "latest_bar_date": END, "staleness_days": report["staleness_days"]}, ensure_ascii=False))
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError) as exc:
        parser.exit(1, "Research error: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
