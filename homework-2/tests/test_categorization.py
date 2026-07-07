"""Auto-classification tests for the classify() heuristic and endpoint."""

import pytest

from src.classification import classify


@pytest.mark.parametrize(
    "subject,description,expected",
    [
        ("Cannot login", "I reset my password but cannot login, authentication fails", "account_access"),
        ("App error", "The app crashes with an exception and is very slow, timeout error", "technical_issue"),
        ("Invoice", "I was charged twice, need a refund for this payment invoice billing", "billing_question"),
        ("Suggestion", "I would like a new feature, please add this enhancement", "feature_request"),
        ("Bug", "There is a bug, a defect, steps to reproduce this regression", "bug_report"),
    ],
)
def test_category_matched_by_representative_text(subject, description, expected):
    assert classify(subject, description)["category"] == expected


def test_priority_urgent_tier():
    result = classify("Down", "critical production down security breach data loss")
    assert result["priority"] == "urgent"


def test_priority_high_tier():
    result = classify("Fix", "This is important and blocking, please respond")
    assert result["priority"] == "high"


def test_priority_low_tier():
    result = classify("Small", "This is a minor cosmetic typo issue")
    assert result["priority"] == "low"


def test_priority_medium_default():
    result = classify("Question", "I have a general question about the dashboard layout options")
    assert result["priority"] == "medium"


def test_confidence_within_zero_one():
    for subject, description in [
        ("Cannot login", "password reset authentication login problem"),
        ("Nothing", "just a plain message with no keywords whatsoever here"),
    ]:
        confidence = classify(subject, description)["confidence"]
        assert 0.0 <= confidence <= 1.0


def test_keywords_populated_on_match():
    result = classify("Payment", "refund my invoice and payment charge please")
    assert result["keywords"]
    assert "refund" in result["keywords"]


def test_reasoning_non_empty():
    result = classify("Anything", "some description text that is long enough")
    assert isinstance(result["reasoning"], str)
    assert result["reasoning"].strip()


def test_fallback_to_other_and_medium():
    result = classify("Hello", "Just saying hello to everyone today about general matters")
    assert result["category"] == "other"
    assert result["priority"] == "medium"
    assert result["keywords"] == []


def test_auto_classify_endpoint_updates_stored_ticket(client, valid_ticket):
    created = client.post(
        "/tickets",
        json=valid_ticket(
            subject="Cannot login to account",
            description="My password stopped working and I cannot login, authentication error",
            category="other",
            priority="medium",
        ),
    ).json()
    assert created["category"] == "other"

    resp = client.post(f"/tickets/{created['id']}/auto-classify")
    assert resp.status_code == 200
    result = resp.json()
    assert result["category"] == "account_access"

    # The stored ticket reflects the new classification.
    stored = client.get(f"/tickets/{created['id']}").json()
    assert stored["category"] == "account_access"
    assert stored["classification"]["confidence"] == result["confidence"]


def test_auto_classify_endpoint_missing_ticket_returns_404(client):
    resp = client.post("/tickets/missing/auto-classify")
    assert resp.status_code == 404
