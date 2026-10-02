"""Prop trading research and paper execution workbench."""

from .timezone_bootstrap import ensure_new_york_timezone as _ensure_new_york_timezone

_ensure_new_york_timezone()
del _ensure_new_york_timezone
