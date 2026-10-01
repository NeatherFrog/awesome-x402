# Public economic calendar

PropDesk can retrieve the current Forex Factory weekly calendar from the fixed public HTTPS endpoint
`https://nfs.faireconomy.media/ff_calendar_thisweek.json`, distributed by Fair Economy Media. It requires no account, API key, cookie, or secret. Calendar availability supports conditional paper planning; it does not establish a trading edge or compliance with a particular firm's news policy.

The final production-style check on **1 October 2026** succeeded with HTTP 200: 142 provider rows, current-week coverage, and an independent response hash matching the real background worker cache. [Live provenance](news-live-check.json) records source, UTC timestamps and SHA-256 without redistributing raw rows. Earlier connection failures remain handled as unknown calendars; network availability must be checked on each installation. TLS verification remains enabled.

## Module contract

`CalendarFeed(directory)` stores its optional cache at `directory/news.json`; the application's state directory is normally `.local`. Construction, `status()`, and `context()` never fetch data or create files.

```python
from propdesk.news import CalendarFeed

calendar = CalendarFeed(".local")
status = calendar.refresh()     # Explicit network operation, subject to the TTL.
news = calendar.context()      # Pass as setup context["news"].
status = calendar.status()      # Local inspection only.
calendar.start(enabled=lambda: autopilot.status()["enabled"])
# During server shutdown:
joined = calendar.stop(timeout=12)
```

Each method optionally accepts an aware `datetime` named `now` for deterministic fixtures. Production callers should omit it from `refresh()` so `retrieved_at` and every event's `known_at` reflect the clock after the HTTPS response finishes. They are not provider publication timestamps.

`status()` returns `state` (`ready`, `stale`, or `unknown`), `confirmed`, `retrieved_at`, `observed_at`, `age_seconds`, `event_count`, `coverage`, `body_sha256`, `refresh_due`, `next_refresh_at`, `last_attempt_at`, `last_error`, `provenance`, and `warnings`. Worker diagnostics are `worker_running`, `worker_stopping`, `worker_poll_interval`, and `worker_error`. `context()` returns the setup-compatible news object directly: `confirmed`, `source`, `observed_at`, normalized `events`, `generation: "provider"`, and the provenance/coverage fields. Each event contains only `title`, `currency`, `impact`, `time`, and `known_at`.

The application calls `refresh()` before an explicit market scan and starts the calendar worker while serving. `start(enabled=callback, poll_interval=30)` explicitly creates one non-daemon worker; constructing the feed or reading it never starts one. The callback must promptly return a boolean, normally the persisted autopilot enabled state. While enabled, the worker checks every 30 seconds and refreshes when the one-hour TTL is due, independently of the daily research schedule. Disabling autopilot suspends background network requests. Explicit refresh and background refresh share the same mutex and TTL, so concurrent requests cannot duplicate a fetch.

`start()` returns `True` for a new worker or `False` when one already runs. `stop(timeout=12)` sets its stop signal, interrupts the polling wait, and joins the worker; it returns whether the join completed. Stop is checked after the enabled callback and immediately before starting a refresh. An in-progress HTTPS operation finishes under its transport timeout rather than being killed during a cache write. If a caller chooses a shorter join budget and receives `False`, the thread reference remains available for a later join. Server shutdown should stop the calendar and autopilot workers. Background errors are reported with fixed sanitized messages, without tracebacks or exception contents. The worker never contacts a broker, submits orders, or replaces explicitly supplied manual news context.

## Freshness and coverage

Refreshes are limited to once per hour. The original retrieval time controls successful cache freshness; a failed attempt is also throttled for an hour within the running process. A snapshot can be confirmed only when all of these conditions hold:

- At least one timed event has a recognized economic impact, and the entire response passes validation.
- The retrieval timestamp is neither in the future nor more than six hours old.
- The provider events establish one Sunday–Saturday local week through their explicit UTC offsets, and the current time lies inside that week's conservative UTC coverage.

With different provider offsets, the coverage interval is their intersection. A calendar for a previous week, mixed weeks, ambiguous boundary, empty response, or a response containing only non-economic entries leaves the calendar unknown. Inferred week coverage follows the endpoint's current-week contract; it cannot prove that the provider has included every event.

On a failed refresh, the prior valid cache remains byte-for-byte intact. Its original timestamp and events are retained while it remains fresh and within scope, together with a failure warning. A failure never advances freshness, fabricates an empty checked calendar, or replaces unavailable data with synthetic events. Stale or invalid context has `confirmed: false` and no events for the current decision.

## Validation and bounded transport

The fetcher permits only HTTPS on `nfs.faireconomy.media`, including up to three redirects to that same host. It rejects credentials in URLs, other ports/hosts, and HTTPS downgrades; certificate and hostname verification remain enabled. The fixed request has a ten-second transport timeout, a shared deadline across redirects and bounded body reads, a 1 MiB response cap, and no authentication headers. HTTP/network/TLS errors are sanitized rather than exposing response headers or arbitrary exception details.

The JSON must be finite, contain no repeated object fields, stay within bounded nesting/complexity, and contain 1–200 provider rows. Each row requires a bounded safe title, a recognized currency (`AUD`, `CAD`, `CHF`, `CNY`, `EUR`, `GBP`, `JPY`, `NZD`, `USD`, or `ALL`), an explicit full ISO timestamp with a known UTC offset, and a recognized impact. Dates are normalized to UTC without guessing a timezone. Tentative/all-day text, naive dates, unknown offsets, unsupported currencies or impacts, duplicate events, control characters, and unsafe titles reject the update.

`High`, `Medium`, and `Low` become economic events. Recognized `Holiday` and `Non-Economic` rows remain auditable normalized cache rows but are excluded from economic blackout events with an explicit warning. Their dates still require a known offset. Holidays do not validate exchange sessions, market opening, or firm restrictions. Economic events establish coverage; an unsupported row is never silently dropped to obtain a checked calendar.

The cache is written through a private temporary file and atomic replacement. Loads validate its bounded regular-file format, fixed source/version, normalized content fingerprint, and coverage; symlink cache files/directories are rejected. `body_sha256` identifies the received response. These fingerprints detect accidental inconsistency and support provenance; they are not provider signatures. The cache contains no forecast, actual, previous values, account credentials, or trading instructions.

## Planning limits

The general paper checklist currently treats high-impact events from any supported currency conservatively within 30 minutes before through 15 minutes after the event. This common window does not encode every firm's affected instruments, exception policies, pending-order rules, or execution restrictions. If firm rules restrict news and the calendar is unknown, that uncertainty must remain a blocking prerequisite.

Forecast, actual, and previous values are excluded from signals. A snapshot learned today cannot be used to claim that its information was available during past strategy tests: every `known_at` is today's retrieval time, and historical provider publication times are unverified. This source supplies no sentiment, macro-cycle classification, executable quotes, or profit guarantee.

Validate the module with `python -m unittest tests.test_news -v`. The fixture suite covers UTC conversion and knowledge times, holidays, week boundaries, empty/stale/ambiguous data, cache retention/TTL, live-plan blackout compatibility, finite/bounded JSON, redirect/TLS constraints and shared deadlines, sanitized failures, cache consistency/symlink handling, and the worker's enable/disable, hourly cadence, concurrency, cancellation, and shutdown behavior.

The separately downloaded raw Yahoo OHLC snapshots under `data/current-history/` are local research inputs. Public accessibility does not establish redistribution rights; keep them out of Git and distributable packages unless rights are established. Frozen protocol, source provenance, training locks, hashes, and derived research reports can be retained without republishing the raw quotes.
