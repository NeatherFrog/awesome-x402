# Subscription research worker

This optional worker runs useful, bounded research reviews through the official
Codex CLI using its existing **ChatGPT login**. It does not call the separately
billed OpenAI API, trade, send Telegram notifications, modify strategy source or
activate subscription resets. A continuously operating market scanner is a
separate service; model tokens are used for research jobs rather than each tick.

## Verified official interface

On 2026-10-02, the installed CLI reported `codex-cli 0.159.0-alpha.3`.
`codex login status` reported `Logged in using ChatGPT`. Its installed help
confirmed native `--search`, noninteractive `exec`, read-only sandbox,
`--json`, `--output-schema`, `--output-last-message`, `--ephemeral`,
`--ignore-user-config` and `--strict-config`.

Primary sources:

- [Official Codex repository README](https://github.com/openai/codex/blob/main/README.md)
  describes installing official CLI and signing in with a ChatGPT plan.
- [Noninteractive documentation pointer](https://github.com/openai/codex/blob/rust-v0.159.0-alpha.3/docs/exec.md)
  links to [official noninteractive documentation](https://developers.openai.com/codex/noninteractive).
- [Pinned official configuration schema](https://github.com/openai/codex/blob/rust-v0.159.0-alpha.3/codex-rs/core/config.schema.json)
  defines `sqlite_home`, `log_dir` and `history.persistence="none"`.
- [Pinned installation-ID implementation](https://github.com/openai/codex/blob/rust-v0.159.0-alpha.3/codex-rs/core/src/installation_id.rs)
  and [in-process startup](https://github.com/openai/codex/blob/rust-v0.159.0-alpha.3/codex-rs/app-server/src/in_process.rs)
  explain the current cloud runtime blocker below.

GitHub sources and installed help were retrieved. The developer-documentation
pages themselves returned proxy CONNECT 403 in this host and were not read.
Compatibility with an arbitrary older CLI is not assumed: missing flags cause
preflight refusal; unsupported configuration is rejected under strict mode.

## Current host execution result

CLI/auth preflight succeeds, but **actual subscription research has not run in
this cloud host**. An isolated one-job smoke invocation failed before reaching a
model with:

```text
Error: failed to initialize in-process app-server client: Read-only file system (os error 30)
```

One meaningful diagnostic retry used the officially supported SQLite/log paths
inside the job's writable artifact directory and disabled history persistence.
It failed at the same pre-initialization step. No model token usage was reported.
The queue now records `runtime_unavailable` and pauses rather than retrying.

The pinned implementation unconditionally opens `$CODEX_HOME/installation_id`
for read **and write/create**, then locks it during in-process startup. This
host's existing Codex home is immutable. Redirecting SQLite and logs cannot
remove that write requirement. The worker preserves existing `CODEX_HOME` and
auth; it does not copy credentials, switch home, widen the model's sandbox or
request API keys. A normal local official CLI installation with a writable
Codex home can use the worker; successful local execution still needs to be
verified. Preflight therefore explicitly reports
`runtime_execution_verified=false`.

## Durable queue and bounded work

State lives under `.local/research-jobs/`, excluded from source/distribution:

```text
queue.sqlite3                         durable queue, leases and pause state
registry.json                        readable exported registry
artifacts/<job-id>/attempt-<number>/  request, frozen context, events, report
```

The SQLite queue deduplicates by task type, exact question, frozen context and
runner version. Changed research evidence creates a new task; reopening the
queue preserves old evidence. Approved context is bounded UTF-8 research docs
(`docs/*.md`, `docs/*.json`) and optionally `propdesk/liquidity.py`. Private state,
credentials, external paths and escaping symlinks cannot be selected as context.
The caller's selected documents must themselves be suitable for research use.

There is one transactional worker lease and one active job. Crashed worker/job
leases are recoverable. Transient failures and timeouts retry with exponential
backoff starting at 60 seconds, at most three attempts. The durable queue defaults
to at most 1,000 total jobs. Each session runs at most 24 hours and 100 attempts
by default (configurable up to 1,000); each job defaults to 15 minutes and is
bounded by the remaining session time. Empty queues normally stop, or poll at
an explicitly chosen interval until the session deadline.

The six seeded jobs audit primary-source evidence, independently review each of
the four frozen liquidity/FVG variants, and review the recorded experimental
results. They request falsification tests and failure conditions, rather than
claiming that a chart/course demonstrates profit. Repeated `seed` calls deduplicate
identical context. More useful jobs can be enqueued, within the same bounds.

## Execution and outputs

Each attempt receives a separate frozen context directory. The official CLI runs
with `--sandbox read-only`; only the Python worker and CLI's native final-output
writer create reports. No `--add-dir`, full-access mode, approval-bypass flag or
source patch application is used. SQLite and logs are explicitly redirected to
the attempt's runtime directory; history persistence is disabled. Original auth
location is preserved. User configuration is ignored to prevent accidental
alternate-provider routing, and API-key/provider billing variables are not
forwarded. Ordinary home, existing Codex home and network-proxy settings are
preserved without printing their values.

`--search` enables official native live web search. If unavailable, inaccessible
sources must be marked unavailable/unverified; the worker does not claim to
crawl paid courses. `--no-web` disables that flag. The model returns structured
JSON with a summary, hypotheses, sources with access attribution, limitations
and next tests. Schema and size validation are required before `report.json`
exists. Sources marked checked remain the model's attribution, not independent
verification. Reports never qualify a strategy for live trading automatically.

Events/stdout are capped at 2,000,000 bytes, stderr at 128,000, and final JSON at
256,000. Overruns terminate the process and fail the job. Timeouts terminate the
process group on POSIX or the PID tree on Windows. Potential credential-like
CLI error strings are redacted in saved logs. Ctrl-C also terminates the current
process; lease recovery preserves the interrupted job.

Per-job token usage is recorded **only** when the CLI emits a numeric
`turn.completed.usage` event. Missing usage remains `null`. The worker does not
invent a remaining-token counter, quota-reset clock or pricing estimate.

Quota errors pause the whole queue, preserve the job and stop the session. A
minimum one-hour cooldown must elapse before an explicit `resume`; this does
not mean the subscription quota has recovered. Authentication/runtime failures
also pause until repaired. The worker does not reset quota, probe continuously
after quota rejection, rotate accounts or fall back to paid API access.

## Commands

Install official Codex CLI separately and sign in through its ordinary ChatGPT
flow. Never put API keys or exchange credentials in research questions or docs.
From the project directory:

```bash
python scripts/run_research_worker.py check
python scripts/run_research_worker.py seed
python scripts/run_research_worker.py run --max-jobs 6 --hours 24 --timeout 900
python scripts/run_research_worker.py status
python scripts/run_research_worker.py export
```

For continued bounded polling while new jobs are added:

```bash
python scripts/run_research_worker.py run --idle-wait 10 --hours 24 --max-jobs 100
```

After repairing auth/runtime or recovering subscription access and waiting out
the recorded cooldown:

```bash
python scripts/run_research_worker.py resume
```

This is a command-line background research component, not yet an integrated
application button or proof that jobs run continuously after this chat ends.

## Tests

`python -W error::ResourceWarning -m unittest tests.test_research_runner -v`
checks frozen-context deduplication and reopen, external/private path rejection,
single-worker leases and crash recovery, stale-owner rejection, three-attempt
cap, quota cooldown/pause, retry backoff, real fake-process timeouts/termination,
blocked stdin, auth/runtime stops, bounded logs, schema rejection, actual usage
capture, secret environment exclusion, redaction and bounded seeded jobs.
Those tests use local fake CLI processes; they are not subscription execution
or profitability evidence.
