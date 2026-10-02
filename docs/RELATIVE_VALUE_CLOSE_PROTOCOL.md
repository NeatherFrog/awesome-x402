# Close-confirmed residual execution interpretation

This is a new preregistered **execution interpretation of the existing48 BTCETH
relative-value variants**, not48 independent new strategies or improved alpha.
The original conservative hourly-corner study remains frozen and unchanged. Its
returns were lower bounds under an intentionally adverse spread-stop model.
Independent BTC/ETH hourly corners need not occur simultaneously and therefore
cannot demonstrate that a live spread stop actually triggered.

The original economic hypotheses, all48 signal/hedge/risk/cost/holding parameters,
funding rules, physical isolated collateral, precision assumptions, source data
and common8%-monthly objective are unchanged. All2024–2026 market history is
generally inspected; this is adaptive research, not a globally blind test.

## Exactly three reviewed AST changes

`propdesk/relative_value_close.py` clones the original simulation function. An
AST regression test verifies exact structural equality except these changes:

1. A held pair's residual stop uses the **previous synchronized closed-hour
   BTC/ETH prices**. Crossing frozen3.5sigma triggers execution at the next open.
   A current opening gap alone does not create a previously unknown stop order.
2. The artificial intrabar residual-stop branch based on independent adverse
   corners is removed. There is no claimed native intrabar spread stop.
3. Funding-credit suppression for ambiguous intrabar exits now depends only on
   possible individual-leg liquidation. The removed spread-stop rule cannot
   invalidate an otherwise eligible funding settlement.

Entry gap cancellation is unchanged. The existing frozen-model target remains
prior-close known and fills at next open. Individual-leg **opening/intrabar
liquidation checks**, adverse/favorable portfolio bounds and liquidation-before-
positive-funding-credit priority remain unchanged. Worst/peak risk bounds can
still reject an otherwise profitable close-signal strategy: that conservative
risk-envelope rejection must be distinguished from economic signal PNL.

## Actual funding, money and costs

Both legs are actual Binance USD-M perpetuals, with recorded exact settlement
timestamps. T+2milliseconds is after T orders, cannot finance them, and new holdings need
60seconds entitlement. Open exits avoid later events. Mark prices and exact
liquidation tiers are unavailable; trade-bar proxies remain provisional. Positive
funding cannot rescue an earlier possible individual liquidation. Both baseline
and doubled-cost simulations must have zero liquidation or unfunded deficit.

The single physical100,000 account supplies both isolated margins, entry fees and
all subsequent capital. Gross entry cap2x, isolated leverage2x and risk0.25/0.5%
initial account are unchanged. Every one of the four leg-sides pays5bps fee,
2bps adverse slippage and half of1bp full spread. Fees, quantity filters and
maintenance assumptions are not executable account certifications. No resizing,
capital injection or favorable cost substitution follows an outcome.

## Research order and accounting

Freeze all new/original producer hashes, parent report/protocol hashes, source
bindings and `docs/EIGHT_PERCENT_PROTOCOL.json` before outcomes. Run **TRAIN2024
only** first, including original chronological CV folds and doubled-cost stress.
Every parameter's economic cost decomposition is retained:

`gross_price_PNL = net_PNL + fees + adverse_fill_cost - funding_PNL`.

This is an accounting identity at the **same modeled quantities and exits**, not
a resized zero-cost backtest. It is valid absent liquidation/unpaid deficits;
those cases carry an explicit invalid-identity flag and cannot qualify. This
separates price-signal economics from fees/funding and adverse account bounds.

TRAIN requires positive net/doublecost return, adverse account drawdown<=10%,
reference daily loss<=5% initial capital,30 completed pairs,60 days, two positive
fixed training folds, and zero base/stress liquidation/debt. If none pass, both
2025 and2026 strategy performance remain unopened. If any pass, one fixed
highest-score primary is locked before OOS; this first run still opens neither
window. Optional later `--evaluate-locked` evaluates exactly that primary and
stops after any failure, with no alternative or rescaling.

The common OOS8% geometric-calendar-month objective,99% dependence-aware daily
confidence screen, six full months,60 completed pairs, median/positive-month/
chronological-half checks and drawdown limits remain unchanged. Any retrospective
pass still lacks genuinely new future observations, exact prop contract/stage/
withdrawal replay and executable mark/order validation. It is not an8% monthly
cash payout claim or a guarantee for each month.

```sh
python -m unittest tests.test_relative_value_close
python scripts/research_relative_value_close.py --freeze
python scripts/research_relative_value_close.py --run
# Only after a valid TRAIN primary exists, without changing its lock:
python scripts/research_relative_value_close.py --evaluate-locked
```

No actual orders, Telegram alerts, payouts, source substitution or globally blind
history claims occur. Original archive CC BY-NC-SA restrictions and personal
non-production research scope remain recorded.
