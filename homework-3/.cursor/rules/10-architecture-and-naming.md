---
description: Layering, naming, API conventions and patterns to avoid in application code
globs: ["app/**/*.py"]
alwaysApply: false
---

# Architecture, naming and patterns

## Layering (enforced by an architecture test — do not break it "temporarily")

```
api/  →  services/  →  domain/
             ↑
  adapters/ + infrastructure/  (injected, never imported by domain)
```

- `app/domain/` imports **nothing** from `app/api/`, `app/services/`, `app/infrastructure/` or `app/adapters/`.
- Decision logic is **pure and total**: no I/O, no `datetime.now()` (inject a `Clock`), no randomness (inject a generator), no logging inside `decide()`.
- External systems are reached only through a port in `app/ports/`. Every port has a production adapter **and** a deterministic fake used by tests.
- Redis is an accelerator. Card `status` on the authorization path is read from the primary database, never from cache.

## Naming

| Thing | Convention | Example |
|---|---|---|
| Money field | suffix `_minor` + sibling `currency` | `daily_limit_minor`, `currency` |
| Timestamp | suffix `_at`, UTC, RFC 3339 on the wire | `activated_at` |
| Identifier | prefixed ULID, opaque to clients | `vc_01H...`, `txn_01H...`, `cus_`, `aud_`, `apr_` |
| Boolean | reads as an assertion | `is_active`, `requires_approval` (not `flag`, not `status_bool`) |
| Error code | closed enum in `app/errors/catalog.py`, snake_case | `limit_exceeded_daily` |
| Audit action | `<subject>.<verb>` past tense | `card.frozen`, `controls.updated` |
| Test for an edge case | named after its spec id | `test_ec_09_concurrent_authorizations_share_one_daily_cap` |

## API conventions

- Request models: Pydantic v2 with `ConfigDict(extra="forbid")` — a typo in a field name must fail loudly, not silently do nothing.
- Errors: RFC 9457 `application/problem+json` with `type`, `title`, `status`, `detail`, `code`, `correlation_id`.
- Status codes: `400` malformed · `401` unauthenticated · `403` forbidden **or** insufficient auth strength · `404` unknown-or-not-yours · `409` state/idempotency/concurrency conflict · `422` semantically invalid · `429` rate limited (+ `Retry-After`) · `503` degraded dependency.
- Pagination is **cursor-based** and signed; `limit` default 25, max 100; sort `(occurred_at DESC, id DESC)`. `OFFSET` and unbounded `COUNT(*)` are forbidden on customer-facing lists.
- No PII in URLs or query strings — ops search takes a POST body.
- Amounts on the wire are integers with an explicit currency; never a formatted string, never a float.

## Patterns to avoid

- `card.status = X` outside `app/domain/state_machine.py`.
- Read-modify-write on spend counters in Python — use atomic conditional `UPDATE`.
- Sending a notification or webhook inside a request handler — append to the outbox instead.
- Boolean parameters that switch behavior — write two functions.
- Bare `except:`, `except Exception: pass`, or returning `None` to signal failure where `None` is also valid data.
- `# type: ignore` without a comment explaining why and a linked issue.
- Retries on non-idempotent operations; retries on `4xx`; unbounded retries.
- Dead code, commented-out code, TODOs without an owner and an issue link.

## When adding a mutating endpoint, add in the same change

audit action · authorization-matrix rows · rate-limit bucket · idempotency support · error codes in `docs/errors.md`. The build fails if one is missing — fix the omission, never the check.
