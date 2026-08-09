# Homework 4 — 4-Agent Bug-Fix Pipeline (Design)

**Date**: 2026-08-10
**Author**: Simon Darienko
**Source requirements**: `homework-4/TASKS.md`

## Goal

Deliver a bug-fix pipeline of AI agents that runs **end to end from a single command**, operating on a
small self-contained application that ships with intentional defects. The pipeline must produce real
artifacts (research, verified research, plan, fix summary, security report, test report), apply real
code fixes, and generate real unit tests.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| App stack | Python 3 (stdlib only) + pytest | Consistent with `homework-2`; no runtime dependencies to install beyond pytest |
| App shape | CLI + library modules | Deterministic, easy to unit-test, no server lifecycle in the pipeline |
| Agent runtime | `claude -p` (Claude Code headless) driven by `run-pipeline.sh` | Real LLM agents, real artifacts; no bespoke SDK glue |
| Caching | Stage is skipped when its declared `output` artifact already exists; `--force` re-runs | A reviewer can replay the pipeline for free and inspect committed artifacts, then regenerate on demand |
| Screenshots | Real terminal transcripts rendered to PNG | Evidence is genuine tool output, not a mockup; raw `.log` files are committed alongside |

## Component 1 — Mini application (Task 5)

`homework-4/src/`, entry point `python -m src.cli`:

| Module | Responsibility |
|---|---|
| `models.py` | `Task` dataclass, `Priority`/`Status` vocabularies, serialization |
| `storage.py` | JSON-file task store (load/save/add/all), `export_report` to a path |
| `auth.py` | API-token check guarding admin commands |
| `stats.py` | Aggregate statistics over a task collection |
| `cli.py` | Sub-commands `add`, `list`, `stats`, `export`, `admin` |

### Seeded defects

Documented in `context/bugs/BUG-001/bug-context.md` as one support report with three symptoms.

- **D1 (functional)** — `stats.average_completion_days()` divides by `len(completed)` without an
  empty guard → `ZeroDivisionError` whenever no task is completed.
- **D2 (functional)** — `list --sort priority` sorts by the raw priority *string*, so ordering is
  alphabetical (`high, low, medium, urgent`) instead of by severity rank.
- **D3 (security)** — `auth.py` carries a hardcoded fallback token, compares tokens with `==`
  (non-constant-time), and `storage.export_report()` joins a user-supplied filename onto the export
  directory without validation → path traversal outside the export root.

`tests/` ships with a small passing baseline suite that does **not** cover the defects, so
"run tests after each change" is meaningful and the generated tests add real coverage.

## Component 2 — Pipeline runner

`homework-4/run-pipeline.sh` — one command, six stages, strict order:

```
bug-researcher → research-verifier → bug-planner → bug-fixer → security-verifier → unit-test-generator
```

Four of these are the required graded agents (research-verifier, bug-fixer, security-verifier,
unit-test-generator); bug-researcher and bug-planner are the supporting stages named in the required
run order.

Per stage the runner:

1. Parses the agent's YAML frontmatter: `model`, `skills`, `output`, `allowed_tools`.
2. Builds the system prompt from the agent body **plus the full text of every file listed in
   `skills:`** — this is how skills load automatically, with no manual per-agent invocation.
3. Invokes `claude -p --model <model> --append-system-prompt <agent+skills> <task prompt>`.
4. Verifies the declared `output` artifact exists; missing artifact = stage failure = pipeline stop.
5. Tees stdout to `artifacts/logs/<run-id>/<NN>-<stage>.log`.

Flags: `--force` (ignore cache), `--from <stage>`, `--only <stage>`, `--bug <ID>`, `--dry-run`,
`--help`.

**Security gate**: after `security-verifier`, the runner greps `security-report.md` for
`CRITICAL`/`HIGH` findings and prints a prominent warning (the agent writes reports only and never
edits code, per its spec), then continues to test generation so the run always yields a full artifact
set.

## Component 3 — Model assignment

| Agent | Model | Why |
|---|---|---|
| bug-researcher | `claude-sonnet-5` | Mechanical breadth-first code search; volume over depth |
| research-verifier | `claude-opus-5` | Fact-checking file:line claims and grading quality — errors here poison every later stage |
| bug-planner | `claude-opus-5` | Design decisions and exact before/after code |
| bug-fixer | `claude-sonnet-5` | Executes an already-specified plan; routine edits |
| security-verifier | `claude-opus-5` | Adversarial reasoning about injection, secrets, traversal |
| unit-test-generator | `claude-sonnet-5` | Template-driven test scaffolding under the FIRST skill |

## Component 4 — Skills

- `skills/research-quality-measurement.md` — five graded levels (A `VERIFIED` … E `UNRELIABLE`) with
  explicit thresholds over three measured dimensions (reference accuracy, snippet fidelity,
  root-cause coverage), a scoring procedure, and the mandatory section list for
  `verified-research.md`.
- `skills/unit-tests-FIRST.md` — Fast / Independent / Repeatable / Self-validating / Timely, each
  with pytest-specific do/don't rules and a self-check table the test generator must fill in inside
  `test-report.md`.

## Artifacts

`homework-4/context/bugs/BUG-001/`:

```
bug-context.md
research/codebase-research.md
research/verified-research.md
implementation-plan.md
fix-summary.md
security-report.md
test-report.md
```

## Error handling

- Any stage exiting non-zero, or failing to write its declared output, aborts the pipeline with the
  failing stage name and log path.
- `bug-fixer` stops and documents in `fix-summary.md` if the test suite fails after a change, rather
  than continuing to the next change.
- Missing `claude` CLI, missing Python, or missing pytest is detected up front by a preflight check.

## Testing

- Baseline suite must pass before the pipeline runs (pre-fix state, defects uncovered).
- After the pipeline: full suite (baseline + generated) must pass, and the previously failing
  reproduction cases must now be covered.
- Runner behavior itself is verified by `--dry-run` (stage order, model per stage, cache decisions).
