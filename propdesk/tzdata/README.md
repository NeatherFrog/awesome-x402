# Bundled IANA timezone data

Public-domain TZif fallback for standard Windows CPython without an installed IANA database.
UTC uses datetime.timezone.utc. Europe/Kiev resolves the bundled Europe/Kyiv file.
The system timezone database is preferred whenever available.

Source: installed Debian tzdata package 2026b-0+deb13u1, IANA tzdb release 2026b.
Upstream: https://www.iana.org/time-zones
Release archive: https://data.iana.org/time-zones/releases/tzdata2026b.tar.gz
Original installed files: /usr/share/zoneinfo/<IANA key>. Copied without transformation.
License: public domain, as recorded in /usr/share/doc/tzdata/copyright.
The IANA Time Zone Database is in the public domain.

| IANA key | TZif SHA-256 |
| --- | --- |
| Europe/Prague | `1bd7dd8545e6cf1eb9d419f267a57b00e60857d115e5a309326e3878968b2d9c` |
| Europe/Kyiv | `fb0ae91bd8cfb882853f5360055be7c6c3117fd2ff879cf727a4378e3d40c0d3` |
| America/New_York | `e9ed07d7bee0c76a9d442d091ef1f01668fee7c4f26014c0a868b19fe6c18a95` |
| America/Chicago | `feba326ebe88eac20017a718748c46c68469a1e7f5e7716dcb8f1d43a6e6f686` |
