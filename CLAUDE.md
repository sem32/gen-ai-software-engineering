# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

This is a **homework submission repository** for the "GenAI and Agentic AI for Software Engineering" training course — not a single application. Each `homework-N/` directory is an independent assignment with its own tech stack, source tree, and run instructions. There is no shared build system, no root-level dependencies, and no cross-homework code reuse.

Because assignments are added over time, most `homework-N/` folders start as scaffolding (`src/`, `docs/screenshots/`, `demo/` held open with `.gitkeep`) and are filled in when that homework is worked on. Do not assume a folder is implemented just because it exists.

## The authoritative spec for each assignment is `TASKS.md`

Every `homework-N/TASKS.md` is the graded requirement sheet — endpoints, data models, validation rules, required files, deliverables, and success criteria. **Read the relevant `TASKS.md` before doing any work in a homework folder**, and treat its "Deliverables" / "Success Criteria" / "Expected Project Structure" sections as the definition of done. The template `README.md` and `HOWTORUN.md` in each folder are placeholders to be replaced, not existing docs to preserve.

Note: `homework-4/TASKS.md` and `homework-5/TASKS.md` both refer to themselves as "Homework 5" in places and their example structures say `homework-5/` — this is a labeling artifact in the source material. Match work to the folder you are actually in, and follow the task content rather than the mislabeled heading.

## Assignment map (what each folder is)

| Folder | Assignment | Stack | Key deliverable beyond code |
|--------|-----------|-------|----------------------------|
| `homework-1` | Banking Transactions REST API (in-memory) | Node.js or Python (your choice) | Working CRUD + validation + filtering API |
| `homework-2` | Customer-support ticket system w/ multi-format import (CSV/JSON/XML) + auto-classification | Node/Express, Python/Flask-FastAPI, or Java/Spring | Test suite **>85% coverage** + 4 audience-specific docs w/ Mermaid diagrams |
| `homework-3` | Specification-driven design — **docs only, no code** | n/a | Layered `specification.md`, `agents.md`, editor/AI rules, rationale README |
| `homework-4` | 4-agent pipeline (research verifier → bug fixer → security verifier → unit-test generator) over a seeded-bug sample app | any single language | Agents in `agents/*.agent.md`, skills, one-command pipeline run |
| `homework-5` | Configure 3 external MCP servers (GitHub, Filesystem, Jira/Notion) + build a custom FastMCP server | Python (FastMCP) | `mcp.json` w/ 4 servers, `custom-mcp-server/server.py`, screenshots of MCP calls |
| `homework-6` | Capstone: 4 meta-agents that generate a transaction-processing pipeline (validator, fraud detector, settlement/compliance) | any language | File-based agent messaging under `shared/`, context7 MCP + custom MCP, coverage-gate hook (blocks push < 80%) |

`homework-6/sample-transactions.json` is the fixed input for the capstone pipeline — read it before shaping agent logic.

## Conventions that apply across homeworks

- **Money & finance domain**: use precise decimal types for amounts (`decimal.Decimal`, not `float`), ISO 4217 currency codes, and never log PII (account numbers, names) in plaintext. HW1/HW3/HW6 all restate this.
- **Per-homework docs are mandatory and graded**: each implemented folder must contain `README.md` (solution overview + **author name**), `HOWTORUN.md` (numbered setup→run→test steps), and screenshots in `docs/screenshots/`. Missing docs/screenshots are grounds for rejection per the root `README.md`.
- Build/lint/test commands are **per homework and stack-dependent** — they live in that folder's `HOWTORUN.md` and its `package.json` / `requirements.txt` / `pyproject.toml`. There is no repo-wide command.

## Submission workflow (git)

One branch per assignment, named `homework-N-submission` (this repo's current branch follows that pattern). Commit work there, push, and open a **detailed PR** into the fork's `main` — the PR body is the primary submission narrative and must include what was implemented, how AI was used, how to verify, and embedded screenshots. Bare/one-line PRs are rejected. Do not open PRs against the upstream course repo.

## Reference material

`recommended-agents-skills-pipelines.md` (repo root) is a research compilation of Claude Code agents, skills, and agentic pipelines relevant to the course — background reading, not part of any submission.
