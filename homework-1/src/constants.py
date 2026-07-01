"""Domain constants shared across the API."""

# A pragmatic subset of ISO 4217 currency codes accepted by the API.
# Kept explicit (rather than pulling a heavy dependency) so validation is
# deterministic and easy to reason about in tests.
VALID_CURRENCIES: frozenset[str] = frozenset(
    {
        "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD",
        "CNY", "HKD", "SGD", "SEK", "NOK", "DKK", "PLN", "CZK",
        "HUF", "RON", "BGN", "TRY", "INR", "BRL", "MXN", "ZAR",
        "AED", "SAR", "ILS", "KRW", "THB", "MYR", "IDR", "PHP",
    }
)

# Allowed transaction types.
TRANSACTION_TYPES: frozenset[str] = frozenset({"deposit", "withdrawal", "transfer"})

# Allowed transaction statuses.
TRANSACTION_STATUSES: frozenset[str] = frozenset({"pending", "completed", "failed"})

# Account identifiers follow the format ACC-XXXXX where X is alphanumeric
# (at least one character after the dash).
ACCOUNT_PATTERN = r"^ACC-[A-Za-z0-9]+$"
