"""Data-availability bootstrap for direct stdlib ZoneInfo lookup on Windows.

Kept separate from frozen research producers: no trading rules or TZif bytes
change. Existing host data remains preferred to the verified bundled database.
"""
from pathlib import Path
import zoneinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


_BUNDLED_ROOT = Path(__file__).resolve().parent / "tzdata"


def ensure_new_york_timezone():
    """Resolve NY normally, registering existing TZif data only if unavailable.

    Windows often has neither a system IANA database nor the optional PyPI
    tzdata package. Append the existing package root only after ordinary lookup
    fails. Missing or corrupt fallback data still fails loudly; no handwritten
    DST rules or timezone substitutions are used.
    """
    try:
        return ZoneInfo("America/New_York")
    except ZoneInfoNotFoundError:
        current = tuple(zoneinfo.TZPATH)
        fallback = str(_BUNDLED_ROOT)
        if fallback not in current:
            zoneinfo.reset_tzpath((*current, fallback))
        return ZoneInfo("America/New_York")
