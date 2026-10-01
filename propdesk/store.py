"""Local SQLite persistence. Amounts are account-currency units, never pips."""
from __future__ import annotations

import csv
import io
import json
import math
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def finite(value, name, minimum=None, maximum=None):
    if isinstance(value, bool):
        raise ValueError(f"{name}: требуется число")
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{name}: требуется число") from None
    if not math.isfinite(number):
        raise ValueError(f"{name}: число должно быть конечным")
    if minimum is not None and number < minimum:
        raise ValueError(f"{name}: минимум {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{name}: максимум {maximum}")
    return number


def utc_time(value, name):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError(f"{name}: требуется ISO 8601 с часовым поясом")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{name}: неверная дата") from None
    if parsed.tzinfo is None:
        raise ValueError(f"{name}: укажите часовой пояс, например Z")
    return parsed.astimezone(timezone.utc).isoformat()


class Store:
    def __init__(self, directory=None):
        directory = Path(directory or os.environ.get("TRADING_DATA_DIR") or ROOT / ".local")
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "propdesk.sqlite3"
        with self.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS profiles (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS journal (id TEXT PRIMARY KEY, created TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS signals (id TEXT PRIMARY KEY, created TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS research (id TEXT PRIMARY KEY, created TEXT NOT NULL, payload TEXT NOT NULL);
            """)

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def profiles(self, defaults):
        profiles = {p["id"]: dict(p) for p in defaults}
        with self.connect() as conn:
            for pid, payload in conn.execute("SELECT id,payload FROM profiles ORDER BY id"):
                profiles[pid] = json.loads(payload)
        return list(profiles.values())

    def save_profile(self, profile):
        with self.connect() as conn:
            conn.execute("INSERT INTO profiles VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                         (profile["id"], json.dumps(profile, ensure_ascii=False, allow_nan=False)))

    def journal(self):
        with self.connect() as conn:
            rows = [json.loads(row[0]) for row in conn.execute("SELECT payload FROM journal ORDER BY created DESC,id DESC")]
        return {"trades": rows, "stats": journal_stats(rows)}

    def add_trade(self, body):
        if body.get("side") not in ("long", "short"):
            raise ValueError("side: long или short")
        symbol = str(body.get("symbol", "")).strip().upper()
        if not symbol or len(symbol) > 32:
            raise ValueError("symbol: от 1 до 32 символов")
        entry = finite(body.get("entry"), "entry", 1e-12, 1e12)
        exit_price = finite(body.get("exit"), "exit", 1e-12, 1e12)
        stop = finite(body.get("stop"), "stop", 1e-12, 1e12)
        qty = finite(body.get("quantity"), "quantity", 1e-12, 1e12)
        multiplier = finite(body.get("contract_multiplier", 1), "contract_multiplier", 1e-12, 1e9)
        fees = finite(body.get("fees", 0), "fees", 0, 1e12)
        direction = 1 if body["side"] == "long" else -1
        if (entry - stop) * direction <= 0:
            raise ValueError("Стоп должен быть ниже входа для long и выше для short")
        now = datetime.now(timezone.utc).isoformat()
        opened = utc_time(body.get("opened_at") or now, "opened_at")
        closed = utc_time(body.get("closed_at") or now, "closed_at")
        if datetime.fromisoformat(closed) < datetime.fromisoformat(opened):
            raise ValueError("closed_at не может быть раньше opened_at")
        if not isinstance(body.get("setup_followed", False), bool):
            raise ValueError("setup_followed: требуется boolean")
        gross = (exit_price - entry) * qty * multiplier * direction
        pnl = gross - fees
        risk = abs(entry - stop) * qty * multiplier + fees
        if not all(math.isfinite(x) for x in (gross, pnl, risk, pnl / risk)):
            raise ValueError("Числа сделки превышают допустимый диапазон расчёта")
        for name, limit in (("notes", 4000), ("strategy", 100), ("emotion", 100)):
            if not isinstance(body.get(name, ""), str) or len(body.get(name, "")) > limit:
                raise ValueError(f"{name}: максимум {limit} символов")
        trade = {"id": str(uuid4()), "symbol": symbol, "side": body["side"],
                 "entry": entry, "exit": exit_price, "stop": stop, "quantity": qty,
                 "contract_multiplier": multiplier, "fees": fees, "gross_pnl": round(gross, 8),
                 "pnl": round(pnl, 8), "risk_amount": round(risk, 8), "return_r": round(pnl / risk, 6),
                 "strategy": body.get("strategy", ""), "notes": body.get("notes", ""),
                 "emotion": body.get("emotion", ""), "setup_followed": body.get("setup_followed", False),
                 "opened_at": opened, "closed_at": closed, "mode": "manual_journal"}
        with self.connect() as conn:
            conn.execute("INSERT INTO journal VALUES (?,?,?)", (trade["id"], now, json.dumps(trade, ensure_ascii=False, allow_nan=False)))
        return trade

    def delete_trade(self, trade_id):
        with self.connect() as conn:
            return conn.execute("DELETE FROM journal WHERE id=?", (trade_id,)).rowcount > 0

    def export_journal(self):
        rows = self.journal()["trades"]
        cols = ["id", "symbol", "side", "opened_at", "closed_at", "entry", "exit", "stop", "quantity",
                "contract_multiplier", "fees", "pnl", "return_r", "strategy", "setup_followed", "emotion", "notes"]
        out = io.StringIO(newline="")
        writer = csv.DictWriter(out, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            # Prevent spreadsheet formula injection in user-authored text cells.
            safe = dict(row)
            for key in ("symbol", "strategy", "emotion", "notes"):
                value = str(safe.get(key, ""))
                if value.lstrip().startswith(("=", "+", "-", "@")):
                    safe[key] = "'" + value
            writer.writerow(safe)
        return out.getvalue()

    def save_research(self, result):
        rid = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute("INSERT INTO research VALUES (?,?,?)", (rid, now, json.dumps(result, ensure_ascii=False, allow_nan=False)))
            conn.execute("DELETE FROM research WHERE id NOT IN (SELECT id FROM research ORDER BY created DESC LIMIT 10)")
        return rid

    def latest_research(self):
        with self.connect() as conn:
            row = conn.execute("SELECT id,payload FROM research ORDER BY created DESC LIMIT 1").fetchone()
        if not row:
            return None
        result = json.loads(row[1])
        result["research_id"] = row[0]
        return result

    def add_signal(self, payload):
        now = datetime.now(timezone.utc).isoformat()
        signal = {"id": str(uuid4()), "received_at": now, "symbol": str(payload.get("symbol", "")).upper()[:32],
                  "side": payload.get("side"), "strategy": str(payload.get("strategy", ""))[:100],
                  "price": finite(payload.get("price"), "price", 1e-12),
                  "source": "tradingview", "status": "received_planning_only", "executed": False}
        if not signal["symbol"] or signal["side"] not in ("long", "short", "flat"):
            raise ValueError("Сигналу нужны symbol и side: long/short/flat")
        with self.connect() as conn:
            conn.execute("INSERT INTO signals VALUES (?,?,?)", (signal["id"], now, json.dumps(signal)))
            conn.execute("DELETE FROM signals WHERE id NOT IN (SELECT id FROM signals ORDER BY created DESC LIMIT 500)")
        return signal

    def signals(self):
        with self.connect() as conn:
            return [json.loads(x[0]) for x in conn.execute("SELECT payload FROM signals ORDER BY created DESC LIMIT 50")]


def journal_stats(rows):
    pnl = [x["pnl"] for x in rows]
    wins = sum(x > 0 for x in pnl)
    losses = abs(sum(x for x in pnl if x < 0))
    gross_wins = sum(x for x in pnl if x > 0)
    # Chronological realized equity drawdown; no claim about floating drawdowns.
    cumulative = peak = max_dd = 0.0
    for row in sorted(rows, key=lambda x: x["closed_at"]):
        cumulative += row["pnl"]
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)
    groups = {}
    for row in rows:
        group = groups.setdefault(row["strategy"] or "Без стратегии", {"trades": 0, "pnl": 0, "total_r": 0})
        group["trades"] += 1
        group["pnl"] += row["pnl"]
        group["total_r"] += row["return_r"]
    return {"total_trades": len(rows), "net_pnl": round(sum(pnl), 8), "win_rate": wins / len(rows) * 100 if rows else 0,
            "profit_factor": gross_wins / losses if losses else None,
            "expectancy_r": sum(x["return_r"] for x in rows) / len(rows) if rows else 0,
            "discipline_pct": sum(x["setup_followed"] for x in rows) / len(rows) * 100 if rows else 0,
            "max_drawdown": round(max_dd, 8), "by_strategy": groups,
            "drawdown_basis": "realized_journal_only"}
