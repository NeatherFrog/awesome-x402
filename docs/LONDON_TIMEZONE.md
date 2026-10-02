# London session timezone

The new FX-session study uses `Europe/London`, including the historical UK summer-time transitions. Its fallback file is copied without transformation from the installed Debian `tzdata 2026b-0+deb13u1`, IANA release 2026b, `/usr/share/zoneinfo/Europe/London`.

Bundled file: `propdesk/tzdata/Europe/London`; SHA-256: `c85495070dca42687df6a1c3ee780a27cbcb82f1844750ea6f642833a44d29b4`.

Upstream: https://www.iana.org/time-zones . Release: https://data.iana.org/time-zones/releases/tzdata2026b.tar.gz . License: public domain, recorded in the installed `/usr/share/doc/tzdata/copyright`. The host database is preferred; the new study loads this actual TZif fallback when London is unavailable. No original frozen timezone producer was changed.
