# Error catalog

> Generated from the single source of truth: [`gateway/errors.py`](../gateway/errors.py). The live copy
> is served by the API at `GET /errors`, so a client can generate its own handling rather than copy this
> table by hand.

Every error the API returns is an **RFC 9457 problem document** (`application/problem+json`):

```json
{
  "type":       "urn:hw6:error:transaction-rejected",
  "title":      "Transaction rejected by the pipeline",
  "status":     422,
  "detail":     "transaction BAD1 was rejected: unknown_currency:XYZ",
  "instance":   "/transactions",
  "code":       "transaction_rejected",
  "request_id": "9f21c0b4e77a",
  "reasons":    ["unknown_currency:XYZ"],
  "outcome":    { "…": "the full terminal outcome" }
}
```

The five registered members come first; `code`, `request_id` and the per-error extras are RFC 9457
extension members. **Switch on `code`**, not on `title` or `detail` — those are for humans and may be
reworded. `type` is a URN: stable, and deliberately not a URL we do not serve (RFC 9457 does not
require it to be dereferenceable).

## The catalog

| code | HTTP | Meaning | Extensions | Retryable |
|---|---:|---|---|:--:|
| `invalid_json` | 400 | The body is not parseable JSON, or not UTF-8 | `line`, `column` | no |
| `invalid_body` | 400 | Parseable, but not an acceptable shape — an array sent to the single endpoint, an empty batch, a batch over the limit, a message addressed to another agent | `addressed_to` | no |
| `invalid_query` | 400 | A query parameter is missing, blank, out of range or names an unknown rule pack | `parameter`, `available` | no |
| `validation_failed` | 400 | The submission does not match the transaction schema | `errors[]` — one entry per field with `field`, `code`, `detail` | no |
| `payload_too_large` | 413 | Body above 1 MiB | `limit_bytes` | no |
| `not_found` | 404 | No such route, or no such agent | `available_agents` | no |
| `transaction_not_found` | 404 | No result stored for that id | `transaction_id` | no |
| `method_not_allowed` | 405 | Wrong verb on a known path — the `Allow` header lists the right ones | `allowed_methods` | no |
| `transaction_rejected` | **422** | A **business verdict**: the pipeline rejected it. The result *is* stored — `Location` points at it | `reasons[]`, `outcome`, `transaction_id` | no |
| `transaction_held` | **409** | A **business verdict**: held for manual review. Also stored and retrievable | `reasons[]`, `outcome`, `transaction_id` | no |
| `rule_pack_unavailable` | 500 | The configured rule pack could not be loaded — server misconfiguration | — | no |
| `pipeline_error` | 500 | The pipeline produced no terminal outcome, or a message routed nowhere | `routed_to`, `downstream_status` | no |
| `upstream_unavailable` | **503** | A downstream agent service could not be reached after retries | `next_agent`, `attempts`, `entrypoint` | **yes** |
| `internal_error` | 500 | Anything unexpected | — | no |

## Two rules that explain the whole table

**A business verdict is not a failed request.** A rejected or held transaction was received,
processed, journalled and stored. `422`/`409` communicate *what the pipeline decided*; `4xx` in the
`400`/`404`/`405`/`413` band communicate *that the request itself was wrong*. The practical
consequence: on a `422` you still get a `Location` header and `GET /transactions/{id}` works.

**A 5xx never carries an upstream exception string.** `problem_from_exception` maps unexpected
exceptions onto `internal_error` and **discards** the original message, because an exception string can
carry a filesystem path or a value that was masked elsewhere (guardrail IN-10). The real cause goes to
the server log; the client gets the catalog's generic detail and a `request_id` that ties the two
together.

## Correlating an error with the journal

Every response carries `X-Request-Id`, the same value appears as `request_id` in the problem document,
and every audit line the request produced carries it in `detail.request_id`:

```bash
curl -s -D- -X POST localhost:8080/transactions -d '{"…"}' | grep -i x-request-id
curl -s 'localhost:8080/audit?limit=200' | grep <that-id>
```

## Non-goals, stated so nobody has to guess

- **No authentication, no TLS, no rate limiting.** This is a loopback-only demo surface with no
  credentials. Half an auth story would be worse than none; see CR-02 §5.
- **Permissive CORS** (`Access-Control-Allow-Origin: *`) so the presentation works when opened as a
  `file://` page. Acceptable exactly because there is nothing to steal and nothing to authenticate.
- **No idempotency key on the public API.** Idempotency exists *between* services, keyed on
  `message_id`, where retries actually happen. A client-facing key would be the next thing to add.
