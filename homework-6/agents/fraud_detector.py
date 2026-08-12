"""Agent 2 of the runtime pipeline — risk scoring (spec task T-2).

Consumes validated transactions and attaches a ``fraud`` section: a capped 0–100 risk score, a
risk level, a review flag and the itemised list of rules that fired. The detector never touches
the monetary amount (guardrail IN-4) and reads no wall clock — the transaction's own timestamp
drives the timing rules (guardrail IN-6).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

if __package__ in (None, ""):  # pragma: no cover - only when run as a script (PEP 366)
    import sys as _sys

    _sys.path.append(str(Path(__file__).resolve().parent.parent))
    __package__ = "agents"

from .base import BaseAgent
from .protocol import CURRENCY_REGIONS, mask_account, parse_amount, parse_timestamp, usd_equivalent

NEXT_AGENT = "compliance_checker"

#: Score thresholds. Below MEDIUM is "low".
MEDIUM_THRESHOLD = 30
HIGH_THRESHOLD = 60
MAX_SCORE = 100

#: Reporting threshold — anything at or above this USD-equivalent goes to manual review (MO-3).
REVIEW_AMOUNT_USD = Decimal("10000")
#: Structuring window: deliberately just under the reporting threshold.
STRUCTURING_FLOOR_USD = Decimal("9000")
#: "Unusual timing" window in UTC hours, half-open: 00:00 <= t < 06:00.
UNUSUAL_HOUR_END = 6

#: Illustrative internal watchlist of masked destination accounts — demonstration data, not a feed.
WATCHLIST_ACCOUNTS = frozenset({"****4242"})


@dataclass(frozen=True)
class RuleHit:
    """A single fired rule."""

    code: str
    points: int
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "points": self.points, "reason": self.reason}


@dataclass(frozen=True)
class RuleContext:
    """Everything a rule is allowed to look at."""

    transaction: dict[str, Any]
    amount: Decimal
    currency: str
    usd_amount: Decimal
    hour_utc: int
    country: str | None
    channel: str | None
    destination: str

    @property
    def unusual_hour(self) -> bool:
        return 0 <= self.hour_utc < UNUSUAL_HOUR_END


def _rule_high_value(ctx: RuleContext) -> RuleHit | None:
    if ctx.usd_amount >= REVIEW_AMOUNT_USD:
        return RuleHit("high_value", 40, "at or above the 10,000 USD reporting threshold")
    return None


def _rule_very_high_value(ctx: RuleContext) -> RuleHit | None:
    if ctx.usd_amount >= Decimal("50000"):
        return RuleHit("very_high_value", 20, "at or above 50,000 USD")
    return None


def _rule_structuring(ctx: RuleContext) -> RuleHit | None:
    if STRUCTURING_FLOOR_USD <= ctx.usd_amount < REVIEW_AMOUNT_USD:
        return RuleHit("structuring", 35, "just below the 10,000 USD reporting threshold")
    return None


def _rule_unusual_timing(ctx: RuleContext) -> RuleHit | None:
    if ctx.unusual_hour:
        return RuleHit("unusual_timing", 25, f"submitted at {ctx.hour_utc:02d}:xx UTC")
    return None


def _rule_cross_border(ctx: RuleContext) -> RuleHit | None:
    region = CURRENCY_REGIONS.get(ctx.currency)
    if region is None or ctx.country is None:
        return None
    if ctx.country not in region:
        return RuleHit("cross_border", 20, f"{ctx.country} is outside the {ctx.currency} region")
    return None


def _rule_off_hours_api(ctx: RuleContext) -> RuleHit | None:
    if ctx.channel == "api" and ctx.unusual_hour:
        return RuleHit("off_hours_api", 15, "automated channel used outside business hours")
    return None


def _rule_watchlist_destination(ctx: RuleContext) -> RuleHit | None:
    if ctx.destination in WATCHLIST_ACCOUNTS:
        return RuleHit("watchlist_destination", 30, "destination account is on the watchlist")
    return None


#: The rule table is a module constant so tests can assert on it directly.
RULES: tuple[Callable[[RuleContext], "RuleHit | None"], ...] = (
    _rule_high_value,
    _rule_very_high_value,
    _rule_structuring,
    _rule_unusual_timing,
    _rule_cross_border,
    _rule_off_hours_api,
    _rule_watchlist_destination,
)


def build_context(transaction: dict[str, Any]) -> RuleContext:
    """Extract the rule inputs from a validated transaction."""
    currency = str(transaction["currency"])
    amount = parse_amount(transaction["amount"])
    metadata = transaction.get("metadata") or {}
    destination = str(transaction.get("destination_account", ""))
    if not destination.startswith("****"):
        destination = mask_account(destination)
    return RuleContext(
        transaction=transaction,
        amount=amount,
        currency=currency,
        usd_amount=usd_equivalent(amount, currency),
        hour_utc=parse_timestamp(transaction["timestamp"]).hour,
        country=metadata.get("country"),
        channel=metadata.get("channel"),
        destination=destination,
    )


def score_transaction(transaction: dict[str, Any]) -> dict[str, Any]:
    """Score a validated transaction. Pure: same input, same output, always."""
    ctx = build_context(transaction)
    hits = [hit for hit in (rule(ctx) for rule in RULES) if hit is not None]
    raw_score = sum(hit.points for hit in hits)
    score = min(raw_score, MAX_SCORE)

    if score >= HIGH_THRESHOLD:
        level = "high"
    elif score >= MEDIUM_THRESHOLD:
        level = "medium"
    else:
        level = "low"

    return {
        "agent": FraudDetector.name,
        "risk_score": score,
        "risk_level": level,
        "review_required": level == "high" or ctx.usd_amount >= REVIEW_AMOUNT_USD,
        "usd_equivalent": str(ctx.usd_amount),
        "triggered_rules": [hit.as_dict() for hit in hits],
    }


class FraudDetector(BaseAgent):
    """Scores validated transactions for risk and routes them onward to compliance."""

    name = "fraud_detector"
    inbox = "output"

    def score(self, transaction: dict[str, Any]) -> dict[str, Any]:
        """Instance-level alias of :func:`score_transaction`."""
        return score_transaction(transaction)

    def process_message(self, message: dict[str, Any]) -> dict[str, Any]:
        data = self.next_data(message)
        assessment = score_transaction(data)
        data["fraud"] = assessment
        data["status"] = (
            "flagged_for_review" if assessment["review_required"] else "fraud_cleared"
        )
        return self.forward(message, data, NEXT_AGENT)
