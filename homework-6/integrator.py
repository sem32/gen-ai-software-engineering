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

from agents import PIPELINE_AGENTS, ReportingAgent  # noqa: E402
from agents.protocol import Workspace, build_message  # noqa: E402

DEFAULT_SAMPLE = PROJECT_ROOT / "sample-transactions.json"
DEFAULT_SHARED = PROJECT_ROOT / "shared"

FIRST_AGENT = "transaction_validator"
INTEGRATOR_NAME = "integrator"


def load_sample(sample_path: Path | str) -> list[dict[str, Any]]:
    """Load the raw transaction records."""
    records = json.loads(Path(sample_path).read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError(f"{sample_path} must contain a JSON array of transactions")
    return records


def seed_input(workspace: Workspace, transactions: list[dict[str, Any]]) -> list[Path]:
    """Write one protocol message per transaction into ``shared/input``."""
    audit = workspace.audit_logger()
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
) -> dict[str, Any]:
    """Run the whole pipeline end to end and return the run summary."""
    transactions = load_sample(sample_path)
    workspace = Workspace.create(shared_root, reset=reset)
    audit = workspace.audit_logger()

    def say(line: str) -> None:
        if verbose:
            print(line)

    say(f"[integrator] workspace  : {workspace.root}")
    say(f"[integrator] input file  : {sample_path}")
    seed_input(workspace, transactions)
    say(f"[integrator] ingested    : {len(transactions)} transaction(s) -> shared/input")

    for agent_class in PIPELINE_AGENTS:
        emitted = agent_class(workspace, audit).run()
        terminal = sum(1 for message in emitted if message["target_agent"] == "pipeline_results")
        say(
            f"[{agent_class.name}] processed {len(emitted)} message(s), "
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
    args = parser.parse_args(argv)

    summary = run_pipeline(
        args.sample, args.shared, reset=not args.no_reset, verbose=not args.quiet
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
