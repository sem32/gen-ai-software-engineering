"""Auto-classification of tickets (category + priority).

Pure, deterministic, keyword-based heuristic classifier. No external
dependencies beyond the stdlib. The combined ``subject + description`` text
is lower-cased once and every keyword/phrase is checked as a substring
match against it (so multi-word phrases like ``"cannot access"`` are matched
as contiguous text, same as single words).

Category selection
------------------
For each category (in the fixed priority order defined in
``_CATEGORY_KEYWORDS``) we count how many *distinct* keywords from that
category's list appear in the text. The category with the most matches
wins; ties are broken by the order in ``_CATEGORY_KEYWORDS`` (first listed
wins) because we only replace the current best on a strictly-greater count.
If no category has any match at all, the result is ``"other"``.

Priority selection
------------------
Priority tiers are checked in strict precedence order: ``urgent`` first,
then ``high``, then ``low``. As soon as a tier has at least one keyword
match, that tier is returned (regardless of match counts in lower tiers).
If nothing matches any tier, priority defaults to ``"medium"``.

Confidence formula
-------------------
- If a real category was found (not ``"other"``):
  ``confidence = min(0.95, 0.5 + 0.15 * (num_category_keywords_matched - 1))``
  i.e. a single keyword match gives the base confidence of 0.5, and each
  additional distinct matched keyword adds 0.15, capped at 0.95.
  If, in addition, a non-default priority (``urgent``/``high``/``low``) was
  also detected, we add a further +0.05 (still capped at 0.95) since two
  independent signals agreeing increases our confidence in the result.
- If no category matched (falling back to ``"other"``):
  confidence is 0.15 if at least a priority keyword matched (some signal
  was found, just not enough to pick a category) or 0.1 if nothing matched
  at all.
"""

# Ordered so that, on tied match counts, the earlier-listed category wins.
_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    (
        "account_access",
        [
            "login",
            "log in",
            "password",
            "2fa",
            "sign in",
            "sign-in",
            "locked out",
            "can't access",
            "cannot access",
            "reset password",
            "authentication",
        ],
    ),
    (
        "technical_issue",
        [
            "error",
            "crash",
            "crashes",
            "not working",
            "broken",
            "freeze",
            "frozen",
            "slow",
            "timeout",
            "exception",
            "fails to load",
        ],
    ),
    (
        "billing_question",
        [
            "payment",
            "invoice",
            "refund",
            "charge",
            "charged",
            "billing",
            "subscription",
            "price",
            "overcharged",
        ],
    ),
    (
        "feature_request",
        [
            "feature request",
            "feature",
            "suggestion",
            "would like",
            "please add",
            "enhancement",
            "it would be nice",
        ],
    ),
    (
        "bug_report",
        [
            "bug",
            "defect",
            "reproduce",
            "steps to reproduce",
            "unexpected behavior",
            "regression",
        ],
    ),
]

# Checked in this exact order: urgent > high > low. First tier with any
# keyword match wins, regardless of how many keywords matched in it.
_PRIORITY_TIERS: list[tuple[str, list[str]]] = [
    (
        "urgent",
        [
            "can't access",
            "cannot access",
            "critical",
            "production down",
            "security",
            "data loss",
            "breach",
        ],
    ),
    (
        "high",
        [
            "important",
            "blocking",
            "asap",
            "urgent",
            "escalate",
        ],
    ),
    (
        "low",
        [
            "minor",
            "cosmetic",
            "suggestion",
            "typo",
            "whenever",
        ],
    ),
]


def _best_category(text: str) -> tuple[str, list[str]]:
    """Return (category, matched_keywords) with the most keyword matches.

    Ties go to the earlier-listed category since we only overwrite the
    current best on a strictly greater match count.
    """
    best_category = "other"
    best_matched: list[str] = []
    best_count = 0
    for category, keywords in _CATEGORY_KEYWORDS:
        matched = [kw for kw in keywords if kw in text]
        if len(matched) > best_count:
            best_count = len(matched)
            best_category = category
            best_matched = matched
    return best_category, best_matched


def _best_priority(text: str) -> tuple[str, list[str]]:
    """Return (priority, matched_keywords) using urgent > high > low
    precedence. Defaults to ("medium", []) when nothing matches."""
    for tier, keywords in _PRIORITY_TIERS:
        matched = [kw for kw in keywords if kw in text]
        if matched:
            return tier, matched
    return "medium", []


def _dedupe(items: list[str]) -> list[str]:
    """Deduplicate while preserving first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def classify(subject: str, description: str) -> dict:
    """Classify a ticket's category and priority from its text content.

    Returns a dict with keys: category, priority, confidence, reasoning,
    keywords. See module docstring for the matching and confidence rules.
    """
    text = f"{subject} {description}".lower()

    category, cat_matched = _best_category(text)
    priority, pri_matched = _best_priority(text)

    keywords = _dedupe(cat_matched + pri_matched)

    if category != "other":
        confidence = min(0.95, 0.5 + 0.15 * (len(cat_matched) - 1))
        if priority != "medium":
            confidence = min(0.95, confidence + 0.05)
    else:
        confidence = 0.15 if pri_matched else 0.1

    if cat_matched:
        cat_part = f"category '{category}' on keywords: {', '.join(cat_matched)}"
    else:
        cat_part = f"category '{category}' (no keyword matches, defaulted)"

    if pri_matched:
        pri_part = f"priority '{priority}' on: {', '.join(pri_matched)}"
    else:
        pri_part = f"priority '{priority}' (no keyword matches, defaulted)"

    reasoning = f"Matched {cat_part}; {pri_part}."

    return {
        "category": category,
        "priority": priority,
        "confidence": confidence,
        "reasoning": reasoning,
        "keywords": keywords,
    }
