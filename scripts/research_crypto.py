#!/usr/bin/env python3
"""One frozen, archival ETH/BTC 5-minute research protocol, not live signals."""
from __future__ import annotations

import argparse
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

SOURCE_COMMIT = "b530600718ddacf6234958917ef744ba1fc3bf18"
SOURCE_PATH = "tests/testdata/ETH_BTC-5m.json"
SOURCE_SHA = "a5adc2e6df5e901febbba9a4a1a10775835b235dd69f35c340a17af9d5932c15"
SOURCE_URL = "https://github.com/freqtrade/freqtrade/blob/" + SOURCE_COMMIT + "/" + SOURCE_PATH
SYMBOL = "ETHBTC"
FILENAME = "ETHBTC-5m.csv"
STRATEGY_IDS = ["ema_pullback", "donchian_breakout", "rsi_reversion", "bollinger_reversion",
                "trend_momentum", "inside_bar_breakout", "volatility_expansion", "buy_hold"]
CONFIG = {
    "source": "csv", "symbol": SYMBOL, "account_size": 100_000, "risk_pct": 0.25,
    "max_leverage": 1, "quantity_step": 0.00001, "contract_multiplier": 1,
    "fee_bps": 10, "slippage_bps": 2, "spread_bps": 2, "fee_per_unit": 0,
    "train_fraction": 0.6, "max_drawdown_pct": 8, "strategy_ids": STRATEGY_IDS,
    "prop_profile": normalize_profile({"id": "crypto-archive-static", "name": "Учебный static · BTC quote",
        "account_size": 100_000, "status": "illustrative", "verified_at": None,
        "daily_loss_pct": 5, "max_loss_pct": 10, "drawdown_type": "static",
        "daily_reset_timezone": "UTC", "quantity_step": 0.00001,
        "max_calendar_days": None}),
}
LIMITATIONS = [
    "Это архивный upstream testdata-снимок января 2018 года, не текущие котировки и не сегодняшний сигнал.",
    "Источник — ETH_BTC fixture Freqtrade 2021.12. Оригинальный exchange/vendor и отсутствие ручных изменений тестовых данных независимо не подтверждены.",
    "Цена ETH выражена в BTC; модельный счёт — номинальные 100 000 BTC quote units. Доходность в процентах/R нельзя выдавать за USD P&L или выплату проп-фирмы.",
    "Движок моделирует long и short. Short в обычном spot без заёма невозможен; borrowing, funding, margin, ограничения площадки и ликвидность не включены. Результат не исполним как spot-бот.",
    "Комиссия 10 bps на сторону — предположение, не подтверждённый тариф этого источника; slippage 2 bps и spread 2 bps дают 26 bps полного оборота.",
    "Двадцатидневная выборка и один ETH/BTC рынок не устанавливают устойчивость на других эпохах, биржах, валютных котировках или проп-CFD.",
    "Семь фиксированных семейств и варианты параметров создают множественный поиск. Описательный bootstrap не корректирует этот эффект; edge и выплаты не доказаны.",
    "Стратегия/параметры выбираются только на train. После отказа этого победителя лучшая holdout-альтернатива не подставляется.",
    "Replay проверяет лишь учебные 5% daily / 10% static loss floors на OHLC. Действующие правила фирмы, реальные исполнения и payout-пригодность не подтверждены.",
]


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def convert_candles(rows):
    """Copy actual epoch-ms OHLCV, rejecting gaps, invented envelopes and order."""
    if not isinstance(rows, list) or not rows:
        raise ValueError("Expected a nonempty upstream candle list")
    bars = []
    previous_epoch = None
    for row in rows:
        if not isinstance(row, list) or len(row) != 6:
            raise ValueError("Upstream candle must contain epoch_ms and five OHLCV values")
        epoch = row[0]
        if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch % 300_000:
            raise ValueError("Expected a 5-minute-aligned integer Unix epoch in milliseconds")
        if previous_epoch is not None and epoch - previous_epoch != 300_000:
            raise ValueError("Upstream candles must have consecutive, ascending 5-minute timestamps")
        previous_epoch = epoch
        stamp = datetime.fromtimestamp(epoch / 1000, timezone.utc).isoformat().replace("+00:00", "Z")
        bars.append({"time": stamp, **dict(zip(("open", "high", "low", "close", "volume"), row[1:]))})
    return validate_bars(bars)


def prepare(source_root, data_dir):
    source_root, data_dir = Path(source_root), Path(data_dir)
    result = subprocess.run(["git", "show", SOURCE_COMMIT + ":" + SOURCE_PATH], cwd=source_root,
                            check=True, capture_output=True)
    if hashlib.sha256(result.stdout).hexdigest() != SOURCE_SHA:
        raise ValueError("Pinned upstream candle SHA-256 mismatch")
    bars = convert_candles(json.loads(result.stdout))
    if len(bars) != 5760:
        raise ValueError("Pinned upstream sample row count changed")
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / FILENAME
    path.write_text(to_csv(bars), encoding="utf-8")
    license_result = subprocess.run(["git", "show", SOURCE_COMMIT + ":LICENSE"], cwd=source_root,
                                    check=True, capture_output=True)
    (data_dir / "UPSTREAM-LICENSE.txt").write_bytes(license_result.stdout)
    provenance = {
        "schema": 1, "source_repository": "https://github.com/freqtrade/freqtrade",
        "source_release": "2021.12", "source_commit": SOURCE_COMMIT, "source_path": SOURCE_PATH,
        "source_url": SOURCE_URL, "source_sha256": SOURCE_SHA,
        "predeclared_pairs": ["ETH/BTC"], "symbol": SYMBOL, "file": FILENAME,
        "base_currency": "ETH", "quote_currency": "BTC", "volume_unit": "ETH",
        "nominal_account_currency": "BTC", "nominal_account_size": 100_000,
        "timeframe": "5m", "bars": len(bars), "start": bars[0]["time"], "end": bars[-1]["time"],
        "sha256": digest(path), "data_fingerprint": data_fingerprint(bars),
        "conversion": "Unix epoch milliseconds -> explicit UTC bar-open timestamp; direct copy of source OHLCV; no resampling, sorting, or invented highs/lows.",
        "availability": "2021.12 tree has ETH_BTC-5m.json as its only BTC/ETH base-pair JSON fixture. Current head uses Feather and pyarrow was unavailable. UNITTEST_* synthetic fixtures were excluded.",
        "license": "Upstream GPL-3.0 LICENSE included verbatim; only factual OHLCV data copied, no upstream application code.",
        "historical_only": True, "spot_execution_validated": False, "prop_execution_validated": False,
        "limitations": LIMITATIONS,
    }
    (data_dir / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return provenance


def research(data_dir, as_of):
    data_dir = Path(data_dir)
    provenance = json.loads((data_dir / "provenance.json").read_text(encoding="utf-8"))
    if provenance.get("source_commit") != SOURCE_COMMIT or provenance.get("predeclared_pairs") != ["ETH/BTC"]:
        raise ValueError("Sample provenance differs from frozen protocol")
    path = data_dir / FILENAME
    if digest(path) != provenance["sha256"]:
        raise ValueError("Canonical crypto sample changed; do not silently reuse the holdout")
    bars = parse_csv(path.read_text(encoding="utf-8"))
    if data_fingerprint(bars) != provenance["data_fingerprint"]:
        raise ValueError("Canonical crypto fingerprint mismatch")
    engine_paths = [ROOT / "propdesk" / name for name in ("backtest.py", "strategies.py", "market.py", "risk.py", "compliance.py", "timezones.py")]
    before = {str(path.relative_to(ROOT)): digest(path) for path in engine_paths}
    result = run_research(bars, CONFIG)
    after = {str(path.relative_to(ROOT)): digest(path) for path in engine_paths}
    if before != after:
        raise ValueError("Engine changed during the study")
    # Retain standard engine fields, all metrics/decisions/context; strip large
    # trade/curve arrays while reporting long/short counts explicitly.
    for item in result["strategies"]:
        item["direction_counts"] = {side: sum(t["direction"] == side for t in item["trades"]) for side in ("long", "short")}
        item.pop("trades")
        item.pop("equity_curve")
    result["provenance"] = provenance
    stale = (as_of - date.fromisoformat(bars[-1]["time"][:10])).days
    active = [item for item in result["strategies"] if not item["baseline"]]
    return {"schema": 1, "study_id": "ethbtc-5m-2018-fixed-v1", "as_of": as_of.isoformat(),
            "historical_only": True, "spot_execution_validated": False, "profit_is_guaranteed": False,
            "live_orders_enabled": False, "latest_bar_date": bars[-1]["time"][:10], "staleness_days": stale,
            "engine_sha256": before, "provenance": provenance, "fixed_config": CONFIG,
            "limitations": LIMITATIONS, "reports": [result],
            "counts": {"assets": 1, "active_strategy_tests": len(active),
                       "positive_active_holdouts": sum(item["test_metrics"]["net_profit"] > 0 for item in active),
                       "qualified_active_holdouts": sum(item["eligible"] for item in active),
                       "selected_training_winners": int(result["selected_strategy"] is not None)}}


def markdown(report):
    result = report["reports"][0]
    winner = next(item for item in result["strategies"] if item["training_winner"])
    m = winner["test_metrics"]
    lines = ["# Независимая проверка архивного ETH/BTC", "",
             f"Реальные upstream OHLCV: {report['provenance']['start']} — {report['provenance']['end']}, "
             f"5 минут, 5 760 полностью закрытых баров. На {report['as_of']} давность — {report['staleness_days']} дней.", "",
             f"Источник: [Freqtrade 2021.12 fixture]({SOURCE_URL}), commit `{SOURCE_COMMIT}`, "
             f"SHA-256 исходного JSON `{SOURCE_SHA}`. Внешняя vendor-верификация качества отсутствует.", "",
             "ETH/BTC выбран по единственному подходящему имени файла до просмотра P&L. "
             "Параметры и победитель выбираются на первых 60%; последние 40% только проверяют этот выбор. "
             "Семь заранее заданных семейств и buy & hold; замена победителя после holdout не допускается.", "",
             "Модель: номинальный счёт 100 000 BTC, риск 0,25%, плечо 1, quantity step 0,00001 ETH; "
             "комиссия 10 bps/сторону, slippage 2 bps/сторону, полный spread 2 bps, около 26 bps оборота. "
             "Это quote-BTC исследование. Цифры не обозначают долларовый счёт, реальные spot-исполнения или выплаты проп-фирмы.", "",
             f"Победитель train: **{winner['id']}**. Holdout {m['net_return_pct']:.4f}%, "
             f"DD {m['max_drawdown_pct']:.4f}%, {m['total_trades']} сделок. "
             f"Выбор для paper-review: **{result['selected_strategy'] or 'нет'}**.", "",
             "| Стратегия | Train, % | Holdout, % | DD, % | Сделок | Long/short | PF | CI mean R | WF +/окон | Квалифицирована |",
             "| --- | ---: | ---: | ---: | ---: | --- | ---: | --- | --- | --- |"]
    for item in result["strategies"]:
        metric, wf = item["test_metrics"], item["walk_forward"]
        ci = item["confidence"]["mean_r_ci95"]
        ci_text = "—" if ci is None else f"[{ci[0]:.3f}; {ci[1]:.3f}]"
        pf = "—" if metric["profit_factor"] is None else f"{metric['profit_factor']:.3f}"
        decision = "ориентир" if item["baseline"] else "да" if item["eligible"] else "нет"
        directions = item["direction_counts"]
        label = item["id"] + (" ★ train" if item["training_winner"] else "")
        lines.append(f"| {label} | {item['train_metrics']['net_return_pct']:.4f} | {metric['net_return_pct']:.4f} | {metric['max_drawdown_pct']:.4f} | {metric['total_trades']} | {directions['long']}/{directions['short']} | {pf} | {ci_text} | {wf['positive_folds']}/{wf['fold_count']} | {decision} |")
    lines.extend(["", "Причины отказа победителя train: " + (" ".join(winner["reasons"]) or "фильтры пройдены; реальная исполнимость не подтверждена."), "", "## Ограничения", ""])
    lines.extend("- " + item for item in LIMITATIONS)
    lines.extend(["", "## Воспроизведение", "", "```bash", "python3 scripts/research_crypto.py --as-of 2026-10-01", "```", "",
                  "Сеть и сторонние Python-пакеты не нужны. Проверяются CSV SHA-256, отпечаток баров и стабильность исходников движка. "
                  "Для восстановления исходной конвертации используйте `--prepare-from /tmp/prop-lab-crypto-source`, "
                  "где Git должен содержать закреплённый commit 2021.12. Нельзя повторно подгонять параметры по открытому holdout.", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-from", type=Path)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "crypto-history")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs")
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    args = parser.parse_args()
    try:
        if args.prepare_from:
            prepare(args.prepare_from, args.data_dir)
        report = research(args.data_dir, args.as_of)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "crypto-results.json").write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")
        (args.output_dir / "CRYPTO_RESULTS.md").write_text(markdown(report), encoding="utf-8")
        print(json.dumps({"study_id": report["study_id"], "counts": report["counts"],
                          "training_candidate": report["reports"][0]["training_candidate"],
                          "training_winner_holdout_pct": report["reports"][0]["summary"]["net_return_pct"]}, ensure_ascii=False))
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError) as exc:
        parser.exit(1, "Crypto research error: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
