"""Customer API fixtures test probe validation, not live platform recovery."""

from copy import deepcopy
from datetime import datetime, timezone
import json
import re
import urllib.error

import pytest

from autotriager_shop.customer_probe import (
    CustomerProbe, HTTPResponse, ProbeError, validate_recovery_receipt,
)


PRODUCT = "0PUK6V6EV0"
USER = "autotriager-probe-" + "a" * 32
NOW = datetime(2026, 10, 2, 8, 0, 10, tzinfo=timezone.utc)


def _response(body, status=200, content_type="application/json"):
    return HTTPResponse(status, json.dumps(body).encode(), content_type, 12.5)


def _order():
    return {"orderId": "order-123", "shippingTrackingId": "track-456",
            "shippingAddress": {"streetAddress": "secret-address"},
            "email": "secret@example.org", "creditCardNumber": "secret-card",
            "items": [{"item": {"productId": PRODUCT, "quantity": 1},
                       "cost": {"currencyCode": "USD", "units": 25, "nanos": 0}}]}


class FixtureTransport:
    def __init__(self, checkout=None, *, populated=False, cart_product=PRODUCT):
        self.calls = []
        self.checkout = checkout if checkout is not None else _response(_order())
        self.populated = populated
        self.cart_product = cart_product

    def __call__(self, method, url, *, json_body, headers, timeout):
        self.calls.append({"method": method, "url": url, "body": json_body,
                           "headers": headers, "timeout": timeout})
        if "/api/cart" in url:
            if method == "POST":
                self.populated = True
            return _response({"userId": USER, "items": (
                [{"productId": self.cart_product, "quantity": 1}] if self.populated else [])})
        if "/api/checkout" in url:
            return self.checkout
        raise AssertionError(f"Unexpected probe request: {method} {url}")


def _probe(transport):
    return CustomerProbe(transport=transport, clock=lambda: NOW)


def _successful_receipt():
    receipt = _probe(FixtureTransport()).probe_checkout("incident-1", PRODUCT, synthetic_user_id=USER)
    # Unit fixtures remain test_transport. This deliberate replacement tests
    # the live-receipt validator's content contract, not actual runtime success.
    receipt["source_kind"] = "captured_shop"
    return receipt


def _validate(receipt, **overrides):
    kwargs = {"scope_id": "incident-1", "journey": "checkout", "product_id": PRODUCT,
              "not_before": "2026-10-02T08:00:00+00:00", "now": "2026-10-02T08:00:15+00:00"}
    kwargs.update(overrides)
    return validate_recovery_receipt(receipt, **kwargs)


def test_checkout_success_requires_actual_order_and_preserves_matching_path():
    transport = FixtureTransport()
    receipt = _probe(transport).probe_checkout("incident-1", PRODUCT, synthetic_user_id=USER)
    assert receipt["business_success"] and receipt["created_order"]
    assert receipt["reason"] == "confirmed_order_for_requested_item"
    assert receipt["source_kind"] == "test_transport"
    assert [call["method"] for call in transport.calls] == ["GET", "POST", "GET", "POST"]
    assert transport.calls[-1]["url"] == "http://127.0.0.1:8080/api/checkout?currencyCode=USD"
    assert all(re.fullmatch(r"00-" + receipt["trace_id"] + r"-[0-9a-f]{16}-01", call["headers"]["traceparent"])
               for call in transport.calls)
    assert receipt["trace_context_observed"] is False
    assert receipt["requests"][-1]["response"]["items"] == [{"product_id": PRODUCT, "quantity": 1}]
    assert _validate(receipt)["reason"] == "not_live_customer_observation"
    assert _validate(_successful_receipt())["accepted"]


@pytest.mark.parametrize("response", [
    _response({"error": "Failed to place order."}, 500),
    _response({"error": "secret-card", "code": "PAYMENT_FAILED"}, 422),
    _response({"error": "secret-address", **_order()}, 200),
    _response({}, 200),
    HTTPResponse(200, b"not-json", "text/plain"),
    _response({**_order(), "orderId": ""}, 200),
    _response({**_order(), "shippingTrackingId": ""}, 200),
    _response({**_order(), "items": []}, 200),
    _response({**_order(), "items": [{"item": {"productId": "other", "quantity": 1}}]}, 200),
    _response({**_order(), "items": [{"item": {"productId": PRODUCT, "quantity": 0}}]}, 200),
    _response({**_order(), "items": _order()["items"] + [None]}, 200),
])
def test_http_and_body_failures_cannot_confirm_order(response):
    receipt = _probe(FixtureTransport(response)).probe_checkout("incident-1", PRODUCT, synthetic_user_id=USER)
    assert receipt["business_success"] is False
    assert receipt["created_order"] is False
    assert receipt["status"] == "failed"
    assert not _validate(receipt)["accepted"]


def test_public_receipt_redacts_customer_card_address_and_server_error_strings():
    transport = FixtureTransport(_response({"error": "secret@example.org secret-address secret-card", "code": "PAYMENT_FAILED"}, 422))
    receipt = _probe(transport).probe_checkout("incident-1", PRODUCT, synthetic_user_id=USER)
    rendered = json.dumps(receipt)
    for sensitive in (USER, "someone@example.com", "4432-8015-6152-0454", "1600 Amphitheatre", "secret-card", "secret-address", "secret@example.org"):
        assert sensitive not in rendered
    assert receipt["requests"][-1]["response"] == {"json_body": True, "error_present": True, "error_code": "PAYMENT_FAILED"}
    assert len(receipt["requests"][-1]["response_body_sha256"]) == 64
    good = json.dumps(_successful_receipt())
    assert "secret-address" not in good and "secret-card" not in good


def test_failed_checkout_cart_retry_does_not_add_duplicate_item():
    transport = FixtureTransport(populated=True)
    receipt = _probe(transport).probe_checkout("incident-1", PRODUCT, synthetic_user_id=USER)
    assert receipt["created_order"]
    assert [call["method"] for call in transport.calls] == ["GET", "POST"]
    assert "/api/checkout" in transport.calls[-1]["url"]


def test_mismatching_existing_cart_refuses_checkout():
    transport = FixtureTransport(populated=True, cart_product="other")
    receipt = _probe(transport).probe_checkout("incident-1", PRODUCT, synthetic_user_id=USER)
    assert not receipt["business_success"]
    assert receipt["reason"] == "synthetic_cart_does_not_match_journey"
    assert len(transport.calls) == 1


@pytest.mark.parametrize("origin", [
    "https://example.com", "http://127.0.0.1:9090", "http://127.0.0.1:8080/",
    "http://127.0.0.1:8080@evil.example", "http://localhost.evil:8080", "http://user:password@127.0.0.1:8080",
])
def test_nonlocal_or_modified_origins_refused(origin):
    with pytest.raises(ProbeError):
        CustomerProbe(origin)


def test_real_customer_session_and_path_injection_refused_before_requests():
    transport = FixtureTransport()
    probe = _probe(transport)
    for invalid in ("real-customer", USER + "/", ""):
        with pytest.raises(ProbeError):
            probe.probe_checkout("incident-1", PRODUCT, synthetic_user_id=invalid)
    with pytest.raises(ProbeError):
        probe.probe_catalog("incident-1", "../secret")
    assert transport.calls == []


def test_transport_failure_is_unavailable_not_success_and_string_is_not_saved():
    def unavailable(*args, **kwargs):
        raise urllib.error.URLError("secret-token secret-card")
    receipt = _probe(unavailable).probe_catalog("incident-1", PRODUCT)
    assert receipt["status"] == "unavailable" and not receipt["business_success"]
    assert "secret-token" not in json.dumps(receipt)


@pytest.mark.parametrize("overrides", [
    {"scope_id": "other"}, {"journey": "product_catalog"}, {"product_id": "other"},
    {"not_before": "2026-10-02T08:00:11+00:00"}, {"now": "2026-10-02T08:05:00+00:00"},
    {"now": "2026-10-02T08:00:09+00:00"}, {"now": "invalid"}, {"max_age_seconds": 0},
])
def test_stale_mismatched_or_invalid_path_does_not_close(overrides):
    assert not _validate(_successful_receipt(), **overrides)["accepted"]


def test_success_boolean_without_actual_matching_order_not_accepted():
    for modification in ({"items": []}, {"orderId": ""}, {"error_present": True}):
        receipt = deepcopy(_successful_receipt())
        receipt["requests"][-1]["response"].update(modification)
        assert not _validate(receipt)["accepted"]


def test_catalog_has_actual_product_body_and_failure_cannot_hide_behind_http_200():
    for body, expected in ([{"id": PRODUCT}], True), ([], False), ({"error": "catalog down"}, False), ([{"id": "other"}], False):
        receipt = _probe(lambda *args, **kwargs: _response(body)).probe_catalog("incident-1", PRODUCT)
        assert receipt["business_success"] is expected


def test_image_asset_result_never_claims_browser_feature_flag_equivalence():
    calls = []
    def transport(method, url, **kwargs):
        calls.append(url)
        if "/api/products/" in url:
            return _response({"id": PRODUCT, "picture": "SolarSystemColorImager.jpg"})
        return HTTPResponse(200, b"image-bytes", "image/jpeg", 15)
    receipt = _probe(transport).probe_image("incident-1", PRODUCT)
    assert receipt["business_success"]
    assert receipt["browser_equivalent"] is False
    assert receipt["journey"] == "product_image_asset"
    assert calls[-1] == "http://127.0.0.1:8080/images/products/SolarSystemColorImager.jpg"
    receipt["source_kind"] = "captured_shop"
    assert not _validate(receipt, journey="product_image_asset")["accepted"]
