# Цель: 8% в месяц и реальные условия выплаты

Этот новый расчёт отделяет торговую прибыль, виртуальный nominal счёта и деньги, полученные после split, caps и fees. Старые исследования стратегий сохранены. Публичные правила FTMO/Topstep перепроверены2 октября2026; договор пользователя, текущий аккаунт и рабочий коннектор не подтверждены.

**Ни одна текущая стратегия не доказала устойчивую доходность8% в месяц.** Числа ниже — арифметика цели и явно синтетические проверки правил, а не наши реальные сделки, выплаты или прогноз вероятности прохождения.

## Две разные трактовки цели

На условном счёте100,000USD торговые8% — это8000USD net trading PnL после торговых расходов, до разделения прибыли с фирмой. Получить8000USD на собственный счёт — более высокая цель.

| Условие | Из8000USD trading PnL | Требуется для8000USD cash |
| --- | ---: | ---: |
| FTMO2-Step, базовый split80% |6400USD до внешних расходов |10000USD gross profit до split |
| Split90%, без caps/fees |7200USD |8888.888889USD gross profit |
| Topstep100K XFA Standard, первый подходящий request |До3000gross:2700до method fee;2670после30ACH |Минимум3 подходящих payout windows плюс50%-balance/cap constraints |
| Topstep100K XFA Consistency, первый подходящий request |До4000gross:3600до method fee;3570после30ACH |Минимум3 подходящих payout windows плюс eligibility/reserve constraints |

8% каждый месяц с реинвестированием соответствуют `(1.08**12−1)*100 =151.817011682%` годовых. Вынимать фиксированные8000USD каждый месяц относительно исходных100000USD —96000USD, или96% годового nominal. Это разные модели, и обе нуждаются в доказанной торговой стратегии.

## FTMO CFD2-Step Swing

Первый исследовательский кандидат по совместимости продукта — **FTMO CFD2-Step Swing**. Static allowance10000USD больше Topstep100K allowance3000USD; Swing допускает overnight/weekend и исключение из отдельного selected-news window, а legitimate EAs/VPS условно разрешены. Это не доказанный победитель по EV и не предложение купить challenge.

Replay моделирует три отдельных этапа:

1. Challenge: fresh100000USD, цель10000USD, четыре дня открытия позиций.
2. Verification: новый fresh100000USD, цель5000USD, снова четыре дня открытия позиций. Прибыль Challenge не переносится в выводимые деньги.
3. Funded: fresh account, profit target отсутствует. Reward зависит от eligibility и одобрения, а не от прохождения общей8%-цели.

Общий floor —90000USD. Daily floor — balance в00:00Europe/Prague минус5000USD. Equity включает открытый PnL, swaps и commissions. Например, balance101000USD и equity95500USD в новую полночь нарушают новый daily floor96000USD, хотя предыдущий floor95000USD ещё не был нарушен.

Reset использует IANA Europe/Prague и реальные23/25-часовые DST дни. Platform server clock не заменяет clock правила. При касании floor локальный сценарий консервативно считает breach; точная broker tolerance не проверена.

Публичный Reward допускает запрос на14-й или следующий день после first placed trade при закрытых positions/orders. Источник не определяет точно inclusive calendar против elapsed-hours; сценарий требует **и14 местных календарных дней, и14 полных24-часовых суток**. Bank-wire minimum20USD относится к closed profit; crypto minimum50USD требует другого подтверждённого метода. После Reward этот replay завершает account stage: следующий счёт должен получить отдельный fresh snapshot, а не вымышленное восстановление старого daily floor.

Точная checkout fee для100K/Swing/валюты/региона неизвестна. Advertised FROM€89 не используется как fee выбранного аккаунта. Возможный refund, конвертация валюты, intermediary fees и payout approval не включены в ложный «точный net EV».

## Topstep100K: nominal не равно loss budget

Trading Combine имеет reference nominal100000USD, target6000USD и55% consistency. Maximum Loss Limit составляет **3000USD**, то есть8000USD monthly trading goal равен2.666667 таким risk allowances.

MLL trailing использует EOD balance, а не intraday equity peak, и floor не падает. В Combine floor начинается с97000USD и фиксируется у100000USD. В XFA actual balance начинается с **0USD**, floor−3000USD; floor фиксируется у0USD. Это не новый депозит100000USD. После первого payout floor становится0USD независимо от прежнего положения.

Intraday unrealized equity touch проверяется до EOD ratchet. Хороший closing balance не исправляет earlier breach. Optional100K DLL2000USD моделируется отдельно: он вызывает forced-flat/session pause, а не автоматически MLL failure. Точный порядок открытия ордеров после intrabar DLL touch нельзя установить только по envelopes, поэтому full contract compliance никогда не сертифицируется.

Периоды не смешиваются: trading/session close15:10CT, next session17CT; day lock для payout16CT. Trading Combine consistency использует session-final point; XFA payout days — отдельный16CT point. Source MLL описывает EOD, но не доказывает точную backend minute. Replay требует явный session-final snapshot и сохраняет это ограничение. Generic weekday calendar не доказывает holiday/product-specific earlier close.

XFA Standard требует пять новых winning days с net PnL≥150USD. XFA Consistency требует три trading days и largest winning day≤40% **нового window net profit**. После запроса предыдущий retained balance не входит в этот denominator; request day не засчитывается в следующем window.

Request ограничен50% текущего balance и cap3000USD Standard /4000USD Consistency. Base split90%, после него для ACH/SWIFT дополнительно30USD. Minimum125USD интерпретируется как gross request только для сценария: source не уточняет gross/net. Grandfathered/promotion cap исключения не применяются к неизвестному новому аккаунту.

**Синтетический пример**, показывающий reserve/cycle ограничения:15 вымышленных winning days дают12000USD trading profit — первые пять по1200, следующие десять по600. Три eligible requests по3000gross дают8100USD после90% split и8010USD после трёх30USD ACH fees. Условные первая подписка99USD и activation149USD уменьшают первый economic cash до7762USD. Эти положительные дни придуманы для проверки арифметики; они не найдены торговым алгоритмом. XFA monthly subscription после pass отсутствует, поэтому first-entry costs нельзя повторять как funded monthly fee.

Cloud order transmission/relay для Topstep запрещены; SIM API требует personal device. LFA имеет другие правила и не поддерживается этим reference model. API/data subscriptions, частные договоры и реальные выплаты отдельно не подтверждены.

Базовый100K Standard checkout:99USD за30 дней evaluation плюс149USD activation при XFA. No Activation Fee path:149USD за30 дней и0activation. При одном/two/three billings суммарные reference fees составляют Standard248/347/446USD против149/298/447USD. Поэтому выбранный в сценариях Standard fee path — явное допущение, а не доказанно самый дешёвый checkout; неизвестные время pass/resets/promotion не заменяются удобной fee оценкой.

## Какой edge требуется арифметически

Для8000USD base FTMO cash нужны10000USD trading profit. При fixed250USD риска и30 сделках за месяц это40R, или1.333333 **net R на сделку**. В искусственной бинарной модели net winner+2R/loser−1R нужна ожидаемая доля выигрышей77.7778%. При риске500USD требуется20R, или0.666667R на сделку, соответствующие55.5556% в той же условной модели.

Это формула `expected_net_R = p*winner_R − (1−p)`; она не оценивает фактическую win rate, корреляции проигрышей, gap loss, stochastic monthly variation или вероятность payout. Параметры необходимо получить из строгого out-of-sample и нового forward, а торговые комиссии должны быть уже включены в net outcomes. Произвольное повышение риска не создаёт edge.

## Вход и воспроизведение replay

`propdesk.prop_objective.replay_stage(points,stage,metadata)` принимает trade-only source path: UTC `interval_start/time`, balance, net_equity, worst_equity, best_equity, позиции/orders и точные trade-open times. Envelopes должны включать оба endpoint и весь intraday диапазон; intervals contiguous. Все обязательные reset snapshots нужны явно. Missing midnight/session mark, floating PnL или свежий аккаунт с перенесённой evaluation прибылью приводят к отказу.

Source deposits/payouts исключаются из input; modeled gross withdrawals ведутся отдельно. Permitted payout не превращается в DLL trading loss, но уменьшает доступный MLL buffer. `replay_lifecycle` требует правильную stage sequence и временной порядок.

[prop-payout-objective.json](prop-payout-objective.json) сохраняет objective formulas,16 unit checks, восемь synthetic paths, два separate-stage lifecycles, input/producers SHA256 и individual official receipt hashes. Все параметры сценариев встроены; их можно повторить вызовами replay. Реальные platform fills/equity и личный договор пока отсутствуют, поэтому `strategy_profitability_established=false`, `user_verified_contract=false`, `live_orders=false`. Market quote/backtest series сами по себе не являются prop-account replay.

Текущая цель следующего рыночного исследования — искать проверяемую net expectancy при конкретных instruments/costs и этих stage rules. Отсутствие qualified edge остаётся основанием для «не торговать»; успешные synthetic arithmetic cases не повышаются до торговых сигналов.
