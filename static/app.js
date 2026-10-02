'use strict';
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
const state = {profiles: [], strategies: [], journal: {trades: [], stats: {}}, research: null, activeProfile: null, detailId: null, accountDirty: false, updates: null, updateAction: false, setup: null, scanJob: null, scanStarting: false, autopilot: null, autopilotAction: false, autopilotError: ''};
Object.assign(state,{trader:null,traderAction:false,traderError:'',replayDiary:null,strategyEvidence:null,strategyEvidenceError:''});
Object.assign(state,{researchProgress:null,researchProgressError:''});
const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
const num = (value, digits = 2) => value === null || value === undefined || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString('ru-RU', {minimumFractionDigits: digits, maximumFractionDigits: digits});
const money = value => value === null || value === undefined ? '—' : '$' + num(value);
const pct = value => value === null || value === undefined ? '—' : num(value) + '%';
const signClass = value => Number(value) > 0 ? 'positive' : Number(value) < 0 ? 'negative' : '';
const timestamp = value => { if (!value) return '—'; const d = new Date(value); return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('ru-RU', {timeZone: 'Europe/Kyiv', day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}) + ' · Киев'; };
const localTimestamp = value => {if(!value)return '—';const date=new Date(value);return Number.isNaN(date.getTime())?'—':date.toLocaleString('ru-RU',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',timeZoneName:'short'});};
const shortDate = value => { const d = new Date(value); return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('ru-RU',{timeZone:'UTC',day:'2-digit',month:'short'}); };
const fields = form => Object.fromEntries(new FormData(form));
const numeric = (form, name) => Number(form.elements.namedItem(name).value);
const checked = (form, name) => form.elements.namedItem(name).checked;
const itemById = (items, id) => items.find(item => item.id === id);
const badge = (text, style = 'neutral') => '<span class="badge badge-' + style + '">' + esc(text) + '</span>';
const inlineMetric = (title, value, style = '', detail = '') => '<div class="inline-metric"><small>' + esc(title) + '</small><strong class="' + style + '">' + esc(value) + '</strong>' + (detail ? '<span class="metric-detail">' + esc(detail) + '</span>' : '') + '</div>';
const messages = {
'Baseline is a reference, not a qualified prop strategy.':'Buy & hold — ориентир для сравнения, не допущенная проп-стратегия.',
'Synthetic DEMO data cannot establish a trading edge or qualify a strategy.':'Синтетическое демо не подтверждает edge и не допускает стратегию к торговле.',
'Holdout expectancy is not positive after execution costs.':'Ожидание на тестовой выборке не положительно после издержек.',
'Holdout profit factor is below 1.20.':'Profit factor на тесте ниже 1,20.',
'The descriptive 95% mean-R interval includes zero or is unavailable.':'95% описательный интервал среднего R включает ноль или недоступен.',
'Worst-bar holdout drawdown reaches the configured account loss limit.':'Просадка по худшей цене свечи достигает лимита аккаунта.',
'Walk-forward validation has insufficient independent windows or trade evidence.':'Недостаточно окон или сделок для проверки walk-forward.',
'Walk-forward results are not positive in at least two-thirds of windows.':'Менее двух третей окон walk-forward показывают положительный результат.',
'No fresh closed-bar setup. Wait for a new bar; this is not a live quote.':'На последней закрытой свече нет свежего сетапа. Дождитесь новых данных; это не текущая котировка.',
'No active strategy was requested; buy-and-hold is only a reference.':'Активная стратегия не выбрана; buy & hold используется как ориентир.',
'Synthetic illustration only; no live order or verified trading edge.':'Синтетический пример: подтверждённого edge и реального сигнала нет.',
'The training candidate did not pass the evidence gates; this observation is for research only.':'Победитель обучения не прошёл отбор. Наблюдение доступно только для исследования.',
'Conditional closed-bar plan. Re-check the account rules, live spread, calendar and actual entry before paper execution.':'Условный план по закрытой свече. Проверьте правила, актуальный спред, календарь и цену входа перед бумажной сделкой.',
'DEMO: all OHLCV data are synthetic. Performance is interface validation, not market evidence.':'DEMO: все свечи синтетические. Результат проверяет работу интерфейса, а не прибыльность на рынке.',
'Seven fixed strategy families are a starting catalog, not an exhaustive search of all strategies or assets.':'Каталог содержит семь семейств стратегий и ориентир buy & hold. Это начальный набор гипотез.',
'OHLC fills, quantities and costs are approximations; exchange calendars, tick paths, financing and live liquidity require separate validation.':'Исполнение на OHLC и издержки приближённые. Календари, тики, финансирование и реальная ликвидность требуют отдельной проверки.',
'Training searches and exploratory regime comparisons can overfit. The holdout must not be reused to tune parameters.':'Подбор параметров и сравнение рыночных режимов могут переобучиться. Не используйте тест для повторной настройки.',
'Positive historical results and descriptive intervals do not guarantee future profit or prop-firm payouts.':'Положительная история и статистические интервалы не гарантируют будущую прибыль или выплату.',
'Final input row is assumed closed. Export only fully closed bars; the next opening price is unknown.':'Последняя строка считается закрытой свечой. Загружайте только закрытые свечи; следующая цена открытия неизвестна.',
'User-supplied data provenance, corporate actions and survivorship are not independently verified.':'Происхождение CSV, корпоративные события и полнота выборки не проверены независимым источником.',
'Fractional theoretical quantities are enabled; configure the real contract multiplier, quantity step and broker minimums.':'Разрешён теоретический дробный объём. Задайте множитель, шаг контракта и минимальный объём вашего брокера.',
'The training winner did not pass qualification. No alternate strategy is selected from holdout results.':'Победитель обучения не прошёл отбор. Другая стратегия по итогам теста автоматически не выбирается.',
'The stricter descriptive 99% mean-R interval includes zero or lacks 20 holdout trades':'99% описательный интервал среднего R включает ноль или на тесте менее 20 сделок.',
'Global scanner did not select this market; it is a diagnostic research observation':'Глобальный выбор не допускает этот рынок вместо основного. Результат доступен для исследования.',
'no_qualified_primary':'Рынок, выбранный на обучении, не прошёл финальную проверку. Другой рынок по доходности теста автоматически не подставляется.',
'paper_research_candidate':'Победитель обучения прошёл исторические фильтры. Следующий шаг — проверка свежих котировок, контекста и правил аккаунта в бумажном сценарии.',
'Firm rules are illustrative or not user verified':'Правила учебные или не подтверждены пользователем.',
'A public HTTPS rule source is required':'Нужен публичный HTTPS-источник действующих правил.',
'Rule verification is future dated or more than 90 days old':'Дата проверки правил некорректна или старше 90 дней.',
'An explicit UTC rule verification timestamp is required':'Не указана дата проверки правил в UTC.',
'The locked primary market did not qualify; another holdout is not substituted':'Первый выбор обучения не прошёл отбор; другой результат теста не подставляется.',
'At least 30 out-of-sample trades are required for payout economics':'Для модели выплат нужно минимум 30 сделок на отложенной истории.',
'This profile prohibits automated trading':'Профиль запрещает автоматическую торговлю.',
'Firm account currency differs; cross-currency EV cannot be ranked without conversion':'Валюта аккаунта отличается; сравнение экономики требует конвертации.',
'Research risk exceeds this firm profile risk limit':'Риск исследования превышает лимит риска профиля.'
};
const translate = value => {const s = String(value ?? ''); if(messages[s]) return messages[s]; const m=s.match(/^Holdout has (\d+) trades; at least (\d+) are required\.$/);if(m)return 'На тесте '+m[1]+' сделок; требуется минимум '+m[2]+'.';return s;};
const tabMeta = {
overview:{label:'Найти сетапы',eyebrow:'СЕТАП · УРОВНИ · ПРИЧИНА РЕШЕНИЯ',title:'Ваш план на сегодня.<br><span>По условиям рынка.</span>',description:'Найдите сетапы. Программа сама проверит рынки и покажет, где есть допустимый план, а где нужно ждать.'},
strategy:{label:'Стратегия',eyebrow:'ДОПУСК · РЕЗУЛЬТАТЫ · ПРИЧИНЫ',title:'Что прошло проверку.<br><span>И что осталось вне рынка.</span>',description:'Допуск стратегии и результаты автоматических проверок. Исторический отчёт сам по себе не разрешает вход.'},
settings:{label:'Настройки',eyebrow:'РАСПИСАНИЕ · ДАННЫЕ · ПАРАМЕТРЫ',title:'Настройте проверки.<br><span>Следите за решением.</span>',description:'Расписание автоматических проверок и доступ к дополнительным инструментам.'},
scanner:{label:'Диагностика рынков',eyebrow:'РУЧНАЯ ПРОВЕРКА ИСТОРИИ',title:'История рынков.<br><span>Дополнительная диагностика.</span>',description:'Ручной расчёт доступен в раскрывающемся блоке. Его результат не становится торговым сигналом автоматически.'},
lab:{label:'Ручной бэктест',eyebrow:'ИСТОРИЯ · ИЗДЕРЖКИ · ПРОВЕРКА',title:'Свои данные.<br><span>Ручная проверка.</span>',description:'Дополнительный бэктест с издержками и отложенной выборкой. Результат не заменяет допуск стратегии.'},
setups:{label:'Сетапы',eyebrow:'ВХОД · РИСК · ЦЕЛЬ · ОТМЕНА',title:'Планируйте уровни.<br><span>Проверяйте контекст.</span>',description:'Условные зоны по исследованной истории, режиму рынка и доступному новостному календарю.'},
firms:{label:'Правила',eyebrow:'СНАЧАЛА ДОГОВОР · ПОТОМ РИСК',title:'Знайте правила.<br><span>Берегите аккаунт.</span>',description:'Соберите собственные профили и сравнивайте ограничения до торговли.'},
checker:{label:'Чекер сделки',eyebrow:'ПРОВЕРКА ДО ОТКРЫТИЯ ПОЗИЦИИ',title:'Сначала риск.<br><span>Потом решение.</span>',description:'Рассчитайте допустимый объём и проверьте ограничения своего аккаунта.'},
journal:{label:'Дневник',eyebrow:'ПРОЦЕСС ВАЖНЕЕ ОДНОЙ СДЕЛКИ',title:'Фиксируйте сделки.<br><span>Улучшайте процесс.</span>',description:'Входы, издержки, дисциплина и выводы — в локальном дневнике.'},
integrations:{label:'Данные и экспорт',eyebrow:'ФОРМАТЫ · ИСТОРИЯ · API',title:'Ваш рабочий процесс.<br><span>Ваши инструменты.</span>',description:'TradingView, история CSV и локальные форматы для дополнительной проверки.'},
updates:{label:'Обновления',eyebrow:'GITHUB · ВАША КОПИЯ PROP LAB',title:'Развиваем программу.<br><span>Вы обновляете по кнопке.</span>',description:'Проверяйте новые версии и продолжайте работу со своим дневником и настройками.'}
};
function navigate(tab, updateHash = true) {
if(!tabMeta[tab]) tab='overview';
const advanced=$('#advanced-tools');advanced.open=Boolean(advanced.querySelector('[data-tab="'+tab+'"]'));
$$('.tab-panel').forEach(el=>el.hidden=el.id!=='tab-'+tab);
$$('[data-tab]').forEach(el=>{const active=el.dataset.tab===tab;el.classList.toggle('active',active);if(active)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
$('#breadcrumb-current').textContent=tabMeta[tab].label;
$('#page-title').innerHTML=tabMeta[tab].title;
$('#page-eyebrow').textContent=tabMeta[tab].eyebrow;
$('#page-description').textContent=tabMeta[tab].description;
document.title=tabMeta[tab].label+' · PROP LAB';
if(updateHash&&location.hash!=='#'+tab)history.replaceState(null,'','#'+tab);
if(updateHash)window.scrollTo({top:0,left:0,behavior:'instant'});
}
function notice(id, text, type='error') {const el=$('#'+id);el.hidden=!text;el.className='notice notice-'+type;el.textContent=text;}
let toastTimer;
function toast(message) {$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>{$('#toast').hidden=true;},4500);}
function busy(button, loading, text) {if(loading){button.dataset.original=button.innerHTML;button.disabled=true;button.textContent=text||'Выполняется…';}else{button.disabled=false;if(button.dataset.original)button.innerHTML=button.dataset.original;}}
async function api(url, options = {}) {
const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),180000);
try{
const response=await fetch(url,{...options,headers:{'Accept':'application/json',...(options.body?{'Content-Type':'application/json'}:{}),...options.headers},signal:controller.signal});
const body=await response.text();let data;try{data=JSON.parse(body);}catch{throw new Error('Сервер вернул неожиданный ответ ('+response.status+').');}
if(!response.ok){const detail=typeof data.details==='string'?data.details:Array.isArray(data.details)?data.details.join('; '):'';throw new Error((data.error||'Ошибка '+response.status)+(detail?': '+detail:''));}
return data;
}catch(error){if(error.name==='AbortError')throw new Error('Время ожидания истекло. Проверьте соединение с сервером и повторите.');if(error instanceof TypeError)throw new Error('Нет связи с локальным сервером. Проверьте, что он запущен, и обновите страницу.');throw error;}finally{clearTimeout(timer);}
}
async function post(url, data) {return api(url,{method:'POST',body:JSON.stringify(data)});}
function profileLabel(profile) {return profile.name+(profile.status!=='user_verified'?' · УЧЕБНЫЙ':' · проверен вами');}
function renderProfiles() {
const options=state.profiles.map(p=>'<option value="'+esc(p.id)+'">'+esc(profileLabel(p))+'</option>').join('');
['active-profile-select','research-profile','check-profile','payout-profile','scanner-profile'].forEach(id=>{const select=$('#'+id);if(!select)return;const old=select.value;select.innerHTML=options;select.value=itemById(state.profiles,old)?old:state.activeProfile;});
const p=itemById(state.profiles,state.activeProfile);
if(p)$('#today-profile-name').textContent=p.name;
if(p)$('#active-profile-summary').innerHTML=badge(p.status==='user_verified'?'ПРОВЕРЕНО ПОЛЬЗОВАТЕЛЕМ':'ПРАВИЛА НЕ ПРОВЕРЕНЫ',p.status==='user_verified'?'good':'warning')+
'<div class="profile-mini-row"><span>Капитал / цель</span><strong>'+esc(money(p.account_size))+' / '+esc(pct(p.profit_target_pct))+'</strong></div><div class="profile-mini-row"><span>Дневной / общий лимит</span><strong>'+esc(pct(p.daily_loss_pct))+' / '+esc(pct(p.max_loss_pct))+'</strong></div><div class="profile-mini-row"><span>Стоимость / доля выплаты</span><strong>'+esc(money(p.challenge_fee))+' / '+esc(pct(p.payout_split_pct))+'</strong></div>';
$('#profiles-list').innerHTML=state.profiles.map(p=>'<article class="profile-card '+(p.id===state.activeProfile?'active':'')+'"><div class="profile-card-head"><div><h3>'+esc(p.name)+'</h3><div class="profile-type">'+esc({static:'Статическая просадка',trailing_eod:'Trailing на конец дня',trailing_intraday:'Trailing intraday'}[p.drawdown_type]||p.drawdown_type)+'</div></div>'+badge(p.status==='user_verified'?'ПРОВЕРЕНО ВАМИ':'УЧЕБНЫЙ ПРИМЕР',p.status==='user_verified'?'good':'warning')+'</div><div class="profile-numbers"><div><small>Аккаунт</small><strong>'+esc(money(p.account_size))+'</strong></div><div><small>Цель</small><strong>'+esc(pct(p.profit_target_pct))+'</strong></div><div><small>Доля выплаты</small><strong>'+esc(pct(p.payout_split_pct))+'</strong></div></div><div class="profile-mini-row"><span>Лимиты: день / всего</span><strong>'+esc(pct(p.daily_loss_pct))+' / '+esc(pct(p.max_loss_pct))+'</strong></div><div class="profile-mini-row"><span>Отбор / минимальные дни</span><strong>'+esc(money(p.challenge_fee))+' / '+esc(num(p.min_trading_days,0))+'</strong></div><div class="profile-rules">'+[['news_allowed','Новости'],['overnight_allowed','Ночь'],['weekend_allowed','Выходные'],['ea_allowed','Алгоритмы']].map(([key,label])=>'<span class="'+(p[key]!==true?'restricted':'')+'">'+esc(label)+' '+(p[key]===true?'✓':p[key]===false?'×':'?')+'</span>').join('')+'</div><div class="profile-actions"><button class="button button-secondary" data-edit-profile="'+esc(p.id)+'">Редактировать ↗</button><button class="button '+(p.id===state.activeProfile?'button-secondary':'button-primary')+'" data-select-profile="'+esc(p.id)+'">'+(p.id===state.activeProfile?'Активный профиль':'Использовать →')+'</button></div><p class="profile-meta">'+esc(p.verified_at?'Сверено: '+timestamp(p.verified_at):'Условия реальной фирмы не подтверждены')+'</p></article>').join('');
}
const firmModelGaps={two_evaluation_phases:'Два самостоятельных этапа отбора',stage_specific_min_days:'Отдельные торговые дни по этапам',conditional_fee_refund:'Условный возврат вступительного взноса',configured_fee:'Точная цена выбранного аккаунта',actual_instrument_costs:'Реальные издержки инструмента',agreement_and_user_region:'Применимый договор и регион пользователя',positive_day_denominator:'Лучший день относительно суммы прибыльных дней',reward_reset:'Сброс условий после выплаты',funded_standard_news_weekend:'Новости и переносы на Standard Account',zero_based_xfa_balance:'Express Account начинается с нулевого баланса',trailing_balance_cap:'Trailing-граница и её остановка',DLL_session_stop_not_breach:'Дневной стоп сессии отдельно от нарушения аккаунта',subscription_activation:'Подписка и активация аккаунта',winning_day_threshold:'Требования к прибыльному дню',payout_caps_withdrawal_floor:'Лимит выплаты и граница после вывода',scaling_tier_image:'Непроверенные уровни масштабирования',remote_order_flow_prohibited:'Запрет передачи заявок с удалённого сервера',LFA_distinct_cost_conflict:'Противоречия в издержках Live Account'};
function officialSourceLink(value,label) {
try{const url=new URL(value);if(url.protocol==='https:'&&!url.username&&!url.password)return '<a href="'+esc(url.href)+'" target="_blank" rel="noopener noreferrer">'+esc(label)+' ↗</a>';}catch{}
return esc(label);
}
function renderFirmReview(data) {
const products=data.draft_products||data.proposed_products||[],sources=data.sources||[],facts=data.facts||[],priority=data.research_priority||{},candidate=products.find(product=>product.id===(priority.product_id||data.decision?.candidate_product_id));
if(data.review_status==='unavailable'||!products.length)throw new Error('Подготовленная сводка ещё не опубликована в этой версии.');
let html='<div class="firm-review-status">'+badge('ПУБЛИЧНАЯ СВЕРКА · ПРАВИЛА НЕ ПОДТВЕРЖДЕНЫ','warning')+'<small>Сверено: '+esc(timestamp(data.reviewed_at))+' · '+esc(num(sources.length,0))+' источников · '+esc(num(facts.length,0))+' фактов</small></div>';
if(candidate)html+='<div class="firm-review-priority"><span class="eyebrow">ПРИОРИТЕТ ИССЛЕДОВАНИЯ ДОГОВОРА</span><h3>'+esc(candidate.firm+' · '+candidate.product)+'</h3><p>Условные стратегии FX и металлов с переносом позиций: сначала проверяем статический общий лимит, отдельные этапы и разрешённый режим Swing.</p><div class="firm-review-facts">'+inlineMetric('Рабочий рынок','Не выбран')+inlineMetric('Подтверждённый профиль','Нет')+inlineMetric('Ожидаемая прибыль','Не установлена')+'</div><p class="field-help">Нужны устойчивый holdout и форвард-проверка, точная стоимость аккаунта, спецификация инструментов и модель каждого этапа. Текущие исследования могут отклонить все рынки.</p></div>';
html+='<div class="firm-review-products">'+products.map(product=>{
const topstep=Boolean(product.tc_mll),limits=[],terms=[];
if(topstep){limits.push('Combine: цель '+money(product.tc_profit_target_usd)+' на '+money(product.tc_initial_balance_usd));limits.push('Trailing от максимума EOD balance: '+money(product.tc_mll.allowance_usd)+', граница до '+money(product.tc_mll.cap_floor_usd));limits.push('Лучший день: '+pct(product.tc_best_day_pct_total_net)+' общего net P&L');limits.push('XFA: стартовый баланс '+money(product.xfa_initial_balance_usd)+', начальная граница '+money(product.xfa_mll_initial_floor_usd));terms.push('Подписка '+money(product.tc_base_monthly_fee_usd)+'/месяц; активация XFA '+money(product.xfa_standard_activation_usd));if(product.payout)terms.push('Выплата: '+num(product.payout.winning_days,0)+' дней с net ≥ '+money(product.payout.minimum_daily_net_usd)+', доля '+pct(product.payout.split_pct)+', cap '+money(product.payout.standard_cap_usd));}
else{if(product.stage_targets_pct)limits.push('Цели: Challenge '+pct(product.stage_targets_pct.challenge)+' → Verification '+pct(product.stage_targets_pct.verification));else if(product.id==='review-ftmo-1step-standard'){const target=facts.find(fact=>fact.id==='ftmo_1step_target')?.structured_value?.challenge_target_pct;if(target!==undefined)limits.push('Цель Challenge: '+pct(target));}limits.push('Дневной лимит: '+pct(product.daily_loss_pct_original)+' исходного капитала; сброс '+(product.daily_reset||'не установлен'));if(product.total_loss)limits.push('Общий лимит: '+pct(product.total_loss.pct_original)+' · '+(product.total_loss.type==='static'?'статический':'Trailing EOD balance'));if(product.min_opening_days)limits.push('Минимум '+num(product.min_opening_days.challenge,0)+' торговых дней на каждом этапе');if(product.best_day_rule)limits.push('Лучший день: '+pct(product.best_day_rule.pct)+' суммы net P&L прибыльных дней');terms.push('Точная цена аккаунта не установлена'+(product.advertised_entry_fee_from?'; рекламный минимум '+num(product.advertised_entry_fee_from.amount,0)+' '+product.advertised_entry_fee_from.currency:''));terms.push('Базовая доля выплаты: '+pct(product.payout_split_base_pct));}
const productSources=sources.filter(source=>(product.source_ids||[]).includes(source.id));
return '<article class="firm-review-product" data-review-product="'+esc(product.id)+'"><div>'+badge(product.id===candidate?.id?'ПРИОРИТЕТ ДОГОВОРА':'ДРУГОЙ СЦЕНАРИЙ','neutral')+'<h3>'+esc(product.firm)+'</h3><p>'+esc(product.product)+'</p></div><h4>Этапы и лимиты</h4><ul>'+limits.map(value=>'<li>'+esc(value)+'</li>').join('')+'</ul><h4>Стоимость и выплаты</h4><ul>'+terms.map(value=>'<li>'+esc(value)+'</li>').join('')+'</ul><details class="settings-details"><summary>Что не покрывает текущая модель ('+(product.model_gaps||[]).length+')</summary><ul class="reasons-list">'+(product.model_gaps||[]).map(gap=>'<li>'+esc(firmModelGaps[gap]||gap)+'</li>').join('')+'</ul></details><details class="settings-details"><summary>Источники продукта ('+productSources.length+')</summary><ul class="reasons-list">'+productSources.map(source=>'<li>'+officialSourceLink(source.final_url||source.requested_url,source.title||source.id)+'<small>'+esc(timestamp(source.retrieved_at))+' · SHA-256 '+esc(String(source.body_sha256||'').slice(0,12))+'</small></li>').join('')+'</ul></details></article>';
}).join('')+'</div>';
const important=['ftmo_swing_rules','ftmo_ea','ftmo_vps','topstep_automation_personal_device','topstep_automation_readonly_server'];
const summaries={ftmo_swing_rules:'Swing: новости, ночь и выходные разрешены с сохранением запретов торговых практик; сменить Standard на Swing после покупки нельзя.',ftmo_ea:'FTMO: EA разрешены условно. Применяются требования к риску, нагрузке и допустимым торговым практикам.',ftmo_vps:'FTMO: VPS/VPN обычно разрешены, но есть исключение для геолокации США на отдельных платформах.',topstep_automation_personal_device:'Topstep: заявки должны исходить с личного устройства; удалённый VPS/VPN/сервер для заявок запрещён.',topstep_automation_readonly_server:'Topstep: сервер может исследовать историю и вести журналы. Размещение, изменение, отмена и передача заявок с него запрещены.'};
html+='<details class="firm-review-evidence"><summary>Новости, алгоритмы и облачный запуск · выдержки источников</summary>'+facts.filter(fact=>important.includes(fact.id)).map(fact=>'<article><h4>'+esc(summaries[fact.id]||fact.claim)+'</h4><blockquote>'+esc(fact.supporting_quote)+'</blockquote><p>'+officialSourceLink(fact.source_url,'Официальный источник')+'</p></article>').join('')+'</details>';
if(data.unknowns?.length)html+='<details class="firm-review-evidence"><summary>Неразрешённые вопросы и противоречия ('+data.unknowns.length+')</summary><ul class="reasons-list">'+data.unknowns.map(item=>'<li><strong>'+esc(item.firm)+' · '+esc(item.id.replaceAll('_',' '))+'</strong><p>'+esc(item.detail)+'</p></li>').join('')+'</ul></details>';
html+='<p class="firm-review-footer">Документальная сводка не добавляет подтверждённые профили аккаунтов. <a href="/api/firms/review" target="_blank" rel="noopener noreferrer">Полный отчёт JSON ↗</a></p>';
$('#firm-review-output').innerHTML=html;$('#firm-review-output').hidden=false;
}
async function loadFirmReview(manual=false) {
const button=$('#load-firm-review');if(manual)busy(button,true,'Загружаем…');notice('firm-review-error','');
try{const response=await api('/api/firms/review');renderFirmReview(response.review||response);}
catch(e){notice('firm-review-error','Сводка официальных правил недоступна: '+e.message);}
finally{if(manual)busy(button,false);}
}
$('#load-firm-review').addEventListener('click',()=>loadFirmReview(true));
function selectProfile(id) {
const profile=itemById(state.profiles,id);if(!profile)return;
state.activeProfile=id;try{localStorage.setItem('prop-lab-profile',id);}catch{}
renderProfiles();
['active-profile-select','research-profile','check-profile','payout-profile','scanner-profile'].forEach(s=>{if($('#'+s))$('#'+s).value=id;});
if(!state.accountDirty){const form=$('#check-form');['balance','equity','day_start_balance','day_start_equity','high_water_equity'].forEach(n=>{form.elements.namedItem(n).value=profile.account_size;});}
$('#check-form').elements.namedItem('confirmed_rules').checked=false;invalidateCheck();
$('#research-account-size').value=profile.account_size;
}
function editProfile(id) {
const form=$('#profile-form');form.reset();const p=itemById(state.profiles,id);
if(p)Array.from(form.elements).forEach(el=>{if(!el.name||el.name==='verified')return;if(el.type==='checkbox')el.checked=p[el.name]===true;else if(el.name in p)el.value=p[el.name]??(el.type==='number'?0:'');});
form.elements.namedItem('verified').checked=false;
$('#profile-form-title').textContent=p?'Редактировать профиль':'Новый профиль';
notice('profile-message','');
}
function renderCatalog() {
$('#strategy-checkboxes').innerHTML=state.strategies.filter(s=>s.id!=='buy_hold').map(s=>'<label class="checkbox" title="'+esc(s.description)+'"><input type="checkbox" name="strategy_ids" value="'+esc(s.id)+'" checked><span>'+esc(s.name)+'</span></label>').join('')+'<p class="field-help">Buy & hold добавляется как ориентир автоматически.</p>';
$('#pine-strategy').innerHTML=state.strategies.map(s=>'<option value="'+esc(s.id)+'">'+esc(s.name)+'</option>').join('');
}
function chart(curve, initial, source) {
const points=(curve||[]).map((p,i)=>({equity:Number(typeof p==='number'?p:p.equity),time:typeof p==='object'?p.time:null,index:i})).filter(p=>Number.isFinite(p.equity));
if(points.length<2)return '<div class="empty-state">Недостаточно точек для графика.</div>';
const w=800,h=260,l=65,r=15,t=15,b=34;
let min=Math.min(...points.map(p=>p.equity),Number(initial)||points[0].equity),max=Math.max(...points.map(p=>p.equity),Number(initial)||points[0].equity);
const pad=(max-min)*.13||Math.max(Math.abs(min)*.01,1);min-=pad;max+=pad;
const x=i=>l+(w-l-r)*i/(points.length-1),y=v=>t+(h-t-b)*(max-v)/(max-min);
const path=points.map((p,i)=>(i===0?'M':'L')+x(i).toFixed(2)+' '+y(p.equity).toFixed(2)).join(' ');
let grid='';for(let i=0;i<5;i++){const v=min+(max-min)*i/4;const yy=y(v);grid+='<line class="grid-line" x1="'+l+'" y1="'+yy+'" x2="'+(w-r)+'" y2="'+yy+'"/><text x="'+(l-11)+'" y="'+(yy+3)+'" text-anchor="end">'+esc(num(v,0))+'</text>';}
const zero=Number(initial)||points[0].equity;
return '<svg class="equity-svg" viewBox="0 0 '+w+' '+h+'" role="img" aria-label="'+esc('Капитал на тестовой выборке: от '+money(points[0].equity)+' до '+money(points[points.length-1].equity)+(String(source).startsWith('demo')?'. Синтетические демо-данные.':''))+'"><defs><linearGradient id="equity-fill-'+esc(source||'chart')+'" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#b6f46f" stop-opacity=".16"/><stop offset="100%" stop-color="#b6f46f" stop-opacity="0"/></linearGradient></defs>'+grid+'<line class="zero-line" x1="'+l+'" x2="'+(w-r)+'" y1="'+y(zero)+'" y2="'+y(zero)+'"/><path d="'+path+' L'+x(points.length-1)+' '+(h-b)+' L'+l+' '+(h-b)+' Z" fill="url(#equity-fill-'+esc(source||'chart')+')"/><path class="equity-line" d="'+path+'"/><text x="'+l+'" y="'+(h-8)+'">'+esc(shortDate(points[0].time))+'</text><text x="'+(w-r)+'" y="'+(h-8)+'" text-anchor="end">'+esc(shortDate(points[points.length-1].time))+'</text>'+(String(source).startsWith('demo')?'<text x="'+(w/2)+'" y="'+(h/2)+'" text-anchor="middle" style="fill:#e8c180;opacity:.3;font-size:23px;letter-spacing:7px">SYNTHETIC DEMO</text>':'')+'</svg>';
}
function confidenceLabel(c) {return typeof c==='object'?({supported_sample:'Поддержано выборкой',fragile:'Неустойчиво',insufficient:'Мало данных'}[c.label]||c.label):String(c??'—');}
function renderStrategyTable() {
if(!state.research)return;const order=$('#strategy-sort').value;
const results=[...state.research.strategies].sort((a,b)=>order==='drawdown'?a.test_metrics.max_drawdown_pct-b.test_metrics.max_drawdown_pct:order==='confidence'?(b.confidence?.sample_size||0)-(a.confidence?.sample_size||0):b.test_metrics.net_return_pct-a.test_metrics.net_return_pct);
$('#strategies-table').innerHTML=results.map(s=>'<tr class="'+(s.id===state.detailId?'selected-row':'')+'"><td><button class="table-button" data-strategy="'+esc(s.id)+'">'+esc(s.name)+'</button><small>'+esc(s.training_winner?'Победитель обучения':s.baseline?'Ориентир':confidenceLabel(s.confidence))+'</small></td><td class="'+signClass(s.train_metrics.net_return_pct)+'">'+esc(pct(s.train_metrics.net_return_pct))+'</td><td class="'+signClass(s.test_metrics.net_return_pct)+'">'+esc(pct(s.test_metrics.net_return_pct))+'</td><td>'+esc(pct(s.test_metrics.max_drawdown_pct))+'</td><td>'+esc(num(s.test_metrics.total_trades,0))+'</td><td>'+badge(s.eligible?'Прошла отбор':s.baseline?'Ориентир':'Отклонена',s.eligible?'good':s.baseline?'neutral':'warning')+'</td></tr>').join('');
}
function renderStrategyDetail(id) {
const s=itemById(state.research?.strategies||[],id);if(!s)return;state.detailId=id;const m=s.test_metrics,wf=s.walk_forward||{},c=s.confidence||{},catalog=itemById(state.strategies,id)||{},replay=s.rule_replay;
let html='<div class="panel-header"><div><span class="eyebrow">ДЕТАЛИ ГИПОТЕЗЫ · ТЕСТ</span><h2>'+esc(s.name)+'</h2></div>'+badge(s.eligible?'ПРОШЛА ОТБОР':'ИССЛЕДОВАНИЕ',s.eligible?'good':'warning')+'</div><p class="detail-description">'+esc(catalog.description||'')+'</p><div class="inline-metrics">'+inlineMetric('Win rate',pct(m.win_rate))+inlineMetric('Profit factor',m.profit_factor===null?'—':num(m.profit_factor))+inlineMetric('Ожидание, R',num(m.expectancy_r,3),signClass(m.expectancy_r))+inlineMetric('Всего издержек',money(m.total_costs))+'</div><div class="strategy-chart">'+chart(s.equity_curve,m.initial_equity,state.research.data.source+'-detail')+'</div><p class="chart-caption">График показывает equity на закрытии; максимум просадки рассчитывается по худшей цене внутри каждой свечи. '+(s.equity_curve_thinned?'Точки графика прорежены, расчёт использует все свечи.':'')+'</p><div class="parameter-chips">'+Object.entries(s.params||{}).map(([k,v])=>'<span>'+esc(k)+' = '+esc(v)+'</span>').join('')+'</div>';
if(s.reasons?.length)html+='<h3>Почему стратегия не допущена</h3><ul class="reasons-list">'+s.reasons.map(r=>'<li>'+esc(translate(r))+'</li>').join('')+'</ul>';
html+='<h3 class="mini-table-title">Проверка устойчивости</h3><div class="inline-metrics">'+inlineMetric('Положительные окна',num(wf.positive_folds,0)+' / '+num(wf.fold_count,0))+inlineMetric('Средняя доходность окон',pct(wf.mean_net_return_pct),signClass(wf.mean_net_return_pct))+inlineMetric('Сделки walk-forward',num(wf.total_trades,0))+inlineMetric('95% интервал среднего R',c.mean_r_ci95?num(c.mean_r_ci95[0],3)+' … '+num(c.mean_r_ci95[1],3):'Мало данных')+'</div><p class="chart-caption">Окна walk-forward находятся до финального теста. Интервал — описательный moving-block bootstrap, не вероятность будущей прибыли.</p>';
if(replay){html+='<h3 class="mini-table-title">Воспроизведение правил на holdout</h3>'+badge({pass:'Лимиты не нарушены',breach:'Нарушение правил',incomplete:'Неполная проверка'}[replay.status]||replay.status,replay.status==='pass'?'good':replay.status==='breach'?'bad':'warning')+'<p class="chart-caption">Один тестовый счёт без сбросов между фазами. Это отдельная проверка истории, не симуляция будущих выплат.</p>';if(replay.reasons?.length)html+='<ul class="reasons-list">'+replay.reasons.slice(0,6).map(r=>'<li>'+esc(translate(r))+'</li>').join('')+'</ul>';if(replay.breaches?.length)html+='<p class="signal-warning">Первое нарушение: '+esc(typeof replay.breaches[0]==='string'?replay.breaches[0]:JSON.stringify(replay.breaches[0]))+'</p>';}
if(s.regime_metrics?.length)html+='<h3 class="mini-table-title">Режимы рынка · исследовательские срезы</h3><div class="table-scroll"><table><thead><tr><th>Режим</th><th>Сделки</th><th>P&amp;L</th><th>Ожидание R</th><th>Выборка</th></tr></thead><tbody>'+s.regime_metrics.map(r=>'<tr><td>'+esc({trend:'Тренд',range:'Диапазон',volatile:'Волатильность',transition:'Переход'}[r.regime]||r.regime)+'</td><td>'+esc(num(r.total_trades,0))+'</td><td class="'+signClass(r.net_profit)+'">'+esc(money(r.net_profit))+'</td><td>'+esc(num(r.expectancy_r,3))+'</td><td>'+badge(r.sufficient_sample?'≥ 20 сделок':'Мало данных',r.sufficient_sample?'neutral':'warning')+'</td></tr>').join('')+'</tbody></table></div><p class="chart-caption">Срезы помогают формулировать новые гипотезы. Автоматическое переключение стратегий по этим итогам не обучено и не проверено.</p>';
html+='<div class="signal-actions"><button class="button button-secondary" data-export-pine="'+esc(s.id)+'">Экспорт Pine ↓</button></div>';
$('#strategy-detail').innerHTML=html;renderStrategyTable();
}
function signalMarkup(signal, isDemo) {
if(!signal)return '<p class="signal-empty">План недоступен.</p>';
const hasPlan=['long','short'].includes(signal.direction)&&signal.stop!==null&&signal.target!==null;
let html='<div class="signal-header"><strong>'+esc(signal.symbol||'')+'</strong>'+badge(hasPlan?(signal.direction==='long'?'LONG / ПОКУПКА':'SHORT / ПРОДАЖА'):'ВНЕ РЫНКА',hasPlan?'neutral':'warning')+badge(isDemo?'СИНТЕТИЧЕСКИЙ ПРИМЕР':signal.status==='candidate'?'УСЛОВНЫЙ ПЛАН':'НЕ ПРОШЁЛ ОТБОР',isDemo?'warning':'neutral')+'</div><div class="signal-time">Последняя закрытая свеча: '+esc(timestamp(signal.reference_time))+'</div><p class="signal-reason">'+esc(translate(signal.reason))+'</p>';
if(hasPlan)html+='<div class="signal-grid"><div><small>Цена закрытия, не вход</small><strong>'+esc(num(signal.reference_price,5))+'</strong></div><div><small>Условный стоп</small><strong>'+esc(num(signal.stop,5))+'</strong></div><div><small>Условная цель</small><strong>'+esc(num(signal.target,5))+'</strong></div></div><div class="signal-warning">'+(isDemo?'DEMO: вымышленные цены. Используйте только для учебной проверки.':'План построен на последней строке CSV и не обновляется в реальном времени. Проверьте свежие цены; такой уровень входа может быть недоступен.')+'</div><button class="button button-secondary" data-use-signal>Проверить '+(isDemo?'учебный ':'')+'сценарий →</button>';
return html;
}
function renderPayout(payout) {
const p=payout||{};
$('#payout-metrics').innerHTML=inlineMetric('Ожидаемый net cash flow',money(p.net_expected_value),signClass(p.net_expected_value),'За одну попытку, после её стоимости')+inlineMetric('Вероятность отбора',p.challenge_pass_probability==null?'—':pct(p.challenge_pass_probability*100))+inlineMetric('Вероятность первой выплаты',p.payout_probability==null?'—':pct(p.payout_probability*100))+inlineMetric('Вероятность нарушения',p.breach_probability==null?'—':pct(p.breach_probability*100));
const notes=[...(p.reasons||[]),...(p.limitations||[])];if(p.status==='illustrative')notes.unshift('УЧЕБНАЯ МОДЕЛЬ: стратегия или правила не подтверждены. Положительный EV этого сценария не доказывает торговый edge.');
$('#payout-notes').innerHTML='<p>'+esc(p.feasible?'Модель одной попытки и первой выплаты. Вероятности относятся к заданной модели, не к будущему рынку.':'Нет допустимой оценки. Выберите стратегию и профиль; учебная модель требует отдельного подтверждения.')+'</p>'+notes.map(n=>'<p>'+esc(translate(n))+'</p>').join('')+(p.percentiles?.p50!==undefined?'<p>Net cash flow P10 / P50 / P90: '+esc(money(p.percentiles.p10))+' / '+esc(money(p.percentiles.p50))+' / '+esc(money(p.percentiles.p90))+'. Убытки номинального проп-счёта не считаются вашим личным долгом.</p>':'');
}
function renderResearch(result) {
if(result.data?.input_source==='reference'||result.data?.provenance?.historical_only===true)result.archived=true;
state.research=result;const s=result.summary||{},d=result.data||{},isDemo=d.source==='demo';
const display=itemById(result.strategies,result.selected_strategy||result.training_candidate)||result.strategies[0];
state.detailId=display?.id;
$('#research-empty').hidden=true;$('#research-output').hidden=false;$('#research-loading').hidden=true;
$('#research-data-banner').className='notice notice-'+(isDemo?'warning':'subtle');
const isYahoo=d.input_source==='yahoo'||d.provider==='Yahoo Finance';
$('#research-data-banner').innerHTML='<div><strong>'+esc(isDemo?'DEMO · СИНТЕТИЧЕСКИЕ ДАННЫЕ':result.archived?'АРХИВ · РЕАЛЬНАЯ ИСТОРИЯ, УСТАРЕВШИЕ КОТИРОВКИ':isYahoo?'YAHOO FINANCE · ПУБЛИЧНАЯ ИССЛЕДОВАТЕЛЬСКАЯ ИСТОРИЯ':'CSV · ПОЛЬЗОВАТЕЛЬСКАЯ ИСТОРИЯ')+'</strong><p>'+esc(d.symbol)+' · '+esc(num(d.bars,0))+' свечей · '+esc(timestamp(d.start))+' — '+esc(timestamp(d.end))+'<br>Обучение: '+esc(num(d.train_bars,0))+' · тест: '+esc(num(d.test_bars,0))+' · интервал: '+esc(num(d.timeframe_minutes,2))+' мин. · SHA-256 '+esc(String(d.hash||'').slice(0,12))+'</p></div>';
$('#research-warnings').innerHTML='<details class="settings-details"><summary>Методология и ограничения ('+(s.warnings||[]).length+')</summary><ul class="reasons-list">'+(s.warnings||[]).map(w=>'<li>'+esc(translate(w))+'</li>').join('')+'</ul></details>';
$('#research-verdict').textContent=isDemo?'Учебное исследование':result.selected_strategy?'Кандидат для бумажной проверки':'Устойчивый кандидат не найден';
$('#research-qualified-badge').className='badge badge-'+(result.selected_strategy?'good':'warning');
$('#research-qualified-badge').textContent=result.selected_strategy?'PAPER REVIEW':isDemo?'DEMO ONLY':'ВНЕ РЫНКА';
$('#research-summary').innerHTML=inlineMetric('Доходность на тесте',pct(s.net_return_pct),signClass(s.net_return_pct))+inlineMetric('Максимум просадки',pct(s.max_drawdown_pct))+inlineMetric('Итоговый капитал',money(s.final_equity))+inlineMetric('Прошли отбор',num(s.qualified_count,0)+' / '+result.strategies.filter(a=>!a.baseline).length);
$('#metric-return').textContent=pct(s.net_return_pct);$('#metric-return').className=signClass(s.net_return_pct);
$('#metric-return-note').textContent=isDemo?'DEMO · не рыночный результат':s.training_candidate_name||s.selected_name||'Ориентир на тесте';
$('#metric-drawdown').textContent=pct(s.max_drawdown_pct);$('#metric-qualified').textContent=num(s.qualified_count,0);
$('#equity-source').className='badge badge-'+(isDemo?'warning':'neutral');$('#equity-source').textContent=isDemo?'SYNTHETIC DEMO':d.symbol+' · CSV';
$('#equity-chart').innerHTML=display?chart(display.equity_curve,s.initial_equity,d.source):'<div class="empty-state">Нет кривой.</div>';
$('#equity-period').textContent=shortDate(d.holdout_start)+' — '+shortDate(d.end);
$('#next-action-title').textContent=isDemo?'Переходите к реальным данным':result.selected_strategy?'Проверьте риск сетапа':'Оставаться вне рынка — решение';
$('#next-action-text').textContent=isDemo?'Загрузите историю вашего брокера. На вымышленных свечах нельзя подтвердить торговое преимущество.':result.selected_strategy?'Исторический отбор пройден. Следующий этап — спецификация контракта, правила и независимый форвард-тест.':'Победитель обучения не подтвердил устойчивость. Новую гипотезу проверяйте на новой отложенной выборке.';
$('#research-signal').innerHTML=signalMarkup(result.latest_signal,isDemo);$('#dashboard-signal').className='';$('#dashboard-signal').innerHTML=signalMarkup(result.latest_signal,isDemo);
$('#payout-strategy').innerHTML=result.strategies.filter(x=>!x.baseline).map(x=>'<option value="'+esc(x.id)+'">'+esc(x.name)+(x.eligible?' · прошла отбор':' · исследование')+'</option>').join('');
$('#payout-strategy').value=result.selected_strategy||result.training_candidate||$('#payout-strategy').value;
$('#payout-illustrative').checked=false;
renderPayout(result.payout);renderFirmComparison(result.firm_comparison||[]);renderStrategyDetail(state.detailId);
refreshSetupResearch();
}
function renderCheck(result) {
const allowed=result.allowed===true,checks=result.rule_checks||{};
let html='<div class="check-result-hero '+(allowed?'':'blocked')+'"><span class="eyebrow">'+esc(result.decision||'BLOCK')+'</span><h2>'+(allowed?'Допустимо в бумажном сценарии':'Сделка заблокирована')+'</h2><p>'+(allowed?'Указанные параметры укладываются в проверяемые лимиты профиля.':'Исправьте причины ниже до повторной проверки.')+'</p></div>';
html+='<div class="inline-metrics">'+inlineMetric('Убыток до стопа + издержки',money(result.risk_amount),allowed?'':'negative')+inlineMetric('Риск от начального капитала',pct(result.risk_pct))+inlineMetric('Запас дневного лимита',money(result.daily_remaining))+inlineMetric('Запас общего лимита',money(result.total_remaining))+'</div>';
html+='<div class="risk-budget"><div class="risk-budget-header"><span>Доступный бюджет новой сделки</span><strong>'+esc(money(result.effective_budget))+'</strong></div><div class="budget-track"><span style="width:'+Math.min(100,Math.max(0,Number(result.risk_amount||0)/Math.max(1,Number(result.effective_budget||0))*100))+'%"></span></div><p class="chart-caption">После открытого риска, резерва и индивидуального лимита сделки.</p><div class="profile-mini-row"><span>Максимальный безопасный объём</span><strong>'+esc(num(result.max_safe_quantity,6))+'</strong></div></div>';
if(result.reasons?.length)html+='<h3>Причины блокировки</h3><ul class="reasons-list">'+result.reasons.map(r=>'<li>'+esc(translate(r))+'</li>').join('')+'</ul>';
html+='<h3>Проверяемые ограничения</h3><div class="check-rules">'+[['rules_confirmed','Актуальные правила подтверждены'],['news_allowed','Окно новостей'],['overnight_allowed','Перенос через ночь'],['weekend_allowed','Выходные'],['ea_allowed','Алгоритмический вход']].map(([k,label])=>{const v=checks[k];const pass=typeof v==='object'?!v.requested||v.allowed===true:v===true;const text=typeof v==='object'?v.requested?(v.allowed===true?'Допустимо':'ЗАПРЕЩЕНО'):'Не запрошено':pass?'Подтверждены':'Нет подтверждения';return '<div class="check-rule"><span>'+esc(label)+'</span><span class="'+(pass?'':'failed')+'">'+esc(text)+'</span></div>';}).join('')+'</div>';
if(result.warnings?.length)html+='<h3 class="mini-table-title">Что ещё проверить</h3><ul class="reasons-list">'+result.warnings.map(w=>'<li>'+esc(translate(w))+'</li>').join('')+'</ul>';
html+='<details class="settings-details"><summary>Подробности расчёта</summary><pre class="code-block">'+esc(JSON.stringify(checks,null,2))+'</pre></details>';
$('#check-result').className='panel';$('#check-result').innerHTML=html+'<p class="chart-caption">Проверка '+esc(timestamp(new Date().toISOString()))+' · только для параметров этого снимка аккаунта.</p>';state.checkFresh=true;
}
function renderJournal(journal) {
state.journal=journal;const trades=journal.trades||[],s=journal.stats||{};
$('#metric-journal').textContent=num(s.total_trades??trades.length,0);$('#metric-journal-note').textContent=trades.length?'Дисциплина: '+pct(s.discipline_pct):'Начните с первой записи';
$('#journal-metrics').innerHTML=[['Итоговый P&L',money(s.net_pnl??0),'Издержки учтены',signClass(s.net_pnl)],['Доля прибыльных',trades.length?pct(s.win_rate):'—','Только закрытые записи',''],['Ожидание, R',trades.length?num(s.expectancy_r,3):'—','P&L / начальный риск',signClass(s.expectancy_r)],['Дисциплина',trades.length?pct(s.discipline_pct):'—','Сделки по плану','']].map(([label,val,note,cls])=>'<article class="metric-card"><div class="metric-label">'+esc(label)+'</div><strong class="'+cls+'">'+esc(val)+'</strong><small>'+esc(note)+'</small></article>').join('');
$('#journal-empty').hidden=trades.length>0;
$('#journal-table').innerHTML=trades.map(t=>'<tr><td><button class="table-button" data-trade="'+esc(t.id)+'">'+esc(t.symbol)+'</button><small>'+esc(timestamp(t.closed_at))+'</small></td><td>'+esc(t.strategy||'—')+'</td><td>'+badge(t.side==='long'?'LONG':'SHORT')+'</td><td class="'+signClass(t.pnl)+'">'+esc(money(t.pnl))+'<small>'+esc(num(t.return_r,2))+' R</small></td><td>'+badge(t.setup_followed?'По плану':'Нарушен план',t.setup_followed?'good':'warning')+'</td><td><button class="delete-trade" data-delete-trade="'+esc(t.id)+'" aria-label="'+esc('Удалить запись '+t.symbol)+'" title="Удалить запись">×</button></td></tr>').join('');
}
function journalDetail(id) {
const t=itemById(state.journal.trades,id);if(!t)return;
$('#journal-detail').hidden=false;$('#journal-detail').className='journal-detail';
$('#journal-detail').innerHTML='<div class="panel-header"><h3>'+esc(t.symbol)+' · '+esc(t.strategy)+'</h3><button class="text-button" data-close-trade>Закрыть ×</button></div><p>'+esc(t.notes||'Без заметок')+'</p><div class="parameter-chips">'+[['Вход',t.entry],['Выход',t.exit],['Стоп',t.stop],['Объём',t.quantity],['Множитель',t.contract_multiplier],['Издержки',t.fees]].map(([k,v])=>'<span>'+esc(k)+': '+esc(num(v,5))+'</span>').join('')+'</div><p>Состояние: '+esc({calm:'спокойствие',fear:'страх',fomo:'FOMO',revenge:'реванш',overconfidence:'излишняя уверенность'}[t.emotion]||t.emotion)+'. Открыта '+esc(timestamp(t.opened_at))+'.</p>';
}
function updateCsvPreview() {
const text=$('#csv-text').value.trim();const rows=text?text.split(/\r?\n/).filter(s=>s.trim()).length-1:0;
$('#csv-preview').textContent=rows?'Примерно '+rows+' строк данных. Сервер проверит заголовок, порядок времени и геометрию каждой свечи.':'Заголовок: timestamp, open, high, low, close, volume. UTC (Z/+00:00), минимум 300 свечей по возрастанию времени.';
}
function setJournalDates() {
const format=date=>{const offset=date.getTimezoneOffset();return new Date(date.getTime()-offset*60000).toISOString().slice(0,16);};
$('#journal-form').elements.namedItem('opened_at').value=format(new Date(Date.now()-3600000));
$('#journal-form').elements.namedItem('closed_at').value=format(new Date());
}
async function exportPine(id) {
const button=$('#pine-download');busy(button,true,'Готовим шаблон…');notice('pine-message','');
try{const response=await fetch('/api/export/pine?strategy_id='+encodeURIComponent(id));if(!response.ok){const error=await response.json();throw new Error(error.error||'Экспорт недоступен для этой стратегии.');}const blob=await response.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=id+'.pine';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),5000);toast('Pine-шаблон скачан. Проверьте настройки в Strategy Tester.');}catch(e){notice('pine-message',e.message);toast(e.message);}finally{busy(button,false);}
}
function useSignal() {
const signal=state.research?.latest_signal;if(!signal||!['long','short'].includes(signal.direction))return;
const form=$('#check-form');form.elements.namedItem('side').value=signal.direction;form.elements.namedItem('entry').value=signal.reference_price;form.elements.namedItem('stop').value=signal.stop;form.elements.namedItem('target').value=signal.target;form.elements.namedItem('contract_multiplier').value=state.research.config?.contract_multiplier||1;form.elements.namedItem('risk_pct').value=state.research.config?.risk_pct||0.25;['fee_bps','spread_bps','slippage_bps','fee_per_unit'].forEach(k=>{form.elements.namedItem(k).value=state.research.config?.[k]||0;});form.elements.namedItem('confirmed_rules').checked=false;invalidateCheck();
navigate('checker');toast(state.research.data.source==='demo'?'Перенесён учебный сценарий с вымышленными ценами.':'Перенесён исторический сценарий. Обновите вход по свежей котировке.');
$('#check-form').elements.namedItem('entry').focus();
}
document.addEventListener('click',async event=>{
const button=event.target.closest('button');if(!button)return;
if(button.dataset.tab)navigate(button.dataset.tab);
if(button.dataset.go)navigate(button.dataset.go);
if(button.dataset.selectProfile){selectProfile(button.dataset.selectProfile);toast('Рабочий профиль выбран. Правила требуют подтверждения.');}
if(button.dataset.editProfile){editProfile(button.dataset.editProfile);$('#profile-form').elements.namedItem('name').focus();}
if(button.dataset.strategy)renderStrategyDetail(button.dataset.strategy);
if(button.dataset.trade)journalDetail(button.dataset.trade);
if(button.hasAttribute('data-close-trade'))$('#journal-detail').hidden=true;
if(button.hasAttribute('data-use-signal'))useSignal();
if(button.dataset.exportPine){$('#pine-strategy').value=button.dataset.exportPine;await exportPine(button.dataset.exportPine);}
if(button.dataset.deleteTrade){if(!confirm('Удалить запись из локального дневника?'))return;busy(button,true,'…');try{const data=await api('/api/journal/'+encodeURIComponent(button.dataset.deleteTrade),{method:'DELETE'});if(data.trades)renderJournal(data);else renderJournal(await api('/api/journal'));$('#journal-detail').hidden=true;toast('Запись удалена.');}catch(e){toast(e.message);busy(button,false);}}
});
$('#research-form').addEventListener('submit',async event=>{
event.preventDefault();const form=event.currentTarget,source=fields(form).source,button=$('#research-submit');notice('research-error','');
const strategy_ids=$$('input[name="strategy_ids"]:checked',form).map(el=>el.value);if(!strategy_ids.length){notice('research-error','Выберите хотя бы одну стратегию.');return;}
const config={};['account_size','risk_pct','fee_bps','spread_bps','slippage_bps','contract_multiplier','max_leverage','quantity_step','fee_per_unit','max_drawdown_pct'].forEach(k=>{if(form.elements.namedItem(k))config[k]=numeric(form,k);});config.train_fraction=numeric(form,'train_pct')/100;config.strategy_ids=strategy_ids;
const symbol=source==='csv'?$('#csv-symbol').value.trim().toUpperCase():source==='yahoo'?($('#yahoo-symbol').value.trim().toUpperCase()||form.elements.namedItem('symbol').value):form.elements.namedItem('symbol').value;
if(!symbol){notice('research-error','Укажите обозначение вашего инструмента.');return;}
if(source==='csv'&&!$('#csv-text').value.trim()){notice('research-error','Загрузите CSV или вставьте историю котировок.');return;}
busy(button,true,'Исследование…');form.setAttribute('aria-busy','true');$('#research-empty').hidden=true;$('#research-output').hidden=true;$('#research-loading').hidden=false;
try{const result=await post('/api/research',{source,symbol,profile_id:form.elements.namedItem('profile_id').value,csv_text:source==='csv'?$('#csv-text').value:undefined,interval:source==='yahoo'?$('#yahoo-interval').value:undefined,range:source==='yahoo'?$('#yahoo-range').value:undefined,config});renderResearch(result);toast('Исследование завершено. Изучите ограничения и причины отбора.');}
catch(e){notice('research-error',e.message);$('#research-loading').hidden=true;if(state.research)$('#research-output').hidden=false;else $('#research-empty').hidden=false;}
finally{busy(button,false);form.removeAttribute('aria-busy');}
});
$$('input[name="source"]').forEach(el=>el.addEventListener('change',()=>{const csv=el.value==='csv',yahoo=el.value==='yahoo';$('#csv-controls').hidden=!csv;$('#yahoo-controls').hidden=!yahoo;$('#demo-description').hidden=csv||yahoo;$('#research-symbol').disabled=csv;}));
$('#yahoo-interval').addEventListener('change',()=>{const hourly=$('#yahoo-interval').value==='1h';$$('option',$('#yahoo-range')).forEach(option=>{option.disabled=hourly?option.value!=='3mo':option.value==='3mo';});$('#yahoo-range').value=hourly?'3mo':'2y';});
$('#csv-file').addEventListener('change',async event=>{const file=event.target.files[0];if(!file)return;if(file.size>4*1024*1024){notice('research-error','Файл превышает 4 МБ. Уменьшите период истории.');return;}try{$('#csv-text').value=await file.text();updateCsvPreview();notice('research-error','');}catch{notice('research-error','Не удалось прочитать файл. Вставьте CSV в поле истории.');}});
$('#csv-text').addEventListener('input',updateCsvPreview);
$('#strategy-sort').addEventListener('change',renderStrategyTable);
$('#active-profile-select').addEventListener('change',e=>selectProfile(e.target.value));
$('#check-profile').addEventListener('change',e=>selectProfile(e.target.value));
$('#research-profile').addEventListener('change',e=>selectProfile(e.target.value));
$('#scanner-profile').addEventListener('change',e=>selectProfile(e.target.value));
$('#new-profile').addEventListener('click',()=>{editProfile(null);$('#profile-form').elements.namedItem('name').focus();});
$('#profile-form').addEventListener('submit',async event=>{
event.preventDefault();const form=event.currentTarget,button=$('#profile-submit'),data=fields(form);notice('profile-message','');
['account_size','challenge_fee','profit_target_pct','daily_loss_pct','max_loss_pct','payout_split_pct','min_trading_days','max_calendar_days','best_day_pct','max_risk_pct','risk_buffer_amount','quantity_step'].forEach(k=>{data[k]=numeric(form,k);});
['news_allowed','overnight_allowed','weekend_allowed','ea_allowed','trailing_cap_at_initial','challenge_required'].forEach(k=>{data[k]=checked(form,k);});
data.id=data.id||'custom-'+Date.now();data.max_calendar_days=data.max_calendar_days||null;data.best_day_pct=data.best_day_pct||null;
const verified=checked(form,'verified');delete data.verified;data.status=verified?'user_verified':'illustrative';data.verified_at=verified?new Date().toISOString():null;
if(verified&&!data.source_url){notice('profile-message','Добавьте ссылку на источник действующих правил.');return;}
busy(button,true,'Сохранение…');try{const result=await post('/api/profiles',data);state.profiles=result.profiles||[...state.profiles.filter(p=>p.id!==result.profile.id),result.profile];selectProfile(result.profile.id);editProfile(result.profile.id);notice('profile-message','Профиль сохранён. Подтверждайте актуальность перед каждой проверкой.','success');toast('Профиль сохранён.');}catch(e){notice('profile-message',e.message);}finally{busy(button,false);}
});
$('#check-form').addEventListener('input',event=>{invalidateCheck();if(['balance','equity','day_start_balance','day_start_equity','high_water_equity','open_risk'].includes(event.target.name))state.accountDirty=true;});
$('#check-form').addEventListener('submit',async event=>{
event.preventDefault();const form=event.currentTarget,button=$('#check-submit'),account={},trade={};notice('check-error','');
['balance','equity','day_start_balance','day_start_equity','high_water_equity','open_risk'].forEach(k=>account[k]=numeric(form,k));account.confirmed_rules=checked(form,'confirmed_rules');
['entry','stop','target','quantity','contract_multiplier','fee_bps','spread_bps','slippage_bps','risk_pct','fee_per_unit'].forEach(k=>trade[k]=numeric(form,k));
['news_window','hold_overnight','hold_weekend','is_automated'].forEach(k=>trade[k]=checked(form,k));trade.side=form.elements.namedItem('side').value;
busy(button,true,'Проверяем…');try{renderCheck(await post('/api/check',{profile_id:form.elements.namedItem('profile_id').value,account,trade}));toast('Проверка завершена. Это бумажный сценарий.');}catch(e){notice('check-error',e.message);}finally{busy(button,false);}
});
$('#journal-form').addEventListener('submit',async event=>{
event.preventDefault();const form=event.currentTarget,button=$('#journal-submit'),data=fields(form);notice('journal-message','');
['entry','exit','stop','quantity','contract_multiplier','fees'].forEach(k=>data[k]=numeric(form,k));data.setup_followed=checked(form,'setup_followed');
try{data.opened_at=new Date(data.opened_at).toISOString();data.closed_at=new Date(data.closed_at).toISOString();}catch{notice('journal-message','Проверьте даты открытия и закрытия.');return;}
if(new Date(data.closed_at)<new Date(data.opened_at)){notice('journal-message','Закрытие не может предшествовать открытию.');return;}
busy(button,true,'Сохранение…');try{const result=await post('/api/journal',data);renderJournal(result.trades?result:await api('/api/journal'));notice('journal-message','Сделка сохранена в локальном дневнике.','success');toast('Запись добавлена.');form.elements.namedItem('notes').value='';['entry','exit','stop'].forEach(k=>form.elements.namedItem(k).value='');setJournalDates();}catch(e){notice('journal-message',e.message);}finally{busy(button,false);}
});
$('#pine-download').addEventListener('click',()=>exportPine($('#pine-strategy').value));
$('#payout-submit').addEventListener('click',async()=>{
const button=$('#payout-submit');notice('payout-error','');const illustrative=$('#payout-illustrative').checked;
if(!state.research)return;
const strategy=itemById(state.research.strategies,$('#payout-strategy').value);
if(!strategy?.eligible&&!illustrative){notice('payout-error','Стратегия не прошла отбор. Для учебного примера отдельно подтвердите учебную симуляцию.');return;}
busy(button,true,'Симуляция…');try{const result=await post('/api/payout',{strategy_id:strategy.id,profile_id:$('#payout-profile').value,config:{allow_illustrative:illustrative,paths:300,risk_pct:Math.min(state.research.config.risk_pct,itemById(state.profiles,$('#payout-profile').value)?.max_risk_pct||1)}});renderPayout(result.payout||result);toast('Сценарий рассчитан. Результат зависит от предпосылок модели.');}catch(e){notice('payout-error',e.message);}finally{busy(button,false);}
});

function invalidateCheck() {
if(!state.checkFresh)return;
state.checkFresh=false;
$('#check-result').className='panel checker-empty';
$('#check-result').innerHTML='<div class="large-glyph">↻</div><span class="eyebrow">ПАРАМЕТРЫ ИЗМЕНЕНЫ</span><h2>Проверьте сделку заново</h2><p>Предыдущая проверка больше не относится к текущим параметрам. Обновите снимок аккаунта и нажмите «Проверить риск».</p>';
}
function renderFirmComparison(rows) {
if(!rows.length){$('#firm-comparison').innerHTML='<p class="field-help">Сравнение появится, когда победитель обучения пройдёт отбор на CSV. Все профили используют одну и ту же тестовую историю; учебные правила остаются неподтверждёнными.</p>';return;}
$('#firm-comparison').innerHTML='<div class="table-scroll"><table><thead><tr><th>Профиль</th><th>Ожидаемый net</th><th>Первая выплата</th><th>Нарушение</th><th>Основание</th></tr></thead><tbody>'+[...rows].sort((a,b)=>(b.net_expected_value??-Infinity)-(a.net_expected_value??-Infinity)).map(r=>'<tr><td>'+esc(r.name)+'</td><td class="'+signClass(r.net_expected_value)+'">'+esc(money(r.net_expected_value))+'</td><td>'+esc(r.payout_probability==null?'—':pct(r.payout_probability*100))+'</td><td>'+esc(r.breach_probability==null?'—':pct(r.breach_probability*100))+'</td><td>'+badge(r.status==='illustrative'?'Учебный':r.feasible?'Модель':'Недостаточно данных',r.status==='illustrative'?'warning':'neutral')+'</td></tr>').join('')+'</tbody></table></div><p class="chart-caption">Ожидаемый личный денежный результат одной попытки после её стоимости. Различия договоров и реальное исполнение могут изменить оценку.</p>';
}
async function loadSignals() {
const button=$('#refresh-signals');busy(button,true,'Обновление…');
try{const data=await api('/api/signals');const signals=data.signals||[];$('#signal-inbox-list').innerHTML=signals.length?'<div class="table-scroll"><table><thead><tr><th>Актив</th><th>Направление</th><th>Стратегия</th><th>Время</th><th>Статус</th></tr></thead><tbody>'+signals.map(s=>'<tr><td>'+esc(s.symbol||'—')+'</td><td>'+esc(s.side||s.direction||'—')+'</td><td>'+esc(s.strategy||s.strategy_id||'—')+'</td><td>'+esc(timestamp(s.time||s.timestamp||s.received_at||s.created_at))+'</td><td>'+badge('Входящее · без заявки','neutral')+'</td></tr>').join('')+'</tbody></table></div>':'<div class="empty-state compact"><p>Входящих событий пока нет. Можно работать с лабораторией и дневником без подключения webhook.</p></div>';
}catch(e){$('#signal-inbox-list').textContent=e.message;}finally{busy(button,false);}
}
$('#refresh-signals').addEventListener('click',loadSignals);

const localDateInput=date=>new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16);
const price=value=>value===null||value===undefined?'—':num(value,Math.abs(Number(value))<1?6:Math.abs(Number(value))<10?5:Math.abs(Number(value))<100?3:2);
const macroLabels={unknown:'Не определён',expansion:'Рост',slowdown:'Замедление',recession:'Рецессия',recovery:'Восстановление'};
function refreshSetupResearch() {
state.setup=null;$('#setup-output').hidden=true;$('#setup-empty').hidden=false;
if(!state.research)return;
const data=state.research.data||{},name=state.research.selected_strategy||state.research.training_candidate;
$('#setup-data-note').className='notice notice-'+(data.source==='demo'?'warning':'subtle');
$('#setup-data-note').innerHTML='<p><strong>'+esc(data.symbol||'История')+'</strong> · '+esc(data.source==='demo'?'Синтетические данные':state.research.archived?'Архивная история · устаревшие котировки':data.input_source==='yahoo'?'Yahoo Finance · публичная история':'Ваша CSV-история')+'<br>Последняя свеча: '+esc(timestamp(data.end))+'<br>'+esc(name?'Кандидат: '+(itemById(state.strategies,name)?.name||name):'Стратегия не прошла отбор')+'</p><button type="button" class="text-button" data-go="lab">Обновить исследование →</button>';
}
function addNewsEvent() {
const row=document.createElement('div');row.className='news-event';
row.innerHTML='<div class="news-event-heading"><strong>Событие календаря</strong><button type="button" class="text-button" data-remove-news aria-label="Удалить событие">×</button></div><label class="field">Название<input data-event="title" type="text" maxlength="300" placeholder="Например решение по ставке" required></label><div class="field-row"><label class="field">Влияние<select data-event="impact"><option value="high">Высокое</option><option value="medium">Среднее</option><option value="low">Низкое</option></select></label><label class="field">Валюта / рынок<input data-event="currency" type="text" maxlength="16" placeholder="USD" required></label></div><label class="field">Время публикации<input data-event="time" type="datetime-local" required></label><label class="field">Когда событие было известно<input data-event="known_at" type="datetime-local" required></label>';
const now=localDateInput(new Date());$('[data-event="time"]',row).value=now;$('[data-event="known_at"]',row).value=now;
$('#setup-news-events').append(row);invalidateSetup();$('[data-event="title"]',row).focus();
}
function invalidateSetup() {
if(!state.setup)return;
state.setup=null;$('#setup-output').hidden=true;$('#setup-empty').hidden=false;
notice('setup-error','Контекст изменился. Рассчитайте зоны заново.','warning');
}
function setupReasons(items) {return (Array.isArray(items)?items:[]).map(item=>'<li>'+esc(translate(typeof item==='string'?item:JSON.stringify(item)))+'</li>').join('');}
function zoneCard(label,zone,tone,detail='') {
let value='—';
if(typeof zone==='number')value=price(zone);
else if(zone&&Number.isFinite(Number(zone.low))&&Number.isFinite(Number(zone.high))&&zone.low!==null&&zone.high!==null)value=price(zone.low)+' … '+price(zone.high);
return '<article class="price-zone price-zone-'+tone+'"><small>'+esc(label)+'</small><strong>'+esc(value)+'</strong><p>'+esc(value==='—'?(tone==='entry'&&detail?detail:'Ценовой уровень пока не рассчитан'):detail)+'</p></article>';
}
function renderSetup(plan) {
state.setup=plan;$('#setup-empty').hidden=true;$('#setup-output').hidden=false;
const status=plan.status,label={wait:'Ждём условия',blocked:'План заблокирован',paper_review:'Кандидат для бумажной проверки'}[status]||'Исследовательский план',context=plan.context||{};
const hasZones=plan.entry_zone&&plan.stop_loss!==null&&plan.stop_loss!==undefined&&plan.take_profit_zone;
const regime=typeof context.regime==='object'?context.regime?.label||context.regime?.regime:context.regime;
const news=typeof context.news_state==='object'?context.news_state?.state||context.news_state?.status:context.news_state;
const sentiment=context.sentiment;
const sentimentLabel=sentiment&&typeof sentiment==='object'?(sentiment.state==='manual_confirmed'&&sentiment.score!==null?'Ручная оценка '+num(sentiment.score,1):{unknown:'Неизвестно',unconfirmed:'Не подтверждено',stale:'Оценка устарела',future_not_known:'Ещё не была доступна'}[sentiment.state]||'Не подтверждено'):typeof sentiment==='number'?num(sentiment,1):String(sentiment||'Неизвестно');
const entryTrigger=plan.entry_zone?.trigger,triggerText=typeof entryTrigger==='number'?'Триггер: '+price(entryTrigger):entryTrigger?translate(entryTrigger):'Вход только при выполнении условий';
let html='<article class="panel setup-plan"><div class="panel-header"><div><span class="eyebrow">'+esc(plan.symbol||'ПЛАН СЕТАПА')+' · '+esc(plan.strategy_id||'СТРАТЕГИЯ НЕ ВЫБРАНА')+'</span><h2>'+esc(label)+'</h2></div>'+badge(status==='paper_review'?'PAPER REVIEW':status==='blocked'?'БЛОК':'ОЖИДАНИЕ',status==='paper_review'?'good':'warning')+'</div>';
html+='<div class="setup-context-chips">'+badge(['long','short'].includes(plan.direction)?plan.direction.toUpperCase():'ВНЕ РЫНКА')+badge('Режим: '+({trend:'тренд',range:'диапазон',volatile:'волатильность',transition:'переход'}[regime]||regime||'не определён'))+badge('Макро: '+(macroLabels[context.macro_cycle]||'не определён'))+'</div>';
html+='<div class="setup-time"><span>Свеча: '+esc(timestamp(plan.reference_time))+'</span><span>Срок плана: '+esc(timestamp(plan.expires_at))+'</span></div>';
html+='<div class="price-zones">'+zoneCard('Зона входа',plan.entry_zone,'entry',triggerText)+zoneCard('Стоп-лосс',plan.stop_loss,'stop','Граница сценария; гэп может увеличить убыток')+zoneCard('Зона фиксации прибыли',plan.take_profit_zone,'target',plan.take_profit_zone?.target!==undefined?'Основная цель: '+price(plan.take_profit_zone.target):'Условная цель по модели')+zoneCard('Зона отмены идеи',plan.invalidation_zone,'cancel','При нарушении условия не открывайте сценарий')+'</div>';
if(plan.rr!==null&&plan.rr!==undefined)html+='<p class="chart-caption">R:R по уровням: '+esc(num(plan.rr))+' · фактические издержки и риск проверьте отдельно.</p>';
html+='<div class="setup-context-summary"><div><small>Настроение</small><strong>'+esc(sentimentLabel)+'</strong></div><div><small>Календарь'+(context.news_generation==='provider'?' · публичный снимок':context.news_generation==='manual'?' · ручной':'')+'</small><strong>'+esc({clear:'Нет событий в окне',checked_no_blackout:'Проверен · нет окна новостей',blackout:'Важное событие в окне',blocked:'Событие в опасном окне',unknown:'Не проверен',unconfirmed:'Не подтверждён'}[news]||news||'Не проверен')+'</strong></div></div>';
if(plan.reasons?.length)html+='<h3 class="mini-table-title">Почему это решение</h3><ul class="reasons-list">'+setupReasons(plan.reasons)+'</ul>';
if(plan.invalidation_conditions?.length)html+='<h3 class="mini-table-title">Когда отменить идею</h3><ul class="reasons-list">'+setupReasons(plan.invalidation_conditions)+'</ul>';
if(plan.warnings?.length)html+='<details class="settings-details" open><summary>Что учитывать перед проверкой</summary><ul class="reasons-list">'+setupReasons(plan.warnings)+'</ul></details>';
if(context.sources){const sources=Array.isArray(context.sources)?context.sources:Object.entries(context.sources).map(([key,value])=>key+': '+(typeof value==='object'?JSON.stringify(value):value));if(sources.length)html+='<details class="settings-details"><summary>Источники контекста</summary><ul class="reasons-list">'+sources.map(source=>'<li>'+esc(typeof source==='string'?source:JSON.stringify(source))+'</li>').join('')+'</ul></details>';}
if(status==='paper_review'&&hasZones&&['long','short'].includes(plan.direction))html+='<div class="setup-transfer"><label class="field">Ваша актуальная цена входа<input id="setup-actual-entry" type="number" min="0.00000001" step="any" placeholder="Введите цену из своей платформы"></label><button class="button button-secondary" data-check-setup>Проверить риск по своей цене <span>→</span></button><p class="field-help">Цена должна находиться в зоне входа. Чекер отдельно потребует актуальные цифры аккаунта и подтверждение правил.</p></div>';
html+='<p class="signal-warning">Условный план по истории. Он не отправляет заявку и не подтверждает доступность этих цен у брокера.</p></article>';
$('#setup-output').innerHTML=html;
}
function useContextSetup() {
const plan=state.setup;if(!plan||plan.status!=='paper_review'||!['long','short'].includes(plan.direction))return;
const entry=Number($('#setup-actual-entry')?.value),low=Number(plan.entry_zone?.low),high=Number(plan.entry_zone?.high);
if(!Number.isFinite(entry)||entry<=0||entry<low||entry>high){notice('setup-error','Введите актуальную цену внутри рассчитанной зоны входа.');$('#setup-actual-entry')?.focus();return;}
if(plan.expires_at&&new Date(plan.expires_at).getTime()<=Date.now()){notice('setup-error','Срок плана истёк. Обновите историю и пересчитайте сетап.');return;}
const target=plan.take_profit_zone?.target??(plan.direction==='long'?plan.take_profit_zone?.low:plan.take_profit_zone?.high),form=$('#check-form'),config=state.research?.config||{};
form.elements.namedItem('side').value=plan.direction;form.elements.namedItem('entry').value=entry;form.elements.namedItem('stop').value=plan.stop_loss;form.elements.namedItem('target').value=target;
form.elements.namedItem('contract_multiplier').value=config.contract_multiplier||1;form.elements.namedItem('risk_pct').value=config.risk_pct||0.25;
['fee_bps','spread_bps','slippage_bps','fee_per_unit'].forEach(key=>{form.elements.namedItem(key).value=config[key]||0;});
form.elements.namedItem('confirmed_rules').checked=false;invalidateCheck();navigate('checker');toast('Условный план перенесён. Подтвердите актуальный риск и правила аккаунта.');
}
$('#add-news-event').addEventListener('click',addNewsEvent);
$('#setup-form').addEventListener('input',invalidateSetup);
$('#setup-form').addEventListener('change',invalidateSetup);
document.addEventListener('click',async event=>{const remove=event.target.closest('[data-remove-news]');if(remove){remove.closest('.news-event').remove();invalidateSetup();}if(event.target.closest('[data-check-setup]'))useContextSetup();const reference=event.target.closest('[data-research-reference]');if(reference)await researchReference(reference);});
$('#setup-form').addEventListener('submit',async event=>{
event.preventDefault();const form=event.currentTarget,button=$('#setup-submit');notice('setup-error','');
try{
const sentimentConfirmed=checked(form,'sentiment_confirmed'),newsConfirmed=checked(form,'news_confirmed'),source=form.elements.namedItem('sentiment_source').value.trim(),observed=form.elements.namedItem('sentiment_observed_at').value,newsSource=form.elements.namedItem('news_source').value.trim(),newsObserved=form.elements.namedItem('news_observed_at').value;
if(sentimentConfirmed&&(!source||!observed))throw new Error('Для подтверждённого настроения нужны источник и время, когда оценка была доступна.');
if(newsConfirmed&&(!newsSource||!newsObserved))throw new Error('Для подтверждённого календаря нужны источник и время проверки.');
const score=numeric(form,'sentiment_score');if(!Number.isFinite(score)||score<-1||score>1)throw new Error('Оценка настроения должна быть от −1 до +1.');
const context={macro_cycle:form.elements.namedItem('macro_cycle').value,sentiment:observed?{score,observed_at:new Date(observed).toISOString(),source,confirmed:sentimentConfirmed}:{},news:{confirmed:newsConfirmed,source:newsSource,observed_at:newsObserved?new Date(newsObserved).toISOString():null,events:$$('.news-event').map(row=>Object.fromEntries(['title','currency','impact','time','known_at'].map(key=>{const value=$('[data-event="'+key+'"]',row).value;return [key,['time','known_at'].includes(key)?new Date(value).toISOString():value.trim()];})))}};
if(!newsConfirmed&&!newsSource&&!newsObserved&&!context.news.events.length)delete context.news;
busy(button,true,'Проверяем контекст…');form.setAttribute('aria-busy','true');const response=await post('/api/setups',{context});renderSetup(response.setup||response);toast('Условный план рассчитан. Проверьте причины решения.');
}catch(e){notice('setup-error',e instanceof RangeError?'Проверьте время новостей и оценки настроения.':e.message);}
finally{busy(button,false);form.removeAttribute('aria-busy');}
});
async function loadReferenceReports() {
const button=$('#load-reference');busy(button,true,'Загружаем архив…');notice('reference-message','');
try{
const data=await api('/api/research/reference'),reports=data.reports||[];$('#reference-results').hidden=false;
notice('reference-message',data.notice||'Архив исследовательских результатов. Это исторические проверки, текущие сигналы из них не создаются.','subtle');
const limitations=Array.isArray(data.limitations)?data.limitations:[],config=data.fixed_config||{};
const archiveNotes=limitations.length?'<details class="settings-details"><summary>Источники, издержки и ограничения исследования</summary><ul class="reasons-list">'+setupReasons(limitations)+'</ul></details>':'';
const fixedNotes=config.train_fraction?'<p class="field-help">Базовый опыт на четырёх акциях: обучение / тест '+esc(num(config.train_fraction*100,0))+' / '+esc(num((1-config.train_fraction)*100,0))+'%, риск '+esc(pct(config.risk_pct))+'. Комиссия / сторона '+esc(num(config.fee_bps,1))+' bps; полный спред '+esc(num(config.spread_bps,1))+' bps; проскальзывание / сторона '+esc(num(config.slippage_bps,1))+' bps. Параметры других исследований указаны в их карточках.</p>':'';
const search=data.edge_search||{},locked=search.locked_training||{},assets=search.training_assets_tested??locked.training_assets_tested,combinations=search.parameter_combinations_tested??locked.parameter_combinations_tested,holds=search.holdout_count??search.holdout_results?.length??locked.shortlist?.length,accepted=search.accepted_historical_candidates;
const searchSummary=assets!==undefined?'<article class="reference-search-summary"><h3>Расширенный поиск на обучающей истории</h3><div class="inline-metrics">'+inlineMetric('Активов исследовано',num(assets,0))+inlineMetric('Комбинаций проверено',num(combinations,0))+inlineMetric('Замороженных кандидатов',num(holds,0))+inlineMetric('Прошли независимый тест',num(accepted,0),accepted>0?'positive':'')+'</div><p>Актив и параметры выбираются на обучении. Отложенная часть проверяет зафиксированный список; слабый результат не заменяется новым победителем на тех же данных.</p>'+((accepted===0)?'<div class="notice notice-warning">Ни один кандидат этого поиска не прошёл отбор. Положительная доходность отдельной проверки сама по себе не подтверждает устойчивый edge.</div>':'')+'</article>':'';
$('#reference-results').innerHTML=reports.length?searchSummary+archiveNotes+fixedNotes+reports.map(report=>{
const strategies=report.strategies||[],period=report.period||report.data||{},provenance=report.provenance||{},symbol=report.symbol||report.data?.symbol||provenance.symbol,source=report.source||provenance.provider||provenance.source||provenance.source_url||provenance.url;
const archiveDate=value=>{const date=new Date(value);return Number.isNaN(date.getTime())?'—':date.toLocaleDateString('ru-RU',{timeZone:'UTC',day:'2-digit',month:'2-digit',year:'numeric'});};
const periodText=typeof period==='string'?period:period.start&&period.end?archiveDate(period.start)+' — '+archiveDate(period.end):'Период указан в отчёте';
const sourceText=source&&typeof source==='object'?source.name||source.provider||JSON.stringify(source):source;
let html='<details class="reference-report"><summary><span><strong>'+esc(symbol||'Инструмент')+'</strong><small>'+esc(report.timeframe||(report.data?.timeframe_minutes===1440?'1 день':report.data?.timeframe_minutes?num(report.data.timeframe_minutes,0)+' мин.':''))+' · '+esc(periodText)+'</small></span>'+badge(report.selected_strategy?'Кандидат прошёл отбор':'Без допущенного кандидата',report.selected_strategy?'good':'warning')+'</summary><p class="chart-caption">Источник: '+esc(sourceText||'См. отчёт')+'. Архивные цены; текущие уровни по ним не применяются. Выбор стратегии выполнен на обучении; ниже отдельный тест после издержек.'+(report.data?.holdout_start?' Тест: '+esc(archiveDate(report.data.holdout_start))+' — '+esc(archiveDate(report.data.end))+'.':'')+'</p>';
if(provenance.nominal_account_currency&&provenance.nominal_account_currency!=='USD')html+='<div class="notice notice-warning">'+esc('Цена и номинальная модель аккаунта выражены в '+provenance.nominal_account_currency+'. Это не долларовый P&L или выплата проп-фирмы. Short моделируется гипотетически; исполнение как обычной spot-сделки не подтверждено.')+'</div>';
if(report.config)html+='<p class="field-help">Риск '+esc(pct(report.config.risk_pct))+'; комиссия / сторона '+esc(num(report.config.fee_bps,1))+' bps, полный спред '+esc(num(report.config.spread_bps,1))+' bps, проскальзывание / сторона '+esc(num(report.config.slippage_bps,1))+' bps.</p>';
html+='<div class="table-scroll"><table><thead><tr><th>Стратегия</th><th>Обучение</th><th>Тест</th><th>Просадка</th><th>Сделки</th><th>Profit factor</th><th>Решение</th></tr></thead><tbody>'+strategies.map(strategy=>{const test=strategy.test_metrics||strategy.holdout||strategy.test||{},train=strategy.train_metrics||strategy.train||{},id=strategy.id||strategy.strategy_id;return '<tr><td>'+esc(strategy.name||itemById(state.strategies,id)?.name||id||'Стратегия')+'</td><td class="'+signClass(train.net_return_pct)+'">'+esc(pct(train.net_return_pct))+'</td><td class="'+signClass(test.net_return_pct)+'">'+esc(pct(test.net_return_pct))+'</td><td>'+esc(pct(test.max_drawdown_pct))+'</td><td>'+esc(num(test.total_trades,0))+'</td><td>'+esc(num(test.profit_factor))+'</td><td>'+badge(strategy.eligible?'Прошла отбор':strategy.baseline?'Ориентир':'Отклонена',strategy.eligible?'good':strategy.baseline?'neutral':'warning')+'</td></tr>';}).join('')+'</tbody></table></div>';
const candidate=itemById(strategies,report.training_candidate),notes=candidate?.reasons||report.summary?.warnings||[];if(notes.length)html+='<h3 class="mini-table-title">Ограничения и причины</h3><ul class="reasons-list">'+setupReasons(notes)+'</ul>';
if(['AAPL','MSFT','JPM','XOM'].includes(symbol))html+='<div class="signal-actions"><button class="button button-secondary" data-research-reference="'+esc(symbol||'')+'">Исследовать архив '+esc(symbol||'')+' <span>→</span></button><a class="button button-secondary" href="/api/data/reference?symbol='+encodeURIComponent(symbol||'')+'">Скачать архив CSV <span>↓</span></a></div>';
return html+'</details>';
}).join(''):'<div class="empty-state compact"><p>Архив ещё не опубликован. Проверьте собственную историю в лаборатории.</p></div>';
}catch(e){notice('reference-message','Архив недоступен: '+e.message);}
finally{busy(button,false);}
}
$('#load-reference').addEventListener('click',loadReferenceReports);
async function researchReference(button) {
const symbol=button.dataset.researchReference;if(!symbol)return;
notice('reference-message','');busy(button,true,'Пересчитываем архив…');
try{const result=await post('/api/research/reference',{symbol});result.archived=true;renderResearch(result);navigate('lab');notice('reference-message','Архив пересчитан и открыт в лаборатории. Котировки устарели: использовать эти уровни как текущий сетап нельзя.','warning');$('#research-output').scrollIntoView({behavior:'smooth',block:'start'});toast('Исторический эксперимент пересчитан. Текущего сигнала нет.');}
catch(e){notice('reference-message','Не удалось исследовать архив: '+e.message);}
finally{busy(button,false);}
}

let scannerPollTimer;
let traderPollTimer,traderExpiryTimer,traderRequestSerial=0;
const traderActiveSetups=new Map();
let traderNotifiedSetups=[];
try{const remembered=JSON.parse(localStorage.getItem('prop-lab-paper-setup-alerts')||'[]');if(Array.isArray(remembered))traderNotifiedSetups=remembered.filter(value=>typeof value==='string').slice(-100);}catch{}
function announceTraderChanges(setups,board) {
const active=new Map(setups.map(market=>[market.symbol+'|'+market.setup.strategy_id+'|'+(market.setup.signal_time||market.setup.reference_close_time||market.setup.reference_time||market.setup.expires_at),market]));
const fresh=[...active.keys()].filter(key=>!traderNotifiedSetups.includes(key));
const expired=[...traderActiveSetups.entries()].filter(([key,market])=>!active.has(key)&&(new Date(market.setup.expires_at).getTime()<=Date.now()||board.markets?.some(current=>current.symbol===market.symbol&&['stale','expired_next_bar'].includes(current.price_state)))).map(([,market])=>market.symbol);
if(fresh.length){const symbols=fresh.map(key=>active.get(key).symbol);notice('today-alert','Новый бумажный сетап: '+symbols.join(', ')+'. Проверьте условия входа и текущий риск.','success');traderNotifiedSetups=traderNotifiedSetups.concat(fresh).slice(-100);try{localStorage.setItem('prop-lab-paper-setup-alerts',JSON.stringify(traderNotifiedSetups));}catch{}}
else if(expired.length)notice('today-alert','План '+[...new Set(expired)].join(', ')+' истёк или потерял свежесть. Отмените сценарий входа; это не сигнал закрытия реальной позиции.','warning');
else if(active.size===0&&traderActiveSetups.size>0)notice('today-alert','Предыдущий бумажный план больше не подтверждён. Дождитесь новой проверки условий.','warning');
traderActiveSetups.clear();active.forEach((market,key)=>traderActiveSetups.set(key,market));
}
let replayDiaryPollTimer, replayDiaryRequest = 0;
function tradingViewLink(value) {
try{const url=new URL(value);if(url.protocol==='https:'&&['www.tradingview.com','tradingview.com'].includes(url.hostname)&&!url.username&&!url.password)return '<a class="button button-secondary small" href="'+esc(url.href)+'" target="_blank" rel="noopener noreferrer">Открыть в TradingView ↗</a>';}catch{}
return '';
}
function replayCandleChart(trade) {
const source=trade.chart,bars=Array.isArray(source?.bars)?source.bars.slice(-120):[];
if(source?.state!=='ready'||!bars.length)return '<div class="replay-chart-empty">OHLC-график недоступен: подтверждённые котировки для этого окна не загружены.</div>';
let previous=-Infinity;
for(const bar of bars){const stamp=new Date(bar.time).getTime(),values=[bar.open,bar.high,bar.low,bar.close];if(!Number.isFinite(stamp)||stamp<=previous||values.some(value=>value===null||!Number.isFinite(Number(value))||Number(value)<=0)||Number(bar.high)<Math.max(...values.map(Number))||Number(bar.low)>Math.min(...values.map(Number)))return '<div class="replay-chart-empty">Структура OHLC не подтверждена; график скрыт.</div>';previous=stamp;}
const indexAt=value=>bars.findIndex(bar=>new Date(bar.time).getTime()===new Date(value).getTime());
const markers=[{index:indexAt(trade.entry_time),price:trade.entry_price,label:'Вход модели',tone:'#b6f46f'}];
if(trade.status==='closed'&&trade.exit_time)markers.push({index:indexAt(trade.exit_time),price:trade.exit_price,label:'Выход модели',tone:'#8dc9ee'});
const visible=markers.filter(marker=>marker.index>=0&&marker.price!==null&&Number.isFinite(Number(marker.price))&&Number(marker.price)>0);
const width=720,height=240,left=59,right=16,top=22,bottom=32;
const prices=bars.flatMap(bar=>[Number(bar.low),Number(bar.high)]).concat(visible.map(marker=>Number(marker.price)));
let low=Math.min(...prices),high=Math.max(...prices);const pad=(high-low||high*.02)*.12;low-=pad;high+=pad;
const x=index=>left+(index+.5)*(width-left-right)/bars.length,y=value=>top+(high-Number(value))/(high-low)*(height-top-bottom),body=Math.max(1,Math.min(8,(width-left-right)/bars.length*.65));
let svg='<svg class="replay-candles" viewBox="0 0 '+width+' '+height+'" role="img" aria-label="'+esc('Исторические OHLC '+trade.symbol+'; маркеры означают только смоделированные сделки')+'"><title>'+esc('Реальная история OHLC '+trade.symbol+' · '+bars[0].time+' — '+bars.at(-1).time)+'</title>';
for(let i=0;i<4;i++){const value=high-(high-low)*i/3,position=y(value);svg+='<line x1="'+left+'" y1="'+position.toFixed(2)+'" x2="'+(width-right)+'" y2="'+position.toFixed(2)+'" stroke="#2a4050" stroke-dasharray="3 5"/><text x="'+(left-8)+'" y="'+(position+3).toFixed(2)+'" text-anchor="end" fill="#839dad" font-size="10">'+esc(price(value))+'</text>';}
bars.forEach((bar,index)=>{const color=Number(bar.close)>=Number(bar.open)?'#a7d789':'#e49393',position=x(index),open=y(bar.open),close=y(bar.close);svg+='<line x1="'+position.toFixed(2)+'" x2="'+position.toFixed(2)+'" y1="'+y(bar.high).toFixed(2)+'" y2="'+y(bar.low).toFixed(2)+'" stroke="'+color+'" stroke-width="1"/><rect x="'+(position-body/2).toFixed(2)+'" y="'+Math.min(open,close).toFixed(2)+'" width="'+body.toFixed(2)+'" height="'+Math.max(1,Math.abs(open-close)).toFixed(2)+'" fill="'+color+'"/>';});
visible.forEach((marker,index)=>{const position=x(marker.index),level=y(marker.price),labelX=Math.min(width-right-5,Math.max(left+5,position)),anchor=position>width*.7?'end':'start';svg+='<line x1="'+position.toFixed(2)+'" x2="'+position.toFixed(2)+'" y1="'+top+'" y2="'+(height-bottom)+'" stroke="'+marker.tone+'" stroke-dasharray="2 5" opacity=".45"/><circle cx="'+position.toFixed(2)+'" cy="'+level.toFixed(2)+'" r="4" fill="'+marker.tone+'" stroke="#0e1a24" stroke-width="2"/><text x="'+labelX.toFixed(2)+'" y="'+(index?height-bottom-8:top+11)+'" fill="'+marker.tone+'" font-size="10" text-anchor="'+anchor+'">'+marker.label+'</text>';});
svg+='<text x="'+left+'" y="'+(height-10)+'" fill="#839dad" font-size="10">'+esc(shortDate(bars[0].time))+'</text><text x="'+(width-right)+'" y="'+(height-10)+'" text-anchor="end" fill="#839dad" font-size="10">'+esc(shortDate(bars.at(-1).time))+'</text></svg>';
return '<div class="replay-chart">'+svg+'</div><p class="replay-chart-caption">Локальный график реальных OHLC · '+esc(localTimestamp(bars[0].time))+' — '+esc(localTimestamp(bars.at(-1).time))+(source.entry_in_view===false?' · вход за пределами окна':'')+'. История по ссылке TradingView может отличаться.</p>';
}
function historicalStrategyLabel(strategy) {
return ({bt_sma_10_30:'SMA10/30 · дневной тренд',qc_ema_15_30:'EMA15/30 · дневной тренд',faber_sma_10m:'SMA10 месяцев · долгий тренд',rsi2_pullback_5:'RSI2 · короткий откат'})[strategy?.id]||strategy?.name||strategy?.id||'Сохранённый алгоритм';
}
function renderReplayDiary(data) {
state.replayDiary=data;const ready=data.state==='ready',summary=data.summary||{},trades=Array.isArray(data.trades)?data.trades:[];
$('#replay-diary-status').textContent=ready?'ИСТОРИЧЕСКАЯ СИМУЛЯЦИЯ':data.state==='in_progress'?'Формируется':'Нет отчёта';
$('#replay-diary-status').className='badge badge-'+(ready?'neutral':'warning');
$('#replay-diary-note').textContent=ready?'Период: '+(data.period?.month||'не указан')+' · '+historicalStrategyLabel(data.strategy)+'. Исторический сценарий на акциях/ETF. Это не исполнения на проп-счёте. Метки времени относятся к дневным барам; точный момент исполнения внутри дня не установлен.':data.reason||'Автоматический дневник появится после сохранения проверяемого исторического сценария.';
$('#replay-diary-summary').innerHTML=ready?inlineMetric('Позиций модели',num(summary.positions,0),'','Закрыто: '+num(summary.closed_in_month,0)+' · открыто на границе: '+num(summary.open_at_period_end,0))+inlineMetric('Изменение капитала за месяц',money(summary.month_equity_change),signClass(summary.month_equity_change),'USD · модель, включая оценку границы')+inlineMetric('Доходность месяца',pct(summary.month_return_pct),signClass(summary.month_return_pct))+inlineMetric('P&L закрытых позиций',money(summary.closed_trade_pnl),signClass(summary.closed_trade_pnl),'За сделки целиком, включая переносы до месяца'):'';
$('#replay-diary-trades').innerHTML=ready&&trades.length?trades.map(trade=>{
const closed=trade.status==='closed',boundary=trade.valuation_boundary;
return '<article class="replay-trade" data-replay-trade="'+esc(trade.id)+'"><div class="replay-trade-heading"><div><h3>'+esc(trade.symbol)+' · '+(trade.side==='short'?'SHORT':'LONG')+'</h3><p>'+esc(trade.carried_from_previous_month?'Перенос из предыдущего месяца':'Вход в этом месяце')+' · '+esc(localTimestamp(trade.entry_time))+'</p></div>'+badge(closed?'ЗАКРЫТА В МОДЕЛИ':'ОТКРЫТА НА ГРАНИЦЕ','neutral')+'</div><div class="replay-trade-numbers">'+inlineMetric('Вход модели',price(trade.entry_price))+inlineMetric('Стоп',price(trade.stop))+inlineMetric(closed?'Выход модели':'Фиксированная цель',closed?price(trade.exit_price):trade.take_profit===null||trade.take_profit===undefined?'Выход по правилу':price(trade.take_profit))+inlineMetric('P&L закрытой позиции',closed?money(trade.pnl):'—',closed?signClass(trade.pnl):'')+'</div>'+replayCandleChart(trade)+'<div class="replay-trade-explanation"><div><h4>Почему вход</h4><ul class="reasons-list">'+setupReasons(trade.entry_reasons||[])+'</ul></div><div><h4>Почему выход / ожидание</h4><ul class="reasons-list">'+setupReasons(trade.exit_reasons||[])+'</ul>'+(closed?'<p>Бар выхода: '+esc(localTimestamp(trade.exit_time))+'</p>':'')+'</div></div>'+(boundary?'<p class="replay-valuation">'+esc(boundary.reason)+' Цена гипотетической оценки: '+esc(price(boundary.hypothetical_liquidation_price))+'.</p>':'')+'<details class="replay-trade-costs"><summary>Объём, риск и издержки модели</summary><p>Объём: '+esc(num(trade.quantity,4))+' · бюджет риска: '+esc(money(trade.risk_amount))+' · результат R от бюджета: '+esc(num(trade.return_r,3))+'.</p>'+(trade.costs?'<p>Комиссии: '+esc(money(trade.costs.fees))+' · спред: '+esc(money(trade.costs.spread))+' · проскальзывание: '+esc(money(trade.costs.slippage))+' · финансирование: '+esc(money(trade.costs.financing_total))+' · суммарно: '+esc(money(trade.costs.total_costs))+'.</p>':'<p>Окончательные издержки открытой позиции не рассчитаны как закрытая сделка.</p>')+'</details><div class="replay-trade-actions">'+tradingViewLink(trade.tradingview_url)+'<small>Отдельный график TradingView. Локальный OHLC выше — график программы.</small></div></article>';
}).join(''):ready?'<div class="empty-state compact"><p>В выбранном месяце позиций этого сценария нет.</p></div>':'<div class="empty-state compact"><p>Исторические сделки не подставляются, пока проверяемый отчёт недоступен.</p></div>';
$('#replay-diary-details').hidden=!data.warnings?.length&&!data.qualification?.reasons?.length;
$('#replay-diary-provenance').innerHTML='<ul class="reasons-list">'+setupReasons([...(data.warnings||[]),...(data.qualification?.reasons||[])])+'</ul>';
}
async function loadReplayDiary() {
clearTimeout(replayDiaryPollTimer);
const request=++replayDiaryRequest, study=$('#replay-diary-study').value;
try{const response=await api('/api/trader/diary?study='+encodeURIComponent(study));if(request!==replayDiaryRequest)return;renderReplayDiary(response.diary||response);notice('replay-diary-error','');}
catch(e){if(request!==replayDiaryRequest)return;$('#replay-diary-status').textContent='Нет связи';notice('replay-diary-error','Дневник симуляций недоступен: '+e.message);}
finally{if(request===replayDiaryRequest)replayDiaryPollTimer=setTimeout(loadReplayDiary,state.replayDiary?.state==='in_progress'?15000:60000);}
}
$('#replay-diary-study').addEventListener('change',()=>{state.replayDiary=null;$('#replay-diary-status').textContent='Загрузка…';$('#replay-diary-summary').innerHTML='';$('#replay-diary-trades').innerHTML='';$('#replay-diary-details').hidden=true;$('#replay-diary-note').textContent='Загружаются решения выбранного алгоритма за последний завершённый месяц.';loadReplayDiary();});
function acceptedTraderSetups(board) {
if(state.traderError||state.traderAction||board?.status!=='paper_review'||board.mode!=='paper'||board.live_orders!==false)return [];
return (board.setups||[]).filter(market=>{
const plan=market.setup,zone=plan?.entry_zone,target=plan?.take_profit_zone,invalidation=plan?.invalidation_zone;
const values=[zone?.low,zone?.high,plan?.stop_loss,target?.low,target?.high,invalidation?.low,invalidation?.high];
if(market.status!=='qualified'||market.price_state!=='fresh'||market.primary!==true||market.selected!==true||market.historical_qualified!==true||market.blockers?.length||plan?.status!=='paper_review'||plan.planning_only!==true||plan.can_trade!==false||!['long','short'].includes(plan.direction)||values.some(value=>value===null||value===undefined||!Number.isFinite(Number(value))||Number(value)<=0))return false;
return Number(zone.low)<=Number(zone.high)&&Number(target.low)<=Number(target.high)&&Number(invalidation.low)<=Number(invalidation.high)&&new Date(plan.expires_at).getTime()>Date.now();
});
}
function traderEvidenceReason(value) {
const text=String(value||'').replace(/^(historical_holdout|confirmation):\s*/,'');
if(text==='Descriptive99% synchronized-month interval includes zero or has fewer than24 months')return '99% интервал месячного результата включает ноль или не имеет достаточной выборки: устойчивость не подтверждена.';
if(text==='Descriptive99% monthly interval includeszero or insufficientmonths')return 'Длинный период пока не подтверждает устойчивость: 99% интервал средней месячной доходности включает ноль.';
const intradayReasons={
'Fewer than60holdouttrades':'На контрольном периоде меньше 60 сделок.',
'Fewer than120holdoutsessions':'На контрольном периоде меньше 120 торговых сессий.',
'Net holdout return is not positive after assumed costs':'После расходов контрольный период не принёс прибыль.',
'Profit factor below1.2 or no finite loss sample':'Соотношение прибылей и убытков ниже 1,2 или недостаточно наблюдаемых убытков.',
'Double friction stress is not positive':'При удвоенных расходах прибыль исчезает.',
'Worst-bar drawdown reaches8%':'Просадка достигает установленного лимита 8%.',
'99% synchronized5-session-block confidence lower bound does not exceedzero':'99% интервал дневного результата включает ноль: преимущество не подтверждено.'
};
if(intradayReasons[text])return intradayReasons[text];
return translate(text);
}
function secondaryTraderEvidence(evidence) {
const studies=Array.isArray(evidence?.studies)?evidence.studies.filter(study=>study.id!=='sourced_daily'):[];
if(!studies.length)return '';
return '<div class="secondary-evidence"><h3>Дополнительные зафиксированные проверки</h3>'+studies.map(study=>{
const primary=study.primary,title=study.title||'Отдельная проверка',symbols=Array.isArray(study.symbols)?study.symbols.join(', '):'';
if(!primary){const unavailable=study.state==='source_incomplete';return '<article><h4>'+esc(title)+'</h4><p>'+esc(unavailable?'Недостаточно корректных сессионных данных. Доходность не рассчитана; цены исполнения не выдумываются.':study.state==='unavailable'?'Проверяемого отчёта пока нет.':'Проверка ещё не завершена; итог и сетапы из неё не создаются.')+'</p>'+(unavailable&&study.availability_errors?.length?'<ul class="reasons-list">'+study.availability_errors.slice(0,3).map(item=>'<li>'+esc(item.symbol)+' · '+esc(item.reason)+'</li>').join('')+'</ul>':'')+'</article>'; }
const windows=Object.values(primary.windows||{});
return '<article><div class="panel-header"><h4>'+esc(title)+'</h4>'+badge(primary.status==='historically_positive_watch'?'WATCH · НЕТ ДОПУСКА':'ОТБОР НЕ ПРОЙДЕН','warning')+'</div><p>'+esc(historicalStrategyLabel(primary))+(symbols?' · '+esc(symbols):'')+(study.interval?' · '+esc(study.interval):'')+'</p>'+windows.map(window=>{const metrics=window.metrics||{},stress=window.friction_stress||{},data=window.data||{};return '<p class="field-help">Отложенная история: '+esc(localTimestamp(data.start))+' — '+esc(localTimestamp(data.end))+'.</p><div class="inline-metrics">'+inlineMetric('Результат после издержек',pct(metrics.net_return_pct),signClass(metrics.net_return_pct))+inlineMetric('Просадка модели',pct(metrics.max_drawdown_pct))+inlineMetric('Сделки модели',num(metrics.total_trades,0))+(stress.net_return_pct!==undefined?inlineMetric('При повышенных издержках',pct(stress.net_return_pct),signClass(stress.net_return_pct)):'')+'</div>';}).join('')+'<ul class="reasons-list">'+setupReasons((primary.reasons||[]).slice(0,3).map(traderEvidenceReason))+'</ul><p class="field-help">'+esc(study.decision||'Применимость к реальному проп-контракту не подтверждена.')+'</p></article>';
}).join('')+(evidence.sequential_search_notice?'<p class="field-help">'+esc(evidence.sequential_search_notice)+'</p>':'')+'</div>';
}
function renderTraderEvidence(board) {
const evidence=board?.evidence,primary=evidence?.primary;
$('#legacy-history').hidden=!primary;$('#today-evidence').hidden=!primary;if(!primary)return;
$('#today-evidence-title').textContent=historicalStrategyLabel(primary);
$('#today-evidence-status').textContent=primary.status==='historically_positive_watch'?'WATCH · НЕТ ДОПУСКА':'ОТБОР НЕ ПРОЙДЕН';
const reasons=(primary.reasons||[]).map(traderEvidenceReason);
$('#today-evidence-reason').textContent=(primary.status==='historically_positive_watch'?'Два исторических периода положительны после издержек. ':'')+(reasons[0]||'Применимость инструментов, исполнения и договора проп-фирмы ещё не подтверждена.')+' Алгоритм остаётся под наблюдением; готовый вход определяется отдельной проверкой условий.';
$('#today-evidence-windows').innerHTML=['historical_holdout','confirmation'].map(key=>{const window=primary.windows?.[key];if(!window)return '';const metrics=window.metrics||{},data=window.data||{};return '<article><h3>'+({historical_holdout:'Отложенная история',confirmation:'Последующее подтверждение'}[key])+'</h3><p>'+esc(localTimestamp(data.start))+' — '+esc(localTimestamp(data.end))+'</p><div>'+inlineMetric('Результат после издержек',pct(metrics.net_return_pct),signClass(metrics.net_return_pct))+inlineMetric('Максимальная просадка',pct(metrics.max_drawdown_pct))+inlineMetric('Сделки модели',num(metrics.total_trades,0))+'</div></article>';}).join('');
$('#today-evidence-related').innerHTML=secondaryTraderEvidence({...evidence,studies:(evidence.studies||[]).filter(study=>study.id!=='sourced_daily'&&study.primary?.status==='historically_positive_watch')});
const sources=Array.isArray(primary.sources)?primary.sources:[];
$('#today-evidence-detail-content').innerHTML='<p class="field-help">'+esc(evidence.decision||'Исторические результаты требуют отдельной проверки применимости к проп-счёту.')+'</p>'+(primary.rules?'<h3>Зафиксированные правила</h3><pre class="code-block">'+esc(typeof primary.rules==='string'?primary.rules:JSON.stringify(primary.rules,null,2))+'</pre>':'')+(sources.length?'<h3>Источники стратегии</h3><ul class="reasons-list">'+sources.map(source=>'<li>'+officialSourceLink(source.url||source.source_url,source.title||source.name||source.strategy_id||'Официальный источник')+'</li>').join('')+'</ul>':'')+'<ul class="reasons-list">'+[...reasons,...(evidence.limitations||[]).map(translate)].map(reason=>'<li>'+esc(reason)+'</li>').join('')+'</ul>'+secondaryTraderEvidence(evidence);
}
function renderTraderBoard() {
const board=state.trader,button=$('#find-setups'),error=state.traderError;
renderTraderEvidence(board);
const searching=state.traderAction||board?.status==='searching'||['queued','running'].includes(board?.job?.state);
const setups=acceptedTraderSetups(board),ready=!searching&&!error&&setups.length>0;
if(searching||error)notice('today-alert','');
clearTimeout(traderExpiryTimer);
if(!searching&&!error&&board)announceTraderChanges(setups,board);
if(ready){const expiry=Math.min(...setups.map(market=>new Date(market.setup.expires_at).getTime()));traderExpiryTimer=setTimeout(renderTraderBoard,Math.min(2147483647,Math.max(1,expiry-Date.now()+1)));}
button.disabled=searching;button.innerHTML=searching?'Ищем сетапы…':'Найти сетапы <span>↗</span>';
$('#today-board').setAttribute('aria-busy',String(searching||!board&&!error));
$('#today-status').className='badge badge-'+(ready?'good':searching?'neutral':'warning');
$('#today-status').textContent=error?'Нет связи':searching?'Проверяем рынки':ready?'БУМАЖНЫЙ ПЛАН':'ВНЕ РЫНКА';
$('#today-title').textContent=error?'Решение сейчас неизвестно':searching?'Ищем допустимые сетапы':ready?(setups.length===1?'Есть сетап для проверки':'Есть сетапы для проверки'):'Сейчас остаёмся вне рынка';
$('#today-action').textContent=error?'Дождитесь связи или повторите поиск.':searching?'Дождитесь проверки котировок, стратегии и правил.':ready?'Вход только при выполнении условий и проверке риска.':'Не открывайте новый сценарий по этому решению.';
const progress=board?.job?.progress,details=progress?.details||{};
$('#today-reason').textContent=error||searching?(error||((Number.isFinite(Number(details.finished))&&Number(details.total)>0)?'Проверено рынков: '+num(details.finished,0)+' из '+num(details.total,0)+'.':'Программа сама проверяет доступные рынки. Можно продолжать работу с дневником.')):board?.status==='paper_review'&&!ready?'Сохранённый план истёк или не содержит полного подтверждённого ценового сценария. Дождитесь новой проверки.':board?.decision||'Сохранённого допустимого сетапа пока нет. Нажмите «Найти сетапы» для проверки рынков.';
$('#today-levels').hidden=!ready;
$('#today-levels').innerHTML=ready?setups.map(market=>{const plan=market.setup;return '<article class="today-setup-card"><div class="today-setup-heading"><h3>'+esc(market.symbol)+' · '+(plan.direction==='long'?'LONG':'SHORT')+'</h3>'+badge('УСЛОВНЫЙ ВХОД','neutral')+'</div><div class="price-zones">'+zoneCard('Зона входа',plan.entry_zone,'entry',typeof plan.entry_zone.trigger==='string'?translate(plan.entry_zone.trigger):'Только после выполнения условия')+zoneCard('Стоп-лосс',plan.stop_loss,'stop','Граница риска сценария')+zoneCard('Зона take profit',plan.take_profit_zone,'target','Цели из сохранённого плана')+zoneCard('Отмена идеи',plan.invalidation_zone,'cancel','Вне условий сценарий отменяется')+'</div><p class="today-setup-time">Закрытая свеча: '+esc(localTimestamp(plan.reference_close_time||plan.reference_time))+' · действителен до '+esc(localTimestamp(plan.expires_at))+'</p>'+(plan.reasons?.length?'<ul class="reasons-list">'+setupReasons(plan.reasons)+'</ul>':'')+'<button class="button button-secondary small" data-go="checker">Чекер риска →</button></article>';}).join(''):'';
const markets=Array.isArray(board?.markets)?board.markets:[],primary=markets.find(market=>market.primary),blockers=primary?.blockers||[];
const quoteFailures=markets.filter(market=>market.status==='unavailable').length;
const quoteReason=quoteFailures===markets.length&&quoteFailures>0?'Котировки всех '+quoteFailures+' запрошенных рынков недоступны. Свежие условия входа проверить невозможно.':quoteFailures>0?'Котировки '+quoteFailures+' из '+markets.length+' рынков недоступны; охват проверки неполный.':'';
notice('today-risk',!ready&&!searching&&!error?[quoteReason,...blockers.slice(0,4).map(translate)].filter(Boolean).join('\n'):'','warning');
$('#today-next-check').textContent=searching?'После завершения проверки':board?.next_check_at&&board?.automation?.enabled!==false?localTimestamp(board.next_check_at):board?.automation?.enabled?'По автоматическому расписанию':'По кнопке «Найти сетапы»';
$('#today-source').textContent=error?'Данные не подтверждены':board?.generated_at?'Состояние на '+localTimestamp(board.generated_at):'Сохранённое состояние ещё не получено';
$('#today-market-statuses').innerHTML=markets.length?markets.map(market=>'<article class="today-market"><div><strong>'+esc(market.symbol)+'</strong>'+badge(market.status==='qualified'?'История прошла отбор':market.status==='unavailable'?'Нет котировок':'Отбор не пройден',market.status==='qualified'?'neutral':'warning')+'</div><p>'+esc({fresh:'Свежие закрытые бары',stale:'Котировки устарели',future_unclosed:'Свеча ещё не закрыта',expired_next_bar:'План истёк',unknown:'Свежесть не подтверждена'}[market.price_state]||'Свежесть не подтверждена')+'</p>'+(market.blockers?.length?'<ul class="reasons-list">'+setupReasons(market.blockers)+'</ul>':'')+'</article>').join(''):'<p class="field-help">Состояние отдельных рынков появится после проверки.</p>';
}
let strategyEvidenceLoading=false,strategyEvidenceLastRequest=0;
function strategyReportUrl(value) {
if(typeof value!=='string'||!value.startsWith('/api/trader/evidence?'))return null;
try{
const url=new URL(value,window.location.origin),knownStudies=['broad','low_turnover','liquidity','funding','funding_sized','funding_static','funding_calibrated'];
if(url.origin!==window.location.origin||url.pathname!=='/api/trader/evidence'||url.hash||url.searchParams.size!==1||!knownStudies.includes(url.searchParams.get('study')))return null;
return url.pathname+url.search;
}catch{return null;}
}
function renderStrategyEvidence() {
const data=state.strategyEvidence,error=state.strategyEvidenceError,status=$('#strategy-evidence-status'),summary=$('#strategy-evidence-summary'),count=$('#strategy-evidence-count'),note=$('#strategy-evidence-note'),details=$('#strategy-evidence-details');
$('#strategy-evidence-card').setAttribute('aria-busy',String(strategyEvidenceLoading));
if(error){status.textContent='Нет связи';status.className='badge badge-warning';summary.textContent='Не удалось загрузить результаты проверки.';count.hidden=true;note.hidden=false;note.textContent=error;details.hidden=true;return;}
if(!data){status.textContent='Загрузка…';status.className='badge badge-neutral';return;}
const candidate=data.phase==='candidate_needs_forward_test'&&data.primary?.mode==='paper_candidate';
status.textContent=candidate?'БУМАЖНЫЙ КАНДИДАТ':'НЕТ ДОПУСКА';status.className='badge badge-'+(candidate?'warning':'neutral');
summary.textContent=candidate?'Кандидат для форвард-проверки: '+String(data.primary.title||'стратегия')+'.':'Проверенной стратегии пока нет';
const variants=data.variant_count;count.hidden=!Number.isInteger(variants)||variants<0;count.textContent=count.hidden?'':'Проверено конфигураций: '+num(variants,0)+'.';
note.hidden=false;note.textContent=candidate?'Нужна проверка на будущих данных. Реальная торговля и Telegram не включены.':'Реальная торговля и Telegram не включены.';
const reports=(Array.isArray(data.studies)?data.studies:[]).filter(study=>study&&study.phase!=='unavailable').map(study=>{const url=strategyReportUrl(study.report_url);return url?'<a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">'+esc(study.title||'Отчёт')+' <span>JSON ↗</span></a>':'';}).filter(Boolean);
details.hidden=reports.length===0;
$('#strategy-evidence-reports').innerHTML=reports.join('')+'<p class="field-help">Исторические результаты требуют отдельной проверки на будущих данных.</p>';
}
async function loadStrategyEvidence(force=false) {
if(strategyEvidenceLoading||(!force&&Date.now()-strategyEvidenceLastRequest<10000))return;
strategyEvidenceLoading=true;strategyEvidenceLastRequest=Date.now();renderStrategyEvidence();
try{
const data=await api('/api/trader/evidence');
if(!data||!['no_qualified_strategy','candidate_needs_forward_test'].includes(data.phase)||!Number.isInteger(data.variant_count)||data.variant_count<0||data.live_orders!==false||data.telegram_enabled!==false||data.forward_test_required!==true||(data.phase==='candidate_needs_forward_test'&&data.primary?.mode!=='paper_candidate'))throw new Error('Сервер вернул неподтверждённое состояние стратегии.');
state.strategyEvidence=data;state.strategyEvidenceError='';
}catch(e){state.strategyEvidenceError=e.message;}
finally{strategyEvidenceLoading=false;renderStrategyEvidence();}
}
function scheduleTraderPoll() {
clearTimeout(traderPollTimer);traderPollTimer=setTimeout(()=>loadTraderBoard(),state.traderError?5000:state.trader?.status==='searching'||['queued','running'].includes(state.trader?.job?.state)?1500:15000);
}
let researchProgressLoading=false,researchProgressLastRequest=0;
const researchProgressStudies=['pairs','pairs_close','sessions','fx','native_fvg','native_trend','native_context','metals','crypto_flow'];
function researchProgressReportUrl(study) {
return researchProgressStudies.includes(study)?'/api/trader/research-progress?study='+encodeURIComponent(study):null;
}
function renderResearchProgress() {
const summary=$('#research-progress-summary'),details=$('#research-progress-details'),data=state.researchProgress;
if(state.researchProgressError){summary.textContent='Результаты исследований · цель: 8% в месяц. Связь с отчётами недоступна.';details.hidden=true;return;}
if(!data)return;
summary.textContent='Результаты исследований · цель: 8% в месяц. По отчётам проверено '+num(data.reported_evaluated_configurations,0)+' конфигураций ('+num(data.previous_evaluated_configurations,0)+' ранее + '+num(data.new_reported_evaluated_configurations,0)+' новых). Сигналы по этим результатам не включены.'+(data.crypto_pending_reports?' Крипто: ждём следующие отчёты.':'');
const studies=Array.isArray(data.studies)?data.studies:[];
$('#research-progress-reports').innerHTML=studies.filter(item=>item&&researchProgressStudies.includes(item.id)).map(item=>{
const url=researchProgressReportUrl(item.id),count=Number.isInteger(item.reported_evaluated_configurations)?item.reported_evaluated_configurations:0;
const verification=item.replay_artifacts_verified?'Файлы протокола, движка и истории подтверждены':item.protocol_verified&&item.producer_hashes_verified&&!item.input_available?'Версия подтверждена; исходные файлы истории отсутствуют':item.status==='missing_report'?'Отчёт ещё не опубликован':'Контрольные суммы не подтверждены';
return '<div><p><strong>'+esc(item.title||'Исследование')+'</strong> · '+esc(num(count,0))+' конфигураций<br>'+esc(verification)+'</p>'+(item.status!=='missing_report'?'<a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">Отчёт JSON ↗</a>':'')+(item.id==='pairs_close'?'<p class="field-help">48 повторных оценок исполнения; не 48 новых независимых стратегий.</p>':'')+'</div>';
}).join('')+'<p class="field-help">Контроль исходных файлов подтверждён для '+esc(num(data.new_replay_artifacts_verified_configurations,0))+' новых конфигураций. Прежние 292 — учёт выполненных исследований. Цель доходности не означает допуск к торговле; торговля и Telegram не включаются этим разделом.</p>';
details.hidden=false;
}
async function loadResearchProgress(force=false) {
if(researchProgressLoading||(!force&&Date.now()-researchProgressLastRequest<15000))return;
researchProgressLoading=true;researchProgressLastRequest=Date.now();
try{
const data=await api('/api/trader/research-progress');
if(!data||data.target_monthly_return_pct!==8||!Number.isInteger(data.reported_evaluated_configurations)||data.reported_evaluated_configurations<0||data.live_orders!==false||data.telegram_enabled!==false||data.eligible_for_paper!==false||!Array.isArray(data.studies))throw new Error('Неподтверждённое состояние исследований.');
state.researchProgress=data;state.researchProgressError='';
}catch(e){state.researchProgressError=e.message;}
finally{researchProgressLoading=false;renderResearchProgress();}
}
async function loadTraderBoard(force=false) {
clearTimeout(traderPollTimer);if(state.traderAction&&!force)return;
loadStrategyEvidence(force);
loadResearchProgress(force);
const serial=++traderRequestSerial;
try{const response=await api('/api/trader/board');if(serial!==traderRequestSerial)return;state.trader=response.board||response;state.traderError='';renderTraderBoard();}
catch(e){if(serial!==traderRequestSerial)return;state.traderError='Связь с помощником недоступна: '+e.message;renderTraderBoard();}
finally{if(serial===traderRequestSerial&&!state.traderAction)scheduleTraderPoll();}
}
$('#find-setups').addEventListener('click',async()=>{
if(state.traderAction||state.trader?.status==='searching'||['queued','running'].includes(state.trader?.job?.state))return;
navigate('overview');clearTimeout(traderPollTimer);++traderRequestSerial;state.traderAction=true;state.traderError='';renderTraderBoard();
try{await post('/api/trader/qualified-setups',{});await loadTraderBoard(true);}
catch(e){state.traderError='Найти сетапы не удалось: '+e.message;}
finally{state.traderAction=false;renderTraderBoard();scheduleTraderPoll();}
});

function scannerSourceControls() {
const archive=$('#scanner-form').elements.namedItem('scanner_source').value==='reference';
$('#scanner-online-controls').hidden=archive;
notice('scanner-source-note',archive?'Архив без сети: AAPL, MSFT, JPM и XOM в общем окне 2015–2018. Результаты повторной проверки не создают текущие сигналы.':'По умолчанию: EURUSD, XAUUSD, NAS100, BTCUSD, MES=F, MNQ=F, AAPL и MSFT. Публичная история Yahoo; брокерские цены и исполнение проверяются отдельно.','subtle');
}
function scannerIsActive() {return state.scanStarting||['queued','running'].includes(state.scanJob?.state);}
function scannerCostControls() {const form=$('#scanner-form'),disabled=scannerIsActive()||checked(form,'use_market_costs');['fee_bps','spread_bps','slippage_bps'].forEach(key=>{form.elements.namedItem(key).disabled=disabled;});}
function renderScannerJob() {
const job=state.scanJob,active=scannerIsActive(),form=$('#scanner-form');
Array.from(form.elements).forEach(element=>{element.disabled=active;});
scannerCostControls();
$('#scanner-start').innerHTML=active?'Поиск выполняется…':'Найти лучший рынок и стратегию <span>→</span>';
form.setAttribute('aria-busy',String(active));
$('#scanner-empty').hidden=Boolean(job)||state.scanStarting;
$('#scanner-job-panel').hidden=!job&&!state.scanStarting;
$('#scanner-output').hidden=active||!job?.result||job.state!=='completed';
renderAutopilot();
if(!job&&!state.scanStarting)return;
const progress=job?.progress||{},details=progress.details||{},stage=progress.stage||'loading';
const title=state.scanStarting?'Запускаем поиск':job?.state==='completed'?'Исследование завершено':job?.state==='failed'?'Поиск не завершён':job?.state==='interrupted'?'Поиск прерван':{starting:'Подготавливаем поиск',calendar:'Обновляем публичный календарь',loading:'Загружаем историю',training:'Сравниваем на обучении',locking:'Фиксируем выбор обучения',training_locked:'Выбор обучения зафиксирован',holdout:'Проверяем отложенную историю',validation:'Проверяем устойчивость',completed:'Исследование завершено'}[stage]||'Исследуем рынки';
$('#scanner-stage').textContent=title;
$('#scanner-job-badge').textContent=state.scanStarting||job?.state==='running'?'Выполняется':{completed:'Готово',failed:'Ошибка',interrupted:'Прерван'}[job?.state]||job?.state||'Подготовка';
$('#scanner-job-badge').className='badge badge-'+(job?.state==='completed'?'good':['failed','interrupted'].includes(job?.state)?'warning':'neutral');
$('#scanner-progress').hidden=!active;
$('#scanner-progress-track').hidden=!active;
const finished=Number(details.finished??details.completed),total=Number(details.total);
$('#scanner-progress-text').textContent=Number.isFinite(finished)&&Number.isFinite(total)&&total>0?'Обработано '+finished+' из '+total+(details.symbol?' · '+details.symbol:''):typeof details.note==='string'?details.note:typeof progress.details==='string'?progress.details:'Кандидаты выбираются на обучении, затем проверяются отдельно.';
$('#scanner-progress-fill').style.width=(Number.isFinite(finished)&&total>0?Math.min(100,Math.max(0,finished/total*100)):12)+'%';
$('#scanner-job-time').textContent=job?.created_at?'Запущен: '+timestamp(job.created_at):'Подготавливаем задачу';
if(job?.state==='failed'||job?.state==='interrupted')notice('scanner-error',job.error?(typeof job.error==='string'?job.error:JSON.stringify(job.error)):'Задача прервана. Можно запустить новое исследование.');
if(job?.state==='completed'&&job.result)renderScannerReport(job.result,job.id);
}
function renderScannerReport(report,jobId) {
const markets=Array.isArray(report.markets)?report.markets:[],selected=report.selected_symbol,primary=report.primary_symbol,archive=report.source==='reference';
const profile=itemById(state.profiles,report.selected_profile_id||report.firm_comparison?.recommended_profile_id),verified=Boolean(profile&&profile.status==='user_verified');
const decision=typeof report.decision==='string'?report.decision:report.decision?.message||report.decision?.reason||'Решение относится к этой исторической проверке.';
const noData=report.market_count===0;
let html='<article class="panel scanner-verdict"><div class="panel-header"><div><span class="eyebrow">ПОСЛЕ ИЗДЕРЖЕК · ФИНАЛЬНАЯ ПРОВЕРКА</span><h2>'+esc(selected?'Кандидат для бумажной проверки':noData?'История не получена':'Устойчивый кандидат не найден')+'</h2></div>'+badge(selected?'PAPER REVIEW':noData?'НЕТ ДАННЫХ':'ВНЕ РЫНКА',selected?'good':'warning')+'</div><p class="detail-description">'+esc(translate(decision))+'</p><div class="inline-metrics">'+inlineMetric('Рынок выбран на обучении',primary||'—')+inlineMetric('Прошёл окончательный отбор',selected||'Ни один')+inlineMetric('Рынков с данными',num(report.market_count??markets.length,0))+inlineMetric('Профиль правил',verified?profile.name:'Не выбран')+'</div>';
html+='<div class="notice notice-'+(verified?'subtle':'warning')+'">'+esc(verified?'Выбран профиль, правила которого вы подтвердили. Перед сделкой сверяйте действующий договор и состояние аккаунта.':'Действующие правила подходящей фирмы не подтверждены: рекомендованная фирма не установлена. Историческая доходность не подтверждает возможность выплаты.')+'</div>';
if(archive)html+='<div class="notice notice-warning">Архивные котировки прошлых лет. Это повторный исследовательский расчёт; актуальных цен и торгового сигнала здесь нет.</div>';
if(report.warnings?.length)html+='<details class="settings-details"><summary>Методология и ограничения ('+report.warnings.length+')</summary><ul class="reasons-list">'+setupReasons(report.warnings)+'</ul></details>';
html+='</article><div class="scanner-market-list">'+markets.map(market=>{
const research=market.report||{},candidate=itemById(research.strategies||[],research.training_candidate||research.selected_strategy),metrics=candidate?.test_metrics||research.summary||{},data=research.data||{},qualified=typeof market.qualified==='boolean'?market.qualified:selected===market.symbol;
let card='<article class="panel scanner-market"><div class="panel-header"><div><span class="eyebrow">'+esc(market.primary||primary===market.symbol?'ПЕРВЫЙ ВЫБОР ОБУЧЕНИЯ':'КАНДИДАТ ОБУЧЕНИЯ')+'</span><h2>'+esc(market.symbol)+(market.rank!==undefined?' <small>#'+esc(market.rank)+'</small>':'')+'</h2></div>'+badge(qualified?'Пройден отбор':'Не допущен',qualified?'good':'warning')+'</div><p class="scanner-market-period">'+esc(timestamp(data.start))+' — '+esc(timestamp(data.end))+'<br>'+esc(candidate?.name||research.summary?.training_candidate_name||'Нет кандидата стратегии')+' · '+esc(data.timeframe_minutes?num(data.timeframe_minutes,0)+' мин.':'Интервал указан в отчёте')+'</p><div class="inline-metrics">'+inlineMetric('Доходность теста',pct(metrics.net_return_pct),signClass(metrics.net_return_pct))+inlineMetric('Просадка',pct(metrics.max_drawdown_pct))+inlineMetric('Сделок на тесте',num(metrics.total_trades,0))+inlineMetric('Profit factor',num(metrics.profit_factor))+'</div>';
const reasons=[...(market.reasons||[]),...(candidate?.reasons||[])];if(reasons.length)card+='<details class="settings-details"><summary>Причины решения</summary><ul class="reasons-list">'+setupReasons([...new Set(reasons)])+'</ul></details>';
const confidence=market.adjusted_confidence||{};if(Array.isArray(confidence.mean_r_interval))card+='<p class="chart-caption">Описательный '+esc(num(confidence.interval_confidence_pct,0))+'% интервал среднего R: '+esc(num(confidence.mean_r_interval[0],3))+' … '+esc(num(confidence.mean_r_interval[1],3))+'. Это оценка выборки, не вероятность будущей прибыли.</p>';
if(research.config){const costs=research.config;card+='<details class="settings-details"><summary>Издержки и контракт модели</summary><p class="field-help">Комиссия / сторона '+esc(num(costs.fee_bps,2))+' bps; фиксированная комиссия на единицу / сторона '+esc(money(costs.fee_per_unit??0))+'. Полный спред '+esc(num(costs.spread_bps,2))+' bps; проскальзывание / сторона '+esc(num(costs.slippage_bps,2))+' bps.<br>Множитель '+esc(num(costs.contract_multiplier??1,2))+'; шаг объёма '+esc(num(costs.quantity_step,5))+'. Параметры исследования нужно сверить с исполнением вашего брокера.</p></details>';}
if(research.strategies?.length)card+='<button class="button button-secondary" data-use-scan="'+esc(market.symbol)+'" data-scan-job="'+esc(jobId)+'">Открыть исследование <span>→</span></button>';
return card+'</article>';
}).join('')+'</div>';
const firms=report.firm_comparison?.profiles||[];if(Array.isArray(firms)&&firms.length)html+='<article class="panel scanner-firms"><div class="panel-header"><div><span class="eyebrow">ПРАВИЛА И ЭКОНОМИКА АККАУНТА</span><h2>Проверка профилей фирм</h2></div></div>'+firms.map(firm=>'<div class="scanner-firm-row"><div><strong>'+esc(firm.profile_name||firm.profile_id||'Профиль')+'</strong>'+badge({needs_verified_rules:'Нужны актуальные правила',not_supported:'Недостаточно оснований',modeled_positive:'Положительная модель',model_not_positive:'Модель не положительна'}[firm.status]||firm.status||'Не выбран',firm.recommended?'good':'warning')+'</div>'+(firm.simulation?.net_expected_value!==null&&firm.simulation?.net_expected_value!==undefined?'<p class="field-help">Net одной попытки по модели: '+esc(money(firm.simulation.net_expected_value))+'. Модель не подтверждает будущую выплату.</p>':'')+(firm.reasons?.length?'<details class="settings-details"><summary>Причины</summary><ul class="reasons-list">'+setupReasons(firm.reasons)+'</ul></details>':'')+'</div>').join('')+'<p class="field-help">Подтверждение профиля — ваша сверка договора. Сервис не подтверждает согласие фирмы принять такую торговлю или выплатить прибыль.</p></article>';
const errors=report.fetch_errors||report.diagnostics||[];
if(Array.isArray(errors)&&errors.length)html+='<article class="panel scanner-diagnostics"><div class="panel-header"><h2>Недоступные данные</h2>'+badge(errors.length+' рынков','warning')+'</div><ul class="reasons-list">'+errors.map(error=>'<li><strong>'+esc(error.symbol||'Источник')+'</strong> · '+esc(error.error||error.reason||JSON.stringify(error))+'</li>').join('')+'</ul><p class="field-help">При недоступности публичного источника можно запустить архив без сети или исследовать CSV своего брокера в лаборатории.</p></article>';
$('#scanner-output').innerHTML=html;
}
function scheduleScannerPoll(delay=1500) {clearTimeout(scannerPollTimer);if(['queued','running'].includes(state.scanJob?.state))scannerPollTimer=setTimeout(()=>refreshScannerStatus(false),delay);}
async function refreshScannerStatus(manual=true) {
clearTimeout(scannerPollTimer);const button=$('#scanner-refresh');if(manual)busy(button,true,'Проверяем…');
try{
const data=await api(state.scanJob?.id?'/api/scanner/jobs/'+encodeURIComponent(state.scanJob.id):'/api/scanner/jobs/latest');
state.scanJob=Object.prototype.hasOwnProperty.call(data,'job')?data.job:data;
notice('scanner-error','');renderScannerJob();scheduleScannerPoll();
}catch(e){notice('scanner-error','Не удалось получить состояние поиска: '+e.message);scheduleScannerPoll(5000);}
finally{if(manual)busy(button,false);}
}
async function loadScannerLatest() {
try{const data=await api('/api/scanner/jobs/latest');state.scanJob=data.job||null;renderScannerJob();scheduleScannerPoll();}
catch(e){notice('scanner-error','Состояние автопоиска недоступно: '+e.message);}
}
$('#scanner-refresh').addEventListener('click',()=>refreshScannerStatus(true));
$$('input[name="scanner_source"]').forEach(input=>input.addEventListener('change',scannerSourceControls));
$('#scanner-form').elements.namedItem('use_market_costs').addEventListener('change',scannerCostControls);
$('#scanner-interval').addEventListener('change',()=>{const hourly=$('#scanner-interval').value==='1h';$$('option',$('#scanner-range')).forEach(option=>{option.disabled=hourly?option.value!=='3mo':option.value!=='2y';});$('#scanner-range').value=hourly?'3mo':'2y';});
$('#scanner-form').addEventListener('submit',async event=>{
event.preventDefault();if(scannerIsActive())return;const form=event.currentTarget,source=form.elements.namedItem('scanner_source').value,config={};notice('scanner-error','');
try{
['risk_pct','fee_bps','spread_bps','slippage_bps'].forEach(key=>{config[key]=numeric(form,key);});
config.use_market_costs=checked(form,'use_market_costs');
const raw=form.elements.namedItem('symbols').value.trim(),symbols=source==='yahoo'&&raw?[...new Set(raw.split(/[\s,;]+/).filter(Boolean).map(symbol=>symbol.toUpperCase()))]:undefined;
if(symbols&&(symbols.length>12||symbols.some(symbol=>!/^[A-Z0-9.^=\-]{1,32}$/.test(symbol))))throw new Error('Введите до 12 тикеров через запятую: например EURUSD, BTCUSD, AAPL.');
state.scanStarting=true;renderScannerJob();const response=await post('/api/scanner/jobs',{source,symbols,interval:source==='yahoo'?form.elements.namedItem('interval').value:'1d',range:source==='yahoo'?form.elements.namedItem('range').value:'2y',profile_id:form.elements.namedItem('profile_id').value||state.activeProfile,config});
state.scanJob=response.job||response;state.scanStarting=false;renderScannerJob();scheduleScannerPoll();toast('Автопоиск запущен. Можно продолжать работу с другими вкладками.');
}catch(e){state.scanStarting=false;renderScannerJob();notice('scanner-error',e.message);}
});
document.addEventListener('click',async event=>{
const button=event.target.closest('[data-use-scan]');if(!button)return;
busy(button,true,'Открываем исследование…');notice('scanner-error','');
try{const response=await post('/api/scanner/use',{job_id:button.dataset.scanJob,symbol:button.dataset.useScan}),research=response.research||response.report||response;renderResearch(research);navigate('lab');toast('Результат открыт. Для сетапа нужны свежая история, контекст и подтверждённые правила.');}
catch(e){notice('scanner-error',e.message);toast(e.message);}
finally{busy(button,false);}
});

function renderCalendarStatus(data) {
const ready=data.state==='ready'&&data.confirmed===true;
$('#calendar-feed-badge').textContent=ready?'Снимок готов':data.state==='stale'?'Устарел':'Нет данных';
$('#calendar-feed-badge').className='badge badge-'+(ready?'good':'warning');
const provider=data.provider||'Публичный недельный календарь';
$('#calendar-feed-note').textContent=provider+'. '+(ready?'Получен '+timestamp(data.retrieved_at)+', событий: '+num(data.event_count,0)+'. Полноту расписания и торговые запреты проверьте по договору.':data.retrieved_at?'Последний снимок '+timestamp(data.retrieved_at)+'. Без свежей области календарь считается неизвестным.':'Свежего снимка нет; календарь считается неизвестным. Автопоиск обновляет его перед загрузкой рынков.');
notice('calendar-feed-message',data.last_error||'', 'warning');
}
async function loadCalendarStatus(refresh=false) {
const button=$('#refresh-calendar');if(refresh)busy(button,true,'Получаем календарь…');
try{const data=refresh?await post('/api/news/refresh',{}):await api('/api/news/status');renderCalendarStatus(data);if(refresh)toast(data.confirmed?'Публичный снимок календаря обновлён.':'Свежий календарь пока недоступен; причина указана в статусе.');}
catch(e){$('#calendar-feed-badge').textContent='Нет связи';$('#calendar-feed-badge').className='badge badge-warning';notice('calendar-feed-message','Календарь недоступен: '+e.message);}
finally{if(refresh)busy(button,false);}
}
$('#refresh-calendar').addEventListener('click',()=>loadCalendarStatus(true));

let autopilotPollTimer,autopilotRequestSerial=0,autopilotResearchJob=null,autopilotCalendarJob=null;
function renderAutopilot() {
const data=state.autopilot,toggle=$('#autopilot-toggle'),run=$('#autopilot-run');
$('.autopilot-card').setAttribute('aria-busy',String(state.autopilotAction));
toggle.setAttribute('aria-pressed',String(data?.enabled===true));
toggle.disabled=state.autopilotAction||!data;
run.disabled=state.autopilotAction||!data||data.running===true||scannerIsActive();
$('#autopilot-refresh').disabled=state.autopilotAction;
$('#autopilot-results').disabled=!(data?.job_id||state.scanJob?.id);
if(!data){if(state.autopilotError){$('#autopilot-badge').textContent='Нет связи';$('#autopilot-description').textContent='Состояние автоматического поиска сейчас недоступно.';notice('autopilot-error',state.autopilotError);}return;}
toggle.innerHTML=state.autopilotAction?'Сохраняем…':data.enabled?'Остановить автопроверки <span>Ⅱ</span>':'Включить автопроверки <span>→</span>';
const label=data.running?(data.state==='stalled'?'Проверка задержана':data.enabled?'Проверяет рынки':'Завершает проверку'):data.enabled?(data.last_error?'Ожидает повтора':data.state==='waiting_for_idle'?'Ждёт свободного окна':'Включён'):'Выключен';
$('#autopilot-badge').textContent=label;
$('#autopilot-badge').className='badge badge-'+(data.last_error?'warning':data.enabled?'good':'neutral');
$('#autopilot-description').textContent=data.running?(data.enabled?'Проверка выполняется в фоне. Решение и причины появятся на экране сетапов.':'Новые автоматические проверки остановлены. Текущая проверка завершится и сохранит результат.'):data.enabled?'По расписанию проверяем рынки и сохраняем причины допуска или отказа.':'Автоматические проверки остановлены. Можно включить расписание или найти сетапы одной кнопкой.';
$('#autopilot-last-attempt').textContent=data.last_attempt_at?timestamp(data.last_attempt_at):'Ещё не было';
$('#autopilot-next-attempt').textContent=!data.enabled&&!data.running?'Остановлен':data.next_attempt_at?timestamp(data.next_attempt_at):data.running?'После завершения':'Ожидается расписание';
$('#autopilot-result').textContent=data.running?'Проверка выполняется':data.result_ready?(data.selected_symbol?'Прошёл исторический отбор: '+data.selected_symbol:'Допустимая стратегия не найдена'):data.last_error?'Нужна повторная проверка':data.job_id?'Результат пока не готов':'Результатов пока нет';
const error=state.autopilotError||(data.last_error?(typeof data.last_error==='string'?data.last_error:JSON.stringify(data.last_error)):'');
notice('autopilot-error',error,state.autopilotError?'error':'warning');
if(state.autopilotError){$('#autopilot-badge').textContent='Требует внимания';$('#autopilot-badge').className='badge badge-warning';}
}
function scheduleAutopilotPoll() {
clearTimeout(autopilotPollTimer);
if(state.autopilot&&(state.autopilot.enabled||state.autopilot.running))autopilotPollTimer=setTimeout(()=>loadAutopilotStatus(),state.autopilot.running?5000:20000);
}
async function synchronizeAutopilotResearch(data) {
if(data.running||!data.result_ready||!data.job_id||autopilotResearchJob===data.job_id)return;
if(state.research?.autopilot_job_id===data.job_id){autopilotResearchJob=data.job_id;return;}
const job=data.job_id,previous=state.research;
try{
const response=await api('/api/research/latest');
if(state.autopilot?.job_id!==job||state.autopilot.running)return;
autopilotResearchJob=job;
if(response.research?.autopilot_job_id===job&&state.research===previous)renderResearch(response.research);
}catch(e){if(state.autopilot?.job_id===job){state.autopilotError='Результат поиска сохранён, но отчёт не удалось показать: '+e.message;renderAutopilot();}}
}
async function loadAutopilotStatus() {
clearTimeout(autopilotPollTimer);if(state.autopilotAction)return;
const serial=++autopilotRequestSerial;
try{
const response=await api('/api/autopilot');if(serial!==autopilotRequestSerial||state.autopilotAction)return;
state.autopilot=response.autopilot||response;state.autopilotError='';renderAutopilot();
if(state.autopilot.job_id&&state.autopilot.job_id!==state.scanJob?.id)await loadScannerLatest();
await synchronizeAutopilotResearch(state.autopilot);
if(state.autopilot.job_id&&!state.autopilot.running&&autopilotCalendarJob!==state.autopilot.job_id){autopilotCalendarJob=state.autopilot.job_id;await loadCalendarStatus();}
}catch(e){if(serial!==autopilotRequestSerial)return;state.autopilotError='Состояние автопилота недоступно: '+e.message;renderAutopilot();}
finally{if(serial===autopilotRequestSerial&&!state.autopilotAction)scheduleAutopilotPoll();}
}
async function changeAutopilot(payload) {
if(state.autopilotAction)return;clearTimeout(autopilotPollTimer);++autopilotRequestSerial;state.autopilotAction=true;state.autopilotError='';renderAutopilot();notice('autopilot-error','');
try{
const response=await post('/api/autopilot',payload);state.autopilot=response.autopilot||response;state.autopilotError='';renderAutopilot();
if(state.autopilot.job_id)await loadScannerLatest();
await synchronizeAutopilotResearch(state.autopilot);
if(state.autopilot.job_id&&!state.autopilot.running&&autopilotCalendarJob!==state.autopilot.job_id){autopilotCalendarJob=state.autopilot.job_id;await loadCalendarStatus();}
toast(payload.action==='run'?(state.autopilot.running?'Проверка запущена. Решение появится на экране сетапов.':'Запрос проверки обработан. Состояние показано в карточке.'):state.autopilot.enabled?'Автопроверки включены. Решения будут обновляться по расписанию.':'Автоматические проверки остановлены.');
}catch(e){state.autopilotError='Изменение автопилота не выполнено: '+e.message;notice('autopilot-error',state.autopilotError);toast(e.message);}
finally{state.autopilotAction=false;renderAutopilot();scheduleAutopilotPoll();}
}
$('#autopilot-toggle').addEventListener('click',()=>{if(state.autopilot)changeAutopilot({enabled:!state.autopilot.enabled});});
$('#autopilot-run').addEventListener('click',()=>changeAutopilot({action:'run'}));
$('#autopilot-refresh').addEventListener('click',loadAutopilotStatus);
$('#autopilot-results').addEventListener('click',()=>{navigate('scanner');loadScannerLatest();});

function renderUpdates() {
const data=state.updates,apply=$('#apply-update'),check=$('#check-updates');
check.disabled=state.updateAction;
apply.disabled=state.updateAction||!data||!data.configured||data.mode==='development'||data.can_apply!==true||data.busy===true||data.restart_required===true;
$('#tab-updates').setAttribute('aria-busy',String(state.updateAction));
if(!data)return;
const remoteChecked=Boolean(data.latest_commit||data.latest_version);
$('#update-current-version').textContent=data.current_version?'v'+data.current_version:'—';
$('#update-current-commit').textContent=data.current_commit?String(data.current_commit).slice(0,8):'Скачанная версия';
$('#update-latest-version').textContent=data.latest_version?'v'+data.latest_version:remoteChecked&&data.available===false?'Без изменений':'Не проверена';
$('#update-latest-commit').textContent=data.latest_commit?String(data.latest_commit).slice(0,8):'Нажмите «Проверить»';
$('#update-repository').textContent=data.repository||'Не настроен';
$('#update-branch').textContent=data.branch||'—';
const label=data.restart_required?'Нужен перезапуск':data.busy?'Обновление идёт':!data.configured?'Нет источника':data.available===true?'Новая версия':remoteChecked&&data.available===false?'Актуальная версия':'Не проверено';
$('#update-badge').textContent=label;
$('#update-badge').className='badge badge-'+(data.restart_required?'warning':data.available===true?'good':'neutral');
if(data.mode==='development')notice('update-mode-note','Обновление проверяется здесь; применение доступно в скачанной установленной копии.','subtle');
else if(!data.configured)notice('update-mode-note','Источник обновлений не настроен. Проверьте конфигурацию установки.','warning');
else if(data.restart_required)notice('update-mode-note','Обновление установлено. Перезапустите приложение, чтобы начать работу с новой версией.','warning');
else if(data.can_apply!==true)notice('update-mode-note','Установка сейчас недоступна. Нажмите «Проверить», чтобы уточнить состояние обновления.','warning');
else notice('update-mode-note','');
}
function updateProgress(active,title='',description='') {
state.updateAction=active;$('#update-progress').hidden=!active;
$('#update-progress-title').textContent=title;$('#update-progress-description').textContent=description;
renderUpdates();
}
async function loadUpdateStatus() {
try{state.updates=await api('/api/updates/status');renderUpdates();}
catch(e){$('#update-badge').textContent='Нет связи';notice('update-message',e.message);}
}
async function checkUpdates() {
if(state.updateAction)return;
notice('update-message','');updateProgress(true,'Проверяем GitHub','Сравниваем вашу копию с опубликованной версией.');
try{
state.updates=await post('/api/updates/check',{});renderUpdates();
$('#update-check-note').textContent='Проверено: '+timestamp(new Date().toISOString())+'. Следующая проверка — по вашему нажатию.';
notice('update-message',state.updates.available===true?'На GitHub есть обновление. Установите его кнопкой «Обновить из GitHub».':'Ваша копия соответствует опубликованной версии.','success');
}catch(e){notice('update-message','Проверка не завершена: '+e.message);}
finally{updateProgress(false);}
}
async function waitForUpdatedServer(result) {
const deadline=Date.now()+60000;
while(Date.now()<deadline){
await new Promise(resolve=>setTimeout(resolve,1000));
const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),2000);
try{
const response=await fetch('/api/health',{cache:'no-store',headers:{'Accept':'application/json'},signal:controller.signal});
if(!response.ok)continue;
const health=await response.json();
if((!result.commit||health.commit===result.commit)&&(!result.version||health.version===result.version)){location.reload();return true;}
}catch{}finally{clearTimeout(timer);}
}
return false;
}
async function applyUpdate() {
if(state.updateAction||$('#apply-update').disabled)return;
notice('update-message','');updateProgress(true,'Проверяем и устанавливаем обновление','Сохраняем резервную копию и заменяем файлы программы. Не закрывайте приложение.');
try{
const result=await post('/api/updates/apply',{});
if(!result.updated){await loadUpdateStatus();notice('update-message','Уже установлена последняя опубликованная версия.','success');return;}
state.updates={...state.updates,restart_required:result.restart_required!==false,available:false};renderUpdates();
if(result.restarting){
updateProgress(true,'Запускаем новую версию','Страница обновится автоматически, когда приложение снова будет готово.');
if(!await waitForUpdatedServer(result))notice('update-message','Обновление установлено. Автоматический перезапуск не подтвердился: перезапустите приложение через лаунчер и обновите эту страницу.','warning');
}else notice('update-message','Обновление установлено. Перезапустите приложение, затем обновите эту страницу.','success');
}catch(e){notice('update-message','Обновление не установлено: '+e.message);}
finally{updateProgress(false);}
}
$('#check-updates').addEventListener('click',checkUpdates);
$('#apply-update').addEventListener('click',applyUpdate);
$('#open-updates').addEventListener('click',()=>{navigate('updates');checkUpdates();});

window.addEventListener('hashchange',()=>navigate(location.hash.slice(1),false));
async function initialize() {
navigate(location.hash.slice(1),false);setJournalDates();editProfile(null);scannerCostControls();$('#setup-form').elements.namedItem('sentiment_observed_at').value=localDateInput(new Date());
try{
const data=await api('/api/bootstrap');state.profiles=data.profiles||[];state.strategies=data.strategies||[];
let saved;try{saved=localStorage.getItem('prop-lab-profile');}catch{}
state.activeProfile=itemById(state.profiles,saved)?saved:state.profiles[0]?.id;
renderProfiles();renderCatalog();renderJournal(data.journal||{trades:[],stats:{}});
if(state.activeProfile)selectProfile(state.activeProfile);
if(data.symbols?.length)$('#research-symbol').innerHTML=data.symbols.map(symbol=>'<option>'+esc(symbol)+'</option>').join('');
$('#webhook-status').textContent=data.webhook_configured?'Приём событий настроен. Заявки не исполняются.':'Приём webhook не настроен. Для подключения задайте WEBHOOK_TOKEN в окружении сервера; секрет не показывается в интерфейсе.';$('#app-version').textContent=data.version?'v'+data.version:'—';$('#connection-status').textContent='Локальный сервер';$('#connection-status').className='connection connected';
if(data.latest_research){renderResearch(data.latest_research);}loadSignals();loadUpdateStatus();loadScannerLatest();loadAutopilotStatus();loadFirmReview();loadCalendarStatus();loadTraderBoard();loadReplayDiary();
}catch(e){notice('global-error',e.message);$('#connection-status').textContent='Нет связи';$('#connection-status').className='connection disconnected';}
}
initialize();
