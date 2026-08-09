---
description: Always-on FinTech defaults for the virtual cards service — money, PAN handling, fail-closed behavior, scope discipline
globs: ["**/*"]
alwaysApply: true
---

# Core rules — always apply

This repository is an **issuer-side virtual card platform in a regulated (PCI DSS / PSD2 / GDPR) environment**.
Authoritative documents, in precedence order: `specification.md` → `agents.md` → these rules.
When two rules conflict, **the more restrictive one wins** and you say so in your response.

## Non-negotiable defaults

1. **Money is `int` minor units + an ISO-4217 currency string.**
   Use the `Money` value object from `app/domain/money.py`. `float`, `round()`, `/ 100` and `Decimal`-with-fractional-minor-units on a money path are defects — including in tests, fixtures, docstrings and log messages. Never do arithmetic across currencies.

2. **Card credentials do not exist in this codebase.**
   The tokens `pan`, `card_number`, `cardnumber`, `card_no`, `cvv`, `cvc`, `cvv2`, `track2`, `full_pan` are forbidden as field names, columns, variables, log keys, fixture values or example data. Only `pan_last4` (display: `•••• 4242`) and `processor_card_token` exist. Reveal is processor-hosted; PAN never transits our servers.

3. **Fail closed.** On any uncertainty — unknown card status, missing spending controls, unreachable dependency, expired token, unparsable config, exceeded latency budget — the answer is **decline / deny / 4xx**. Never write a permissive `else`, a `try/except: pass` that continues, or a timeout handler that approves.

4. **Every mutation is idempotent, optimistically locked and audited in the same transaction.**
   No mutating endpoint, job or event consumer ships without: `Idempotency-Key` handling, a `version` check, and an `AuditService.record(...)` call inside the same DB transaction.

5. **Least privilege by default.** New endpoints start with no access and declare exactly the scopes they need. Return `404`, not `403`, for resources the caller may not know exist.

6. **Stay in scope.** Implement exactly the `T-nn` task you were given. No opportunistic refactors, no formatting sweeps, no dependency bumps, no "while I was in there" fixes. Put them in a follow-up note instead.

## Stop and ask — do not guess

Stop and ask the human when:
- `specification.md` is silent, ambiguous or self-contradictory about the behavior you need;
- the change would alter the PCI boundary (anything touching reveal, processor tokens, or webhook signature verification);
- the change would touch the audit chain, an applied migration, or a CI security gate;
- a test can only be made to pass by weakening a control, adding a `sleep`, or adding a retry;
- the task appears to require handling real card or customer data.

Guessing a requirement in this domain is worse than being slow.

## Never do without an explicit instruction

`git push --force` · commit to `main` · rewrite history · edit applied migrations · delete or `xfail` tests · disable a CI gate · relax the redaction filter, the authorization matrix, the maker-checker check or a rate limit · bulk-mutate cards · drop a column in the same release that stops using it.
