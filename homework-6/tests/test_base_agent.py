"""Unit tests for the shared agent runtime (spec task T-0 / §3.5)."""

from __future__ import annotations

import pytest

from agents.base import BaseAgent
from agents.protocol import TERMINAL_TARGET, ProtocolError


def test_process_message_must_be_implemented(workspace, make_message):
    with pytest.raises(NotImplementedError):
        BaseAgent(workspace).process_message(make_message())


def test_finalize_rejects_a_status_outside_the_closed_set(workspace, make_message):
    agent = BaseAgent(workspace)
    with pytest.raises(ProtocolError, match="terminal status"):
        agent.finalize(make_message(), {"transaction_id": "TXN001", "status": "probably_fine"})


@pytest.mark.parametrize("status", ["rejected", "held", "settled"])
def test_finalize_accepts_every_terminal_status(workspace, make_message, status):
    message = agent_finalize(workspace, make_message(), status)
    assert message["target_agent"] == TERMINAL_TARGET
    assert message["data"]["status"] == status


def agent_finalize(workspace, message, status):
    return BaseAgent(workspace).finalize(message, {"transaction_id": "TXN001", "status": status})


def test_next_data_is_a_deep_copy(workspace, make_message):
    message = make_message()
    data = BaseAgent(workspace).next_data(message)
    data["metadata"]["channel"] = "changed"
    assert message["data"]["metadata"]["channel"] == "online"


def test_next_data_tolerates_a_missing_payload(workspace):
    assert BaseAgent(workspace).next_data({}) == {}


def test_forward_preserves_the_message_type(workspace, make_message):
    incoming = make_message()
    incoming["message_type"] = "correction"
    outgoing = BaseAgent(workspace).forward(incoming, {"transaction_id": "TXN001"}, "next_agent")
    assert outgoing["message_type"] == "correction"
    assert outgoing["target_agent"] == "next_agent"


def test_agent_uses_the_injected_audit_logger(workspace):
    logger = workspace.audit_logger()
    assert BaseAgent(workspace, logger).audit is logger
