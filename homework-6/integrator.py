"""Orchestrator for the multi-agent banking pipeline (spec task T-6).

Creates the shared workspace, drops one protocol message per input record into ``shared/input``,
runs the agents in order — each draining its inbox once — and finally produces the run summary.

Usage::

    python integrator.py                      # run against sample-transactions.json
    python integrator.py --sample other.json  # run against a different input file
    python integrator.py --no-reset           # keep whatever is already in shared/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    # append, never insert: the local `mcp/` directory must not shadow the installed `mcp` package
    sys.path.append(str(PROJECT_ROOT))

from agents import PIPELINE_AGENTS, PolicyEngine, ReportingAgent  # noqa: E402
from agents.policy_engine import available_packs  # noqa: E402
from agents.protocol import Workspace, build_message  # noqa: E402

DEFAULT_SAMPLE = PROJECT_ROOT / "sample-transactions.json"
DEFAULT_SHARED = PROJECT_ROOT / "shared"

FIRST_AGENT = "transaction_validator"
INTEGRATOR_NAME = "integrator"
TERMINAL_TARGET = "pipeline_results"


def build_agent(agent_class, workspace: Workspace, audit, rules=None):
    """Instantiate one agent, handing the rule pack to the only agent that takes one."""
    if agent_class is PolicyEngine:
        return agent_class(workspace, audit, pack=rules)
    return agent_class(workspace, audit)


def drain_pipeline(
    workspace: Workspace, audit=None, rules=None
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Run every message-driven agent once, in order, and report what each emitted.

    This is the single code path the CLI, the API gateway and the demo all go through — the gateway
    must never reimplement a decision (spec T-13).
    """
    audit = audit if audit is not None else workspace.audit_logger()
    stages: list[tuple[str, list[dict[str, Any]]]] = []
    for agent_class in PIPELINE_AGENTS:
        emitted = build_agent(agent_class, workspace, audit, rules).run()
        stages.append((agent_class.name, emitted))
    return stages


def submit_transaction_traced(
    workspace: Workspace, transaction: dict[str, Any], *, rules=None, audit=None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Like :func:`submit_transaction`, but also returns the hops this transaction actually took.

    The trace is *observed*, not reconstructed: it records which agent emitted which status while the
    drain was happening. It gives the in-process transport the same hop-by-hop story the REST chain
    returns, so the presentation can animate either one.
    """
    audit = audit if audit is not None else workspace.audit_logger()
    seeded = seed_input(workspace, [transaction], audit=audit)
    wanted = transaction.get("transaction_id")

    def belongs(message: dict[str, Any]) -> bool:
        if wanted is None:
            return True
        return str((message.get("data") or {}).get("transaction_id")) == str(wanted)

    trace: list[dict[str, Any]] = []
    terminal: list[dict[str, Any]] = []

    for position, (agent_name, emitted) in enumerate(drain_pipeline(workspace, audit, rules), start=1):
        for message in emitted:
            if not belongs(message):
                continue
            is_terminal = message["target_agent"] == TERMINAL_TARGET
            trace.append(
                {
                    "agent": agent_name,
                    "position": position,
                    "status": str((message.get("data") or {}).get("status", "unknown")),
                    "next": message["target_agent"],
                    "terminal": is_terminal,
                }
            )
            if is_terminal:
                terminal.append(message)

    if terminal:
        return terminal[-1], trace

    raise RuntimeError(
        f"transaction {wanted!r} produced no terminal outcome "
        f"(seeded {len(seeded)} message(s), {len(trace)} hop(s))"
    )


def submit_transaction(
    workspace: Workspace, transaction: dict[str, Any], *, rules=None, audit=None
) -> dict[str, Any]:
    """Push one raw transaction through the pipeline and return its terminal message.

    Used by the HTTP gateway: seed one message, drain the agents, then pick the terminal message that
    came out. Returns ``None`` only if the transaction produced no terminal outcome at all, which
    would be a reconciliation bug rather than a business result.
    """
    audit = audit if audit is not None else workspace.audit_logger()
    seeded = seed_input(workspace, [transaction], audit=audit)
    wanted = transaction.get("transaction_id")

    terminal: list[dict[str, Any]] = [
        message
        for _name, emitted in drain_pipeline(workspace, audit, rules)
        for message in emitted
        if message["target_agent"] == TERMINAL_TARGET
    ]

    if wanted is not None:
        for message in terminal:
            if str((message.get("data") or {}).get("transaction_id")) == str(wanted):
                return message
    if len(terminal) == 1:
        # No usable id (the validator will have rejected it for that) but the drain is serialised,
        # so a single terminal message is unambiguously this submission's outcome.
        return terminal[0]

    # Nothing terminal came back — surface it rather than pretending the call succeeded.
    raise RuntimeError(
        f"transaction {wanted!r} produced no terminal outcome "
        f"(seeded {len(seeded)} message(s), {len(terminal)} terminal)"
    )


def load_sample(sample_path: Path | str) -> list[dict[str, Any]]:
    """Load the raw transaction records."""
    records = json.loads(Path(sample_path).read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError(f"{sample_path} must contain a JSON array of transactions")
    return records


def seed_input(
    workspace: Workspace, transactions: list[dict[str, Any]], audit=None
) -> list[Path]:
    """Write one protocol message per transaction into ``shared/input``."""
    audit = audit if audit is not None else workspace.audit_logger()
    paths: list[Path] = []
    for transaction in transactions:
        message = build_message(
            source_agent=INTEGRATOR_NAME,
            target_agent=FIRST_AGENT,
            message_type="transaction",
            data=dict(transaction),
        )
        paths.append(workspace.write_message(workspace.input_dir, message))
        audit.record(
            INTEGRATOR_NAME,
            str(transaction.get("transaction_id", "UNKNOWN")),
            "ingested",
            {"target_agent": FIRST_AGENT},
        )
    return paths


def run_pipeline(
    sample_path: Path | str = DEFAULT_SAMPLE,
    shared_root: Path | str = DEFAULT_SHARED,
    *,
    reset: bool = True,
    verbose: bool = True,
    rules=None,
) -> dict[str, Any]:
    """Run the whole pipeline end to end and return the run summary.

    ``rules`` selects the policy rule pack (a name, a path or a loaded pack). ``None`` means the
    default pack, or whatever ``HW6_POLICY_RULES`` names.
    """
    transactions = load_sample(sample_path)
    workspace = Workspace.create(shared_root, reset=reset)
    audit = workspace.audit_logger()

    def say(line: str) -> None:
        if verbose:
            print(line)

    say(f"[integrator] workspace  : {workspace.root}")
    say(f"[integrator] input file  : {sample_path}")
    say(f"[integrator] rule pack   : {PolicyEngine(workspace, audit, pack=rules).pack_name}")
    seed_input(workspace, transactions, audit=audit)
    say(f"[integrator] ingested    : {len(transactions)} transaction(s) -> shared/input")

    for agent_name, emitted in drain_pipeline(workspace, audit, rules):
        terminal = sum(1 for message in emitted if message["target_agent"] == TERMINAL_TARGET)
        say(
            f"[{agent_name}] processed {len(emitted)} message(s), "
            f"{terminal} terminal, {len(emitted) - terminal} forwarded"
        )

    summary = ReportingAgent(workspace, audit).run()

    pending = len(list(workspace.input_dir.glob("*.json"))) + len(
        list(workspace.output_dir.glob("*.json"))
    )
    quarantined = len(list(workspace.quarantine_dir.glob("*.json")))
    summary["reconciled"] = (
        summary["total_transactions"] + quarantined == len(transactions) and pending == 0
    )
    summary["pending_messages"] = pending
    summary["quarantined_messages"] = quarantined
    summary["input_count"] = len(transactions)

    if verbose:
        print()
        print(render_results_table(summary))

    return summary


def render_results_table(summary: dict[str, Any]) -> str:
    """Fixed-width table of every terminal outcome, for the terminal."""
    header = f"{'TRANSACTION':<13}{'STATUS':<11}{'AMOUNT':>12} {'CUR':<5}{'RISK':<12}DETAIL"
    width = max(len(header), 96)
    lines = ["PIPELINE RESULTS", "=" * width, header, "-" * width]
    for row in summary["transactions"]:
        risk = "-" if row["risk_score"] is None else f"{row['risk_score']} ({row['risk_level']})"
        lines.append(
            f"{row['transaction_id']:<13}{row['status']:<11}{row['amount']:>12} "
            f"{row['currency']:<5}{risk:<12}{row['detail']}"
        )
    lines.append("-" * width)

    counts = "  ".join(f"{status}={count}" for status, count in summary["by_status"].items())
    lines.append(f"total={summary['total_transactions']}  {counts}")
    for currency, buckets in summary["volume_by_currency"].items():
        parts = "  ".join(f"{key}={value}" for key, value in buckets.items())
        lines.append(f"{currency}: {parts}")
    lines.append(
        f"reconciled={'yes' if summary.get('reconciled') else 'NO'}  "
        f"pending={summary.get('pending_messages', 0)}  "
        f"quarantined={summary.get('quarantined_messages', 0)}"
    )
    lines.append("=" * width)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Multi-agent banking pipeline orchestrator")
    parser.add_argument("--sample", default=str(DEFAULT_SAMPLE), help="input transactions file")
    parser.add_argument("--shared", default=str(DEFAULT_SHARED), help="shared workspace root")
    parser.add_argument(
        "--no-reset", action="store_true", help="do not clear shared/ before the run"
    )
    parser.add_argument("--quiet", action="store_true", help="suppress progress output")
    parser.add_argument(
        "--rules",
        default=None,
        metavar="PACK",
        help=f"policy rule pack: a name, a file name or a path (available: {', '.join(available_packs())})",
    )
    args = parser.parse_args(argv)

    summary = run_pipeline(
        args.sample,
        args.shared,
        reset=not args.no_reset,
        verbose=not args.quiet,
        rules=args.rules,
    )

    if not summary["reconciled"]:
        print(
            "[integrator] RECONCILIATION FAILED — "
            f"{summary['input_count']} in, {summary['total_transactions']} terminal, "
            f"{summary['pending_messages']} still pending",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
