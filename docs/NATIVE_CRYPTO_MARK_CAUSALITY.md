# Retrospective correction of mark96 causal review

The independent review retracts its earlier unconditional causal green for
protocol `682b6ea6df249aee086b3acc35d5d5879af5010612874cef6e1a11fde7bc4f9b`. This correction was discovered after
freeze and real TRAIN outcomes; the original engine, driver, protocol, all96
TRAIN rows, nominal selection and primary ledgers remain byte-identical.

A synthetic BTC old position has a known indicator exit at 2024-01-20 01:00 UTC,
while ETH has a new entry at the same opening. Both prices are flat100 with
high100.02/low99.98; risk1%, hourly decisions, stop2 prior dailyATR. Changing
**only BTC's future whole-bar volume from10 to0** changes ETH's opening quantity
from **998.25 to997.752**. Old BTC exit cash is recovered before new ETH sizing;
shared reservations for two NEW intents did not cover an OLD exit versus NEW
entry. This is a causal execution-model defect, not a claimed market trade.

The full96 TRAIN computation completed;20 nominal gate passes and the fixed
channel5/2 hourly/risk1%/ATR3 selection are retained as historical rejected-model
outputs. Their +10.2642% annual TRAIN return and +9.0515% doubled-friction return
cannot support strategy promotion. No2025 or2026 strategy performance was
opened. There are no live orders, paper/Telegram promotion or payout claims.

The immutable correction receipt is
`data/native-crypto-mark-research/retrospective-causality-audit.json`; it binds
the protocol, original engine, completed report, training-results/selection
and source digests. First repository recording is 2026-10-02T12:07:59.643484Z;
the independent finding was received before that recording. Its positive
pre-outcome audit is retained with this explicit retraction.

A separately registered execution interpreter may reserve ALL new quantities,
cash, gross and risk before any old-close/current-volume/funding outcomes.
Released collateral cannot enlarge another opening in that decision. The same
96 signals/risk/cost choices must remain fixed; no use of these outcomes to
retune alpha or sizing, and independent coupled-case review precedes new returns.
