# Compatibility with the installed 0.5 updater

The unchanged updater from release commit `9b38ac3cb14427e7a9ce1f6caa61c437bdaca0b0` successfully installed the exact public candidate `6336c37d5bf171d6b002fae38016eeeb77a31a13` into disposable copies of both actual 0.5 distributions. The candidate is on `trading-eight-percent-research`; this check does not claim it has already reached `main`.

The [machine-readable receipt](UPDATE_COMPATIBILITY_0_5.json) records the public archive URL, hashes, original limits, package hashes and all 26 copied research receipt hashes.

| Archive measurement | Actual candidate | Installed 0.5 limit |
|---|---:|---:|
| Compressed bytes | 6,573,119 | 20,971,520 |
| Expanded bytes, including unmanaged files | 38,324,037 | 52,428,800 |
| Files | 402 | 1,000 |
| ZIP entries | 448 | 2,000 |

The actual GitHub archive omits exactly the two designated optional historical reports, `docs/edge-search.json` and `docs/current-research.json`. Their original bytes remain in Git, and the full distribution builder still includes them. This leaves 14,104,763 expanded bytes below the original updater ceiling. Raising the new updater's limit alone would not have fixed the first update from an installed 0.5 version.

Both checks start from the actual generic or Windows 0.5 ZIP and verify every installed source hash before updating. They run the original `apply`, archive validation, backup, installation and state-writing code. The exact public candidate ZIP is fetched first; only the two API responses are supplied locally, with commit metadata pointing to this candidate. The original download-size bound is checked on those bytes. This isolates installation compatibility from the current `main` branch and network availability.

The update installs 327 managed files and sets `restart_required=true`. All 201 original source files have matching backup hashes. Private test state stays unchanged, all 15 public fixture files remain intact, and all 35 bundled Windows runtime files keep their original hashes. No private test contents are included in this receipt.

The updated research board verifies protocol, producer and training-result receipts for all nine completed studies. Every copied receipt matches its frozen original bytes. Because raw research histories are absent, all nine studies correctly report `input_available=false` and `input_hashes_verified=false`; receipt verification does not establish a complete replay or trading profitability.

These checks execute the updater on Linux, including against Windows package contents. They do not execute Windows binaries, Windows-specific locking or the launcher restart. Windows CI and launcher checks remain separate. Repeat this compatibility check against the exact final merge/release archive whenever packaged files change; evidence for this candidate does not automatically cover a later commit.
