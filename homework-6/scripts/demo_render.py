#!/usr/bin/env python3
"""Formatting helpers for ``demo.sh`` (spec task T-14).

Kept as a file rather than a shell here-doc for one concrete reason: a here-doc *is* the script's
stdin, so a here-doc formatter cannot also read a piped response. This module reads the response from
stdin and takes the labelling from argv, which is what the demo actually needs.

    curl ... | python scripts/demo_render.py submission "settled" 201
    curl ... | python scripts/demo_render.py health 8801
"""

from __future__ import annotations

import json
import sys
from typing import Any


def _load() -> Any:
    raw = sys.stdin.read().strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _hops(body: dict[str, Any]) -> str:
    trace = body.get("trace") or (body.get("outcome") or {}).get("trace") or []
    return " -> ".join(str(hop.get("agent", "?")).split("_")[0] for hop in trace)


def render_submission(label: str, status: str) -> int:
    body = _load()
    if not isinstance(body, dict):
        print(f"  {label:<26} HTTP {status:<5}(no readable response)")
        return 0

    outcome = body.get("outcome") if isinstance(body.get("outcome"), dict) else body
    verdict = outcome.get("status") or body.get("code") or "?"

    if outcome.get("net_amount"):
        extra = f"net {outcome['net_amount']} {outcome.get('currency', '')}"
        if outcome.get("priority"):
            extra += f" · {outcome['priority']}"
    elif body.get("reasons"):
        extra = ", ".join(body["reasons"])
    elif body.get("errors"):
        extra = ", ".join(f"{item['field']}:{item['code']}" for item in body["errors"])
    else:
        extra = body.get("detail", "")

    print(f"  {label:<26} HTTP {status:<5}{str(verdict):<22}{extra}")
    hops = _hops(body)
    if hops:
        print(f"  {'':<26}      hops: {hops}")
    return 0


def render_health(port: str) -> int:
    body = _load()
    if not isinstance(body, dict):
        print(f"  ?  (service on :{port} did not answer)")
        return 0
    print(
        f"  {body.get('position', '?')}. {str(body.get('agent', '?')):<24} :{port}  "
        f"next={str(body.get('next', '?')):<22} pack={body.get('rule_pack') or '-'}"
    )
    return 0


def render_agents() -> int:
    body = _load()
    if not isinstance(body, dict):
        print("  (no agent catalog)")
        return 0
    for agent in body.get("agents", []):
        print(
            f"  {agent['position']}. POST {agent['route']:<44} next={agent.get('next_agent')}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: demo_render.py {submission|health|agents} [...]", file=sys.stderr)
        return 2

    mode, rest = args[0], args[1:]
    if mode == "submission":
        return render_submission(rest[0] if rest else "", rest[1] if len(rest) > 1 else "?")
    if mode == "health":
        return render_health(rest[0] if rest else "?")
    if mode == "agents":
        return render_agents()
    print(f"unknown mode {mode!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
