"""Unit tests for the settlement processor (spec task T-4, edge cases EC-11/EC-13/EC-14)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from agents.protocol import TERMINAL_TARGET, parse_amount
from agents.settlement_processor import (
    DEFAULT_LAG_DAYS,
    FEE_CAP,
    FEE_FLOOR,
    SettlementProcessor,
    calculate_fee,
    next_business_day,
    settle_transaction,
)

# --------------------------------------------------------------------------------------
# Fees
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "amount,expected_fee",
    [
        ("1500.00", "3.75"),
        ("3200.00", "8.00"),
        ("500.00", "1.25"),
        ("9999.99", "25.00"),  # 24.999975 rounds half-up to the cap
    ],
)
def test_calculate_fee_applies_the_rate(amount, expected_fee):
    assert calculate_fee(Decimal(amount), "USD") == Decimal(expected_fee)


def test_ec_13_fee_floor_is_applied():
    assert calculate_fee(Decimal("100.00"), "USD") == FEE_FLOOR


def test_ec_14_fee_cap_is_applied():
    assert calculate_fee(Decimal("75000.00"), "USD") == FEE_CAP


def test_fee_is_quantised_to_the_currency_minor_unit():
    fee = calculate_fee(Decimal("1500"), "JPY")
    assert fee == Decimal("4")
    assert -fee.as_tuple().exponent == 0


# --------------------------------------------------------------------------------------
# Business days
# --------------------------------------------------------------------------------------


def test_next_business_day_skips_the_weekend():
    friday = date(2026, 3, 20)
    assert friday.weekday() == 4
    assert next_business_day(friday, 1) == date(2026, 3, 23)  # Monday


def test_ec_11_friday_wire_settles_on_tuesday():
    assert next_business_day(date(2026, 3, 20), 2) == date(2026, 3, 24)


def test_next_business_day_with_zero_days_is_a_no_op():
    assert next_business_day(date(2026, 3, 21), 0) == date(2026, 3, 21)


def test_next_business_day_rejects_negative_days():
    with pytest.raises(ValueError):
        next_business_day(date(2026, 3, 16), -1)


# --------------------------------------------------------------------------------------
# Settlement figures
# --------------------------------------------------------------------------------------


def test_settle_transaction_produces_the_expected_figures(make_transaction):
    settlement = settle_transaction(make_transaction())
    assert settlement["settlement_id"] == "STL-TXN900"
    assert settlement["gross_amount"] == "1500.00"
    assert settlement["fee"] == "3.75"
    assert settlement["net_amount"] == "1496.25"
    assert settlement["value_date"] == "2026-03-17"  # Monday + 1 business day
    assert settlement["business_day_lag"] == 1


def test_wire_transfers_settle_two_business_days_out(make_transaction):
    settlement = settle_transaction(make_transaction(transaction_type="wire_transfer"))
    assert settlement["business_day_lag"] == 2
    assert settlement["value_date"] == "2026-03-18"


def test_unknown_transaction_type_uses_the_default_lag(make_transaction):
    transaction = make_transaction()
    transaction["transaction_type"] = "exotic"
    assert settle_transaction(transaction)["business_day_lag"] == DEFAULT_LAG_DAYS


def test_ledger_invariant_holds(make_transaction):
    for amount in ("100.00", "1500.00", "9999.99", "75000.00"):
        settlement = settle_transaction(make_transaction(amount=amount))
        assert parse_amount(settlement["fee"]) + parse_amount(settlement["net_amount"]) == Decimal(
            amount
        )


def test_settlement_id_falls_back_when_the_id_is_absent(make_transaction):
    transaction = make_transaction()
    del transaction["transaction_id"]
    assert settle_transaction(transaction)["settlement_id"] == "STL-UNKNOWN"


# --------------------------------------------------------------------------------------
# Message handling
# --------------------------------------------------------------------------------------


def test_process_message_produces_a_terminal_settled_result(workspace, make_message):
    outgoing = SettlementProcessor(workspace).process_message(
        make_message(target_agent="settlement_processor")
    )
    assert outgoing["target_agent"] == TERMINAL_TARGET
    assert outgoing["data"]["status"] == "settled"
    assert outgoing["data"]["settlement"]["settled_at"].endswith("Z")


def test_instance_alias_matches_module_function(workspace, make_transaction):
    transaction = make_transaction()
    assert SettlementProcessor(workspace).settle(transaction) == settle_transaction(transaction)
