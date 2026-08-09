# Screenshots — Homework 4

Two groups of evidence.

## A. The agent pipeline in action

Rendered from the **real transcripts** of the recorded run `20260810-002935`. Each image is the actual
terminal output of `run-pipeline.sh` / `pytest`, converted to PNG by
[`pipeline/render_terminal.py`](../../pipeline/render_terminal.py); the raw text it was rendered from
is committed next to it in [`transcripts/`](transcripts/), so every line is checkable.

| Screenshot | Shows | Raw transcript |
|---|---|---|
| [`01-pipeline-run.png`](01-pipeline-run.png) | Single-command run: preflight, all six stages with their model / auto-loaded skill / output, the security gate, and the final summary table with per-stage duration and cost | [`02-dry-run.txt`](transcripts/02-dry-run.txt), [`01b-pipeline-summary.txt`](transcripts/01b-pipeline-summary.txt) |
| [`02-agents-live.png`](02-agents-live.png) | Two agents working live: `research-verifier` (Opus 5) checking file:line claims and re-running reproductions, `bug-fixer` (Sonnet 5) editing files and running `pytest` after every change | [`03-agent-verifier.txt`](transcripts/03-agent-verifier.txt), [`04-agent-fixer.txt`](transcripts/04-agent-fixer.txt) |
| [`03-fixes-applied.png`](03-fixes-applied.png) | `diff -u` of the pre-fix snapshot against the fixed source — the actual code changes the `bug-fixer` agent made to `stats.py`, `storage.py`, `auth.py` | [`05-fixes-diff.txt`](transcripts/05-fixes-diff.txt) |
| [`04-security-scan.png`](04-security-scan.png) | `security-report.md`: review scope, severity counts (0 CRITICAL / 0 HIGH / 1 MEDIUM / 4 LOW / 1 INFO) and the first finding in full | [`06-security-report.txt`](transcripts/06-security-report.txt) |
| [`05-unit-tests.png`](05-unit-tests.png) | `pytest -v` — 32 baseline + 17 generated = **49 passed**; one generated file run in isolation; and the independent check that 10 of the generated tests **fail** against the pre-fix source | [`07-tests-after.txt`](transcripts/07-tests-after.txt), [`08-tests-prefix-proof.txt`](transcripts/08-tests-prefix-proof.txt) |

The full run transcript (all six stages, 120 lines) is [`transcripts/01-pipeline-run.txt`](transcripts/01-pipeline-run.txt).
Complete per-stage logs and raw result metadata live in [`../../artifacts/logs/20260810-002935/`](../../artifacts/logs/20260810-002935/).

## B. The Claude Code session that built this homework

`4_1.png` … `4_19.png` — screen captures of the interactive Claude Code session (Opus 5, CLI v2.1.226)
that produced this submission, in chronological order: the design interview and the stack / runtime /
evidence decisions (`4_1`), the proposed design including the per-agent model table and the two skills
(`4_5`), app scaffolding and agent/skill authoring, the runner implementation and the moment the
pipeline was launched for real (`4_14`), and the verification and documentation pass that closed the
work (`4_19`).

These document the **AI-assisted development of the pipeline**; group A documents the **pipeline's own
agents doing the graded work**.
