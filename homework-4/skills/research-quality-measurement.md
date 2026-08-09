---
name: research-quality-measurement
description: Use when verifying a codebase research document to grade how trustworthy it is - defines the five research quality levels, the three measured dimensions, the scoring procedure, and the required structure of verified-research.md
applies_to: research-verifier.agent.md
---

# Research Quality Measurement

A research document is only useful if a planner can act on it without re-checking it. This skill
defines **how to measure that trust** and **what label to publish**.

Never report a quality level you did not compute. The level is the output of the procedure below,
not an impression.

## Step 1 — Enumerate claims

Extract every **checkable claim** from the research document. A claim is checkable when it asserts
something a reader can confirm against the repository. Three kinds:

| Kind | Example |
|---|---|
| **Reference claim** | "the divide happens in `src/stats.py:48`" |
| **Snippet claim** | a quoted block of code presented as existing source |
| **Behavioural claim** | "`completion_rate()` already guards the empty case", "no test covers this path" |

Ignore prose that is opinion, plan, or recommendation — it is not a claim, and it is not scored.
Record the total claim count `N`. If `N == 0`, the research is unusable: level **E**.

## Step 2 — Verify each claim

For every claim, open the cited file and check it. One of four verdicts:

| Verdict | Meaning |
|---|---|
| `VERIFIED` | The claim is exactly right (file exists, line number lands on the cited code, snippet matches character-for-character apart from indentation, behaviour reproduces) |
| `DRIFTED` | Substantially right but imprecise: line number off by ≤3 lines, snippet abridged or reflowed but semantically identical, path missing a directory prefix |
| `WRONG` | Contradicted by the source: line points at unrelated code, snippet does not exist, behaviour claim is false |
| `UNVERIFIABLE` | Cannot be checked as written (no file cited, ambiguous reference, claim about something outside the repository) |

Behavioural claims must be checked by reading the code — and, where a command is cheap and
non-destructive, by running it. Say which method you used.

## Step 3 — Score the three dimensions

**D1 Reference accuracy** = `(VERIFIED + 0.5 × DRIFTED) / N`, expressed as a percentage.

**D2 Snippet fidelity** = share of snippet claims whose quoted code matches the source. If the
document contains no snippets, D2 is `n/a` and does not lower the grade — but note it, because
research without snippets is harder to act on.

**D3 Root-cause coverage** — a judgement call, so state the reasoning in one sentence:

| Value | Criterion |
|---|---|
| `COMPLETE` | Every reported symptom in the bug context is traced to a specific file:line cause, and the fix location is unambiguous |
| `PARTIAL` | At least one symptom is described without an identified cause, or the cause is named without a location |
| `MISSING` | The research restates symptoms without locating any cause |

## Step 4 — Assign the level

Take the level whose **every** condition is met, scanning from A downwards.

| Level | Label | Reference accuracy (D1) | Snippet fidelity (D2) | Root cause (D3) | Hard blockers |
|---|---|---|---|---|---|
| **A** | `VERIFIED` | ≥ 98% | 100% or n/a | `COMPLETE` | zero `WRONG`, zero `UNVERIFIABLE` |
| **B** | `RELIABLE` | ≥ 90% | ≥ 90% or n/a | `COMPLETE` | zero `WRONG` on a claim the plan depends on |
| **C** | `USABLE_WITH_CORRECTIONS` | ≥ 75% | ≥ 75% or n/a | `COMPLETE` or `PARTIAL` | every `WRONG` claim is corrected in this report |
| **D** | `WEAK` | ≥ 50% | any | `PARTIAL` | — |
| **E** | `UNRELIABLE` | < 50% | any | any | — |

**Gate rule.** Levels **A, B, C** are a `PASS`: the Bug Planner may proceed, using this report's
corrections in place of the original claims. Levels **D** and **E** are a `FAIL`: the pipeline must
stop and the research must be redone. Say this explicitly.

**Escalation rules** (apply after the table):

- Any `WRONG` claim about a file that the fix must touch caps the level at **C**, whatever D1 says.
- A missing file (cited path does not exist at all) caps the level at **C**.
- `D3 = MISSING` caps the level at **E** — research that locates no cause cannot be planned against.
- Never round a percentage up across a threshold. 89.6% is not 90%.

## Step 5 — Write the result file

`verified-research.md` must contain these sections, in this order, with these headings:

```markdown
# Verified Research — <BUG-ID>

## Verification Summary
<!-- verdict PASS/FAIL, Research Quality <LEVEL> (<LABEL>), claim counts, D1/D2/D3 values,
     one sentence on whether the Bug Planner may proceed -->

## Verified Claims
<!-- table: # | Claim | Cited location | Verdict | Evidence (what you found at that location) -->

## Discrepancies Found
<!-- one subsection per DRIFTED/WRONG/UNVERIFIABLE claim: what the research said,
     what the source actually says, the corrected reference, and the impact on the fix.
     Write "None." if there are none. -->

## Research Quality Assessment
<!-- the computed level with the arithmetic shown (D1 = x/N = %), the reasoning behind D3,
     any escalation rule applied, and what would have to change to reach the next level up -->

## References
<!-- every file:line you personally opened during verification, plus the research document
     and bug context you read -->
```

Rules for the result file:

- Quote the **corrected** reference next to every discrepancy, so the planner never has to open the
  original research document.
- Do not fix the code. Do not write a plan. Verification only.
- Every `file:line` you print must be one you actually opened in this session.
