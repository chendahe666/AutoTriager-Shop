"""Bounded local Astronomy Shop customer-path probes.

These probes observe the customer API, not the incident operator's fault flags.
Checkout creates a synthetic order in the local demo and must be requested
explicitly. It does not modify production settings or execute model commands.
The returned receipts contain selected response fields and response hashes;
customer addresses, email, session IDs, and card information are not retained.

Contract audited at OpenTelemetry Demo commit
dedc0178918e260823323b8d95005a8cb924b007:
src/frontend/pages/api/{cart,checkout}.ts, products/index.ts and
src/frontend/protos/demo.ts. A successful HTTP status is insufficient for an
order: the actual order must contain the requested item and a tracking ID.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
import time
from typing import Any, Callable, Mapping, Protocol
import urllib.error
import urllib.parse
import urllib.request
import uuid


SOURCE_COMMIT = "dedc0178918e260823323b8d95005a8cb924b007"
_LOCAL_ORIGINS = frozenset({"http://127.0.0.1:8080", "http://localhost:8080", "http://[::1]:8080"})
_ID = re.compile(r"[A-Za-z0-9_-]{1,100}\Z")
_SYNTHETIC_USER = re.compile(r"autotriager-probe-[0-9a-f]{32}\Z")
_MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class ProbeError(ValueError):
    """The requested probe is outside the declared local contract."""


@dataclass(frozen=True)
class HTTPResponse:
    status: int
    body: bytes
    content_type: str = "application/json"
    elapsed_ms: float = 0.0


class Transport(Protocol):
    def __call__(self, method: str, url: str, *, json_body: Mapping[str, Any] | None,
                 headers: Mapping[str, str], timeout: float) -> HTTPResponse: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> None:
        return None


def _http(method: str, url: str, *, json_body: Mapping[str, Any] | None,
          headers: Mapping[str, str], timeout: float) -> HTTPResponse:
    """Send only to the validated local origin, without following redirects."""
    encoded = json.dumps(json_body).encode("utf-8") if json_body is not None else None
    request = urllib.request.Request(url, data=encoded, method=method,
                                     headers={"Accept": "application/json", **headers})
    if encoded is not None:
        request.add_header("Content-Type", "application/json")
    # Proxy environment variables must not route a local probe elsewhere.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    started = time.monotonic()
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        body = response.read(_MAX_RESPONSE_BYTES + 1)
        if len(body) > _MAX_RESPONSE_BYTES:
            raise ProbeError("Response exceeded the bounded probe size")
        return HTTPResponse(status=response.code, body=body,
                            content_type=response.headers.get("Content-Type", ""),
                            elapsed_ms=(time.monotonic() - started) * 1000)


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ProbeError("Probe clock must supply a timezone-aware timestamp")
    return value.astimezone(timezone.utc).isoformat()


def _time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as error:
        raise ProbeError("Invalid receipt timestamp") from error
    if parsed.tzinfo is None:
        raise ProbeError("Receipt timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ProbeError(f"Invalid {label}")
    return value


def _json(response: HTTPResponse) -> Any:
    if len(response.body) > _MAX_RESPONSE_BYTES:
        return None
    try:
        return json.loads(response.body)
    except (ValueError, UnicodeDecodeError):
        return None


def _items(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return result
    for row in value:
        if not isinstance(row, dict):
            continue
        item = row.get("item", row)
        if not isinstance(item, dict):
            continue
        product = item.get("productId")
        quantity = item.get("quantity")
        if isinstance(product, str) and _ID.fullmatch(product) and type(quantity) is int:
            result.append({"product_id": product, "quantity": quantity})
    return result


def _has_exact_item(value: Any, product_id: str) -> bool:
    return (isinstance(value, list) and len(value) == 1
            and _items(value) == [{"product_id": product_id, "quantity": 1}])


def _public_body(body: Any) -> dict[str, Any]:
    """Retain contract fields only; never retain arbitrary server error text."""
    if isinstance(body, list):
        products = [{"id": row["id"]} for row in body
                    if isinstance(row, dict) and isinstance(row.get("id"), str)
                    and _ID.fullmatch(row["id"])]
        return {"product_count": len(body), "products": products}
    if not isinstance(body, dict):
        return {"json_body": False}
    result: dict[str, Any] = {"json_body": True}
    for name in ("id", "orderId", "shippingTrackingId"):
        value = body.get(name)
        if isinstance(value, str) and _ID.fullmatch(value):
            result[name] = value
    if "items" in body:
        result["items"] = _items(body["items"])
    if "error" in body or "errors" in body:
        result["error_present"] = True
        # This is the official public error code, not arbitrary upstream text.
        if body.get("code") == "PAYMENT_FAILED":
            result["error_code"] = "PAYMENT_FAILED"
    return result


class CustomerProbe:
    def __init__(self, shop_origin: str = "http://127.0.0.1:8080", *,
                 transport: Transport = _http, timeout: float = 15.0,
                 clock: Callable[[], datetime] = _utc) -> None:
        if shop_origin not in _LOCAL_ORIGINS:
            raise ProbeError("Customer probes are restricted to local demo port 8080")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 30:
            raise ProbeError("Timeout must be within (0, 30] seconds")
        self.shop_origin = shop_origin
        self.transport = transport
        self.timeout = float(timeout)
        self.clock = clock

    def _start(self, scope_id: str, journey: str, product_id: str | None) -> dict[str, Any]:
        _identifier(scope_id, "scope ID")
        if product_id is not None:
            _identifier(product_id, "product ID")
        return {"schema_version": 1, "probe_id": uuid.uuid4().hex, "scope_id": scope_id,
                "journey": journey, "product_id": product_id, "origin": self.shop_origin,
                "source_kind": "captured_shop" if self.transport is _http else "test_transport",
                "source_commit": SOURCE_COMMIT, "started_at": _timestamp(self.clock()),
                "trace_id": uuid.uuid4().hex, "requests": [],
                "trace_context_generated": True, "trace_context_observed": False,
                "created_order": False,
                "business_success": False, "status": "failed", "reason": "incomplete_probe"}

    def _request(self, receipt: dict[str, Any], method: str, path: str,
                 json_body: Mapping[str, Any] | None = None) -> tuple[HTTPResponse | None, Any]:
        if not path.startswith("/") or path.startswith("//") or "\\" in path:
            raise ProbeError("Probe path must stay on the declared local origin")
        # Internal paths are fixed; this also prevents custom transport redirect claims.
        if urllib.parse.urlsplit(self.shop_origin + path).netloc != urllib.parse.urlsplit(self.shop_origin).netloc:
            raise ProbeError("Probe path changed the declared origin")
        entry: dict[str, Any] = {"method": method, "path": path.split("?")[0],
                                 "started_at": _timestamp(self.clock())}
        parent_span_id = uuid.uuid4().hex[:16]
        entry["client_parent_span_id"] = parent_span_id
        try:
            result = self.transport(method, self.shop_origin + path, json_body=json_body,
                                    headers={"traceparent": f"00-{receipt['trace_id']}-{parent_span_id}-01",
                                             "Cache-Control": "no-cache"}, timeout=self.timeout)
            body = _json(result)
            entry.update({"http_status": result.status, "content_type": result.content_type,
                          "elapsed_ms": round(result.elapsed_ms, 3),
                          "response_body_sha256": hashlib.sha256(result.body).hexdigest(),
                          "response_bytes": len(result.body), "response": _public_body(body)})
        except (OSError, TimeoutError, urllib.error.URLError, ProbeError) as error:
            # Exception strings can expose destinations or supplied customer data.
            entry.update({"http_status": None, "transport_error": type(error).__name__})
            result, body = None, None
        entry["finished_at"] = _timestamp(self.clock())
        receipt["requests"].append(entry)
        return result, body

    def _finish(self, receipt: dict[str, Any], success: bool, reason: str) -> dict[str, Any]:
        finished_at = _timestamp(self.clock())
        receipt.update({"finished_at": finished_at, "checked_at": finished_at,
                        "time": {"started_at": receipt["started_at"], "finished_at": finished_at},
                        "business_success": success,
                        "reason": reason, "status": "success" if success else "failed"})
        if any(row.get("transport_error") for row in receipt["requests"]):
            receipt["status"] = "unavailable"
        return receipt

    def probe_catalog(self, scope_id: str, product_id: str | None = None) -> dict[str, Any]:
        receipt = self._start(scope_id, "product_catalog", product_id)
        result, body = self._request(receipt, "GET", "/api/products?currencyCode=USD")
        valid = (result is not None and result.status == 200 and isinstance(body, list)
                 and bool(body) and all(isinstance(row, dict) and isinstance(row.get("id"), str)
                                        and _ID.fullmatch(row["id"]) for row in body))
        if valid and product_id is not None:
            valid = any(row["id"] == product_id for row in body)
        return self._finish(receipt, bool(valid), "catalog_items_received" if valid else "catalog_unavailable_or_invalid")

    def probe_image(self, scope_id: str, product_id: str) -> dict[str, Any]:
        """Check asset retrieval only, not browser/OpenFeature imageSlowLoad behavior."""
        receipt = self._start(scope_id, "product_image_asset", product_id)
        receipt["browser_equivalent"] = False
        receipt["limitation"] = "Asset retrieval omits browser feature-flag behavior; it cannot validate imageSlowLoad recovery."
        result, body = self._request(receipt, "GET", f"/api/products/{product_id}?currencyCode=USD")
        if result is None or result.status != 200 or not isinstance(body, dict) or body.get("id") != product_id:
            return self._finish(receipt, False, "product_unavailable_or_mismatched")
        picture = body.get("picture")
        if not isinstance(picture, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,150}", picture) or picture in {".", ".."}:
            return self._finish(receipt, False, "invalid_image_path")
        result, _ = self._request(receipt, "GET", f"/images/products/{picture}")
        valid = (result is not None and result.status == 200 and bool(result.body)
                 and result.content_type.lower().split(";")[0].startswith("image/"))
        return self._finish(receipt, bool(valid), "image_asset_received" if valid else "image_asset_unavailable_or_invalid")

    def probe_checkout(self, scope_id: str, product_id: str, *,
                       synthetic_user_id: str | None = None) -> dict[str, Any]:
        """Place one local synthetic order, preserving a failed cart for a retry.

        A caller may supply and retain a synthetic session privately for a retry;
        the public receipt deliberately stores only its hash. The method never
        accepts a real customer's session or caller-supplied payment details.
        """
        receipt = self._start(scope_id, "checkout", product_id)
        user = "autotriager-probe-" + uuid.uuid4().hex if synthetic_user_id is None else synthetic_user_id
        if not isinstance(user, str) or not _SYNTHETIC_USER.fullmatch(user):
            raise ProbeError("Checkout requires an isolated synthetic customer session")
        receipt["synthetic_purchase"] = True
        receipt["synthetic_user_sha256"] = hashlib.sha256(user.encode("utf-8")).hexdigest()
        cart_path = "/api/cart?" + urllib.parse.urlencode({"sessionId": user, "currencyCode": "USD"})
        result, body = self._request(receipt, "GET", cart_path)
        if result is None or result.status != 200 or not isinstance(body, dict) or not isinstance(body.get("items"), list):
            return self._finish(receipt, False, "cart_unavailable_or_mismatched")
        # Official ValkeyCartStore stores an empty protobuf on EmptyCartAsync;
        # later AddItemAsync retains that blank UserId. Session-specific requests
        # identify the cart, while a nonempty conflicting returned ID is rejected.
        if body.get("userId") not in ("", user):
            return self._finish(receipt, False, "cart_unavailable_or_mismatched")
        if body["items"]:
            if not _has_exact_item(body["items"], product_id):
                return self._finish(receipt, False, "synthetic_cart_does_not_match_journey")
        else:
            result, body = self._request(receipt, "POST", "/api/cart", {"userId": user, "item": {"productId": product_id, "quantity": 1}})
            if result is None or result.status != 200 or not isinstance(body, dict) or body.get("userId") not in ("", user) or not _has_exact_item(body.get("items"), product_id):
                return self._finish(receipt, False, "cart_add_not_confirmed")
            result, body = self._request(receipt, "GET", cart_path)
            if result is None or result.status != 200 or not isinstance(body, dict) or body.get("userId") not in ("", user) or not _has_exact_item(body.get("items"), product_id):
                return self._finish(receipt, False, "cart_contents_not_confirmed")
        # Public official-demo defaults, supplied only to the local sandbox.
        payload = {"userId": user, "userCurrency": "USD", "email": "someone@example.com",
                   "address": {"streetAddress": "1600 Amphitheatre Parkway", "city": "Mountain View",
                               "state": "CA", "country": "United States", "zipCode": "94043"},
                   "creditCard": {"creditCardNumber": "4432-8015-6152-0454", "creditCardCvv": 672,
                                  "creditCardExpirationYear": 2030, "creditCardExpirationMonth": 1}}
        result, body = self._request(receipt, "POST", "/api/checkout?currencyCode=USD", payload)
        valid = (result is not None and result.status == 200 and isinstance(body, dict)
                 and not ("error" in body or "errors" in body)
                 and isinstance(body.get("orderId"), str) and bool(_ID.fullmatch(body["orderId"]))
                 and isinstance(body.get("shippingTrackingId"), str) and bool(_ID.fullmatch(body["shippingTrackingId"]))
                 and _has_exact_item(body.get("items"), product_id))
        reason = "confirmed_order_for_requested_item" if valid else "order_not_confirmed"
        if isinstance(body, dict) and body.get("code") == "PAYMENT_FAILED":
            reason = "payment_failed"
        receipt["created_order"] = bool(valid)
        return self._finish(receipt, bool(valid), reason)


def validate_recovery_receipt(receipt: Mapping[str, Any], *, scope_id: str, journey: str,
                              not_before: str, product_id: str | None = None,
                              now: str | None = None, max_age_seconds: float = 60) -> dict[str, Any]:
    """Require a fresh successful probe of the declared affected customer path.

    This is one necessary closure signal. Backend recovery must be checked
    separately. An operator action receipt or an old successful probe is not
    evidence of present customer recovery.
    """
    if receipt.get("scope_id") != scope_id or receipt.get("journey") != journey or receipt.get("product_id") != product_id:
        return {"accepted": False, "reason": "scope_or_customer_path_mismatch"}
    if receipt.get("origin") not in _LOCAL_ORIGINS:
        return {"accepted": False, "reason": "origin_not_allowlisted"}
    if receipt.get("source_kind") != "captured_shop":
        return {"accepted": False, "reason": "not_live_customer_observation"}
    if isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, (int, float)) or not 0 < max_age_seconds <= 300:
        return {"accepted": False, "reason": "invalid_freshness_bound"}
    try:
        started = _time(receipt.get("started_at", ""))
        finished = _time(receipt.get("finished_at", ""))
        cutoff = _time(not_before)
        current = _time(now) if now is not None else _utc()
    except ProbeError:
        return {"accepted": False, "reason": "invalid_probe_time"}
    if started < cutoff or finished < started or finished > current or (current - finished).total_seconds() > max_age_seconds:
        return {"accepted": False, "reason": "stale_or_invalid_probe_time"}
    if receipt.get("business_success") is not True or receipt.get("status") != "success":
        return {"accepted": False, "reason": "customer_path_not_recovered"}
    requests = receipt.get("requests")
    if not isinstance(requests, list) or not requests or not isinstance(requests[-1], dict):
        return {"accepted": False, "reason": "missing_customer_request_receipt"}
    final = requests[-1]
    body = final.get("response", {})
    if final.get("http_status") != 200 or not isinstance(body, dict) or body.get("error_present"):
        return {"accepted": False, "reason": "successful_business_response_missing"}
    if journey == "checkout":
        valid = (final.get("method") == "POST" and final.get("path") == "/api/checkout"
                 and receipt.get("created_order") is True
                 and isinstance(body.get("orderId"), str) and bool(_ID.fullmatch(body["orderId"]))
                 and isinstance(body.get("shippingTrackingId"), str) and bool(_ID.fullmatch(body["shippingTrackingId"]))
                 and body.get("items") == [{"product_id": product_id, "quantity": 1}])
        if not valid:
            return {"accepted": False, "reason": "confirmed_matching_order_missing"}
    elif journey == "product_catalog":
        products = body.get("products")
        valid = (final.get("method") == "GET" and final.get("path") == "/api/products"
                 and isinstance(products, list) and bool(products)
                 and (product_id is None or {"id": product_id} in products))
        if not valid:
            return {"accepted": False, "reason": "matching_catalog_response_missing"}
    elif journey == "product_images":
        import math
        duration = final.get("elapsed_ms")
        valid = (receipt.get("browser_equivalent") is True
                 and receipt.get("browser_image_displayed") is True
                 and receipt.get("image_threshold_ms") == 1500
                 and body.get("image_displayed") is True
                 and type(body.get("image_bytes")) is int and body["image_bytes"] > 0
                 and isinstance(receipt.get("image_path"), str)
                 and re.fullmatch(r"/images/products/[A-Za-z0-9_.-]{1,150}", receipt["image_path"])
                 and final.get("method") == "GET" and final.get("path") == receipt["image_path"]
                 and isinstance(duration, (float, int)) and not isinstance(duration, bool)
                 and math.isfinite(duration) and 0 <= duration <= 1500)
        if not valid:
            return {"accepted": False, "reason": "fresh_native_browser_image_success_missing"}
    else:
        # Bare asset retrieval cannot verify the actual feature-flag browser path.
        return {"accepted": False, "reason": "customer_journey_not_validated_for_closure"}
    return {"accepted": True, "reason": "fresh_customer_path_success", "probe_id": receipt.get("probe_id")}
