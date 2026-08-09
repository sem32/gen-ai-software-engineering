---
description: Agent 1 — generate a technical specification following the homework-6 template
argument-hint: [feature or system to specify]
allowed-tools: Read, Write, Glob, Grep
---

# Agent 1 — Specification writer

Produce a complete technical specification for: **$ARGUMENTS**

If `$ARGUMENTS` is empty, ask what should be specified and stop — do not guess.

## Before writing

1. Read `homework-6/specification.md` — it is the reference implementation of this template and
   shows the expected depth.
2. Read `homework-6/agents.md` for the behavioural rules the resulting system must obey.
3. Read `homework-3/specification-TEMPLATE-example.md` for the original template wording.
4. If the target already has code, read it. A specification that contradicts the code is worthless.

## Required output structure

Write the result to `specification.md` in the target directory, with **all** of these sections:

1. **High-Level Objective** — exactly one sentence describing what the system does.
2. **Mid-Level Objectives** — 4–6 concrete, individually testable requirements in a table with
   stable ids (`MO-1`, `MO-2`, …). Each must be falsifiable: "amounts at or above 10 000 are
   flagged with a risk score", not "the system is secure".
3. **Implementation Notes** — at minimum:
   - monetary values use an exact decimal type, parsed from strings, never `float`;
   - currency codes are ISO 4217, validated against an explicit allow-list;
   - logging is an audit trail carrying an ISO 8601 timestamp, agent name, transaction id, outcome;
   - PII (account numbers, holder names, free-text descriptions) is masked before it leaves the
     process — never logged in plaintext;
   - the tech stack, with one row per layer.
4. **Context** — *Beginning state* (files that exist now, what the input data looks like) and
   *Ending state* (every file that must exist afterwards, plus the coverage target).
5. **Low-Level Tasks** — one entry per component, in build order, each in exactly this shape:

   ```
   Task: [Component name]
   Prompt: "[the exact prompt you would hand to Claude Code or Copilot]"
   File to CREATE: path/to/file.py
   Function to CREATE: signature(arg: type) -> type
   Details: [what it checks, transforms or decides]
   Acceptance criteria: [checkbox list, each verifiable by running something]
   ```

Then add two supporting sections:

6. **Guardrails (`IN-*`)** — the rules an implementer must never violate.
7. **Edge cases (`EC-*`)** — a table of case → required behaviour, covering at minimum: the empty
   input, the duplicate, the malformed record, the boundary value, and the permission/fail-closed
   case.

## Rules

- Be specific enough that two different engineers would build the same thing.
- Every objective must be checkable by a command, a test name or a file that must exist.
- Prefer explicit refusal over clever inference: state what the system must reject.
- Do not write implementation code — this command produces the specification only.
- Finish by listing which acceptance criteria are still unverified.
