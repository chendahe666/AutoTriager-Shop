"""Observe one real Astronomy Shop ProductCard image, without changing faults.

The pinned storefront fetches images using its evaluated delay header and displays
the response as a blob background. A bare asset GET cannot exercise this path.
Only the selected image request receives missing trace context; its existing
headers, including the upstream delay header, are preserved and never retained.
The 1500 ms success threshold is prospective, not fitted to a fault result.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable, Mapping, Protocol
import urllib.parse
import uuid

from .customer_probe import (CustomerProbe, ProbeError, SOURCE_COMMIT, _SYNTHETIC_USER,
                             _has_exact_item, _identifier, _public_body, _timestamp, _utc)

IMAGE_THRESHOLD_MS = 1500
_ORIGINS = frozenset({"http://127.0.0.1:8080", "http://localhost:8080", "http://[::1]:8080"})
_IMAGE_PATH = re.compile(r"/images/products/[A-Za-z0-9_.-]+\.(?:jpg|jpeg|png|webp)\Z", re.I)
_TRACEPARENT = re.compile(r"00-([0-9a-f]{32})-([0-9a-f]{16})-0[01]\Z")
_REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{1,100}\Z")


def _browser_runtime() -> Any:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        # The local demo has an isolated, pinned browser test dependency folder.
        # This is a real browser dependency, never a mock fallback. Incompatible
        # Python wheels still fail explicitly rather than substituting evidence.
        bundled = Path(__file__).resolve().parents[1] / ".local-demo/browser-test-libs"
        if not bundled.is_dir():
            raise
        sys.path.insert(0, str(bundled))
        from playwright.sync_api import sync_playwright
    return sync_playwright


def _launch_args() -> dict[str, Any]:
    executables = (Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
                   Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"))
    executable = next((str(path) for path in executables if path.is_file()), None)
    return {"headless": True, **({"executable_path": executable} if executable else {})}


class BrowserAdapter(Protocol):
    def __call__(self, *, origin: str, product_id: str,
                 timeout_ms: int, trace_id: str) -> Mapping[str, Any]: ...


class CheckoutBrowserAdapter(Protocol):
    def __call__(self, *, origin: str, product_id: str, timeout_ms: int,
                 trace_id: str, synthetic_user_id: str) -> Mapping[str, Any]: ...


def _trace(value: Any) -> str | None:
    match = _TRACEPARENT.fullmatch(value) if isinstance(value, str) else None
    if match and match[1] != "0" * 32 and match[2] != "0" * 16:
        return match[1]
    return None


def _finite(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _safe_checkout_body(public: Any) -> dict[str, Any]:
    if not isinstance(public, dict):
        return {}
    body: dict[str, Any] = {}
    for name in ("orderId", "shippingTrackingId"):
        value = public.get(name)
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
            body[name] = value
    if "items" in public:
        rows = public["items"]
        body["items"] = [{"product_id": row["product_id"], "quantity": row["quantity"]}
            for row in rows if isinstance(row, dict) and isinstance(row.get("product_id"), str)
            and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", row["product_id"])
            and type(row.get("quantity")) is int] if isinstance(rows, list) else []
    for name in ("json_body", "error_present"):
        if type(public.get(name)) is bool:
            body[name] = public[name]
    if public.get("error_code") == "PAYMENT_FAILED":
        body["error_code"] = "PAYMENT_FAILED"
    return body


def _playwright_image(*, origin: str, product_id: str, timeout_ms: int,
                      trace_id: str, screenshot_path: Path | None = None) -> Mapping[str, Any]:
    """Fresh browser context; no order submissions or simulator/control writes."""
    with _browser_runtime()() as driver:
        browser = driver.chromium.launch(**_launch_args())
        try:
            context = browser.new_context(viewport={"width": 1280, "height": 800},
                                          service_workers="block")
            metadata = context.request.get(
                f"{origin}/api/products/{product_id}?currencyCode=USD",
                timeout=timeout_ms, max_redirects=0)
            if metadata.status != 200:
                return {"error_kind": "product_metadata_unavailable"}
            product = metadata.json()
            picture = product.get("picture") if isinstance(product, dict) else None
            if (not isinstance(product, dict) or product.get("id") != product_id
                    or not isinstance(picture, str)):
                return {"error_kind": "product_metadata_invalid"}
            image_path = "/images/products/" + picture
            if not _IMAGE_PATH.fullmatch(image_path):
                return {"error_kind": "product_image_path_invalid"}
            requests: list[dict[str, Any]] = []
            observed: dict[int, dict[str, Any]] = {}
            flag_response_seen = False
            selected_url = origin + image_path
            page = context.new_page()

            def route_request(route: Any) -> None:
                request = route.request
                parsed = urllib.parse.urlsplit(request.url)
                if f"{parsed.scheme}://{parsed.netloc}" != origin:
                    route.abort()
                    return
                # These POSTs are ordinary browser telemetry or read-only flag
                # evaluation, not configuration updates. Cart and checkout stay
                # blocked in this image-only probe.
                allowed_post = (parsed.path.startswith("/flagservice/")
                                or parsed.path in {"/otlp-http/v1/traces", "/v1/traces"})
                if request.method not in {"GET", "HEAD"} and not (request.method == "POST" and allowed_post):
                    route.abort()
                    return
                if parsed.path.startswith(("/feature/api/write", "/feature/api/read", "/api/checkout", "/api/cart")):
                    route.abort()
                    return
                if request.url != selected_url:
                    route.continue_()
                    return
                headers = dict(request.headers)
                native = _trace(headers.get("traceparent"))
                generated = False
                if not native:
                    headers["traceparent"] = f"00-{trace_id}-{uuid.uuid4().hex[:16]}-01"
                    generated = True
                request_id = headers.get("x-request-id")
                if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
                    request_id = str(uuid.uuid4())
                    headers["x-request-id"] = request_id
                entry = {"path": image_path, "method": request.method,
                         "started_at": _timestamp(_utc()), "_started": time.monotonic(),
                         "trace_id": native or trace_id,
                         "traceparent_source": "native_browser" if native else "generated_when_absent",
                         "trace_context_generated": generated, "request_id": request_id,
                         "http_status": None, "image_bytes": 0, "content_type": "",
                         "image_displayed": False}
                requests.append(entry)
                observed[id(request)] = entry
                route.continue_(headers=headers)

            def response_received(response: Any) -> None:
                nonlocal flag_response_seen
                if urllib.parse.urlsplit(response.url).path.startswith("/flagservice/"):
                    flag_response_seen = response.status == 200
                entry = observed.get(id(response.request))
                if entry is not None:
                    entry["http_status"] = response.status
                    entry["content_type"] = response.headers.get("content-type", "").split(";")[0]
                    response_id = response.headers.get("x-request-id")
                    if response_id == entry["request_id"]:
                        entry["request_id_echoed"] = True

            def request_finished(request: Any) -> None:
                entry = observed.get(id(request))
                if entry is None:
                    return
                timing = request.timing.get("responseEnd", -1)
                entry["elapsed_ms"] = (timing if _finite(timing) and timing > 0
                                       else (time.monotonic() - entry["_started"]) * 1000)
                entry["timing_source"] = "browser_resource_timing" if _finite(timing) and timing > 0 else "observer_monotonic"
                entry["finished_at"] = _timestamp(_utc())
                entry["_finished"] = time.monotonic()
                response = request.response()
                try:
                    entry["image_bytes"] = len(response.body()) if response else 0
                except Exception:
                    entry["image_bytes"] = 0

            def request_failed(request: Any) -> None:
                entry = observed.get(id(request))
                if entry is not None:
                    entry["error_kind"] = "image_request_failed"
                    entry["finished_at"] = _timestamp(_utc())
                    entry["_finished"] = time.monotonic()

            context.route("**/*", route_request)
            page.on("response", response_received)
            page.on("requestfinished", request_finished)
            page.on("requestfailed", request_failed)
            begun = time.monotonic()
            page.goto(origin + "/", wait_until="domcontentloaded", timeout=timeout_ms)
            selected = page.locator(f'a[href="/product/{product_id}"] [data-cy="product-card"]')
            deadline = begun + timeout_ms / 1000
            displayed = False
            while time.monotonic() < deadline:
                page.wait_for_timeout(200)
                if not requests or selected.count() != 1:
                    continue
                last = requests[-1]
                # Initial default flags may trigger an aborted/fast fetch before
                # evaluation. Wait for evaluated browser state and the final
                # selected request to settle; never pick the fastest response.
                if (not flag_response_seen or "_finished" not in last
                        or time.monotonic() - last["_finished"] < 2
                        or time.monotonic() - begun < 3):
                    continue
                displayed = selected.evaluate("""async card => {
                  const nodes = [card, ...card.querySelectorAll('*')];
                  for (const node of nodes) {
                    const bg = getComputedStyle(node).backgroundImage;
                    const match = bg.match(/url\\([\"']?(blob:[^\"')]+)[\"']?\\)/);
                    if (!match) continue;
                    const image = new Image(); image.src = match[1];
                    try { await image.decode(); if (image.naturalWidth > 0 && image.naturalHeight > 0) return true; }
                    catch (_) { return false; }
                  }
                  return false;
                }""")
                if displayed or last.get("error_kind") or last.get("http_status") != 200:
                    break
            if requests:
                requests[-1]["image_displayed"] = displayed
            if screenshot_path is not None:
                try:
                    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(screenshot_path), full_page=True)
                except Exception:
                    # An optional screenshot failure cannot erase the actual
                    # customer observation or manufacture another outcome.
                    pass
            return {"product_id": product_id, "image_path": image_path,
                    "flag_evaluation_observed": flag_response_seen,
                    "requests": requests[-3:], "image_displayed": displayed}
        finally:
            browser.close()


def _playwright_checkout(*, origin: str, product_id: str, timeout_ms: int,
                         trace_id: str, synthetic_user_id: str,
                         screenshot_path: Path | None = None) -> Mapping[str, Any]:
    """Native cart and submit clicks; only a fixed isolated demo purchase allowed."""
    with _browser_runtime()() as driver:
        browser = driver.chromium.launch(**_launch_args())
        requests: list[dict[str, Any]] = []
        order_confirmation = False
        try:
            context = browser.new_context(viewport={"width": 1280, "height": 800}, service_workers="block")
            context.add_init_script("localStorage.setItem('session', " + json.dumps(json.dumps(
                {"userId": synthetic_user_id, "currencyCode": "USD"})) + ");")
            page = context.new_page()
            starts: dict[int, tuple[float, str | None, str, bool]] = {}

            def route_request(route: Any) -> None:
                request = route.request
                url = urllib.parse.urlsplit(request.url)
                if f"{url.scheme}://{url.netloc}" != origin:
                    route.abort(); return
                if url.path.startswith(("/feature/api/write", "/feature/api/read")):
                    route.abort(); return
                allowed_post = (url.path.startswith("/flagservice/")
                                or url.path in {"/api/cart", "/api/checkout", "/otlp-http/v1/traces", "/v1/traces"})
                if request.method not in {"GET", "HEAD"} and not (request.method == "POST" and allowed_post):
                    route.abort(); return
                if url.path in {"/api/cart", "/api/checkout"} and request.method == "POST":
                    try:
                        payload = request.post_data_json
                    except Exception:
                        route.abort(); return
                    if not isinstance(payload, dict) or payload.get("userId") != synthetic_user_id:
                        route.abort(); return
                    if url.path == "/api/cart" and payload.get("item") != {"productId": product_id, "quantity": 1}:
                        route.abort(); return
                    if url.path == "/api/checkout" and payload.get("userCurrency") != "USD":
                        route.abort(); return
                if url.path not in {"/api/cart", "/api/checkout"}:
                    route.continue_(); return
                headers = dict(request.headers)
                native = _trace(headers.get("traceparent"))
                generated = native is None
                if generated:
                    headers["traceparent"] = f"00-{trace_id}-{uuid.uuid4().hex[:16]}-01"
                starts[id(request)] = (time.monotonic(), native or trace_id,
                                       "native_browser" if native else "generated_when_absent", generated)
                route.continue_(headers=headers)

            def response_received(response: Any) -> None:
                request = response.request
                url = urllib.parse.urlsplit(request.url)
                if url.path not in {"/api/cart", "/api/checkout"}:
                    return
                try:
                    body = response.json()
                    raw = response.body()
                except Exception:
                    body, raw = None, b""
                started, observed_trace, parent_source, generated = starts.get(id(request), (time.monotonic(), None, "unlinked", False))
                requests.append({"method": request.method, "path": url.path,
                    "http_status": response.status, "content_type": response.headers.get("content-type", "").split(";")[0],
                    "elapsed_ms": (time.monotonic() - started) * 1000,
                    "trace_id": observed_trace, "traceparent_source": parent_source,
                    "trace_context_generated": generated, "response": _public_body(body),
                    "response_bytes": len(raw), "response_body_sha256": hashlib.sha256(raw).hexdigest(),
                    "matching_order_response": (url.path == "/api/checkout" and isinstance(body, dict)
                        and _has_exact_item(body.get("items"), product_id)
                        and "error" not in body and "errors" not in body),
                    "_actual_body": body})

            context.route("**/*", route_request)
            page.on("response", response_received)
            page.goto(origin + "/", wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_function("document.querySelector('[data-cy=product-card]') !== null", timeout=timeout_ms)
            deadline = time.monotonic() + timeout_ms / 1000
            while not any(r["path"] == "/api/cart" and r["method"] == "GET" for r in requests) and time.monotonic() < deadline:
                page.wait_for_timeout(100)
            cart = next((r for r in reversed(requests) if r["path"] == "/api/cart" and r["method"] == "GET"), None)
            if cart is None or cart["http_status"] != 200 or not isinstance(cart["_actual_body"], dict):
                return {"requests": requests, "error_kind": "cart_not_observed", "order_confirmation_displayed": False}
            items = cart["_actual_body"].get("items")
            if items == []:
                page.locator(f'a[href="/product/{product_id}"]').first.click(timeout=timeout_ms)
                page.locator('[data-cy="product-quantity"]').select_option("1", timeout=timeout_ms)
                page.locator('[data-cy="product-add-to-cart"]').click(timeout=timeout_ms)
                page.wait_for_url(origin + "/cart", timeout=timeout_ms)
            elif _has_exact_item(items, product_id):
                # A failed earlier probe may leave the isolated exact cart.
                # Reuse it without adding a duplicate item.
                page.goto(origin + "/cart", wait_until="domcontentloaded", timeout=timeout_ms)
            else:
                return {"requests": requests, "error_kind": "cart_scope_mismatch", "order_confirmation_displayed": False}
            page.locator('#email').fill("autotriager-probe@example.invalid")
            page.locator('#street_address').fill("1600 Amphitheatre Parkway")
            page.locator('#zip_code').fill("94043")
            page.locator('#city').fill("Mountain View")
            page.locator('#state').fill("CA")
            page.locator('#country').fill("United States")
            page.locator('#credit_card_number').fill("4432-8015-6152-0454")
            page.locator('#credit_card_cvv').fill("123")
            page.locator('#credit_card_expiration_year').select_option(str(datetime.now(timezone.utc).year + 1))
            page.locator('#credit_card_expiration_month').select_option("1")
            page.locator('[data-cy="checkout-place-order"]').click(timeout=timeout_ms)
            deadline = time.monotonic() + timeout_ms / 1000
            final: dict[str, Any] | None = None
            while time.monotonic() < deadline:
                page.wait_for_timeout(100)
                final = next((r for r in reversed(requests) if r["path"] == "/api/checkout" and r["method"] == "POST"), None)
                if final is None:
                    continue
                if final["http_status"] != 200:
                    break
                order_id = final["response"].get("orderId")
                if (isinstance(order_id, str) and _identifier(order_id, "order ID")
                        and urllib.parse.urlsplit(page.url).path == f"/cart/checkout/{order_id}"
                        and page.get_by_role("heading", name="Your order is complete!", exact=True).count() == 1
                        and page.get_by_text(order_id, exact=True).count() == 1):
                    order_confirmation = True
                    break
            return {"requests": requests, "order_confirmation_displayed": order_confirmation,
                    "product_id": product_id}
        except Exception as error:
            return {"requests": requests, "order_confirmation_displayed": False,
                    "product_id": product_id, "error_kind": type(error).__name__}
        finally:
            if screenshot_path is not None and "page" in locals():
                try:
                    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(screenshot_path), full_page=True)
                except Exception:
                    pass
            browser.close()


class BrowserCustomerProbe:
    def __init__(self, shop_origin: str = "http://127.0.0.1:8080", *,
                 threshold_ms: int = IMAGE_THRESHOLD_MS, browser_timeout_ms: int = 30000,
                 adapter: BrowserAdapter = _playwright_image,
                 clock: Callable[[], datetime] = _utc, screenshot_path: Path | None = None,
                 checkout_adapter: CheckoutBrowserAdapter = _playwright_checkout) -> None:
        if shop_origin not in _ORIGINS:
            raise ProbeError("Browser probes are restricted to local demo port 8080")
        if type(threshold_ms) is not int or threshold_ms != IMAGE_THRESHOLD_MS:
            raise ProbeError("Image threshold is frozen at 1500 ms")
        if type(browser_timeout_ms) is not int or not 3000 <= browser_timeout_ms <= 30000:
            raise ProbeError("Browser timeout must be within [3000, 30000] ms")
        self.shop_origin, self.threshold_ms = shop_origin, threshold_ms
        self.browser_timeout_ms, self.adapter, self.clock = browser_timeout_ms, adapter, clock
        self.checkout_adapter = checkout_adapter
        self.screenshot_path = screenshot_path
        if screenshot_path is not None:
            root = Path(__file__).resolve().parents[1]
            target = Path(screenshot_path).resolve()
            if not target.is_relative_to(root) or target.suffix.lower() != ".png":
                raise ProbeError("Probe screenshots must be PNG files inside this workspace")
            self.screenshot_path = target

    def probe_product_images(self, scope_id: str, product_id: str = "0PUK6V6EV0") -> dict[str, Any]:
        _identifier(scope_id, "scope ID")
        _identifier(product_id, "product ID")
        started = _timestamp(self.clock())
        trace_id = uuid.uuid4().hex
        receipt: dict[str, Any] = {
            "schema_version": 1, "probe_id": uuid.uuid4().hex, "scope_id": scope_id,
            "journey": "product_images", "product_id": product_id, "origin": self.shop_origin,
            "source_kind": "captured_shop" if self.adapter is _playwright_image else "test_transport",
            "source_commit": SOURCE_COMMIT, "browser_equivalent": True,
            "started_at": started, "created_order": False, "business_success": False,
            "status": "unavailable", "reason": "browser_probe_incomplete", "requests": [],
            "trace_id": None, "trace_ids": [], "trace_context_observed": False,
            "image_threshold_ms": self.threshold_ms, "latency_threshold_ms": self.threshold_ms,
            "browser_image_displayed": False, "image_rendered": False,
            "scope": "One representative SKU on the official catalog ProductCard; not all platform images."}
        try:
            if self.adapter is _playwright_image:
                result = _playwright_image(origin=self.shop_origin, product_id=product_id,
                    timeout_ms=self.browser_timeout_ms, trace_id=trace_id,
                    screenshot_path=self.screenshot_path)
            else:
                result = self.adapter(origin=self.shop_origin, product_id=product_id,
                                      timeout_ms=self.browser_timeout_ms, trace_id=trace_id)
            path = result.get("image_path")
            if (result.get("product_id") != product_id or not isinstance(path, str)
                    or not _IMAGE_PATH.fullmatch(path)):
                receipt["reason"] = "selected_product_path_not_observed"
            elif result.get("flag_evaluation_observed") is not True:
                receipt["reason"] = "browser_flag_evaluation_not_observed"
            else:
                receipt["image_path"] = path
                rows = result.get("requests")
                if not isinstance(rows, list) or not rows:
                    receipt["reason"] = "selected_image_request_not_observed"
                else:
                    for row in rows[-3:]:
                        if not isinstance(row, dict) or row.get("path") != path or row.get("method") != "GET":
                            raise ProbeError("Selected image request path/method mismatch")
                        entry = {"method": "GET", "path": path, "http_status": row.get("http_status")
                                 if type(row.get("http_status")) is int else None,
                                 "content_type": row.get("content_type") if isinstance(row.get("content_type"), str) and re.fullmatch(r"[A-Za-z0-9.+/-]{1,100}", row["content_type"]) else "",
                                 "response": {"image_displayed": row.get("image_displayed") is True,
                                              "image_bytes": row.get("image_bytes") if type(row.get("image_bytes")) is int and row["image_bytes"] >= 0 else 0}}
                        if _finite(row.get("elapsed_ms")):
                            entry["elapsed_ms"] = round(row["elapsed_ms"], 3)
                        if isinstance(row.get("trace_id"), str) and re.fullmatch(r"[0-9a-f]{32}", row["trace_id"]) and row["trace_id"] != "0" * 32:
                            entry["trace_id"] = row["trace_id"]
                        if row.get("traceparent_source") in {"native_browser", "generated_when_absent"}:
                            entry["traceparent_source"] = row["traceparent_source"]
                            entry["trace_context_generated"] = row.get("trace_context_generated") is True
                        if isinstance(row.get("request_id"), str) and _REQUEST_ID.fullmatch(row["request_id"]):
                            entry["request_id"] = row["request_id"]
                            entry["request_id_echoed"] = row.get("request_id_echoed") is True
                        if row.get("timing_source") in {"browser_resource_timing", "observer_monotonic"}:
                            entry["timing_source"] = row["timing_source"]
                        if row.get("error_kind") == "image_request_failed":
                            entry["error_kind"] = "image_request_failed"
                        receipt["requests"].append(entry)
                    final = receipt["requests"][-1]
                    displayed = final["response"]["image_displayed"] and result.get("image_displayed") is True
                    receipt.update({"browser_image_displayed": displayed, "image_rendered": displayed,
                                    "elapsed_ms": final.get("elapsed_ms"), "duration_ms": final.get("elapsed_ms"),
                                    "trace_id": final.get("trace_id"),
                                    "trace_ids": list(dict.fromkeys(r["trace_id"] for r in receipt["requests"] if r.get("trace_id"))),
                                    "traceparent_source": final.get("traceparent_source", "unlinked"),
                                    "trace_context_generated": final.get("trace_context_generated", False)})
                    valid = final["http_status"] == 200 and final["content_type"].startswith("image/") and final["response"]["image_bytes"] > 0 and displayed
                    if not valid:
                        receipt.update(status="failed", reason="selected_image_failed_or_not_displayed")
                    elif not _finite(final.get("elapsed_ms")):
                        receipt.update(status="unavailable", reason="selected_image_timing_unavailable")
                    elif final["elapsed_ms"] > self.threshold_ms:
                        receipt.update(status="degraded", reason="selected_image_exceeded_declared_threshold")
                    else:
                        receipt.update(status="success", reason="selected_image_displayed_within_declared_threshold", business_success=True)
        except Exception as error:
            # Exceptions may contain browser headers, URLs or application data.
            receipt.update(status="unavailable", reason="browser_probe_unavailable",
                           error_kind=type(error).__name__)
        finished = _timestamp(self.clock())
        receipt.update(finished_at=finished, checked_at=finished,
                       time={"started_at": started, "finished_at": finished})
        return receipt

    def probe_catalog(self, scope_id: str, product_id: str | None = None) -> dict[str, Any]:
        return CustomerProbe(self.shop_origin, clock=self.clock).probe_catalog(scope_id, product_id)

    def probe_checkout(self, scope_id: str, product_id: str,
                       synthetic_user_id: str | None = None) -> dict[str, Any]:
        _identifier(scope_id, "scope ID")
        _identifier(product_id, "product ID")
        if synthetic_user_id is None:
            synthetic_user_id = "autotriager-probe-" + uuid.uuid4().hex
        if not isinstance(synthetic_user_id, str) or not _SYNTHETIC_USER.fullmatch(synthetic_user_id):
            raise ProbeError("Only an isolated generated local synthetic customer is allowed")
        started = _timestamp(self.clock())
        receipt: dict[str, Any] = {"schema_version": 1, "probe_id": uuid.uuid4().hex,
            "scope_id": scope_id, "journey": "checkout", "product_id": product_id,
            "origin": self.shop_origin, "source_commit": SOURCE_COMMIT,
            "source_kind": "captured_shop" if self.checkout_adapter is _playwright_checkout else "test_transport",
            "browser_equivalent": True, "synthetic_purchase": True, "started_at": started,
            "created_order": False, "business_success": False, "status": "unavailable",
            "reason": "native_checkout_incomplete", "requests": [], "trace_id": None,
            "trace_context_observed": False, "order_confirmation_displayed": False}
        try:
            arguments = {"origin": self.shop_origin, "product_id": product_id,
                "timeout_ms": self.browser_timeout_ms, "trace_id": uuid.uuid4().hex,
                "synthetic_user_id": synthetic_user_id}
            if self.checkout_adapter is _playwright_checkout:
                result = _playwright_checkout(**arguments, screenshot_path=self.screenshot_path)
            else:
                result = self.checkout_adapter(**arguments)
            rows = result.get("requests")
            if not isinstance(rows, list):
                rows = []
            checkout_rows = [r for r in rows if isinstance(r, dict) and r.get("path") == "/api/checkout" and r.get("method") == "POST"]
            selected = [r for r in rows if isinstance(r, dict) and r.get("path") == "/api/cart" and r.get("method") in {"GET", "POST"}][-10:]
            selected += checkout_rows[-1:]
            for row in selected:
                # Adapter has already sanitized the actual response; whitelist
                # again so injected fixture/private fields cannot leak.
                body = _safe_checkout_body(row.get("response"))
                entry = {"method": row["method"], "path": row["path"],
                         "http_status": row.get("http_status") if type(row.get("http_status")) is int else None,
                         "response": body}
                if row["path"] == "/api/checkout":
                    entry["matching_order_response"] = row.get("matching_order_response") is True
                if _finite(row.get("elapsed_ms")):
                    entry["elapsed_ms"] = round(row["elapsed_ms"], 3)
                if isinstance(row.get("trace_id"), str) and re.fullmatch(r"[0-9a-f]{32}", row["trace_id"]) and row["trace_id"] != "0" * 32:
                    entry["trace_id"] = row["trace_id"]
                if row.get("traceparent_source") in {"native_browser", "generated_when_absent"}:
                    entry["traceparent_source"] = row["traceparent_source"]
                    entry["trace_context_generated"] = row.get("trace_context_generated") is True
                for name in ("response_bytes", "response_body_sha256"):
                    value = row.get(name)
                    if (name == "response_bytes" and type(value) is int and value >= 0) or (name == "response_body_sha256" and isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)):
                        entry[name] = value
                receipt["requests"].append(entry)
            if checkout_rows:
                final = receipt["requests"][-1]
                body = final["response"]
                order = body.get("orderId")
                tracking = body.get("shippingTrackingId")
                valid = (final["http_status"] == 200 and body.get("error_present") is not True
                         and final.get("matching_order_response") is True
                         and isinstance(order, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", order)
                         and isinstance(tracking, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", tracking)
                         and body.get("items") == [{"product_id": product_id, "quantity": 1}])
                confirmed = result.get("order_confirmation_displayed") is True and result.get("product_id") == product_id
                receipt.update(trace_id=final.get("trace_id"), trace_ids=[final["trace_id"]] if final.get("trace_id") else [],
                    traceparent_source=final.get("traceparent_source", "unlinked"),
                    trace_context_generated=final.get("trace_context_generated", False),
                    created_order=bool(valid), order_confirmation_displayed=confirmed,
                    business_success=bool(valid and confirmed),
                    status="success" if valid and confirmed else "failed",
                    reason="native_matching_order_confirmed" if valid and confirmed else "native_matching_order_not_confirmed")
            if result.get("error_kind"):
                receipt["error_kind"] = "native_checkout_incomplete"
        except Exception as error:
            receipt.update(error_kind=type(error).__name__, reason="native_checkout_unavailable")
        finished = _timestamp(self.clock())
        receipt.update(finished_at=finished, checked_at=finished,
                       time={"started_at": started, "finished_at": finished})
        return receipt
