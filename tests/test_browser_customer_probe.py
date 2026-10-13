"""Synthetic transport fixtures: not live storefront or recovery evidence."""

from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

from autotriager_shop.browser_customer_probe import BrowserCustomerProbe, _trace
from autotriager_shop.customer_probe import ProbeError


PATH = "/images/products/SolarSystemColorImager.jpg"
TRACE = "a" * 32


def image_fixture():
    return {"product_id": "0PUK6V6EV0", "image_path": PATH,
            "flag_evaluation_observed": True, "image_displayed": True,
            "requests": [{"method": "GET", "path": PATH, "http_status": 200,
                "elapsed_ms": 120.5, "content_type": "image/jpeg",
                "image_bytes": 98549, "image_displayed": True, "trace_id": TRACE,
                "traceparent_source": "native_browser", "trace_context_generated": False,
                "request_id": "test-id", "request_id_echoed": False}]}


def observe(result):
    calls = []
    def adapter(**kwargs):
        calls.append(kwargs)
        return deepcopy(result)
    receipt = BrowserCustomerProbe(adapter=adapter,
        clock=lambda: datetime(2026, 10, 2, 8, tzinfo=timezone.utc)).probe_product_images("test-scope")
    assert len(calls) == 1
    return receipt


def test_selected_blob_and_timing_produce_scoped_receipt_not_live_fixture():
    receipt = observe(image_fixture())
    assert receipt["business_success"] and receipt["browser_image_displayed"]
    assert receipt["source_kind"] == "test_transport"
    assert receipt["image_threshold_ms"] == 1500 and receipt["elapsed_ms"] == 120.5
    assert receipt["trace_id"] == TRACE and receipt["trace_ids"] == [TRACE]
    assert receipt["trace_context_observed"] is False
    assert receipt["created_order"] is False
    assert receipt["scope_id"] == "test-scope" and receipt["time"]["started_at"] == receipt["started_at"]


@pytest.mark.parametrize("elapsed,status,success", [(1500, "success", True), (1500.1, "degraded", False), (5000, "degraded", False)])
def test_preregistered_threshold_boundary(elapsed, status, success):
    result = image_fixture()
    result["requests"][-1]["elapsed_ms"] = elapsed
    receipt = observe(result)
    assert receipt["status"] == status and receipt["business_success"] is success


@pytest.mark.parametrize("change", [
    {"http_status": 500}, {"content_type": "application/json"}, {"content_type": "text/html"},
    {"image_bytes": 0}, {"image_displayed": False}, {"http_status": True},
])
def test_http200_alone_or_error_body_cannot_pass(change):
    result = image_fixture()
    result["requests"][-1].update(change)
    receipt = observe(result)
    assert not receipt["business_success"] and receipt["status"] == "failed"


@pytest.mark.parametrize("elapsed", [None, float("nan"), float("inf"), -1, True, "100"])
def test_missing_or_invalid_timing_is_unavailable_not_success(elapsed):
    result = image_fixture()
    result["requests"][-1]["elapsed_ms"] = elapsed
    receipt = observe(result)
    assert not receipt["business_success"] and receipt["status"] == "unavailable"
    assert "elapsed_ms" not in receipt["requests"][-1]


def test_final_evaluated_request_used_not_fast_initial_response():
    result = image_fixture()
    result["requests"].append({**result["requests"][0], "elapsed_ms": 5020, "trace_id": "b" * 32})
    receipt = observe(result)
    assert receipt["status"] == "degraded" and receipt["trace_id"] == "b" * 32
    assert receipt["elapsed_ms"] == 5020


def test_blob_not_displayed_cannot_pass_even_image_response_valid():
    result = image_fixture()
    result["image_displayed"] = False
    assert observe(result)["business_success"] is False


@pytest.mark.parametrize("field,value", [("product_id", "another-SKU"), ("image_path", "/images/products/../../secret.jpg"), ("image_path", "http://evil/image.jpg")])
def test_metadata_mismatch_cannot_bind_receipt(field, value):
    result = image_fixture()
    result[field] = value
    receipt = observe(result)
    assert receipt["status"] == "unavailable" and not receipt["business_success"]


def test_request_path_mismatch_fails_closed():
    result = image_fixture()
    result["requests"][0]["path"] = "/images/products/Other.jpg"
    receipt = observe(result)
    assert receipt["status"] == "unavailable" and receipt["error_kind"] == "ProbeError"


def test_unobserved_flag_evaluation_is_not_browser_equivalence_success():
    result = image_fixture()
    result["flag_evaluation_observed"] = False
    assert observe(result)["reason"] == "browser_flag_evaluation_not_observed"


def test_unlinked_trace_preserves_customer_success_but_does_not_claim_correlation():
    result = image_fixture()
    result["requests"][0].pop("trace_id")
    result["requests"][0].pop("traceparent_source")
    receipt = observe(result)
    assert receipt["business_success"] and receipt["trace_id"] is None
    assert receipt["trace_ids"] == [] and receipt["traceparent_source"] == "unlinked"
    assert receipt["trace_context_observed"] is False


def test_private_headers_and_customer_information_never_retained():
    result = image_fixture()
    result["requests"][0].update({"headers": {"x-envoy-fault-delay-request": "5000"},
        "raw_body": "private-card", "email": "secret@invalid", "flag_name": "imageSlowLoad"})
    result["secret"] = "private-value"
    encoded = json.dumps(observe(result))
    for private in ("x-envoy", "5000", "private-card", "secret@invalid", "imageSlowLoad", "private-value"):
        assert private not in encoded


def test_adapter_error_message_is_sanitized():
    def adapter(**kwargs):
        raise RuntimeError("secret header=5000 token=do-not-retain")
    receipt = BrowserCustomerProbe(adapter=adapter).probe_product_images("test-scope")
    assert receipt["error_kind"] == "RuntimeError"
    assert "do-not-retain" not in json.dumps(receipt)


@pytest.mark.parametrize("kwargs", [{"shop_origin": "https://example.com"}, {"shop_origin": "http://127.0.0.1:8080/"}, {"threshold_ms": 5000}, {"threshold_ms": True}, {"browser_timeout_ms": 60000}])
def test_invalid_origin_or_policy_rejected(kwargs):
    with pytest.raises(ProbeError):
        BrowserCustomerProbe(**kwargs)


def test_traceparent_rejects_zero_ids_and_retains_exact_native_identity():
    assert _trace(f"00-{TRACE}-{'b'*16}-01") == TRACE
    assert _trace(f"00-{'0'*32}-{'b'*16}-01") is None
    assert _trace(f"00-{TRACE}-{'0'*16}-01") is None


def test_history_is_bounded_to_three_selected_requests():
    result = image_fixture()
    result["requests"] *= 10
    assert len(observe(result)["requests"]) == 3


def checkout_fixture():
    return {"product_id": "0PUK6V6EV0", "order_confirmation_displayed": True,
        "requests": [{"method": "POST", "path": "/api/checkout", "http_status": 200,
            "matching_order_response": True,
            "trace_id": TRACE, "traceparent_source": "native_browser", "elapsed_ms": 80,
            "response": {"orderId": "order-123", "shippingTrackingId": "tracking-456",
                         "items": [{"product_id": "0PUK6V6EV0", "quantity": 1}]}}]}


def observe_checkout(result):
    calls = []
    def adapter(**kwargs):
        calls.append(kwargs)
        return deepcopy(result)
    receipt = BrowserCustomerProbe(checkout_adapter=adapter).probe_checkout("scope-test", "0PUK6V6EV0")
    assert len(calls) == 1 and calls[0]["synthetic_user_id"].startswith("autotriager-probe-")
    return receipt


def test_native_checkout_requires_matching_response_and_rendered_confirmation():
    receipt = observe_checkout(checkout_fixture())
    assert receipt["business_success"] and receipt["created_order"]
    assert receipt["order_confirmation_displayed"] and receipt["browser_equivalent"]
    assert receipt["source_kind"] == "test_transport" and receipt["trace_id"] == TRACE
    assert receipt["trace_context_observed"] is False and receipt["synthetic_purchase"]


def test_order_created_but_not_visible_is_not_customer_success():
    result = checkout_fixture()
    result["order_confirmation_displayed"] = False
    receipt = observe_checkout(result)
    assert receipt["created_order"] and not receipt["business_success"]
    assert receipt["status"] == "failed"


def test_raw_order_contract_not_accepted_after_lossy_sanitizing():
    result = checkout_fixture()
    result["requests"][-1]["matching_order_response"] = False
    receipt = observe_checkout(result)
    assert not receipt["created_order"] and not receipt["business_success"]


@pytest.mark.parametrize("body", [
    {}, {"error_present": True}, {"orderId": "order-123"},
    {"orderId": "order-123", "shippingTrackingId": "tracking-456", "items": []},
    {"orderId": "order-123", "shippingTrackingId": "tracking-456", "items": [{"product_id": "other", "quantity": 1}]},
    {"orderId": "order-123", "shippingTrackingId": "tracking-456", "items": [{"product_id": "0PUK6V6EV0", "quantity": 2}]},
])
def test_http200_checkout_invalid_body_cannot_create_order(body):
    result = checkout_fixture()
    result["requests"][-1]["response"] = body
    receipt = observe_checkout(result)
    assert not receipt["created_order"] and not receipt["business_success"]


def test_payment_failed422_preserves_sanitized_business_error():
    result = checkout_fixture()
    result["requests"][-1].update(http_status=422, response={"error_present": True, "error_code": "PAYMENT_FAILED", "error": "card-secret"})
    result["order_confirmation_displayed"] = False
    receipt = observe_checkout(result)
    assert not receipt["created_order"] and receipt["status"] == "failed"
    assert receipt["requests"][-1]["response"]["error_code"] == "PAYMENT_FAILED"
    assert "card-secret" not in json.dumps(receipt)


def test_checkout_final_receipt_not_changed_by_later_cart_get():
    result = checkout_fixture()
    result["requests"].append({"method": "GET", "path": "/api/cart", "http_status": 200, "response": {"items": []}})
    receipt = observe_checkout(result)
    assert receipt["business_success"] and receipt["requests"][-1]["path"] == "/api/checkout"


def test_checkout_product_or_method_mismatch_rejected():
    result = checkout_fixture()
    result["product_id"] = "other"
    assert not observe_checkout(result)["business_success"]
    result = checkout_fixture()
    result["requests"][-1]["method"] = "GET"
    assert not observe_checkout(result)["business_success"]


def test_checkout_sanitizes_nested_items_and_never_records_customer_id():
    result = checkout_fixture()
    result["requests"][-1]["response"]["items"][0]["email"] = "customer-secret"
    result["requests"][-1]["response"].update(email="customer-secret", address="address-secret", creditCardNumber="card-secret")
    receipt = observe_checkout(result)
    encoded = json.dumps(receipt)
    for secret in ("customer-secret", "address-secret", "card-secret", "autotriager-probe-"):
        assert secret not in encoded


@pytest.mark.parametrize("user", ["real-customer", "autotriager-probe-nothex", "", 123])
def test_native_checkout_cannot_use_arbitrary_customer(user):
    with pytest.raises(ProbeError):
        BrowserCustomerProbe(checkout_adapter=lambda **kw: {}).probe_checkout("test", "0PUK6V6EV0", user)
