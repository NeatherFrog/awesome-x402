"""Conditional uncertainty of net monthly growth, never an order permission.

Kept separate from immutable study evaluators. This diagnostic distinguishes
an observed 8% monthly average from evidence for that expected growth rate.
"""
from calendar import monthrange
from datetime import date, timedelta
import math
from .research_stats import bootstrap_mean_ci


def monthly_growth_interval(dates, daily_returns, *, confidence=.99, samples=5000, seed=20261002):
    parsed=[date.fromisoformat(x) for x in dates]
    if len(parsed)!=len(daily_returns) or len(parsed)<14:
        raise ValueError('At least14 complete dated calendar-day returns required')
    if any(b-a!=timedelta(days=1) for a,b in zip(parsed,parsed[1:])):
        raise ValueError('Complete consecutive calendar days required')
    if any(not math.isfinite(x) or x<=-1 for x in daily_returns):
        raise ValueError('Finite returns on positive solvent account equity required')
    months=math.fsum(1/monthrange(x.year,x.month)[1] for x in parsed)
    days_per_month=len(parsed)/months
    logs=[math.log1p(x) for x in daily_returns]
    interval=bootstrap_mean_ci(logs,confidence=confidence,samples=samples,block_length=7,seed=seed)
    converted={key:math.expm1(interval[key]*days_per_month) for key in ('lower','mean','upper')}
    return {'observed_geometric_monthly_growth':converted['mean'],
            'conditional_monthly_log_growth_interval':converted,
            'confidence':confidence,'calendar_days':len(parsed),'elapsed_calendar_months':months,
            'target_monthly_growth':.08,'conditional_lower_bound_above_target':converted['lower']>=.08,
            'block_length_days':7,'samples':samples,'seed':seed,
            'future_target_demonstrated':False,'live_orders':False,
            'limitations':'Conditional moving-block inference assumes representative dependent history. It does not correct adaptive selection, regime changes, execution gaps or prop-stage resets; no future8% guarantee.'}
