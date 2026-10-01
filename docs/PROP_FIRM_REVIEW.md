# Актуальная проверка публичных правил FTMO и Topstep

Официальные страницы получены по проверенному HTTPS **1 октября 2026 года**, приблизительно 09:21–09:25 UTC. В отличие от предыдущего состояния сети, эти запросы завершились HTTP 200. Прежние сообщения о proxy 403 описывают ранние проверки, а не результат этого обзора.

Машиночитаемый [prop-firm-review.json](prop-firm-review.json) содержит **47 источников и 79 фактов**: точные requested/final URL, UTC получения, SHA-256 исходных байтов и подтверждающие выдержки. Статус — `public_source_documentary_draft`, `user_verified=false`. Аккаунты не открывались, договор пользователя не подтверждался, challenge не покупался, брокерские действия не выполнялись.

## Практический выбор на текущем этапе

**Первый кандидат по совместимости условий для дальнейшего исследования — FTMO CFD 2-Step Swing.** Причины: общий static drawdown, отсутствие 1-Step Best Day denominator, возможность удержания/news и условное разрешение EAs/VPS. Это не победитель по доказанному EV и не предложение купить испытание.

Текущий рыночный кандидат должен независимо пройти нетронутый holdout, корректный replay конкретных правил и forward paper test. До этого `selected_profile_id=null`, выбранный live-рынок и ожидаемая прибыль отсутствуют. Ни наличие опубликованных правил, ни более удобный договор не исправляют отрицательную стратегию.

Для этой версии критичны пробелы модели: два этапа evaluation FTMO 2-Step, разные minimum days на evaluation и funded, refund, точный configured fee и реальные platform costs. Их нельзя заменить учебным одностадийным профилем и заявить вероятность выплаты.

Topstep остаётся альтернативой для **intraday futures на личном устройстве**. Его актуальная API-политика запрещает remote/cloud order flow. В облаке можно исследовать, хранить данные и наблюдать; нельзя отправлять/изменять/отменять/ретранслировать ордера или создавать trigger, достигающий order endpoint.

## FTMO CFD: продукты и этапы

| Правило | Challenge 1-Step / FTMO Account 1-Step | Challenge 2-Step / Verification / FTMO Account 2-Step |
| --- | --- | --- |
| Evaluation | Одна фаза, target 10% | Две фазы: 10%, затем 5% |
| Funded target | Отсутствует | Отсутствует |
| Daily allowance | 3% исходного капитала | 5% исходного капитала |
| Daily reference | Balance в 00:00 CE(S)T | Balance в 00:00 CE(S)T |
| Total allowance | 10%, EOD trailing по balance | 10%, static от исходного капитала |
| Best Day | ≤50% суммы прибыльных дней | В comparison обозначено отсутствие этого правила |
| Minimum trading days | Отдельный fixed minimum не указан в comparison | 4 дня открытия позиций в каждой evaluation-фазе; funded minimum отсутствует |
| Период | Unlimited | Unlimited |
| Базовый Reward split | 90% | 80%; 90% при дополнительных Scaling/Premium условиях |
| Swing | Недоступен | Доступен при первоначальной конфигурации |
| Fee | Однократный; без refund | Однократный за две фазы; refund с первым Reward при условиях |

Источники: [Trading Objectives](https://ftmo.com/en/trading-objectives/), [Comparison Table](https://ftmo.com/en/comparison-table/), [Reward FAQ](https://ftmo.com/en/faq/how-do-i-withdraw-my-profits/), [Fee FAQ](https://ftmo.com/en/faq/are-the-fees-recurrent/).

### Loss floor и измерение

Daily floor = **balance в полночь − allowance от исходного капитала**. Equity учитывает floating P&L, swaps и commissions. Это не `max(balance,equity)` в начале дня. Reset указан как 00:00 CE(S)T, а не фиксированный UTC offset.

1-Step total floor = максимум исходного капитала и **предыдущих midnight balances** − 10% исходного капитала. Floor не снижается. После Reward withdrawal и выдачи нового счёта first-day floor возвращается к 90% исходного. Intraday equity peak и midnight balance не взаимозаменяемы.

2-Step total floor = 90% исходного капитала, static. В source используется «drops below»; локальный чекер считает касание breach консервативно. Точная tolerance/обработка равенства в платформе не проверена.

### Best Day 1-Step

Denominator — **сумма net closed profit только прибыльных дней**, а не весь net profit с учётом отрицательных дней. В source:

> “your Best Day does not represent more than 50% of your Positive Days’ Profit”

Превышение не является breach: для pass/reward требуется дополнительная прибыль. Искусственно растягивать одну trade idea/hedge по дням ради consistency запрещено [Forbidden Trading Practices](https://ftmo.com/en/forbidden-trading-practices/). Generic consistency `best_day / total_net_profit` не воспроизводит это правило.

### Swing, Standard и новости

[Swing](https://ftmo.com/en/faq/ftmo-swing-account-type/) существует только в 2-Step. Его нельзя получить последующим переключением Standard → Swing. Выбор должен соответствовать первоначальному продукту.

[News FAQ](https://ftmo.com/en/faq/can-i-trade-news/) освобождает evaluation от selected-news window. Funded Standard запрещает entry/exit, включая triggered pending SL/TP, на затронутых инструментах от двух минут до события до двух минут после. Удержание ранее открытой позиции не освобождает от нарушения при SL/TP execution внутри окна. Swing исключён из этого window.

[Holding FAQ](https://ftmo.com/en/faq/do-i-have-to-close-my-positions-overnight-or-before-the-weekend/) требует funded Standard закрываться перед weekend и market break дольше двух часов. Это не запрет любого overnight; evaluation и Swing имеют исключение.

Освобождение Swing/evaluation от отдельных window/holding правил не отменяет общие запреты gap trading вокруг major events, манипуляции, overexposure и non-replicable trading.

### EAs, VPS и спецификации

[Strategy FAQ](https://ftmo.com/en/faq/which-instruments-can-i-trade-and-what-strategies-am-i-allowed-to-use/) допускает algorithmic trading/EAs при legitimate, replicable trading и proper risk management. Сторонний массовый EA имеет allocation caveats. [Forbidden Practices](https://ftmo.com/en/forbidden-trading-practices/) отдельно ограничивает abusive tools, delay/error feeds, manipulative cross-account opposite positions и более 2000 daily server requests.

[VPN/VPS FAQ](https://ftmo.com/en/faq/can-i-travel-or-use-vpn-vps/) говорит о generally allowed use, с исключением US geolocation для MetaTrader/cTrader/TradingView. Этот обзор не устанавливал геолокацию текущего cloud host и не разрешает обход региональных условий.

[Specifications FAQ](https://ftmo.com/en/faq/what-are-the-account-specifications/) указывает leverage Standard до 1:100, Swing до 1:30. Реальные multiplier, commission, spread и swap проверяются в платформе; серверный clock GMT+2/DST не следует подменять account-rule reset.

### Цена и Reward

[Comparison](https://ftmo.com/en/comparison-table/) публикует **FROM €89** для 2-Step и **FROM €79** для 1-Step. Это lower advertised starting price, не стоимость выбранного размера/валюты/платформы/региона. `entry_fee_exact=null` сохранён намеренно.

Reward доступен к запросу на 14-й или последующий день от первого placed trade, с закрытыми позициями/orders. Review и invoice approval предшествуют отправке; опубликованные 1–2 business days не гарантируют выплату пользователя. Minimum closed profit: $20 bank wire, $50 crypto. 1-Step не позволяет rollover; 2-Step позволяет при stated minimum.

Есть отдельная [FTMO Futures Growth/Pro линейка](https://ftmo.com/en/futures/trading-objectives-and-rules/). Она не описывается CFD 1-Step/2-Step таблицей; configuration-dependent Futures правила в этом обзоре полностью не разобраны.

## Topstep: Trading Combine, XFA и LFA

| Продукт | Проверенные базовые условия |
| --- | --- |
| Trading Combine | Simulated evaluation; targets $3K/$6K/$9K на 50K/100K/150K; consistency 55%; возможно от двух дней |
| XFA Standard | Simulated funded-level, balance начинает с $0; для выплаты 5 winning days с Net P&L ≥$150 |
| XFA Consistency | От 3 trading days с trade; largest net winning day ≤40% total net profit |
| Live Funded Account | Реальный капитал; отдельные capital/reserve/DLL/payout условия, не копия Combine/XFA |

Источники: [Combine](https://help.topstep.com/en/articles/8284197-trading-combine-parameters), [Consistency](https://help.topstep.com/en/articles/8284208-consistency-at-topstep), [XFA](https://help.topstep.com/en/articles/8284215-express-funded-account-parameters), [LFA](https://help.topstep.com/en/articles/10657969-live-funded-account-parameters).

### MLL и DLL

[MLL](https://help.topstep.com/en/articles/8284204-what-is-the-maximum-loss-limit) allowances: **$2000/$3000/$4500**. Floor trails EOD balance, не снижается и фиксируется у starting balance. Intraday realized/unrealized Net P&L контролируется в реальном времени; touch приводит к liquidation.

Combine 50K начинается с balance $50000 и initial floor $48000. XFA 50K начинается с **balance $0**, floor −$2000; trailing lock — $0. После первой выплаты MLL становится $0 независимо от предшествующего положения. Generic funded reset на nominal $50000 не воспроизводит это.

[DLL](https://help.topstep.com/en/articles/10490293-daily-loss-limit-in-the-trading-combine-and-express-funded-account) optional в TC/XFA, automatic в LFA. Срабатывание — forced session break, **не MLL violation**. Optional TC/XFA размеры $1000/$2000/$3000; trading session 5 PM–3:10 PM CT, после trigger позиции/orders закрываются до следующей сессии.

[Hours/products](https://help.topstep.com/en/articles/8284206-when-and-what-products-can-i-trade): закрытие каждого weekday к 3:10 PM CT, возобновление с 5 PM CT; отдельные инструменты могут закрываться раньше. No swing trading, no spot Forex. CT не кодируется постоянным UTC offset.

### Consistency и выплаты

Combine сейчас публикует **55% hard line без rounding/buffer**, а не прежние 50%. При слишком большом best day needed profit = best day / 0.55.

[Payout policy](https://help.topstep.com/en/articles/8284233-topstep-payout-policy): base split 90/10, minimum $125. Есть grandfathered exception для пользователей нового dashboard до 12 января 2026; его нельзя применять к новому пользователю.

XFA payout может составить 50% баланса до cap:

| Размер | Standard cap | Consistency cap |
| --- | ---: | ---: |
| 50K | $2000 | $3000 |
| 100K | $3000 | $4000 |
| 150K | $5000 | $6000 |

Winning/trading days в payout-статье фиксируются в 4 PM CT. Отдельная consistency-статья говорит о history lock 3:10 PM CT; эти времена не объединяются в произвольный reset. Request-day не входит в следующий цикл.

Limited-time DLL promotion удваивает caps только для eligible new checkout. Срок окончания не опубликован; повышенный cap не принят за гарантированный base. LFA имеет другие withdrawal/reserve и winning-day условия; API недоступен.

### Цена и execution costs

[Current Pricing](https://help.topstep.com/en/articles/14289835-topstep-pricing-and-payment-questions):

| Размер | Standard monthly | No Activation Fee monthly | Standard activation при XFA |
| --- | ---: | ---: | ---: |
| 50K | $49 | $95 | $149 |
| 100K | $99 | $149 | $149 |
| 150K | $199 | $229 | $149 |

No Activation Fee path имеет $0 activation. XFA не имеет monthly subscription после pass. Combine rebills каждые 30 дней до pass/cancel; breach сам по себе не отменяет billing. Reset/Back2Funded отдельны, не бесплатны. Level 1 SIM data включены, optional Level 2 — $38/month.

[TopstepX commissions](https://help.topstep.com/en/articles/8284213-topstepx-commissions-and-fees) сейчас публикует **MES/MNQ $1.22 roundtrip** ($0.61 per side), ES/NQ $3.78 RT. Это cash cost на контракт, не basis points; spread/slippage добавляются отдельно.

Другой [официальный LFA cost source](https://help.topstep.com/en/articles/8284229-what-are-the-costs-in-the-live-funded-account) содержит конфликтующие commission amounts и арифметику professional data. LFA costs не считаются установленными только по одной таблице. Full XFA scaling tiers находятся в недоступном изображении; missing значения не придуманы.

### Автоматизация, cloud и hedging

[API policy](https://help.topstep.com/en/articles/11187768-topstepx-api-access) допускает custom SIM bots, с HFT/standard-rule ограничениями:

> “All trading activity must originate from your personal device.”

> “The line is order transmission: your server can watch and record, but it cannot trade.”

VPS/VPN/remote orders, modification, cancellation, relay и автоматический trigger к order endpoint запрещены. ProjectX API не обслуживает LFA. API subscription отдельна: $29/month; источник публикует Topstep 50% code, $14.50/month. Наличие API не является разрешением cloud-autotrading.

[Native copier](https://help.topstep.com/en/articles/14434175-topstepx) допускает TC/XFA, исключая LFA. [Cross-account hedging](https://help.topstep.com/en/articles/13747047-understanding-hedging), включая correlated MES/ES/MNQ/NQ и краткое accidental overlap, запрещён.

[Economic releases](https://help.topstep.com/en/articles/8284211-economic-releases) не требуют blanket flatten; однако [purposeful full maximum position into major news](https://help.topstep.com/en/articles/10305426-prohibited-trading-strategies-at-topstep) запрещён. «Новости разрешены» не означает отсутствие риск-ограничений.

## Что считается установленным

Установлены опубликованные на момент получения public-source формулы и product distinctions, а не применимость договора к конкретному пользователю. Unknown/conflict поля, источник каждого факта и модели-пробелы сохранены в JSON.

Не установлены current winning strategy, фактическая будущая вероятность выплаты, наиболее прибыльная фирма, точная configured FTMO price, user eligibility, полностью проверенный legal agreement и право на live order. Автопоиск должен использовать documentary drafts с provenance и не повышать их самостоятельно до `user_verified`.

Следующее полезное действие программы — тестировать свежую рыночную гипотезу с корректными stage-specific правилами и обоснованными costs. При отказе стратегии результат остаётся «не торговать», даже если фирма прошла документальную проверку.
