#!/usr/bin/env python3
"""Render the `claude -p --output-format stream-json` event stream as compact progress lines.

Reads stream-json on stdin, prints one short line per agent action so a pipeline run is
observable while it happens, and writes the final `result` event to a file for the runner to
read (cost, duration, turn count, error status).

Usage: claude -p ... --output-format stream-json --verbose | stream_render.py <result-json-path>
"""

from __future__ import annotations

import json
import sys

DIM = "\033[2m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"

MAX_WIDTH = 96


def clip(text: str, width: int = MAX_WIDTH) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[: width - 1] + "…"


def describe_tool(name: str, params: dict) -> str:
    """One-line description of a tool call."""
    if name in {"Read", "Write", "Edit", "NotebookEdit"}:
        detail = params.get("file_path", "")
    elif name == "Bash":
        detail = params.get("command", "")
    elif name in {"Grep", "Glob"}:
        detail = params.get("pattern", "")
        if params.get("path"):
            detail = f"{detail} in {params['path']}"
    elif name == "TodoWrite":
        detail = f"{len(params.get('todos', []))} item(s)"
    else:
        detail = json.dumps(params)[:120]
    return f"{name}({clip(detail, 78)})" if detail else name


def main() -> int:
    result_path = sys.argv[1] if len(sys.argv) > 1 else None
    final: dict | None = None

    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue

        kind = event.get("type")

        if kind == "system" and event.get("subtype") == "init":
            print(
                f"      {DIM}session {str(event.get('session_id', '?'))[:8]} · "
                f"model {event.get('model', '?')}{RESET}",
                flush=True,
            )

        elif kind == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "text" and block.get("text", "").strip():
                    print(f"      {DIM}» {clip(block['text'])}{RESET}", flush=True)
                elif block.get("type") == "tool_use":
                    print(
                        f"      {CYAN}·{RESET} {describe_tool(block.get('name', '?'), block.get('input', {}))}",
                        flush=True,
                    )

        elif kind == "user":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_result" and block.get("is_error"):
                    body = block.get("content")
                    if isinstance(body, list):
                        body = " ".join(part.get("text", "") for part in body if isinstance(part, dict))
                    print(f"      {YELLOW}! tool error: {clip(body or '', 78)}{RESET}", flush=True)

        elif kind == "result":
            final = event

    if final is None:
        print(f"      {RED}! no result event received from the agent{RESET}", flush=True)
        return 1

    if result_path:
        with open(result_path, "w", encoding="utf-8") as handle:
            json.dump(final, handle, indent=2)

    if final.get("is_error"):
        print(f"      {RED}! agent reported an error: {clip(final.get('result', ''))}{RESET}", flush=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
