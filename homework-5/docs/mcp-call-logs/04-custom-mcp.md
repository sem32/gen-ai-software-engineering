# Custom MCP server (lorem-mcp) — call log

> Produced by `python scripts/verify_mcp_servers.py lorem-custom`, which reads `homework-5/.mcp.json` and opens a real MCP session (initialize → tools/list → tools/call).

The custom FastMCP server from `custom-mcp-server/server.py`, launched over stdio.

```text
### lorem-custom  <-  {"type": "stdio", "command": "./homework-5/.venv/bin/python", "args": ["./homework-5/custom-mcp-server/server.py"]}

========================================================================
lorem-custom :: tools/list  (1 tools)
========================================================================
- read: Read the lorem-ipsum document.
  input schema: {"additionalProperties": false, "properties": {"word_count": {"default": 30, "type": "integer", "description": "How many words to return. Defaults to 30."}}, "type": "object"}

========================================================================
lorem-custom :: resources/list
========================================================================
- lorem://ipsum (text/plain): The lorem-ipsum document, truncated to the default 30 words.

========================================================================
lorem-custom :: resources/templates/list
========================================================================
- lorem://ipsum/{word_count} (text/plain): The lorem-ipsum document, truncated to ``word_count`` words.

========================================================================
lorem-custom :: resources/read  lorem://ipsum   (default word_count = 30)
========================================================================
Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi

-> word count: 30

========================================================================
lorem-custom :: resources/read  lorem://ipsum/10
========================================================================
Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do

-> word count: 10

========================================================================
lorem-custom :: tools/call  read()   (no arguments -> default 30)
========================================================================
Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi

-> word count: 30

========================================================================
lorem-custom :: tools/call  read(word_count=5)
========================================================================
Lorem ipsum dolor sit amet,

-> word count: 5

Done.
```
