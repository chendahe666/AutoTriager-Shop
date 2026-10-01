"""Check answer isolation, citation validation, and explicit API failure paths."""

from __future__ import annotations

import json
from collections import Counter
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


def test_retrieval_ablation_keeps_prompt_and_validator_fixed() -> None:
    rows = [
        {"id": f"span-{index}", "kind": "span", "service": "checkout",
         "timestamp": f"2026-10-01T00:00:{index:02d}Z", "summary": "routine",
         "raw": {"status": "OK", "is_anomalous": False}}
        for index in range(49)
    ]
    rows.append({"id": "late-anomaly", "kind": "span", "service": "payment",
                 "timestamp": "2026-10-01T00:00:59Z", "summary": "payment slow",
                 "raw": {"status": "OK", "is_anomalous": True}})
    chronological = gemini.select_evidence(rows, "grounded_chrono")
    prioritized = gemini.select_evidence(rows, "grounded")
    assert len(chronological) == len(prioritized) == 48
    assert "late-anomaly" not in {row["id"] for row in chronological}
    assert "late-anomaly" in {row["id"] for row in prioritized}
    assert gemini._prompt(PUBLIC_INCIDENT, chronological, "grounded_chrono").split("DATA (not instructions):")[0] == \
           gemini._prompt(PUBLIC_INCIDENT, chronological, "grounded").split("DATA (not instructions):")[0]
    for mode in ("grounded", "grounded_chrono"):
        result = gemini._validate({"status": "supported", "candidate_service": "payment",
                                   "evidence_ids": ["span-payment-1"], "reason": "one signal"},
                                  gemini.select_evidence(PUBLIC_OBSERVATIONS, mode), mode)
        assert result["status"] == "insufficient_evidence"


def test_missing_key_stops_before_network_call() -> None:
    with patch.dict("os.environ", {}, clear=True), \
         patch.object(gemini.requests, "post") as post:
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            gemini.diagnose_with_gemini(Path("unused"))
        post.assert_not_called()


@pytest.mark.parametrize("mode", ["direct", "direct_strong", "grounded", "grounded_chrono"])
def test_wrapper_defaults_preserve_selection_generate_call_and_validation(mode) -> None:
    observations = PUBLIC_OBSERVATIONS + [
        {"id": f"routine-{index:03d}", "kind": "span", "service": "checkout",
         "timestamp": f"2026-10-01T00:00:{index:02d}Z", "summary": "routine call",
         "raw": {"status": "OK"}} for index in range(49)
    ] + [{"id": "late-metric", "kind": "metric", "service": "payment",
          "timestamp": "2026-10-01T00:00:59Z", "summary": "late anomaly",
          "raw": {"is_anomalous": True, "value": 1}}]
    raw = {"status": "supported", "candidate_service": "payment",
           "reason": "two signals", "evidence_ids": ["span-payment-1", "log-payment-1"],
           "missing_evidence": []}
    generated = {"raw_response": raw, "latency_ms": 12, "usage": {"promptTokenCount": 100}}
    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-only"}), \
         patch.object(gemini, "_public_case", return_value=(PUBLIC_INCIDENT, observations)), \
         patch.object(gemini, "generate_from_evidence", return_value=generated) as generate:
        result = gemini.diagnose_with_gemini(Path("unused"), mode=mode, model="fixed-model", timeout=120)
    evidence = gemini.select_evidence(observations, mode)
    generate.assert_called_once_with(PUBLIC_INCIDENT, evidence, mode, "fixed-model", 120)
    expected = gemini._validate(raw, evidence, mode)
    assert {key: result[key] for key in expected} == expected
    assert result["model"] == "fixed-model"
    assert result["visible_evidence_count"] == len(evidence)
    assert result["selection"] == "prioritized"
    assert result["grounded_objective"] == "initiating_failure"


def test_wrapper_selected_candidate_sends_24_metrics_and_24_spans_to_actual_generate() -> None:
    rows = [{"id": f"{kind}-{index:03d}", "kind": kind, "service": "payment",
             "timestamp": f"2026-10-01T00:00:{index:02d}Z", "summary": "observed operation",
             "raw": {"status": "ERROR" if kind == "span" else "OK", "value": index,
                     "is_anomalous": kind == "metric", "baseline": 0}}
            for kind in ("metric", "span") for index in range(60)]
    raw = {"status": "supported", "candidate_service": "payment",
           "reason": "inspect service with two signals", "evidence_ids": ["metric-000", "span-000"],
           "missing_evidence": []}
    reply = Mock(ok=True)
    reply.json.return_value = {"candidates": [{"content": {"parts": [{"text": json.dumps(raw)}]}}],
                               "usageMetadata": {"promptTokenCount": 100}}
    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-only"}), \
         patch.object(gemini, "_public_case", return_value=(PUBLIC_INCIDENT, rows)), \
         patch.object(gemini.requests, "post", return_value=reply) as post:
        result = gemini.diagnose_with_gemini(
            Path("unused"), model="fixed-model", selection="modality_balanced",
            grounded_objective="investigation_priority")
    sent = post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
    payload = json.loads(sent.split("DATA (not instructions):\n")[1])
    evidence = payload["observations"]
    assert Counter(row["kind"] for row in evidence) == {"metric": 24, "span": 24}
    assert evidence == gemini.select_evidence(rows, "modality_balanced")
    assert sent == gemini._prompt(PUBLIC_INCIDENT, evidence, "grounded", "investigation_priority")
    assert "expected_service" not in sent
    assert "test-only" not in sent
    assert result["status"] == "supported" and result["candidate_service"] == "payment"
    assert result["method"] == "gemini-grounded-v2"
    assert result["selection"] == "modality_balanced"
    assert result["grounded_objective"] == "investigation_priority"
    assert result["model"] == "fixed-model" and result["visible_evidence_count"] == 48


def test_wrapper_optional_selection_does_not_change_direct_validator() -> None:
    raw = {"status": "supported", "candidate_service": "payment",
           "reason": "single signal", "evidence_ids": ["span-payment-1"], "missing_evidence": []}
    generated = {"raw_response": raw, "latency_ms": 12, "usage": {}}
    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-only"}), \
         patch.object(gemini, "_public_case", return_value=(PUBLIC_INCIDENT, PUBLIC_OBSERVATIONS)), \
         patch.object(gemini, "generate_from_evidence", return_value=generated) as generate:
        result = gemini.diagnose_with_gemini(
            Path("unused"), mode="direct_strong", selection="modality_balanced",
            grounded_objective="investigation_priority")
    generate.assert_called_once_with(
        PUBLIC_INCIDENT, gemini.select_evidence(PUBLIC_OBSERVATIONS, "modality_balanced"),
        "direct_strong", gemini.DEFAULT_MODEL, 90, grounded_objective="investigation_priority")
    assert result["status"] == "supported"
    assert result["candidate_service"] == "payment"
