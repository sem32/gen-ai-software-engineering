"""Multi-agent banking transaction pipeline — runtime agents.

Pipeline order (spec §3.6)::

    transaction_validator -> fraud_detector -> compliance_checker -> settlement_processor
                                                                  \\-> reporting_agent (aggregates)
"""

from __future__ import annotations

from .base import BaseAgent
from .compliance_checker import ComplianceChecker
from .fraud_detector import FraudDetector
from .protocol import AuditLogger, MoneyError, ProtocolError, Workspace
from .reporting_agent import ReportingAgent
from .settlement_processor import SettlementProcessor
from .transaction_validator import TransactionValidator

#: The message-driven agents, in the order the integrator runs them.
PIPELINE_AGENTS = (
    TransactionValidator,
    FraudDetector,
    ComplianceChecker,
    SettlementProcessor,
)

__all__ = [
    "AuditLogger",
    "BaseAgent",
    "ComplianceChecker",
    "FraudDetector",
    "MoneyError",
    "PIPELINE_AGENTS",
    "ProtocolError",
    "ReportingAgent",
    "SettlementProcessor",
    "TransactionValidator",
    "Workspace",
]
