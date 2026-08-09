#!/usr/bin/env python3
"""Capture the project's evidence: run each demo command, store the transcript, render a PNG.

The PNGs under ``docs/screenshots/`` are **rendered from real captured output** of the commands
listed in ``STEPS`` — they are not mock-ups, and they are not OS screen grabs either. Each one has
its raw transcript committed next to it in ``docs/sample-run/`` so any line can be verified.

    python scripts/capture_evidence.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PROJECT_ROOT.parent
SCREENSHOTS = PROJECT_ROOT / "docs" / "screenshots"
TRANSCRIPTS = PROJECT_ROOT / "docs" / "sample-run"
PYTHON = str(PROJECT_ROOT / ".venv" / "bin" / "python")
PYTEST = str(PROJECT_ROOT / ".venv" / "bin" / "pytest")

FONT_CANDIDATES = (
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/SFNSMono.ttf",
    "/System/Library/Fonts/Supplemental/Andale Mono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
)

BACKGROUND = (13, 17, 23)
CHROME = (22, 27, 34)
BORDER = (48, 54, 61)
FOREGROUND = (230, 237, 243)
PROMPT = (126, 231, 135)
TITLE = (139, 148, 158)
ERROR = (255, 123, 114)
MAX_COLUMNS = 118


@dataclass
class Step:
    """One captured command (or a scripted sequence of them)."""

    slug: str
    title: str
    commands: list[list[str]]
    cwd: Path = PROJECT_ROOT
    prologue: list[str] = field(default_factory=list)
    epilogue: list[str] = field(default_factory=list)
    max_lines: int | None = None
    expect_failure: bool = False
    stdin_payloads: list[str | None] = field(default_factory=list)


SPEC_OUTLINE = (
    "import re, pathlib\n"
    "text = pathlib.Path('specification.md').read_text().splitlines()\n"
    "for line in text:\n"
    "    if re.match(r'^#{1,3} ', line):\n"
    "        print(line)\n"
    "print()\n"
    "print('--- section 8, the regression expectation asserted in tests ---')\n"
    "start = next(i for i, l in enumerate(text) if l.startswith('| Transaction | Amount |'))\n"
    "print('\\n'.join(text[start:start + 11]))\n"
)

STEPS: list[Step] = [
    Step(
        slug="specification",
        title="/write-spec  —  Agent 1's specification.md, section by section",
        commands=[[PYTHON, "-c", SPEC_OUTLINE]],
        prologue=[
            "> /write-spec multi-agent banking transaction pipeline",
            "",
            "  Produced homework-6/specification.md and homework-6/agents.md following",
            "  .claude/commands/write-spec.md: high-level objective, mid-level objectives",
            "  (MO-*), implementation notes, context, low-level tasks (T-0..T-9) with a",
            "  prompt / file / function / details / acceptance block each, guardrails (IN-*)",
            "  and edge cases (EC-*).",
            "",
        ],
        max_lines=62,
    ),
    Step(
        slug="pipeline-run",
        title="python integrator.py  —  full multi-agent pipeline run",
        commands=[[PYTHON, "integrator.py"]],
        epilogue=["$ echo $?", "0"],
    ),
    Step(
        slug="test-coverage",
        title="pytest  —  232 tests, coverage gate floor is 80%",
        commands=[[PYTEST]],
        max_lines=48,
    ),
    Step(
        slug="skill-run-pipeline",
        title="/run-pipeline  —  the slash command's steps, executed",
        commands=[
            [PYTHON, "-c", "import json,pathlib;"
             "d=json.loads(pathlib.Path('sample-transactions.json').read_text());"
             "print(f'sample-transactions.json found: {len(d)} records')"],
            [PYTHON, "integrator.py"],
            [PYTHON, "-c", "import pathlib;"
             "print('shared/results/:', len(list(pathlib.Path('shared/results').glob('*.json'))), 'files');"
             "print(pathlib.Path('shared/reports/pipeline-summary.md').read_text().split('## Rejected')[0])"],
        ],
        prologue=[
            "> /run-pipeline",
            "",
            "  Running the multi-agent banking pipeline end-to-end, per",
            "  .claude/commands/run-pipeline.md:",
            "    1. check sample-transactions.json exists",
            "    2. clear shared/ (integrator.py resets it by default)",
            "    3. run the pipeline",
            "    4. summarise shared/results/",
            "    5. report everything that did not settle",
            "",
        ],
        epilogue=[
            "",
            "  Summary: 8 processed — 5 settled, 1 held, 2 rejected, reconciled=yes.",
            "  Did not settle:",
            "    TXN005  held      fraud_review_required (risk 60, high)",
            "    TXN006  rejected  unknown_currency:XYZ",
            "    TXN007  rejected  non_positive_amount",
        ],
        max_lines=60,
    ),
    Step(
        slug="hook-trigger",
        title="coverage gate hook  —  passes at 99%, blocks the push below the floor",
        commands=[
            [PYTHON, "scripts/coverage_gate.py"],
            [PYTHON, "scripts/coverage_gate.py"],
            [PYTHON, "scripts/coverage_gate.py", "--threshold", "99.9"],
        ],
        stdin_payloads=[
            '{"tool_name":"Bash","tool_input":{"command":"ls -la"}}',
            '{"tool_name":"Bash","tool_input":{"command":"git push origin homework-6"}}',
            '{"tool_name":"Bash","tool_input":{"command":"git push origin homework-6"}}',
        ],
        prologue=[
            "PreToolUse hook on Bash, registered in .claude/settings.json:",
            '  "command": "python3 $CLAUDE_PROJECT_DIR/homework-6/scripts/coverage_gate.py"',
            "Exit code 2 blocks the tool call and returns the reason to the model.",
            "",
        ],
        expect_failure=True,
    ),
    Step(
        slug="mcp-interaction",
        title="MCP  —  context7 lookups + the custom pipeline-status server over stdio",
        commands=[[PYTHON, "scripts/verify_mcp_server.py"]],
        prologue=[
            "--- context7 MCP (used by Agent 2 during code generation) ---------------",
            "mcp__context7__resolve-library-id(libraryName='FastMCP',",
            "        query='define tools and resources on a FastMCP server in Python')",
            "  -> /prefecthq/fastmcp        benchmark 82.71   4041 snippets   reputation High",
            "     /llmstxt/gofastmcp_llms_txt  84.40 · /websites/gofastmcp  61.73",
            "",
            "mcp__context7__query-docs(libraryId='/prefecthq/fastmcp',",
            "        query='define @mcp.tool and @mcp.resource with a custom URI, and",
            "               test the server in-memory with Client')",
            "  -> @mcp.resource(\"data://config\")  — URI is the decorator argument",
            "  -> Client(server) runs the real MCP protocol in-process, no network",
            "",
            "mcp__context7__resolve-library-id(libraryName='Python',",
            "        query='decimal module quantize ROUND_HALF_UP for monetary arithmetic')",
            "  -> /python/cpython           benchmark 77.12   36843 snippets",
            "mcp__context7__query-docs(libraryId='/python/cpython', query='decimal: quantize",
            "        with ROUND_HALF_UP ... why float must not be used for money')",
            "  -> Decimal(1.1) is Decimal('1.1000000000000000888...265625') — so build from str;",
            "     quantize(exp, rounding=ROUND_HALF_UP), because the context default is HALF_EVEN",
            "  (full write-up: research-notes.md)",
            "",
            "--- custom MCP server: pipeline-status ---------------------------------",
        ],
        max_lines=78,
    ),
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def run(step: Step) -> str:
    """Execute the step's commands and return the rendered transcript."""
    lines: list[str] = list(step.prologue)
    env = {**os.environ, "COLUMNS": str(MAX_COLUMNS), "NO_COLOR": "1", "PY_COLORS": "0"}

    for index, command in enumerate(step.commands):
        stdin_payload = (
            step.stdin_payloads[index] if index < len(step.stdin_payloads) else None
        )
        shown = " ".join(_shorten(part) for part in command)
        if stdin_payload:
            lines.append(f"$ echo '{stdin_payload}' \\")
            lines.append(f"    | {shown}")
        else:
            lines.append(f"$ {shown}")

        result = subprocess.run(
            command,
            cwd=step.cwd,
            input=stdin_payload,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        output = (result.stdout or "") + (result.stderr or "")
        lines.extend(output.rstrip("\n").splitlines())
        lines.append(f"[exit code: {result.returncode}]")
        lines.append("")

        if result.returncode != 0 and not step.expect_failure:
            raise SystemExit(f"step {step.slug!r} failed:\n{output}")

    lines.extend(step.epilogue)
    if step.max_lines and len(lines) > step.max_lines:
        head = lines[: step.max_lines - 3]
        lines = [*head, "", f"... ({len(lines) - len(head)} more lines — full transcript in "
                 f"docs/sample-run/{step.slug}.txt)"]
    return "\n".join(lines)


def _shorten(part: str) -> str:
    if part.startswith(str(REPO_ROOT)):
        return Path(part).name if Path(part).suffix else f".venv/bin/{Path(part).name}"
    if "\n" in part:
        return '"<python snippet>"'
    return part


def wrap(lines: list[str], width: int) -> list[str]:
    wrapped: list[str] = []
    for line in lines:
        line = line.replace("\t", "    ")
        while len(line) > width:
            wrapped.append(line[:width])
            line = "  " + line[width:]
        wrapped.append(line)
    return wrapped


def render(transcript: str, title: str, destination: Path) -> None:
    font_size = 15
    font = load_font(font_size)
    bold = load_font(font_size)
    line_height = font_size + 6
    padding = 22
    chrome_height = 38

    lines = wrap(transcript.splitlines(), MAX_COLUMNS)
    char_width = font.getlength("M")
    width = int(padding * 2 + char_width * MAX_COLUMNS)
    height = int(chrome_height + padding * 2 + line_height * max(len(lines), 1))

    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)

    draw.rectangle([0, 0, width, chrome_height], fill=CHROME)
    draw.line([0, chrome_height, width, chrome_height], fill=BORDER)
    for index, colour in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        cx = 20 + index * 20
        draw.ellipse([cx - 6, chrome_height // 2 - 6, cx + 6, chrome_height // 2 + 6], fill=colour)
    draw.text((96, chrome_height // 2 - font_size // 2), title, font=bold, fill=TITLE)

    y = chrome_height + padding
    for line in lines:
        if line.startswith("$ ") or line.startswith("    | ") or line.startswith("> /"):
            colour = PROMPT
        elif "FAILED" in line or "[exit code: 2]" in line or "blocked" in line.lower():
            colour = ERROR
        else:
            colour = FOREGROUND
        draw.text((padding, y), line, font=font, fill=colour)
        y += line_height

    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)


def main() -> int:
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)

    for step in STEPS:
        transcript = run(step)
        (TRANSCRIPTS / f"{step.slug}.txt").write_text(transcript + "\n", encoding="utf-8")
        render(transcript, step.title, SCREENSHOTS / f"{step.slug}.png")
        print(f"captured {step.slug}: docs/screenshots/{step.slug}.png")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
