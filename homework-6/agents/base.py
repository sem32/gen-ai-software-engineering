"""Common runtime for every pipeline agent (spec §3.5, §3.6).

An agent never calls another agent. It drains an inbox directory, claims each message into
``shared/processing`` before working on it, and emits exactly one outgoing message per input —
either forwarded to the next agent through ``shared/output`` or terminal in ``shared/results``.
"""

from __future__ import annotations

import copy
from typing import Any

from . import protocol
from .protocol import TERMINAL_TARGET, AuditLogger, Workspace


class BaseAgent:
    """Base class for the file-driven agents.

    Subclasses set :attr:`name` and :attr:`inbox` and implement :meth:`process_message`.
    """

    #: Agent name, used as the routing key and in the audit trail.
    name: str = "base_agent"
    #: Shared subdirectory this agent reads from.
    inbox: str = "output"

    def __init__(self, workspace: Workspace, audit: AuditLogger | None = None) -> None:
        self.workspace = workspace
        self.audit = audit if audit is not None else workspace.audit_logger()

    # -- to be implemented by subclasses -----------------------------------------------

    def process_message(self, message: dict[str, Any]) -> dict[str, Any]:
        """Turn an incoming message into the next protocol message."""
        raise NotImplementedError

    # -- helpers for subclasses --------------------------------------------------------

    def forward(
        self, message: dict[str, Any], data: dict[str, Any], target_agent: str
    ) -> dict[str, Any]:
        """Build a message routed to the next agent."""
        return protocol.build_message(
            source_agent=self.name,
            target_agent=target_agent,
            message_type=message.get("message_type", "transaction"),
            data=data,
        )

    def finalize(self, message: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
        """Build a terminal message destined for ``shared/results``."""
        status = data.get("status")
        if status not in protocol.TERMINAL_STATUSES:
            raise protocol.ProtocolError(
                f"terminal status must be one of {protocol.TERMINAL_STATUSES}, got {status!r}"
            )
        return protocol.build_message(
            source_agent=self.name,
            target_agent=TERMINAL_TARGET,
            message_type=message.get("message_type", "transaction"),
            data=data,
        )

    @staticmethod
    def next_data(message: dict[str, Any]) -> dict[str, Any]:
        """A deep copy of the incoming payload — agents add sections, never mutate in place."""
        return copy.deepcopy(message.get("data") or {})

    # -- the drain loop ----------------------------------------------------------------

    def run(self) -> list[dict[str, Any]]:
        """Drain the inbox once and return every emitted message."""
        inbox = self.workspace.dir(self.inbox)
        emitted: list[dict[str, Any]] = []

        for path, message, error in list(self.workspace.iter_inbox(inbox, self.name)):
            if error is not None or message is None:
                reason = error or "unreadable message"
                self.workspace.quarantine(path, reason)
                self.audit.record(
                    self.name, "UNKNOWN", "quarantined", {"file": path.name, "reason": reason}
                )
                continue

            self.workspace.claim(path)
            outgoing = self.process_message(message)
            protocol.validate_message(outgoing)

            transaction_id = protocol.transaction_id_of(outgoing)
            terminal = outgoing["target_agent"] == TERMINAL_TARGET
            status = str((outgoing.get("data") or {}).get("status", "unknown"))

            # Audit first, result second (spec §3.3): a crash in between leaves evidence.
            self.audit.record(
                self.name,
                transaction_id,
                status,
                {"terminal": terminal, "next_agent": outgoing["target_agent"]},
            )

            destination = self.workspace.results_dir if terminal else self.workspace.output_dir
            self.workspace.write_message(destination, outgoing, require_masked=terminal)
            emitted.append(outgoing)

        return emitted
