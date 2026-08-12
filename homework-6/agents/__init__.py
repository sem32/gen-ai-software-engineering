"""Multi-agent banking transaction pipeline — runtime agents.

Pipeline order (spec §3.6, extended by CR-01)::

    transaction_validator -> fraud_detector -> compliance_checker -> policy_engine
                                                    -> settlement_processor
                                                    \\-> reporting_agent (aggregates)

``policy_engine`` is the CR-01 addition: it applies a rule pack loaded from JSON, so behaviour is
configuration rather than code. The five original agents are unchanged (guardrail IN-8).
"""

from __future__ import annotations

from .base import BaseAgent
from .compliance_checker import ComplianceChecker
from .fraud_detector import FraudDetector
from .policy_engine import PolicyEngine
from .protocol import AuditLogger, MoneyError, ProtocolError, Workspace
from .reporting_agent import ReportingAgent
from .rule_engine import RuleError, RulePack
from .settlement_processor import SettlementProcessor
from .transaction_validator import TransactionValidator

#: The message-driven agents, in the order the integrator runs them.
PIPELINE_AGENTS = (
    TransactionValidator,
    FraudDetector,
    ComplianceChecker,
    PolicyEngine,
    SettlementProcessor,
)

__all__ = [
    "AuditLogger",
    "BaseAgent",
    "ComplianceChecker",
    "FraudDetector",
    "MoneyError",
    "PIPELINE_AGENTS",
    "PolicyEngine",
    "ProtocolError",
    "ReportingAgent",
    "RuleError",
    "RulePack",
    "SettlementProcessor",
    "TransactionValidator",
    "Workspace",
]
