"""Enumerated value sets shared across the ticket API.

These frozensets are the single source of truth for the allowed values of
categorical ticket fields. Validators in ``models.py`` reference them so the
accepted values stay consistent everywhere.
"""

CATEGORIES = frozenset(
    {
        "account_access",
        "technical_issue",
        "billing_question",
        "feature_request",
        "bug_report",
        "other",
    }
)

PRIORITIES = frozenset({"urgent", "high", "medium", "low"})

STATUSES = frozenset(
    {"new", "in_progress", "waiting_customer", "resolved", "closed"}
)

SOURCES = frozenset({"web_form", "email", "api", "chat", "phone"})

DEVICE_TYPES = frozenset({"desktop", "mobile", "tablet"})
