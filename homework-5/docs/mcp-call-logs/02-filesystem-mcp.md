# Filesystem MCP — call log

> Produced by `python scripts/verify_mcp_servers.py filesystem`, which reads `homework-5/.mcp.json` and opens a real MCP session (initialize → tools/list → tools/call).

`@modelcontextprotocol/server-filesystem`, launched via `npx` with `./homework-5` and `./homework-2`.
This client does not advertise MCP *roots*, so the command-line directories stay in
effect; a roots-aware client such as Claude Code replaces them with its own project
root (see the Task 2 section of the README).

```text
### filesystem  <-  {"type": "stdio", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "./homework-5", "./homework-2"]}

========================================================================
filesystem :: tools/list  (14 tools)
========================================================================
create_directory, directory_tree, edit_file, get_file_info, list_allowed_directories, list_directory, list_directory_with_sizes, move_file, read_file, read_media_file, read_multiple_files, read_text_file, search_files, write_file

========================================================================
filesystem :: tools/call  list_allowed_directories
========================================================================
Allowed directories:
/Users/sem/git/education/gen-ai-software-engineering/homework-5
/Users/sem/git/education/gen-ai-software-engineering/homework-2

========================================================================
filesystem :: tools/call  list_directory(homework-5)
========================================================================
[FILE] .mcp.json
[DIR] .venv
[FILE] TASKS.md
[DIR] custom-mcp-server
[DIR] docs
[DIR] scripts

========================================================================
filesystem :: tools/call  read_text_file(custom-mcp-server/requirements.txt)
========================================================================
# Custom MCP server dependencies (Homework 5, Task 4)
# Install with:  pip install -r custom-mcp-server/requirements.txt
fastmcp>=3.4.6


========================================================================
filesystem :: tools/call  directory_tree(custom-mcp-server)
========================================================================
[
  {
    "name": "lorem-ipsum.md",
    "type": "file"
  },
  {
    "name": "requirements.txt",
    "type": "file"
  },
  {
    "name": "server.py",
    "type": "file"
  }
]

Done.
```
