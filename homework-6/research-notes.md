# Research notes — context7 queries made during code generation

> **Author / Student**: Simon Darienko · **Homework 6 (Capstone)** · Task 2 + Task 4
> **MCP server used**: `context7` (`npx -y @upstash/context7-mcp@latest`), configured in
> [`mcp.json`](mcp.json) and wired into the repository root by
> [`scripts/install_claude_integration.py`](scripts/install_claude_integration.py).
> **Client**: Claude Code (Opus 5), tools `mcp__context7__resolve-library-id` and
> `mcp__context7__query-docs`.

Agent 2 (the code-generation agent) used context7 before writing `mcp/server.py` and
`agents/protocol.py`. Every query below was actually issued during this build; the "Applied"
line points at the file and the line of code that carries the result.

---

## Query 1 — FastMCP: tools, resources and in-memory testing

**Step 1 — `resolve-library-id`**

- Library name searched: `FastMCP`
- Query: *"define tools and resources on a FastMCP server in Python"*
- Candidates returned (with benchmark score): `/prefecthq/fastmcp` (82.71, 4 041 snippets),
  `/llmstxt/gofastmcp_llms_txt` (84.40), `/llmstxt/gofastmcp_llms-full_txt` (71.52),
  `/websites/gofastmcp` (61.73)
- **Library ID chosen: `/prefecthq/fastmcp`** — the upstream repository, highest snippet coverage
  with High source reputation.

**Step 2 — `query-docs`**

- Query: *"define @mcp.tool and @mcp.resource with a custom URI, and test the server in-memory with
  Client"*
- Key returns:
  - `@mcp.resource("data://config")` — a resource is declared with its **URI as the decorator
    argument**, and the function body simply returns the payload; resources are passive reads with
    no side effects.
  - `@mcp.resource("weather://{city}/current")` — URI placeholders become function parameters
    (resource *templates*).
  - In-memory testing: `Client(server)` accepts the **server object directly**, running the real MCP
    protocol in-process with no network and no subprocess — `async with Client(server) as client:
    await client.call_tool(...)`, then assert on `result.data`.

**Applied**

- `mcp/server.py` — `@mcp.resource("pipeline://summary")` uses the custom scheme exactly as
  documented, and the two tools are plain `@mcp.tool`-decorated functions whose docstrings become
  the tool descriptions the model sees.
- `tests/test_mcp_server.py` — the whole MCP test suite runs over the in-memory transport
  (`Client(server_module.mcp)`), so the six MCP tests add ~0.2 s and no flakiness, instead of
  spawning a subprocess per test. `result.data` is used for the structured payload, with a fallback
  to `result.content[0].text`.
- Corollary that shaped the layout: because the server is imported by the tests, the local
  directory `homework-6/mcp/` must never shadow the installed `mcp` package that FastMCP imports —
  hence no `__init__.py` there, `sys.path.append` (never `insert(0)`), and the `sys.path`
  normalisation at the top of `tests/conftest.py`.

---

## Query 2 — Python `decimal`: half-up rounding for money

**Step 1 — `resolve-library-id`**

- Library name searched: `Python`
- Query: *"decimal module quantize ROUND_HALF_UP for monetary arithmetic"*
- Candidates: `/python/cpython` (77.12, 36 843 snippets), `/websites/python_3` (58.50),
  `/websites/devdocs_io_python_3_14` (62.39)
- **Library ID chosen: `/python/cpython`** — the canonical CPython documentation source.

**Step 2 — `query-docs`**

- Query: *"decimal module: quantize with ROUND_HALF_UP, localcontext, and why float must not be used
  for money"*
- Key returns:
  - `Decimal('1.41421356').quantize(Decimal('1.000'))` → `Decimal('1.414')` — `quantize` rounds to
    the **exponent of the operand**, which is exactly the "round to the currency's minor unit"
    operation.
  - `quantize(exp, rounding=None, context=None)` — the rounding mode is a per-call argument;
    without it the context default applies, and CPython's default context is `ROUND_HALF_EVEN`
    (banker's rounding), *not* what a settlement ledger wants.
  - `Decimal(1.1)` → `Decimal('1.100000000000000088817841970012523233890533447265625')` — building a
    `Decimal` from a `float` inherits the binary representation error, so the fix is not "use
    Decimal", it is "use Decimal **constructed from a string**".
  - `localcontext()` for temporarily raising precision inside a calculation, restoring it after.

**Applied**

- `agents/protocol.py::quantize_money` passes `rounding=ROUND_HALF_UP` explicitly and derives the
  target exponent from the currency's minor unit via `Decimal(1).scaleb(-minor_units(currency))`,
  so `JPY` quantises to 0 decimals and `USD` to 2 with the same code path.
- `agents/protocol.py::parse_amount` **rejects `float` (and `bool`) inputs outright** with
  `MoneyError`, precisely because of the `Decimal(1.1)` result above. Amounts stay strings on the
  wire and are parsed once, at the validator boundary.
- `tests/test_protocol.py::test_quantize_money_rounds_half_up_not_bankers` pins the behaviour:
  `Decimal("0.125") → 0.13`, which is where the default `ROUND_HALF_EVEN` would have produced
  `0.12`.
- `agents/settlement_processor.py::FEE_RATE = Decimal("0.0025")` follows the same rule — the fee
  rate is a string-constructed `Decimal`, never `0.0025`.

---

## Query 3 — FastMCP client transports (follow-up)

Issued as part of Query 1's `query-docs` result set rather than as a separate lookup, but worth
recording because it decided a design point:

- Return: *"Using In-Memory Transport with FastMCP Client — connects a client directly to a server
  instance within the same Python process, ideal for testing without network or subprocess
  overhead."*
- **Applied**: two different transports for two different jobs —
  `tests/test_mcp_server.py` uses the in-memory transport (fast, deterministic, part of the coverage
  run), while `scripts/verify_mcp_server.py` uses `StdioTransport` to start `mcp/server.py` as a real
  subprocess. The second one is what produces the `mcp-interaction` evidence, because it proves the
  server works the way an actual MCP client would launch it, not just the way a test imports it.

---

## What context7 changed about the result

Without these lookups the two most likely mistakes would have been:

1. Writing the resource as a tool (or inventing a `@mcp.resource(uri=...)` keyword form) and
   testing the server through a spawned subprocess in every test — slower and flakier.
2. Relying on `Decimal`'s default rounding. Every fee in this pipeline is a half-cent case waiting
   to happen: `9999.99 × 0.0025 = 24.999975`. Banker's rounding and half-up agree there, but
   `0.125 → 0.12` vs `0.13` is exactly the kind of one-cent drift that makes a ledger stop
   balancing, and the `fee + net_amount == amount` invariant in `settle_transaction` would have
   caught it only after the fact.
