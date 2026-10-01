"""Use `python3 -m propdesk --help` from the repository root."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="PROP LAB: исследование стратегий и бумажный дневник")
    sub = parser.add_subparsers(dest="command", required=True)
    web = sub.add_parser("serve", help="Запустить локальный веб-интерфейс")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8000)
    web.add_argument("--data-dir")
    for name in ("demo", "research"):
        command = sub.add_parser(name, help="Синтетическое демо" if name == "demo" else "Исследовать CSV")
        command.add_argument("--symbol", default="EURUSD")
        if name == "research":
            command.add_argument("--csv", required=True)
        command.add_argument("--output")
        command.add_argument("--risk-pct", type=float, default=0.25)
        command.add_argument("--data-dir")
    validate = sub.add_parser("validate-csv", help="Проверить OHLCV CSV")
    validate.add_argument("path")
    args = parser.parse_args()
    try:
        if args.command == "serve":
            from .server import serve
            raise SystemExit(serve(args.host, args.port, args.data_dir))
        elif args.command == "validate-csv":
            from .market import parse_csv
            bars = parse_csv(Path(args.path).read_text(encoding="utf-8-sig"))
            print(json.dumps({"valid": True, "bars": len(bars), "start": bars[0]["time"], "end": bars[-1]["time"]}))
        else:
            from .server import Application
            payload = {"symbol": args.symbol, "source": "demo" if args.command == "demo" else "csv",
                       "config": {"risk_pct": args.risk_pct}}
            if args.command == "research":
                payload["csv_text"] = Path(args.csv).read_text(encoding="utf-8-sig")
            result = Application(args.data_dir).research(payload)
            output = json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2)
            if args.output:
                Path(args.output).write_text(output, encoding="utf-8")
                print(f"Результат сохранён: {args.output}")
            else:
                print(output)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Ошибка: {exc}\n")


if __name__ == "__main__":
    main()
