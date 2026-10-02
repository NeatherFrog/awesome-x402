"""Read original checksum-verified USD-M taker-volume fields, never order books.

USD-M base volume is BTC/ETH; quote volume is USDT; count is the number of
trades. Taker-buy identifies aggressor side, not liquidation/hidden orders.
Zero total volume has undefined ratios and cannot become signed-flow evidence.
"""
from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from propdesk.exchange import ExchangeDataError, convert_klines
from propdesk.funding_data import _rows, _integer, _finite
from propdesk.market import data_fingerprint
from propdesk.perp_resolution import archive_urls

HEADER = ("open_time", "open", "high", "low", "close", "volume", "close_time",
          "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore")
FIELDS = ("quote_volume", "trade_count", "taker_buy_base_volume", "taker_buy_quote_volume")


def flow_row(raw, bar):
    if len(raw) != 12:
        raise ExchangeDataError("Native USD-M flow row requires exactly12 source fields")
    opened = _integer(raw[0], "open_time")
    if opened % 300000 or _integer(raw[6], "close_time") != opened+299999:
        raise ExchangeDataError("Native USD-M millisecond open/close interval inconsistent")
    expected_time=datetime.fromtimestamp(opened/1000,timezone.utc).isoformat().replace('+00:00','Z')
    if bar['time']!=expected_time or any(isinstance(bar[key],bool) or bar[key]!=_finite(raw[index],key)
                                       for index,key in enumerate(('open','high','low','close','volume'),1)):
        raise ExchangeDataError("Raw flow row and canonical OHLCV identity differ")
    quote = _finite(raw[7], "quote_volume")
    count = _integer(raw[8], "trade_count")
    buy_base = _finite(raw[9], "taker_buy_base_volume")
    buy_quote = _finite(raw[10], "taker_buy_quote_volume")
    volume = bar["volume"]
    if min(quote, buy_base, buy_quote) < 0 or buy_base > volume or buy_quote > quote:
        raise ExchangeDataError("Taker-buy volumes must be nonnegative subsets of total volumes")
    if volume == 0:
        if quote or count or buy_base or buy_quote:
            raise ExchangeDataError("Absent-trade row must have all volume/count fields zero")
    elif quote <= 0 or count <= 0:
        raise ExchangeDataError("Positive traded base volume requires positive quote volume and count")
    for base, quoted in ((volume, quote), (buy_base, buy_quote), (volume-buy_base, quote-buy_quote)):
        if base > 0:
            average = quoted/base
            tolerance = max(1e-8, bar["high"]*1e-7)
            if not bar["low"]-tolerance <= average <= bar["high"]+tolerance:
                raise ExchangeDataError("Quote/base volume price leaves its OHLC envelope")
        elif quoted != 0:
            raise ExchangeDataError("Zero base flow cannot have positive quote flow")
    known = datetime.fromtimestamp((opened+300000)/1000, timezone.utc).isoformat().replace("+00:00", "Z")
    return {**bar, "known_at": known, "quote_volume": quote, "trade_count": count,
            "taker_buy_base_volume": buy_base, "taker_buy_quote_volume": buy_quote,
            "taker_buy_base_fraction": buy_base/volume if volume else None,
            "taker_buy_quote_fraction": buy_quote/quote if quote else None}


def parse_archive(content, checksum, symbol, year, month, *, day=None):
    url, _, name = archive_urls(symbol, year, month, day=day)
    rows, source = _rows(content, checksum, name)
    if not rows or tuple(rows.pop(0)) != HEADER:
        raise ExchangeDataError("Strict original USD-M twelve-field header required")
    bars, _ = convert_klines(rows, "5m", timestamp_unit="milliseconds", closed_only=False)
    first = datetime(year, month, day or 1, tzinfo=timezone.utc)
    finish = first+timedelta(days=1 if day is not None else calendar.monthrange(year, month)[1])
    expected = int((finish-first).total_seconds())//300
    if len(bars) != expected or bars[0]['time'] != first.isoformat().replace('+00:00','Z'):
        raise ExchangeDataError("Original flow calendar must contain every native5m interval")
    if any(_integer(row[0], 'open_time') != int(first.timestamp()*1000)+i*300000 for i,row in enumerate(rows)):
        raise ExchangeDataError("Original flow timestamps contain a gap")
    result = [flow_row(raw, bar) for raw, bar in zip(rows, bars)]
    source.update(source_url=url, symbol=symbol, year=year, month=month, day=day, bars=len(result),
                  field_units={"volume": "BTC/ETH base units", "quote_volume": "USDT",
                               "trade_count": "integer trades", "taker_buy_base_volume": "BTC/ETH base units",
                               "taker_buy_quote_volume": "USDT"},
                  ohlcv_fingerprint=data_fingerprint(bars),
                  flow_fingerprint=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest())
    return result, source


def load_originals(data_dir):
    root = Path(data_dir)
    manifest = json.loads((root/'manifest.json').read_text())
    datasets, receipts = {}, []
    for dataset in manifest['datasets']:
        symbol = dataset['symbol']
        if symbol not in ('BTCUSDT','ETHUSDT') or dataset['interval'] != '5m' or not dataset['complete_calendar']:
            raise ExchangeDataError("Only exact complete registered native USD-M sources supported")
        canonical_path=root/(symbol+'-5m.json')
        if hashlib.sha256(canonical_path.read_bytes()).hexdigest()!=dataset['json_sha256']:
            raise ExchangeDataError("Frozen native JSON SHA binding differs")
        assembled = []
        for original in dataset['sources']:
            _,_,name = archive_urls(symbol,original['year'],original['month'],day=original.get('day'))
            content,checksum = (root/'raw'/name).read_bytes(),(root/'raw'/(name+'.CHECKSUM')).read_bytes()
            rows,source = parse_archive(content,checksum,symbol,original['year'],original['month'],day=original.get('day'))
            for key in ('zip_sha256','csv_sha256','source_url'):
                if source[key] != original[key]:
                    raise ExchangeDataError("Original flow source receipt mismatch: "+key)
            if not original['checksum_verified'] or source['ohlcv_fingerprint'] != original['data_fingerprint']:
                raise ExchangeDataError("Original flow OHLCV identity or checksum receipt mismatch")
            receipts.append(source)
            assembled.extend(rows)
        if data_fingerprint(assembled) != dataset['data_fingerprint']:
            # data_fingerprint deliberately retains only canonicalOHLCV fields.
            raise ExchangeDataError("Full native flow/OHLCV calendar identity differs")
        datasets[symbol] = assembled
    if set(datasets) != {'BTCUSDT','ETHUSDT'} or [r['time'] for r in datasets['BTCUSDT']] != [r['time'] for r in datasets['ETHUSDT']]:
        raise ExchangeDataError("Full synchronized BTC/ETH native flow calendars required")
    return datasets, receipts
