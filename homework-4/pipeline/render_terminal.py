#!/usr/bin/env python3
"""Turn a captured terminal transcript into a styled HTML page for screenshotting.

The pipeline logs real ANSI-coloured output. This converts one or more transcripts into an HTML
page that looks like the terminal they came from, so the screenshots committed under
`docs/screenshots/` show genuine tool output rather than a mock-up.

Usage:
    render_terminal.py OUT.html "Title" TRANSCRIPT [TRANSCRIPT ...]

Each TRANSCRIPT may be given as `label=path` to caption the pane.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ANSI_RE = re.compile(r"\033\[([0-9;]*)m")

# Terminal palette (dark background, matching a standard macOS terminal profile).
COLOURS = {
    "30": "#3b4048", "31": "#e06c75", "32": "#98c379", "33": "#e5c07b",
    "34": "#61afef", "35": "#c678dd", "36": "#56b6c2", "37": "#dcdfe4",
    "90": "#7f848e", "91": "#ff7b86", "92": "#b5e890", "93": "#f0d399",
    "94": "#82c4ff", "95": "#dda0f0", "96": "#7fd6dd", "97": "#ffffff",
}


def ansi_to_html(text: str) -> str:
    """Convert ANSI SGR sequences into nested <span> elements."""
    out: list[str] = []
    open_spans = 0
    position = 0

    for match in ANSI_RE.finditer(text):
        out.append(html.escape(text[position : match.start()]))
        position = match.end()
        codes = [code for code in match.group(1).split(";") if code] or ["0"]

        for code in codes:
            if code == "0":
                out.append("</span>" * open_spans)
                open_spans = 0
            elif code == "1":
                out.append('<span style="font-weight:600">')
                open_spans += 1
            elif code == "2":
                out.append('<span style="opacity:.62">')
                open_spans += 1
            elif code in COLOURS:
                out.append(f'<span style="color:{COLOURS[code]}">')
                open_spans += 1

    out.append(html.escape(text[position:]))
    out.append("</span>" * open_spans)
    return "".join(out)


PAGE = """<!doctype html>
<meta charset="utf-8">
<title>{title}</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 28px; background: #14161a;
    font-family: "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
  }}
  h1 {{
    font-family: -apple-system, "Segoe UI", system-ui, sans-serif;
    font-size: 15px; font-weight: 600; color: #dcdfe4;
    margin: 0 0 18px; letter-spacing: .2px;
  }}
  .window {{
    background: #1c1f26; border: 1px solid #2c313a; border-radius: 10px;
    overflow: hidden; margin-bottom: 22px;
    box-shadow: 0 12px 30px rgba(0,0,0,.45);
  }}
  .titlebar {{
    display: flex; align-items: center; gap: 8px;
    padding: 9px 13px; background: #22262e; border-bottom: 1px solid #2c313a;
  }}
  .dot {{ width: 11px; height: 11px; border-radius: 50%; }}
  .caption {{
    margin-left: 8px; font-size: 11.5px; color: #9aa2ad;
    font-family: -apple-system, "Segoe UI", system-ui, sans-serif;
  }}
  pre {{
    margin: 0; padding: 15px 17px; color: #dcdfe4;
    font-size: 12px; line-height: 1.52; white-space: pre-wrap; word-break: break-word;
  }}
</style>
<h1>{title}</h1>
{panes}
"""

PANE = """<div class="window">
  <div class="titlebar">
    <span class="dot" style="background:#ff5f57"></span>
    <span class="dot" style="background:#febc2e"></span>
    <span class="dot" style="background:#28c840"></span>
    <span class="caption">{caption}</span>
  </div>
  <pre>{body}</pre>
</div>"""


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(__doc__)
        return 2

    out_path, title, *sources = argv[1:]
    panes = []

    for source in sources:
        label, _, path = source.partition("=")
        if not path:
            path, label = label, Path(label).name
        text = Path(path).read_text(encoding="utf-8", errors="replace").rstrip("\n")
        panes.append(PANE.format(caption=html.escape(label), body=ansi_to_html(text)))

    Path(out_path).write_text(
        PAGE.format(title=html.escape(title), panes="\n".join(panes)), encoding="utf-8"
    )
    print(out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
