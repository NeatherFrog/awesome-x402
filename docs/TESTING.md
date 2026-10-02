# Offline tests and historical replay

Run `python scripts/test_offline.py --quiet` for the application/unit checks.
The Windows CI uses this runner. It runs ordinary failing tests normally.

One immutable integration test in `test_crypto_flow.py` verifies its parent's
actual private historical files. Its bytes are part of the frozen research
protocol and have not been changed to accommodate CI. When **every** bound
private input is absent, the offline runner reports that exact case as **SKIP**,
not a passing historical replay. New unit tests independently check the actual
common/parent protocol and all public producer hashes and prove the production
verifier still rejects unavailable historical inputs.

If any bound private artifact or a dangling input/parent symlink exists, the
original integration test runs normally. Partial or tampered inputs do not
activate the skip. With all actual research inputs present, ordinary
`python -m unittest discover -s tests -q` also runs the full integration check.
No raw observations, original copyrighted paper bodies, exchange credentials
or user journal are added to a release merely to make unit tests pass.
