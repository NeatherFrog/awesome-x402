"""IANA timezone lookup with dependency-free Windows fallbacks.

CPython's zoneinfo module is standard library, but its timezone database is
usually absent on Windows. Prefer the host database; bundle only the common
prop-account reset zones, retaining real DST transitions through TZif files.
"""
from __future__ import annotations

from datetime import timezone
from functools import lru_cache
from pathlib import Path
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


_BUNDLED_ROOT = Path(__file__).resolve().parent / "tzdata"
_BUNDLED_FILES = {
    "Europe/Prague": "Europe/Prague",
    "Europe/Kyiv": "Europe/Kyiv",
    "Europe/Kiev": "Europe/Kyiv",  # Legacy IANA alias, including the client locale.
    "America/New_York": "America/New_York",
    "America/Chicago": "America/Chicago",
}
_UTC_NAMES = frozenset({"UTC", "Etc/UTC", "GMT", "Etc/GMT", "Zulu", "Etc/Zulu"})
_NAME = re.compile(r"[A-Za-z0-9_+\-]+(?:/[A-Za-z0-9_+\-]+)*\Z")
_system_timezone = ZoneInfo


@lru_cache(maxsize=128)
def _cached_timezone(name):
    try:
        return _system_timezone(name)
    except ZoneInfoNotFoundError:
        if name in _UTC_NAMES:
            return timezone.utc
        filename = _BUNDLED_FILES.get(name)
        if filename is None:
            raise
    # User input never becomes a filesystem path: only explicit mapping values
    # above can select the small bundled public-domain IANA database.
    try:
        with (_BUNDLED_ROOT / filename).open("rb") as stream:
            return ZoneInfo.from_file(stream, key=name)
    except FileNotFoundError:
        raise ZoneInfoNotFoundError("Bundled IANA timezone is missing: " + name) from None


def timezone_for(name):
    """Resolve an IANA key, preserving host-supported zones and UTC/DST.

    Reject filesystem syntax before consulting either source. Unknown valid
    keys raise ZoneInfoNotFoundError; a malformed key raises ValueError.
    """
    if not isinstance(name, str) or not 0 < len(name) <= 128 or not _NAME.fullmatch(name):
        raise ValueError("Invalid IANA timezone name")
    return _cached_timezone(name)
