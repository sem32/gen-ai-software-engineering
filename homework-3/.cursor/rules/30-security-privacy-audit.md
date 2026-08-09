---
description: Security, privacy and audit rules for handlers, adapters, logging, jobs and migrations
globs: ["app/api/**/*.py", "app/services/**/*.py", "app/adapters/**/*.py", "app/jobs/**/*.py", "app/infrastructure/**/*.py", "**/migrations/**/*.py"]
alwaysApply: false
---

# Security, privacy and audit

## Hard rules (a violation is an incident, not a nit)

- **Never** log, print, serialize into an error body, attach to a trace span, or write into a fixture: PAN, CVV, reveal tokens, session tokens, step-up assertions, processor API keys, HMAC secrets.
- **Never** disable or weaken: webhook signature verification, the log redaction filter, the authorization matrix, rate limits, the maker-checker check, the append-only grant on the audit table.
- **Never** widen an error message with upstream exception text — it leaks internals to the customer. Customer-facing copy is generic (`"declined for security reasons"`); detail lives in the audit record.
- **Never** create a path where an authorization can be approved by default, by timeout, or by an exception handler.
- **Never** commit a secret — not in code, `.env`, fixtures, tests or commit messages. If you think you have seen a real secret, stop and report it.
- **Never** make a destructive or irreversible change without an explicit instruction (drop a column, delete rows, rotate a key, bulk-close cards).

## Logging

- Structured JSON only. Log keys are **allow-listed** — a key not on the list is dropped in production and raises in tests.
- Safe to log: `card_id`, `customer_id`, `correlation_id`, `status`, `decision`, `reason_code`, `amount_minor`+`currency`, `actor_type`, durations, counts.
- Never log: `pan_last4` together with a customer name, nicknames, free-text customer input, tokens of any kind, raw webhook bodies, full request bodies of mutating endpoints.
- The Luhn-validating redaction filter is defence in depth, not permission to be careless.

## Audit

- Every state-changing **attempt** — success *and* rejection — produces an audit record with actor, authority (scope or `approval_id`), redacted before/after, reason and `correlation_id`.
- Sensitive **reads** (reveal, ops card lookup, export) are audited too.
- The audit write is in the same transaction as the business change. If it fails, the change rolls back.
- Records are hash-chained and append-only. The application DB role has `INSERT` only. Erasure pseudonymises; it never deletes or rewrites an audit row.
- New audit action → document it in `docs/audit-events.md` in the same PR.

## Authentication and authorization

- Reveal requires a step-up assertion **≤ 120 s** old with ≥ 2 distinct factors, plus a single-use token with TTL ≤ 60 s bound to card, customer, device and IP.
- Close requires `confirm: true` **and** a step-up assertion ≤ 300 s old.
- Administrative lock / release / ops-close require maker-checker: requester ≠ approver, enforced in code, justification ≥ 20 characters, approval expires after 4 hours.
- Webhooks: verify mTLS + HMAC-SHA256 over the **raw body** with a 5-minute timestamp window **before parsing**, and reject replayed `(signature, timestamp)` pairs.
- Rate limits fail **closed** for reveal and card creation, **open** for read endpoints.

## Privacy

- Personal data changes (new stored field, new log field, new export column, changed retention) require an update to `docs/data-map.md` in the same PR.
- Retention: transactions and audit 10 years (assumed, see spec §14 Q3) · idempotency 24 h · reveal tokens ≤ 60 s · ops search index 90 days.
- Legal hold beats erasure: an erasure request pseudonymises but does not delete records inside a regulatory retention window, and the audit chain must still verify afterwards.
- Never generate "realistic" synthetic personal data. Use obvious test markers.

## Migrations

Expand → migrate → contract, across separate releases. Additive and reversible; `alembic downgrade` must work in CI. Never edit a migration that has already been applied — write a new one.
