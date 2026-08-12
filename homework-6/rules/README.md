# Writing a rule pack

A pack is one JSON file in this directory. Its name is the file stem, so `policy-strict.json` is
selected as `policy-strict` — by `--rules` on the CLI, `HW6_POLICY_RULES` in the environment,
`?rules=` on the API, or the `X-Policy-Rules` header between services.

**Rules are data, never code** (guardrail IN-9). There is no `eval`, no `exec`, and no importing a
module named in a config file. If the engine cannot fully understand a pack it refuses the whole pack at
**load time**, naming the rule and the field — a typo can never silently disable a control at decision
time.

## Shape

```json
{
  "name": "policy-example",
  "version": "1.0",
  "description": "What this pack is for, in one sentence.",
  "defaults": { "priority": "standard", "sla_hours": 24 },
  "rules": [
    {
      "id": "express_small_low_risk",
      "description": "Why this rule exists — future you will want this.",
      "enabled": true,
      "order": 10,
      "when": { "all": [
        { "fact": "usd_amount", "op": "<",  "value": "2000" },
        { "fact": "risk_level", "op": "==", "value": "low" }
      ]},
      "then": { "set": { "priority": "express", "sla_hours": 4 }, "tags": ["fast-lane"] },
      "stop": false
    }
  ]
}
```

## Conditions

Four forms, freely nested:

| Form | Meaning |
|---|---|
| `{"all": [c, …]}` | every child is true — **empty list is true** |
| `{"any": [c, …]}` | at least one child is true — **empty list is false** |
| `{"not": c}` | the child is false |
| `{"fact": f, "op": o, "value": v}` | a leaf comparison |

The empty-list behaviours are the arithmetic identities and they are asserted in the suite, because
guessing there would silently invert a policy.

## Operators

`==` `!=` `>` `>=` `<` `<=` `in` `not_in` `contains` `not_contains` `startswith` `matches` (full-match
regex) `is_true` `is_false` `exists` `missing`.

The last four take no `value`. Everything else requires one.

**Write numbers as strings.** `"value": "10000"` compares as an exact `Decimal`; `"value": 10000` (an
int) also works, but a **float is refused outright** — `9.0 > "10"` is false numerically and true
lexicographically, and the engine will not pick one for you.

## Actions

| Key | Effect |
|---|---|
| `set` | assigns scalars: `priority`, `sla_hours`, `dual_approval_required`, `fee_rate`, `fee_floor`, `fee_cap`, `settlement_lag` |
| `tags` | appended to the tag list, de-duplicated, order preserved |
| `hold` | a stable reason code; sets `hold = true` and appends the code to `hold_reasons` |

A monetary override (`fee_*`) is a string parsed into `Decimal` by the settlement processor and
quantised `ROUND_HALF_UP` like every other money path. A negative or unparseable override raises
`MoneyError` — it never falls back silently to the default rate.

## Facts

A flat dictionary built from the accumulated message payload:

`transaction_id` · `transaction_type` · `currency` · `amount` · `usd_amount` · `channel` · `country` ·
`hour_utc` · `weekday` · `source_account` · `destination_account` (both masked `****NNNN`) · `status` ·
`risk_score` · `risk_level` · `review_required` · `fraud_rules` (list of fired rule codes) ·
`ctr_required` · `compliance_decision` · `compliance_holds` · `is_cross_border`

`hour_utc` and `weekday` come from the transaction's own timestamp, never the clock, so a run is
reproducible.

## Ordering and conflicts

Rules sort by `order` (default `100`), ties broken by declaration order. A matching rule with
`"stop": true` ends evaluation. For a scalar field the **last writer wins**, and the outcome records
`decided_by[field] = rule_id` so any conflict is attributable. A `"enabled": false` rule is skipped at
evaluation but **still validated** at load.

## The two shipped packs

| Pack | What it does |
|---|---|
| `policy-default.json` | Additive only: priority, SLA, tags, approval flags. Touches **no** monetary field, so a default run reproduces `specification.md` §8 exactly. A test enforces that. |
| `policy-strict.json` | Holds structuring candidates and off-hours automated submissions; applies a 35 bp surcharge with a 100.00 cap above 20 000 USD. Produces §8b: 3 settled / 3 held instead of 5 / 1, plus one changed fee. |

## Try it

```bash
cd homework-6
.venv/bin/python integrator.py --rules policy-strict          # the whole sample under a pack
.venv/bin/python -m gateway --port 8080                        # then: POST /transactions?rules=policy-strict
curl -s localhost:8080/rules | python3 -m json.tool            # the active pack, as loaded
```

Edit a threshold in `policy-strict.json`, re-run, and watch a verdict move. That is the entire point:
**behaviour is configuration**, and no code changes.
