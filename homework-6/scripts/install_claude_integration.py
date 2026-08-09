#!/usr/bin/env python3
"""Install (or remove) the homework-6 Claude Code integration at the repository root.

Everything this homework produces lives inside ``homework-6/``. But Claude Code only loads three
things from the **repository root**: `.claude/settings.json` (hooks), `.claude/commands/` (slash
commands) and `.mcp.json` (MCP servers). This script wires the homework-6 versions of those into
the root — reversibly, and without silently clobbering anything that is already there.

    python scripts/install_claude_integration.py            # install
    python scripts/install_claude_integration.py --status   # show what is currently wired
    python scripts/install_claude_integration.py --uninstall # remove everything it added
    python scripts/install_claude_integration.py --git-hook  # also install .git/hooks/pre-push

What it does:
  * `.claude/commands/{write-spec,run-pipeline,validate-transactions}.md` -> symlinks into
    `homework-6/.claude/commands/`
  * `.claude/settings.json` -> the coverage-gate hook from `homework-6/.claude/settings.json`
    (merged into an existing file if one is present; a backup is written first)
  * `.mcp.json` -> adds the `context7` and `pipeline-status` entries from `homework-6/mcp.json`
    (existing servers are left untouched)

Nothing outside those three files is modified, and `--uninstall` restores them.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent          # homework-6/
REPO = PROJECT.parent                                     # repository root
COMMANDS = ("write-spec", "run-pipeline", "validate-transactions")
MCP_SERVERS = ("context7", "pipeline-status")
MARKER = "_homework6_managed"


def relative_to_repo(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


# --------------------------------------------------------------------------------------
# slash commands
# --------------------------------------------------------------------------------------


def install_commands(report: list[str]) -> None:
    target_dir = REPO / ".claude" / "commands"
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in COMMANDS:
        source = PROJECT / ".claude" / "commands" / f"{name}.md"
        target = target_dir / f"{name}.md"
        if target.exists() and not target.is_symlink():
            report.append(f"  skip   {relative_to_repo(target)} — a real file is already there")
            continue
        if target.is_symlink() or target.exists():
            target.unlink()
        target.symlink_to(os.path.relpath(source, target_dir))
        report.append(f"  link   {relative_to_repo(target)} -> {relative_to_repo(source)}")


def uninstall_commands(report: list[str]) -> None:
    target_dir = REPO / ".claude" / "commands"
    for name in COMMANDS:
        target = target_dir / f"{name}.md"
        if target.is_symlink():
            target.unlink()
            report.append(f"  remove {relative_to_repo(target)}")
    if target_dir.is_dir() and not any(target_dir.iterdir()):
        target_dir.rmdir()
        report.append(f"  remove {relative_to_repo(target_dir)}/ (empty)")


# --------------------------------------------------------------------------------------
# hooks
# --------------------------------------------------------------------------------------


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def install_settings(report: list[str]) -> None:
    source = load_json(PROJECT / ".claude" / "settings.json")
    target_path = REPO / ".claude" / "settings.json"
    existing = load_json(target_path)

    if existing:
        backup = target_path.with_suffix(".json.pre-homework6")
        if not backup.exists():
            shutil.copy2(target_path, backup)
            report.append(f"  backup {relative_to_repo(backup)}")

    merged = dict(existing)
    hooks = dict(merged.get("hooks") or {})
    for event, entries in (source.get("hooks") or {}).items():
        tagged = [{**entry, MARKER: True} for entry in entries]
        kept = [entry for entry in hooks.get(event, []) if not entry.get(MARKER)]
        hooks[event] = kept + tagged
    merged["hooks"] = hooks
    merged.setdefault("$schema", source.get("$schema", ""))

    dump_json(target_path, merged)
    report.append(f"  write  {relative_to_repo(target_path)} — coverage gate + pipeline reminder")


def uninstall_settings(report: list[str]) -> None:
    target_path = REPO / ".claude" / "settings.json"
    if not target_path.exists():
        return
    settings = load_json(target_path)
    hooks = {
        event: [entry for entry in entries if not entry.get(MARKER)]
        for event, entries in (settings.get("hooks") or {}).items()
    }
    hooks = {event: entries for event, entries in hooks.items() if entries}

    if hooks:
        settings["hooks"] = hooks
        dump_json(target_path, settings)
        report.append(f"  clean  {relative_to_repo(target_path)} — homework-6 hooks removed")
        return

    settings.pop("hooks", None)
    if settings and set(settings) != {"$schema"}:
        dump_json(target_path, settings)
        report.append(f"  clean  {relative_to_repo(target_path)} — homework-6 hooks removed")
    else:
        target_path.unlink()
        report.append(f"  remove {relative_to_repo(target_path)}")


# --------------------------------------------------------------------------------------
# MCP servers
# --------------------------------------------------------------------------------------


def install_mcp(report: list[str]) -> None:
    source = load_json(PROJECT / "mcp.json").get("mcpServers", {})
    target_path = REPO / ".mcp.json"
    config = load_json(target_path)
    servers = config.setdefault("mcpServers", {})
    for name in MCP_SERVERS:
        if name in servers and name != "pipeline-status":
            report.append(f"  keep   .mcp.json::{name} — already configured")
            continue
        servers[name] = source[name]
        report.append(f"  add    .mcp.json::{name}")
    dump_json(target_path, config)

    local_path = REPO / ".claude" / "settings.local.json"
    local = load_json(local_path)
    enabled = local.setdefault("enabledMcpjsonServers", [])
    for name in MCP_SERVERS:
        if name not in enabled:
            enabled.append(name)
    dump_json(local_path, local)
    report.append("  enable settings.local.json::enabledMcpjsonServers")


def uninstall_mcp(report: list[str]) -> None:
    target_path = REPO / ".mcp.json"
    config = load_json(target_path)
    servers = config.get("mcpServers", {})
    for name in MCP_SERVERS:
        if servers.pop(name, None) is not None:
            report.append(f"  remove .mcp.json::{name}")
    if config:
        dump_json(target_path, config)

    local_path = REPO / ".claude" / "settings.local.json"
    local = load_json(local_path)
    if "enabledMcpjsonServers" in local:
        local["enabledMcpjsonServers"] = [
            name for name in local["enabledMcpjsonServers"] if name not in MCP_SERVERS
        ]
        dump_json(local_path, local)
        report.append("  clean  settings.local.json::enabledMcpjsonServers")


# --------------------------------------------------------------------------------------
# git hook
# --------------------------------------------------------------------------------------


def install_git_hook(report: list[str]) -> None:
    hooks_dir = REPO / ".git" / "hooks"
    if not hooks_dir.is_dir():
        report.append("  skip   .git/hooks — not a git checkout")
        return
    target = hooks_dir / "pre-push"
    if target.exists() and not target.is_symlink():
        report.append("  skip   .git/hooks/pre-push — a real hook is already there")
        return
    if target.is_symlink():
        target.unlink()
    target.symlink_to(os.path.relpath(PROJECT / "scripts" / "pre-push", hooks_dir))
    report.append("  link   .git/hooks/pre-push -> homework-6/scripts/pre-push")


def uninstall_git_hook(report: list[str]) -> None:
    target = REPO / ".git" / "hooks" / "pre-push"
    if target.is_symlink():
        target.unlink()
        report.append("  remove .git/hooks/pre-push")


# --------------------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------------------


def status() -> int:
    print(f"repository root : {REPO}")
    for name in COMMANDS:
        target = REPO / ".claude" / "commands" / f"{name}.md"
        state = "linked" if target.is_symlink() else ("file" if target.exists() else "absent")
        print(f"  /{name:<24} {state}")

    settings = load_json(REPO / ".claude" / "settings.json")
    managed = sum(
        1
        for entries in (settings.get("hooks") or {}).values()
        for entry in entries
        if entry.get(MARKER)
    )
    print(f"  coverage-gate hook       {'installed' if managed else 'absent'} ({managed} entries)")

    servers = load_json(REPO / ".mcp.json").get("mcpServers", {})
    for name in MCP_SERVERS:
        print(f"  mcp::{name:<20} {'configured' if name in servers else 'absent'}")

    hook = REPO / ".git" / "hooks" / "pre-push"
    print(f"  git pre-push             {'installed' if hook.exists() else 'absent'}")
    return 0


# --------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--uninstall", action="store_true", help="remove everything this installed")
    mode.add_argument("--status", action="store_true", help="report what is currently wired")
    parser.add_argument("--git-hook", action="store_true", help="also install .git/hooks/pre-push")
    args = parser.parse_args(argv)

    if args.status:
        return status()

    report: list[str] = []
    if args.uninstall:
        uninstall_commands(report)
        uninstall_settings(report)
        uninstall_mcp(report)
        uninstall_git_hook(report)
        headline = "Removed the homework-6 Claude Code integration:"
    else:
        install_commands(report)
        install_settings(report)
        install_mcp(report)
        if args.git_hook:
            install_git_hook(report)
        headline = "Installed the homework-6 Claude Code integration:"

    print(headline)
    print("\n".join(report) if report else "  (nothing to do)")
    if not args.uninstall:
        print("\nRestart Claude Code so it picks up .mcp.json and the hooks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
