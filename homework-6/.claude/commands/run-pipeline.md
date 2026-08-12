---
description: Run the multi-agent banking pipeline end-to-end and summarise the results
allowed-tools: Bash, Read, Glob
---

# Run the multi-agent banking pipeline

Run the pipeline end-to-end from `homework-6/` and report what happened.

## Steps

1. **Check the input exists.** Confirm `homework-6/sample-transactions.json` is present and report
   how many records it holds. If it is missing, stop and say so — do not invent input data.
2. **Clear the shared directories.** `integrator.py` resets `shared/` by default; run it without
   `--no-reset` so `input/`, `processing/`, `output/`, `results/`, `reports/`, `audit/` and
   `quarantine/` all start empty.
3. **Run the pipeline:**
   ```bash
   cd homework-6 && .venv/bin/python integrator.py
   ```
   (fall back to `python3 integrator.py` if the virtualenv is absent — the pipeline itself needs
   no third-party packages).
4. **Summarise `shared/results/`**: total processed, and the count per terminal status
   (`settled` / `held` / `rejected`). Read `shared/reports/pipeline-summary.md` for the
   aggregated view rather than re-deriving it by hand.
5. **Report every transaction that did not settle**:
   - rejected → list the `rejection_reasons` codes;
   - held → list the `compliance.hold_reasons` and the fraud `risk_score`.
6. **Confirm reconciliation**: the run prints `reconciled=yes` when every input record reached a
   terminal state and `input/` + `output/` are empty. If it prints `reconciled=NO`, treat that as a
   failure, show the pending count and inspect `shared/quarantine/`.

## Report format

Present a short table — transaction id, status, amount, risk score, reason — followed by one line
per anomaly. Do not paste the whole JSON. If the exit code is non-zero, say so explicitly and show
the stderr line rather than describing the run as successful.
