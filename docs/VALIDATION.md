# Validation — 0.5.0 research release

2026-10-02: `python3 -m unittest discover -s tests -q` passed **616 tests**
in Linux in27.39 seconds; `node --check static/app.js` and `git diff --check`
passed. Tests use isolated synthetic fixtures for causality/accounting/queue
behavior; they are not trading-profit evidence. Actual market outcomes are
preserved separately with protocol, source, input and stage hashes.

The new causal liquidity engine, spot/perpetual/funding readers,208-config hourly
matrix,64-config portfolio matrix, statistical toolkit, four funding constructions
and durable official-CLI research queue are tested. The evidence API admits a
paper candidate only when the fixed passing phase and every required validation
AND final check agree. Independent audit recomputed nine actual ledger/CI runs
and tested109 invalid promotion states; no critical finding remains in that
reviewed scope. [Audit receipt](FINAL_RESEARCH_AUDIT.md).

Actual browser checks passed the new evidence/status card, read-only report links,
no startup POST, mobile navigation, XSS/same-origin restrictions and HTTP failure
handling. Legacy SMA/RSI/WATCH models are collapsed by default and recoverable.
Cloud server0.5.0 started and `scripts/check_ready.py` passed, including the new
evidence endpoint. All seven protocol/producer hashes verify;292 configurations
are completed, primary=null, orders/Telegram disabled. Manual journal remains0
rows with unchanged SHA256
`4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`.

Three official public-data acquisition runs passed on GitHub. Local decoded data
and canonical CSV hashes match the original checksum-verified manifests. Full
BTC/ETH5m has289,152 contiguous bars each; hourly24,096; funding3,012 events each.
Archive use is personal non-production CC-BY-NC-SA; raw snapshots stay outside
application distributions. Correlations, risk, costs, confidence and failures are
in [EXPERIMENT_REGISTRY.md](EXPERIMENT_REGISTRY.md).

The fixed funding hedge earned+1.823768% /+0.483292% /+0.114545% in2024/2025/Jan–Sep2026.
2026 failed99% interval and half-period stability. This release contains **no
qualified stable strategy, live exchange execution or Telegram trading bot**.
Subscription CLI actual startup failed before a model call because the existing
Codex home is immutable; queue paused`runtime_unavailable`, tokens unknown.

The first native0.5.0 run[36994215927](https://github.com/NeatherFrog/awesome-x402/actions/runs/36994215927)
passed official runtime build, then failed importing the frozen liquidity module:
Windows had no system/PyPI IANA database. No package was published from that run.
The package now registers its already bundled IANA2026b TZif directory only when
ordinary New York lookup fails; host paths remain preferred. Strategy/data/
protocol producer bytes are unchanged. Six new regression tests cover empty host,
fresh-process import, idempotence and2024–2026 DST/lunch boundaries. Independently
comparing the existing bundle with the research host at every289,1525m timestamp
reproduced local clock, UTC offset and fold exactly. Native smoke now imports the
frozen engine in the isolated embedded runtime and checks both seasonal offsets.

Native Windows0.5.0 evidence must match its exact source/package; publication is
performed only after the workflow passes native tests, package launch, evidence
API, updater/restart and preservation. The former0.4.0 evidence below applies
only to that release, not to this code.

---

# Проверка версии 0.4.0

Проверено 1 октября 2026 года в облачной машине: Python 3.12.14, Node 24.19.0 и Chromium. Проверки приложения используют отдельные временные базы и не меняют личный дневник.

- `python3 -m unittest discover -s tests -q`: **470 тестов, все успешны, без пропусков в Linux**, 24,87 с. Добавлены проверки опубликованных дневных/часовых/RSI2 правил, причинности, цены следующего открытия, fixed-stop, издержек, календаря, границ периодов, неизменности исходных снимков/протоколов/выбора; HTTP экрана сетапов, реестра попыток и двух исторических дневников.
- `node --check static/app.js`, Python compileall и `git diff --check`: успешно.
- `scripts/smoke_browser.py`: исследование в свёрнутых инструментах, модель выплаты, бумажный чекер, личный журнал, сохранение после reload, Pine, профили и мобильный экран.
- `scripts/smoke_scanner_browser.py`: настоящее архивное исследование, выбор только на train, расходы, сохранение задания, устаревшие сигналы, восемь ошибок поставщика и девять мобильных вкладок.
- `scripts/smoke_autopilot_browser.py`: один запланированный запуск, отсутствие startup POST, сохранение настроек, явный повтор, fail-closed данные/календарь и отображение только исходного основного результата.
- Дополнительно Chromium проверил главный экран «Найти сетапы», отсутствие кнопок исследования в основном потоке, недоступность котировок без подмены, два положительных исторических сценария без живого допуска, дедупликацию бумажного уведомления и исчезновение просроченных уровней. В дневнике реально отрисованы семь SMA-позиций и две RSI2-позиции с локальными OHLC, обе реальные ссылки TradingView и переход между сценариями; новые запросы не меняют личный журнал. Alert-вход проверен явно обозначенным renderer fixture, а не объявлен найденным рыночным сетапом.
- `bash scripts/start.sh` и `python3 scripts/check_ready.py`: сервер 0.4.0 перезапущен, доступны API, восемь стратегий, профили, три отдельные опубликованные проверки, оба дневника, фоновый поиск, календарь и updater. Перед перезапуском создана согласованная SQLite backup; после перезапуска SHA-256 личных записей совпал. Сам readiness не обращается к внешним сайтам и не пишет сделки.

## Проверенные рыночные результаты

| Проверка | Фиксированный выбор и данные | Результат |
| --- | --- | --- |
| [Дневные источники](SOURCED_RESEARCH.md) | Пять ETF, 5470 дневных баров на актив, 2005–2026; основной SMA10/30 выбран до двух проверок | +6,88% / +6,61%; длинный 99% интервал включает ноль; общего допуска нет |
| [Часовые модели](INTRADAY_RESEARCH.md) | Три ETF, 501 полная сессия; шум14 выбран на первом году | −4,35% на втором году, 377 сделок; все три семейства убыточны |
| [RSI2](MEAN_REVERSION_RESEARCH.md) | Одна фиксированная гипотеза, прежние неизменённые дневные снимки явно повторно используются | +2,60% / +3,51%; carry и двойные расходы отдельно остаются положительными; длинный интервал включает ноль |

Проценты относятся к целым периодам. Убыточные результаты, исходная неподдерживаемая halfday попытка, явное исправление до оценки, хеши протоколов, training locks, сделки и капитал сохранены. Все исполнители прошли независимую проверку финансовых тождеств и причинности. Опубликованные исходники подтверждают происхождение гипотез, не наследуемую авторскую прибыль.

Дневник сентября 2026: SMA — семь позиций, шесть закрытий и одна позиция на границе, изменение капитала −$511,76; RSI2 — две закрытые позиции, +$37,56. Это исторические модели, без реальных исполнений и выплат. Графики собственные; TradingView screenshots не получены. Полный план: [TRADING_PLAN.md](TRADING_PLAN.md).

Прежние [четыре акции](RESEARCH_RESULTS.md), [485 активов](EDGE_SEARCH.md), [GOOG](INDEPENDENT_RESULTS.md), [ETH/BTC](CRYPTO_RESULTS.md) и [восемь свежих рынков](CURRENT_RESEARCH.md) сохраняются. Неудачный основной выбор не заменяется удачной альтернативой после holdout.

## Windows и доставка

Встроенный официальный CPython 3.13.16 проверяется по закреплённому SHA-256 HTTPS-архива, Windows version resource и валидным PSF Authenticode подписям. Проверки TLS, подписи и checksum не отключены. Обычное обновление сохраняет runtime, SQLite, `.env` и настройки; смена runtime требует нового полного пакета.

Ранее полностью прошёл native run [0.3.5](https://github.com/NeatherFrog/awesome-x402/actions/runs/36848168339): 372 теста, запуск пакета из пути с пробелами, реальный update/restart, сохранение данных и явный отказ остановленного порта. Это доказательство той версии, не native доказательство 0.4.0.

Новая сборка публикуется `.github/workflows/windows-package.yml` только после native тестов и `scripts/smoke_windows_package.py` для точного source commit. Smoke дополнительно проверяет наличие всех трёх frozen отчётов, экран сетапов и отдельный RSI2-дневник. Итоговый `windows-validation.json` в ветке distribution содержит source commit, версию, SHA-256 архива и выполненные native проверки. Сравнивайте его с `.installed.json` выбранного ZIP; не подменяйте Windows запуск Linux-проверками. Signed log storage не требуется: bounded/redacted stage diagnostics публикуются GitHub Checks API.

ZIP исключает `.git`, `.local`, реальные токены и сторонние сырые Yahoo котировки. Публичные лицензированные архивы включены отдельно. Исторические графики установки прогреваются фоновым рабочим процессом из пяти Yahoo источников; GET не скачивает цены и не заполняет отсутствующие свечи синтетикой.

## Практические пределы

Официальные FTMO/Topstep документы, Yahoo, GitHub и календарь реально получены 1 октября. Публичные firm drafts не подтверждают личный договор, CFD quotes, тариф и право на выплату. Брокерских заявок и покупок challenge нет. Часовой/дневной OHLC не восстанавливает tick execution; макроцикл и sentiment не объявляются вычисленными новостными сигналами. Pine не компилировался в TradingView, внешний webhook TLS-вход не развёрнут.

Для onboarding сохраняются проверенные startup/readiness инструкции без установки пакетов. Cloud draft не применяет сеть, не публикует snapshot и не доказывает запуск нового task. Скриншоты проверенного интерфейса находятся в игнорируемом `artifacts/`.
