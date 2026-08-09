"""Custom MCP server (Homework 5, Task 4).

Exposes the text of ``lorem-ipsum.md`` to an MCP client:

* **Resources** — URIs the client may *read* from:
    - ``lorem://ipsum``               -> first 30 words (the default)
    - ``lorem://ipsum/{word_count}``  -> first ``word_count`` words
* **Tool** — an action the client may *call*:
    - ``read(word_count: int = 30)``  -> the same word-limited content

Run with stdio transport (the transport MCP clients use for local servers):

    python server.py

Author: Simon Darienko
"""

from __future__ import annotations

import argparse
from pathlib import Path

from fastmcp import FastMCP

DEFAULT_WORD_COUNT = 30
LOREM_FILE = Path(__file__).resolve().parent / "lorem-ipsum.md"

mcp = FastMCP(
    name="lorem-mcp",
    instructions=(
        "Serves word-limited excerpts of a local lorem-ipsum document. "
        "Read the resource lorem://ipsum/{word_count} or call the `read` tool "
        "with an optional word_count argument (default 30)."
    ),
)


def _load_words() -> list[str]:
    """Return every word of ``lorem-ipsum.md``, ignoring Markdown headings."""
    if not LOREM_FILE.exists():
        raise FileNotFoundError(f"Source document not found: {LOREM_FILE}")

    text = LOREM_FILE.read_text(encoding="utf-8")
    body = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    return " ".join(body).split()


def _read_words(word_count: int = DEFAULT_WORD_COUNT) -> str:
    """Return exactly ``word_count`` words from the document, space-separated.

    Raises ``ValueError`` for a non-positive count or a count larger than the
    document, so the client gets an explicit error instead of silent truncation.
    """
    word_count = int(word_count)
    if word_count < 1:
        raise ValueError("word_count must be a positive integer")

    words = _load_words()
    if word_count > len(words):
        raise ValueError(
            f"word_count={word_count} exceeds the document length ({len(words)} words)"
        )

    return " ".join(words[:word_count])


@mcp.resource("lorem://ipsum", mime_type="text/plain")
def lorem_default() -> str:
    """The lorem-ipsum document, truncated to the default 30 words."""
    return _read_words(DEFAULT_WORD_COUNT)


@mcp.resource("lorem://ipsum/{word_count}", mime_type="text/plain")
def lorem_words(word_count: int) -> str:
    """The lorem-ipsum document, truncated to ``word_count`` words."""
    return _read_words(word_count)


@mcp.tool
def read(word_count: int = DEFAULT_WORD_COUNT) -> str:
    """Read the lorem-ipsum document.

    Args:
        word_count: How many words to return. Defaults to 30.

    Returns:
        The first ``word_count`` words of the document, space-separated.
    """
    return _read_words(word_count)


def main() -> None:
    parser = argparse.ArgumentParser(description="Lorem ipsum MCP server")
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "http"],
        help="MCP transport to serve on (default: stdio)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="host for --transport http")
    parser.add_argument("--port", type=int, default=8765, help="port for --transport http")
    args = parser.parse_args()

    if args.transport == "http":
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
