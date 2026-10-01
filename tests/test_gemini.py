"""Check answer isolation, citation validation, and explicit API failure paths."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from autotriager_shop import gemini


PUBLIC_INCIDENT = {
    "case_id": "public-1",
    "title": "Checkout failures",
    "symptom": "Checkout returned errors",
    "start_time": "2026-10-01T00:00:00Z",
    "end_time": "2026-10-01T00:01:00Z",
}
PUBLIC_OBSERVATIONS = [
    {"id": "span-payment-1", "kind": "span", "service": "payment",
     "timestamp": "2026-10-01T00:00:10Z", "summary": "charge failed",
     "raw": {"status": "ERROR", "status_code": 503}},
    {"id": "log-payment-1", "kind": "log", "service": "payment",
     "timestamp": "2026-10-01T00:00:11Z", "summary": "charge failed",
     "raw": {"severity_text": "ERROR"}},
]


def test_grounded_result_is_limited_to_public_evidence() -> None:
    reply = Mock()
    reply.ok = True
    reply.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": (
            '{"status":"supported","candidate_service":"payment",'
            '"reason":"two signals","evidence_ids":'
            '["span-payment-1","log-payment-1","private-answer"],'
            '"missing_evidence":[]}'
        )}]}}],
        "usageMetadata": {},
    }
    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-only"}), \
         patch.object(gemini, "_public_case", return_value=(PUBLIC_INCIDENT, PUBLIC_OBSERVATIONS)), \
         patch.object(gemini.requests, "post", return_value=reply) as post:
        result = gemini.diagnose_with_gemini(Path("unused"))
    prompt = post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
    assert "private-answer" not in prompt
    assert "expected_service" not in prompt
    assert result["status"] == "insufficient_evidence"
    assert result["candidate_service"] is None
    assert result["evidence_ids"] == ["span-payment-1", "log-payment-1"]
    assert result["invalid_citations"] == ["private-answer"]
    assert post.call_args.kwargs["headers"]["x-goog-api-key"] == "test-only"


def test_one_signal_cannot_support_grounded_attribution() -> None:
    visible = gemini.select_evidence(PUBLIC_OBSERVATIONS[:1], "grounded")
    result = gemini._validate({
        "status": "supported", "candidate_service": "payment",
        "evidence_ids": ["span-payment-1"], "reason": "single span",
    }, visible, "grounded")
    assert result["status"] == "insufficient_evidence"
    assert result["candidate_service"] is None


def test_two_signals_on_different_services_do_not_support_candidate() -> None:
    cross_service = [PUBLIC_OBSERVATIONS[0], {
        **PUBLIC_OBSERVATIONS[1], "id": "log-checkout-1", "service": "checkout",
    }]
    visible = gemini.select_evidence(cross_service, "grounded")
    result = gemini._validate({
        "status": "supported", "candidate_service": "payment",
        "evidence_ids": ["span-payment-1", "log-checkout-1"],
        "reason": "mixed services",
    }, visible, "grounded")
    assert result["status"] == "insufficient_evidence"
    assert result["candidate_service"] is None


def test_malformed_candidate_type_abstains_safely() -> None:
    visible = gemini.select_evidence(PUBLIC_OBSERVATIONS, "grounded")
    result = gemini._validate({
        "status": "supported", "candidate_service": [],
        "evidence_ids": ["span-payment-1", "log-payment-1"],
    }, visible, "grounded")
    assert result["status"] == "insufficient_evidence"
    assert result["candidate_service"] is None


def test_missing_key_stops_before_network_call() -> None:
    with patch.dict("os.environ", {}, clear=True), \
         patch.object(gemini.requests, "post") as post:
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            gemini.diagnose_with_gemini(Path("unused"))
        post.assert_not_called()
